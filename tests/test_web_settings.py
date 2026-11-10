import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from mediconfirm.mobile_server import create_app
from mediconfirm.bulk_medications import save_medication_entries
from mediconfirm.intake_store import _moment, record_intake


class WebSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = _moment(None).replace(microsecond=0)
        self.med = dict(name='Demo medicine', strength='5 mg', dose='1 tablet', time=self.now.strftime('%H:%M'))
        save_medication_entries([self.med], self.root / 'data/personal_medications.json')
        self.server = create_app(self.root, 'test', config={'api_key': 'fake-key'})
        self.client = self.server.test_client()
        self.client.get('/?access=test')
        self.client.get('/api/state')
        self.phone = next(iter(self.server.extensions['mediconfirm_sessions'].values()))
        self.phone.app.voice = False

    def tearDown(self):
        for session in self.server.extensions['mediconfirm_sessions'].values():
            session.app.close()
        self.tmp.cleanup()

    def settings(self, **kwargs):
        data = dict(timeout_seconds=30, reminders_enabled=False, caregiver_email='family@example.com')
        data.update(kwargs)
        return self.client.post('/api/action', json={'action': 'settings', 'settings': data})

    def tick_at(self, moment):
        with patch('mediconfirm.mobile_server._moment', side_effect=lambda now: now or moment), \
             patch('mediconfirm.plan_actions._moment', side_effect=lambda now: now or moment), \
             patch('mediconfirm.simple_ui._moment', side_effect=lambda now: now or moment):
            self.phone.tick()

    def test_settings_saved_and_timeout_applies_to_new_event(self):
        self.assertEqual(self.settings().status_code, 200)
        self.client.post('/api/action', json={'action': 'start_reminder'})
        event = self.phone.state()['history_records'][0]
        from datetime import datetime
        self.assertEqual((datetime.fromisoformat(event['deadline_at']) - datetime.fromisoformat(event['started_at'])).total_seconds(), 30)
        self.assertEqual(json.loads(self.phone.settings_path.read_text())['caregiver_email'], 'family@example.com')

    def test_invalid_settings_do_not_replace_saved_settings(self):
        self.settings()
        before = self.phone.settings_path.read_bytes()
        for bad in [0, -1, 'nan', True, 86401]:
            self.assertEqual(self.settings(timeout_seconds=bad).status_code, 400)
        self.assertEqual(self.settings(caregiver_email='not an email').status_code, 400)
        self.assertEqual(self.phone.settings_path.read_bytes(), before)

    def test_auto_reminder_repeat_timeout_and_one_unsent_email(self):
        self.settings(reminders_enabled=True)
        self.tick_at(self.now)
        initial = self.phone.state()['history_records'][0]
        self.assertEqual(initial['status'], 'Pending')
        self.tick_at(self.now + timedelta(seconds=16))
        self.assertIn('Already taken or Not yet', self.phone.app.reminder_text)
        self.tick_at(self.now + timedelta(seconds=31))
        state = self.phone.state()
        self.assertEqual(state['history_records'][0]['status'], 'Unconfirmed')
        self.assertEqual(len(state['family_notifications']), 1)
        notice = state['family_notifications'][0]
        self.assertFalse(notice['sent'])
        self.assertEqual(notice['recipient'], 'family@example.com')
        self.assertEqual(notice['delivery_status'], 'not_enabled')
        self.tick_at(self.now + timedelta(seconds=50))
        self.assertEqual(len(self.phone.state()['family_notifications']), 1)

    def test_taken_event_does_not_timeout(self):
        self.settings(reminders_enabled=True)
        self.tick_at(self.now)
        med = self.phone.app.medications[0]
        record_intake(self.phone.app.log_path, med, med['time'], 'Taken', now=self.now)
        self.tick_at(self.now + timedelta(seconds=40))
        self.assertEqual(self.phone.state()['history_records'][0]['status'], 'Taken')
        self.assertEqual(self.phone.state()['family_notifications'], [])

    def test_severe_report_creates_email_preview_and_pauses(self):
        self.settings()
        result = self.client.post('/api/action', json={'action': 'chat', 'text': 'I have chest pain'}).get_json()
        self.assertEqual(result['flow_page'], 'help')
        self.assertEqual(result['family_notifications'][0]['recipient'], 'family@example.com')
        self.assertFalse(result['family_notifications'][0]['sent'])

    def test_same_browser_profile_restores_settings_after_server_restart(self):
        self.settings()
        self.client.post('/api/action', json={'action': 'start_reminder'})
        cookie = self.client.get_cookie('session').value
        second = create_app(self.root, 'new-access', config={'api_key': 'fake-key'})
        client = second.test_client()
        client.set_cookie('session', cookie)
        response = client.get('/api/state').get_json()
        self.assertEqual(response['settings']['timeout_seconds'], 30)
        self.assertTrue(response['history_records'])
        for session in second.extensions['mediconfirm_sessions'].values():
            session.app.close()

    def test_no_separate_demo_log_can_be_created_from_the_web(self):
        response=self.client.post('/api/action',json={'action':'simulation','value':'new_demo'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.phone.app.log_path,(self.root/'data/intake_records.json').resolve())
        self.assertFalse((self.root/'data/demo_runs').exists())

    def test_clock_exposes_hong_kong_offset_not_secrets(self):
        response = self.client.get('/api/state').get_data(as_text=True)
        self.assertIn('+08:00', response)
        self.assertNotIn('fake-key', response)

    def test_disabled_automatic_reminder_does_not_create_events(self):
        self.tick_at(self.now)
        self.assertEqual(self.phone.state()['history_records'], [])
