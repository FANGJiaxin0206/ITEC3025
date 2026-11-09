import json, tempfile, unittest, base64, io
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from PIL import Image
from mediconfirm.intake_store import start_plan, expire_pending, record_intake, record_recovery
from mediconfirm.simple_ui import SimpleCameraApp

class PlanTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'log.json'
        self.now = datetime(2026, 11, 9, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        self.a = dict(name='A', strength='5 mg', time='08:00', dose='1 tablet', medication_id='a')
        self.b = {**self.a, 'name': 'B', 'medication_id': 'b'}

    def tearDown(self):
        self.tmp.cleanup()

    def events(self):
        return list(json.loads(self.path.read_text())['events'].values())

    def test_multiple_events_independent_and_taken_not_expired(self):
        start_plan(self.path, [self.a, self.b], '08:00', 60, self.now)
        record_intake(self.path, self.a, '08:00', 'Taken', now=self.now)
        events = expire_pending(self.path, self.now + timedelta(seconds=61))
        self.assertEqual({e['name']: e['status'] for e in events}, {'A': 'Taken', 'B': 'Unconfirmed'})
        self.assertEqual(events[1]['reason'], 'confirmation_timeout')

    def test_restart_does_not_extend_deadline(self):
        start_plan(self.path, [self.a], '08:00', 60, self.now)
        deadline = self.events()[0]['deadline_at']
        start_plan(self.path, [self.a], '08:00', 600, self.now + timedelta(seconds=20))
        self.assertEqual(self.events()[0]['deadline_at'], deadline)

    def test_late_explicit_report_can_complete_once(self):
        start_plan(self.path, [self.a], '08:00', 60, self.now)
        expire_pending(self.path, self.now + timedelta(seconds=61))
        e, changed = record_intake(self.path, self.a, '08:00', 'Taken', now=self.now + timedelta(seconds=62))
        self.assertTrue(changed)
        self.assertEqual([x['status'] for x in e['history']], ['Pending', 'Unconfirmed', 'Taken'])
        e, changed = record_intake(self.path, self.a, '08:00', 'Taken', now=self.now + timedelta(seconds=63))
        self.assertFalse(changed)
        self.assertEqual(len(e['history']), 3)

    def test_explicit_pending_has_reason_and_preserves_deadline(self):
        start_plan(self.path, [self.a], '08:00', 60, self.now)
        deadline = self.events()[0]['deadline_at']
        e, _ = record_intake(self.path, self.a, '08:00', 'Pending', now=self.now + timedelta(seconds=20))
        self.assertEqual(e['reason'], 'user_reported_not_taken')
        self.assertEqual(e['deadline_at'], deadline)

    def test_error_does_not_change_status_deadline_or_confirm(self):
        start_plan(self.path, [self.a], '08:00', 60, self.now)
        before = self.events()[0]
        record_recovery(self.path, '08:00', 'asr_failed', self.now)
        e = self.events()[0]
        for k in ['status', 'deadline_at', 'confirmed_at']:
            self.assertEqual(e[k], before[k])
        self.assertEqual(e['last_error']['reason'], 'asr_failed')

    def test_invalid_log_preserved(self):
        self.path.write_text('{bad')
        with self.assertRaises(ValueError):
            start_plan(self.path, [self.a], '08:00', 60, self.now)
        self.assertEqual(self.path.read_text(), '{bad')

    def test_timeout_does_not_overwrite_old_fields(self):
        start_plan(self.path, [self.a], '08:00', 1, self.now)
        expire_pending(self.path, self.now + timedelta(seconds=2))
        expire_pending(self.path, self.now + timedelta(seconds=3))
        self.assertEqual(len(self.events()[0]['history']), 2)

    def test_different_dates_are_different_events(self):
        start_plan(self.path, [self.a], '08:00', 60, self.now)
        start_plan(self.path, [self.a], '08:00', 60, self.now + timedelta(days=1))
        self.assertEqual(len(self.events()), 2)

class RecoveryUITests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / 'log.json'
        self.med = dict(name='A', strength='5 mg', time='08:00', dose='1 tablet')
        self.app = SimpleCameraApp('fake', medications=[self.med], selected_time='08:00', voice=False, log_path=self.log, confirmation_timeout_seconds=1)
        self.app._on_flow({'new': {'action': 'check'}})

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def event(self):
        return next(iter(json.loads(self.log.read_text())['events'].values()))

    def test_asr_failure_does_not_confirm_and_draft_can_be_retried(self):
        with patch('mediconfirm.simple_ui.transcribe_recording', side_effect=RuntimeError('decode error')):
            self.app._on_speech({'new': {'audio': 'bad'}})
        self.assertEqual(self.event()['status'], 'Pending')
        self.assertIn('Record again', self.app.speech_status)
        self.assertFalse(self.app.busy)

    def test_api_failure_invalidates_old_confirmation(self):

        class Client:

            def extract(self, path):
                raise RuntimeError('timed out')
        self.app.client = Client()
        b = io.BytesIO()
        Image.new('RGB', (10, 10), 'white').save(b, format='JPEG')
        self.app._on_photo({'new': {'image': 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()}})
        self.assertFalse(self.app.confirmation_ready)
        self.assertFalse(self.app.busy)
        self.assertEqual(self.event()['status'], 'Pending')

    def test_playback_failure_retains_text_and_state(self):
        self.app.result_text = 'A, 5 mg'
        self.app._on_playback({'new': {'kind': 'error'}})
        self.assertEqual(self.app.result_text, 'A, 5 mg')
        self.assertEqual(self.event()['status'], 'Pending')
        self.assertEqual(self.event()['last_error']['reason'], 'audio_playback_failed')

    def test_tts_failure_is_retryable(self):
        self.app.voice = True
        with patch('gtts.gTTS', side_effect=RuntimeError('offline')):
            self.app._speak('A, 5 mg')
        self.assertTrue(self.app.can_replay)
        self.assertEqual(self.app._last_spoken_text, 'A, 5 mg')
        self.assertEqual(self.event()['status'], 'Pending')
        self.assertIn('Replay', self.app.audio_note)

    def test_plan_timeout_visible_without_fake_taken(self):
        e = self.event()
        expire_pending(self.log, datetime.fromisoformat(e['deadline_at']) + timedelta(seconds=1))
        self.app._on_schedule({'new': {'id': 'refresh'}})
        self.assertIn('Unconfirmed', self.app.schedule_text)
        self.assertIsNone(self.event()['confirmed_at'])
