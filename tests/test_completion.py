import unittest, tempfile, json, base64, io
from pathlib import Path
from datetime import datetime, timedelta, timezone
from PIL import Image
from mediconfirm.simple_ui import SimpleCameraApp
from mediconfirm.plan_actions import process_plan, report_severe

class PlanActionTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'log.json'
        self.med = dict(name='A', strength='5 mg', dose='1 tablet', time='08:00', medication_id='a')
        self.now = datetime(2026, 11, 9, 8, tzinfo=timezone(timedelta(hours=8)))

    def tearDown(self):
        self.tmp.cleanup()

    def run_plan(self, **kw):
        return process_plan(self.path, [self.med], '08:00', 600, now=self.now, **kw)

    def test_first_repeat_timeout_are_once_and_persisted(self):
        e, n, m = self.run_plan(start=True)
        self.assertEqual(len(m), 1)
        self.assertEqual(n, [])
        self.assertEqual(self.run_plan(start=True)[2], [])
        e, n, m = self.run_plan(advance_minutes=5)
        self.assertEqual(e[0]['status'], 'Pending')
        self.assertIn('Have you taken', m[0])
        e, n, m = self.run_plan(advance_minutes=5)
        self.assertEqual(e[0]['status'], 'Unconfirmed')
        self.assertEqual(len(n), 1)
        self.assertTrue(n[0]['simulated'])
        self.assertFalse(n[0]['sent'])
        e, n, m = self.run_plan(advance_minutes=5)
        self.assertEqual(len(n), 1)
        self.assertEqual(m, [])

    def test_direct_10_minutes_skips_repeat_and_notifies_once(self):
        self.run_plan(start=True)
        e, n, m = self.run_plan(advance_minutes=10)
        self.assertEqual(e[0]['status'], 'Unconfirmed')
        self.assertIsNone(e[0].get('repeat_reminder_at'))
        self.assertEqual(len(n), 1)

    def test_taken_never_reminded_or_timed_out(self):
        from mediconfirm.intake_store import record_intake
        self.run_plan(start=True)
        record_intake(self.path, self.med, '08:00', 'Taken', now=self.now)
        e, n, m = self.run_plan(advance_minutes=10)
        self.assertEqual(e[0]['status'], 'Taken')
        self.assertEqual(n, [])
        self.assertEqual(m, [])

    def test_severe_notice_dedup_and_timeout_suppressed(self):
        self.run_plan(start=True)
        notices, new = report_severe(self.path, '08:00', 'I have chest pain', 'session', self.now)
        self.assertIsNotNone(new)
        notices, new = report_severe(self.path, '08:00', 'I have chest pain', 'session', self.now)
        self.assertIsNone(new)
        self.assertEqual(len(notices), 1)
        e, n, m = self.run_plan(advance_minutes=20)
        self.assertTrue(e[0]['interrupted'])
        self.assertEqual(e[0]['status'], 'Pending')
        self.assertEqual(len(n), 1)
        self.assertEqual(m, [])

    def test_two_medicines_remain_independent(self):
        from mediconfirm.intake_store import record_intake
        b = {**self.med, 'name': 'B', 'medication_id': 'b'}
        process_plan(self.path, [self.med, b], '08:00', 600, start=True, now=self.now)
        record_intake(self.path, self.med, '08:00', 'Taken', now=self.now)
        e, n, m = process_plan(self.path, [self.med, b], '08:00', 600, advance_minutes=10, now=self.now)
        self.assertEqual({x['name']: x['status'] for x in e}, {'A': 'Taken', 'B': 'Unconfirmed'})
        self.assertEqual(len(n), 1)

    def test_real_deadline_also_generates_notice_on_refresh(self):
        self.run_plan(start=True)
        e, n, m = process_plan(self.path, [self.med], '08:00', 600, now=self.now + timedelta(minutes=11))
        self.assertEqual(e[0]['status'], 'Unconfirmed')
        self.assertEqual(len(n), 1)

    def test_invalid_advance_is_rejected(self):
        for m in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.run_plan(advance_minutes=m)

class CompleteWorkflowTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'log.json'
        self.med = dict(name='A', strength='5 mg', dose='1 tablet', time='08:00', medication_id='a')
        self.app = SimpleCameraApp('offline-test', voice=False, medications=[self.med], selected_time='08:00', log_path=self.path)

        class Client:

            def extract(self, p):
                return dict(name='A', strength='5 mg')

            def request(self, p):
                return 'Hello.'
        self.app.client = Client()
        b = io.BytesIO()
        Image.new('RGB', (10, 10), 'white').save(b, format='JPEG')
        self.photo = 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def sim(self, a):
        self.app._on_simulation({'new': {'action': a}})

    def verify(self):
        self.app._on_flow({'new': {'action': 'check'}})
        self.app._on_photo({'new': {'image': self.photo}})

    def report(self, text):
        self.app._on_confirm({'new': {'text': text, 'verification_id': self.app.verification_id}})

    def events(self):
        return list(json.loads(self.app.log_path.read_text())['events'].values())

    def test_simulation_uses_separate_file(self):
        self.sim('new_demo')
        self.assertNotEqual(self.app.log_path, self.path)
        self.sim('remind')
        self.sim('advance')
        self.assertEqual(self.events()[0]['status'], 'Pending')
        self.sim('advance')
        self.assertEqual(self.events()[0]['status'], 'Unconfirmed')
        self.assertIn('NOT SENT', self.app.notification_text)
        self.assertFalse(self.path.exists())
        self.sim('normal_log')
        self.assertEqual(self.app.log_path, self.path)

    def test_text_negative_never_saved_as_taken(self):
        self.verify()
        self.report('I have not taken it.')
        self.assertEqual(self.events()[0]['status'], 'Pending')
        self.assertEqual(self.events()[0]['reason'], 'user_reported_not_taken')

    def test_unclear_confirmation_no_record(self):
        self.verify()
        for s in ['yes', 'Have I taken it?', 'Maybe', 'I have taken it but I have not taken it']:
            self.report(s)
            self.assertEqual(self.events()[0]['status'], 'Pending')

    def test_reviewed_positive_explicit_and_duplicate_protected(self):
        self.verify()
        self.assertEqual(self.events()[0]['status'], 'Pending')
        self.report('I have taken it.')
        e = self.events()[0]
        self.assertEqual(e['status'], 'Taken')
        self.assertEqual(e['source'], 'reviewed_text')
        self.verify()
        self.report('I have taken it.')
        self.assertEqual(len(self.events()), 1)
        self.assertEqual(self.events()[0]['confirmed_at'], e['confirmed_at'])

    def test_old_token_rejected_even_for_positive_text(self):
        self.verify()
        old = self.app.verification_id
        self.verify()
        self.app._on_confirm({'new': {'text': 'I have taken it.', 'verification_id': old}})
        self.assertEqual(self.events()[0]['status'], 'Pending')

    def test_serious_report_via_confirmation_blocks_and_notifies(self):
        self.verify()
        self.report('I have chest pain')
        self.assertTrue(self.app._blocked)
        self.assertEqual(self.app.flow_page, 'help')
        self.assertFalse(self.app.confirmation_ready)
        self.assertIn('NOT SENT', self.app.notification_text)
        self.assertNotEqual(self.events()[0]['status'], 'Taken')

    def test_chat_taken_is_not_a_confirmation(self):
        self.verify()
        self.app._on_flow({'new': {'action': 'ask-current'}})
        self.app._on_chat({'new': {'text': 'I have taken it.'}})
        self.assertEqual(self.events()[0]['status'], 'Pending')

    def test_demo_restart_preserves_previous_run(self):
        self.sim('new_demo')
        self.sim('remind')
        old = self.app.log_path
        contents = old.read_bytes()
        self.sim('new_demo')
        self.assertNotEqual(old, self.app.log_path)
        self.assertEqual(old.read_bytes(), contents)

    def test_regular_log_cannot_advance_simulated_time(self):
        self.sim('advance')
        self.assertIn('Start a new demo first', self.app.simulation_text)
        self.assertFalse(self.path.exists())

class RestartSafetyTests(unittest.TestCase):
    setUp = CompleteWorkflowTests.setUp
    tearDown = CompleteWorkflowTests.tearDown
    sim = CompleteWorkflowTests.sim
    verify = CompleteWorkflowTests.verify
    report = CompleteWorkflowTests.report
    events = CompleteWorkflowTests.events

    def test_interrupted_event_cannot_be_confirmed_after_reopening(self):
        self.verify()
        self.report('I have chest pain')
        other = SimpleCameraApp('offline', voice=False, medications=[self.med], selected_time='08:00', log_path=self.path)
        try:
            self.assertTrue(other._blocked)
            self.assertFalse(other.confirmation_ready)
            other._on_flow({'new': {'action': 'check'}})
            self.assertEqual(other.flow_page, 'help')
        finally:
            other.close()

    def test_new_demo_unblocks_without_overwriting_interrupted_record(self):
        self.verify()
        self.report('I have chest pain')
        old = self.path.read_bytes()
        self.sim('new_demo')
        self.assertFalse(self.app._blocked)
        self.assertEqual(self.path.read_bytes(), old)

    def test_initial_simulation_must_be_started(self):
        self.sim('new_demo')
        self.sim('advance')
        self.assertIn('Start a reminder', self.app.simulation_text)

    def test_demo_window_is_fixed_even_if_normal_window_is_short(self):
        self.app._normal_confirmation_timeout_seconds = 30
        self.sim('new_demo')
        self.assertEqual(self.app.confirmation_timeout_seconds, 600)
        self.sim('remind')
        self.sim('advance')
        self.assertEqual(self.events()[0]['status'], 'Pending')
        self.sim('normal_log')
        self.assertEqual(self.app.confirmation_timeout_seconds, 30)
