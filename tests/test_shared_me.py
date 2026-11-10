import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from mediconfirm.bulk_medications import save_medication_entries
from mediconfirm.intake_store import _moment, start_plan, record_intake, _load
from mediconfirm.plan_actions import process_plan
from mediconfirm.shared_storage import prepare_shared_storage
from mediconfirm.web_settings import validate_settings
import test_mobile


class SharedMeTests(unittest.TestCase):
    setUp=test_mobile.MobileTests.setUp
    tearDown=test_mobile.MobileTests.tearDown
    action=test_mobile.MobileTests.action
    photo=test_mobile.MobileTests.photo

    def test_defaults_are_300_and_600_seconds(self):
        state=self.client.get('/api/state').get_json()
        self.assertEqual(state['settings']['repeat_seconds'],300)
        self.assertEqual(state['settings']['timeout_seconds'],600)

    def test_second_browser_sees_same_settings_list_and_history(self):
        self.action('settings',settings=dict(timeout_seconds=40,repeat_seconds=7,caregiver_email='family@example.com',reminders_enabled=False))
        self.photo()
        second=self.app.test_client();second.get('/?access=test-access')
        state=second.get('/api/state').get_json()
        self.assertEqual(state['settings']['repeat_seconds'],7)
        self.assertTrue(state['history_records'])
        self.assertEqual(len(self.app.extensions['mediconfirm_sessions']),1)

    def test_photo_must_match_the_selected_event_not_another_at_same_time(self):
        state=self.action('save_list',medications=[dict(name='Amlodipine Besylate',strength='5 mg',dose='1 tablet',time='12:00'),dict(name='Other medicine',strength='20 mg',dose='1 tablet',time='12:00')]).get_json()
        event=next(e for e in state['daily_plan'] if e['name']=='Other medicine')
        self.action('select_event',event_id=event['event_id'])
        result=self.photo().get_json()
        self.assertEqual(result['verification_status'],'Mismatch')
        self.assertFalse(result['confirmation_ready'])

    def test_ending_help_keeps_one_log_and_never_marks_taken(self):
        self.photo()
        self.action('chat',text='I have chest pain')
        state=self.action('flow',value='end').get_json()
        self.assertNotEqual(state['flow_page'],'help')
        self.assertEqual(state['history_records'][0]['status'],'Unconfirmed')
        self.assertTrue(state['family_notifications'])
        self.assertEqual(self.phone.app.log_path,(self.root/'data/intake_records.json').resolve())

    def test_invalid_repeat_interval_does_not_replace_settings(self):
        self.assertEqual(self.action('settings',settings=dict(timeout_seconds=30,repeat_seconds=30)).status_code,400)
        self.assertEqual(self.action('settings',settings=dict(timeout_seconds=30,repeat_seconds=40)).status_code,400)
        self.assertEqual(self.phone.settings['timeout_seconds'],600)


class SharedStorageTests(unittest.TestCase):
    def test_merge_deduplicates_events_preserves_taken_and_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);canonical=root/'data/intake_records.json';legacy=root/'data/mobile_runs/old/intake_records.json'
            med=dict(name='A',strength='5 mg',dose='1 tablet',time='08:00')
            moment=_moment(None)
            record_intake(canonical,med,'08:00','Taken',now=moment)
            original=canonical.read_bytes()
            start_plan(legacy,[med],'08:00',now=moment)
            prepare_shared_storage(root)
            records=_load(canonical)['events']
            self.assertEqual(len(records),1)
            self.assertEqual(next(iter(records.values()))['status'],'Taken')
            self.assertEqual((root/'data/before_shared_storage/intake_records.json').read_bytes(),original)
            self.assertTrue(legacy.exists())
            before=canonical.read_bytes();prepare_shared_storage(root);self.assertEqual(canonical.read_bytes(),before)

    def test_independent_repeat_delay_is_frozen_for_existing_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log.json';med=dict(name='A',strength='5 mg',dose='1 tablet',time='08:00');moment=_moment(None)
            process_plan(path,[med],'08:00',timeout_seconds=40,repeat_seconds=7,start=True,now=moment)
            _,_,messages=process_plan(path,[med],'08:00',timeout_seconds=600,repeat_seconds=300,now=moment+timedelta(seconds=8))
            self.assertTrue(any('Already taken' in s for s in messages))
            events,_,_=process_plan(path,[med],'08:00',now=moment+timedelta(seconds=41))
            self.assertEqual(events[0]['status'],'Unconfirmed')

    def test_two_processes_do_not_lose_each_others_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'log.json')
            script="from mediconfirm.intake_store import record_intake;import sys;record_intake(sys.argv[1],dict(name=sys.argv[2],strength='5 mg',dose='1 tablet',time='08:00'),'08:00','Taken')"
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
            jobs=[subprocess.Popen([sys.executable,'-c',script,path,name],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for name in ('A','B')]
            for job in jobs:
                out,err=job.communicate(timeout=15);self.assertEqual(job.returncode,0,err.decode())
            self.assertEqual(len(_load(path)['events']),2)
