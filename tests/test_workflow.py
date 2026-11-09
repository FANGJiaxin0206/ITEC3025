import base64
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from mediconfirm.simple_ui import SimpleCameraApp
from mediconfirm.intake_store import record_intake

class FakeClient:

    def __init__(self):
        self.fields = {'name': 'Example A', 'strength': '100 mg'}
        self.extract_calls = 0
        self.prompts = []

    def extract(self, path):
        self.extract_calls += 1
        return self.fields

    def request(self, messages):
        self.prompts.append(messages)
        return 'I hear your concern. When you are ready, you can start the medication check.'

class WorkflowTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / 'intake_records.json'
        self.meds = [{'medication_id': 'a', 'name': 'Example A', 'strength': '100 mg', 'time': '08:00', 'dose': '1 tablet'}]
        self.app = SimpleCameraApp('fake-offline-key', medications=self.meds, selected_time='08:00', voice=False, log_path=self.log)
        self.client = self.app.client = FakeClient()
        b = io.BytesIO()
        Image.new('RGB', (20, 20), 'white').save(b, format='JPEG')
        self.image = 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
        self.counter = 0

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def assert_no_taken(self):
        if self.log.exists():
            self.assertTrue(all((e['status'] != 'Taken' for e in json.loads(self.log.read_text())['events'].values())))

    def route(self, action):
        self.counter += 1
        self.app.flow_request = {'action': action, 'id': str(self.counter)}

    def photo(self):
        self.counter += 1
        self.app.request = {'image': self.image, 'id': str(self.counter)}

    def confirm(self, status='Taken', token=None):
        self.counter += 1
        self.app.confirm_request = {'status': status, 'verification_id': token if token is not None else self.app.verification_id, 'id': str(self.counter)}

    def chat(self, text):
        self.counter += 1
        self.app.chat_request = {'text': text, 'id': str(self.counter)}

    def test_direct_photo_path_never_requires_chat(self):
        self.assertEqual(self.app.flow_page, 'home')
        self.route('check')
        self.photo()
        self.assertTrue(self.app.confirmation_ready)
        self.assert_no_taken()
        self.client.prompts.clear()
        self.confirm()
        self.assertEqual(self.app.flow_page, 'done')
        event = next(iter(json.loads(self.log.read_text())['events'].values()))
        self.assertEqual(event['status'], 'Taken')
        self.assertTrue(event['self_report_only'])
        self.assertEqual(self.client.prompts, [])

    def test_optional_chat_returns_to_same_photo_flow_with_context(self):
        self.route('chat')
        self.chat('I feel tired today')
        self.assertEqual(self.app.flow_page, 'chat')
        self.route('check')
        self.assertIn('I feel tired today', self.app.dialogue.health_reports)
        self.photo()
        self.confirm()
        self.assertEqual(self.app.flow_page, 'done')

    def test_mismatch_cannot_save_intake(self):
        self.route('check')
        self.client.fields['strength'] = '200 mg'
        self.photo()
        self.confirm()
        self.assertFalse(self.app.confirmation_ready)
        self.assert_no_taken()

    def test_uncertain_cannot_save_intake(self):
        self.route('check')
        self.client.fields['strength'] = None
        self.photo()
        self.confirm()
        self.assert_no_taken()

    def test_new_photo_invalidates_previous_token(self):
        self.route('check')
        self.photo()
        old = self.app.verification_id
        self.photo()
        self.confirm(token=old)
        self.assert_no_taken()
        self.confirm()
        self.assertTrue(self.log.exists())

    def test_not_yet_then_taken_updates_one_event(self):
        self.route('check')
        self.photo()
        self.confirm('Pending')
        events = json.loads(self.log.read_text())['events']
        self.assertEqual(next(iter(events.values()))['status'], 'Pending')
        self.assertEqual(self.app.flow_page, 'check')
        self.confirm('Taken')
        events = json.loads(self.log.read_text())['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(next(iter(events.values()))['status'], 'Taken')

    def test_rechecking_taken_event_does_not_duplicate(self):
        self.route('check')
        self.photo()
        self.confirm()
        original = self.log.read_bytes()
        self.route('check')
        self.photo()
        self.confirm()
        self.assertEqual(self.log.read_bytes(), original)
        self.assertIn('No duplicate', self.app.completion_text)

    def test_chat_taken_statement_does_not_write_record(self):
        self.route('chat')
        self.chat('I have taken it')
        self.assert_no_taken()
        self.assertEqual(self.client.prompts[-1][-1]['content'], 'I have taken it')
        self.assertEqual(self.app.flow_page, 'chat')

    def test_storage_failure_does_not_show_completion(self):
        self.route('check')
        self.photo()
        with patch('mediconfirm.simple_ui.record_intake', side_effect=OSError('disk unavailable')):
            self.confirm()
        self.assert_no_taken()
        self.assertEqual(self.app.flow_page, 'check')
        self.assertIn('not saved', self.app.confirmation_status)

    def test_severe_report_blocks_normal_flow_until_explicit_end(self):
        self.route('chat')
        self.chat('I have severe chest pain')
        self.assertEqual(self.app.flow_page, 'help')
        self.assertTrue(self.app._blocked)
        self.route('check')
        self.photo()
        self.confirm()
        self.assertEqual(self.client.extract_calls, 0)
        self.assert_no_taken()
        self.route('end')
        self.assertEqual(self.app.flow_page, 'home')
        self.assertFalse(self.app._blocked)

    def test_switch_time_invalidates_confirmation(self):
        self.route('check')
        self.photo()
        token = self.app.verification_id
        self.app.set_check_time('20:00')
        self.confirm(token=token)
        self.assert_no_taken()

    def test_no_logging_path_never_claims_saved(self):
        self.app.log_path = None
        self.route('check')
        self.photo()
        self.confirm()
        self.assertEqual(self.app.flow_page, 'check')
        self.assertIn('No intake log path is configured', self.app.confirmation_status)

    def test_old_date_verification_cannot_be_confirmed(self):
        self.route('check')
        self.photo()
        self.app._verification_date = '2000-01-01'
        self.confirm()
        self.assert_no_taken()

    def test_ask_about_package_then_resume_does_not_require_retake(self):
        self.route('check')
        self.photo()
        token = self.app.verification_id
        self.route('ask-current')
        self.assertEqual(self.app.flow_page, 'chat')
        self.assertIn('Example A', self.app.package_context)
        self.chat('Is this my morning medication?')
        self.assertIn('Example A', self.client.prompts[-1][0]['content'])
        self.route('resume')
        self.assertEqual(self.app.flow_page, 'check')
        self.assertEqual(self.app.verification_id, token)
        self.assertEqual(self.client.extract_calls, 1)
        self.confirm()
        self.assertTrue(self.log.exists())

    def test_source_grounding_is_attached_to_current_photo(self):
        self.route('check')
        self.photo()
        self.route('ask-current')

        class Source:

            def lookup(self, fields):
                return {'status': 'found', 'source_title': 'Test source', 'published_date': 'test', 'url': 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test', 'general_uses_text': 'Fictional test information only.'}
        self.app.drug_source = Source()
        self.chat('What is this medication used for?')
        self.assertIn('Fictional test information only.', self.client.prompts[-1][0]['content'])
        self.assertEqual(len(self.app.source_links), 1)
        self.app.set_check_time('20:00')
        self.assertEqual(self.app.source_links, [])
        self.assertIsNone(self.app._drug_information)
        self.assertFalse(self.app.has_current_photo)

    def test_retaking_invalidates_old_context_before_new_image(self):
        self.route('check')
        self.photo()
        self.assertTrue(self.app.has_current_photo)
        self.app.photo_clear_request = {'id': 'new-camera-view'}
        self.assertFalse(self.app.has_current_photo)
        self.assertIsNone(self.app.last_result)
        self.confirm()
        self.assert_no_taken()

    def test_cancel_clears_unconfirmed_photo_without_intake_write(self):
        self.route('check')
        self.photo()
        self.route('cancel')
        self.assertEqual(self.app.flow_page, 'home')
        self.assertFalse(self.app.has_current_photo)
        self.assertEqual(self.app.cancel_ack, 1)
        self.confirm()
        self.assert_no_taken()

    def test_cancel_does_not_erase_already_saved_record(self):
        self.route('check')
        self.photo()
        self.confirm()
        before = self.log.read_bytes()
        self.route('cancel')
        self.assertEqual(self.log.read_bytes(), before)
        self.assertIn('kept', self.app.flow_notice)

    def test_replay_cannot_duplicate_confirmation(self):
        self.route('check')
        self.photo()
        self.confirm()
        before = self.log.read_bytes()
        with patch.object(self.app, '_speak') as speak:
            self.app.replay_request += 1
            speak.assert_called_once()
        self.assertEqual(self.log.read_bytes(), before)

    def test_confirmation_unknown_status_is_not_taken(self):
        self.route('check')
        self.photo()
        self.confirm('no')
        self.assert_no_taken()

    def test_saved_record_is_visible_in_package_chat_context(self):
        self.route('check')
        self.photo()
        self.confirm()
        self.route('chat')
        self.chat('Did I confirm this one?')
        self.assertIn('intake_record', self.client.prompts[-1][0]['content'])
        self.assertIn('Taken', self.app.package_context)
        self.route('resume')
        self.assertEqual(self.app.flow_page, 'done')

    def test_general_use_information_cannot_override_mismatch(self):
        self.route('check')
        self.client.fields['strength'] = '200 mg'
        self.photo()
        self.route('ask-current')

        class Source:

            def lookup(self, fields):
                return {'status': 'found', 'source_title': 'Test only', 'published_date': '', 'url': 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test', 'general_uses_text': 'Fictional test content.'}
        self.app.drug_source = Source()
        self.chat('What is this medicine used for?')
        self.route('resume')
        self.confirm()
        self.assertEqual(self.app.last_result['status'], 'Mismatch')
        self.assert_no_taken()

class IntakePersistenceTests(unittest.TestCase):

    def test_multiple_medications_and_dates_remain_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'intakes.json'
            med = {'medication_id': 'a', 'name': 'A', 'strength': '100 mg', 'dose': '1 tablet', 'time': '08:00'}
            day1 = datetime(2026, 11, 9, tzinfo=timezone.utc)
            record_intake(path, med, '08:00', 'Taken', now=day1)
            record_intake(path, {**med, 'medication_id': 'b', 'name': 'B'}, '08:00', 'Taken', now=day1)
            record_intake(path, med, '08:00', 'Taken', now=datetime(2026, 11, 10, tzinfo=timezone.utc))
            self.assertEqual(len(json.loads(path.read_text())['events']), 3)

    def test_corrupt_existing_log_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'intakes.json'
            path.write_text('corrupt')
            med = {'name': 'A', 'strength': '100 mg', 'dose': '1 tablet', 'time': '08:00'}
            with self.assertRaises(ValueError):
                record_intake(path, med, '08:00', 'Taken')
            self.assertEqual(path.read_text(), 'corrupt')
