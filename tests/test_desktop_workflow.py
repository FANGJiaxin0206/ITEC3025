import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
import test_mobile
from mediconfirm.notebook_dashboard import NotebookDashboard
from mediconfirm.simple_ui import SimpleCameraApp
from mediconfirm.time_picker import IntakeTimes

class DesktopWebTests(unittest.TestCase):
 setUp=test_mobile.MobileTests.setUp
 tearDown=test_mobile.MobileTests.tearDown
 action=test_mobile.MobileTests.action
 photo=test_mobile.MobileTests.photo
 def test_bad_retake_invalidates_previous_match(self):
  import io
  state=self.photo().get_json();token=state['verification_id']
  result=self.client.post('/api/photo',data={'photo':(io.BytesIO(b'bad image'),'bad.jpg')})
  self.assertEqual(result.status_code,400)
  self.assertFalse(self.phone.app.confirmation_ready)
  self.action('confirm',status='Taken',verification_id=token)
  self.assertNotEqual(self.phone.app.flow_page,'done')
 def test_prepare_camera_clears_old_confirmation(self):
  self.photo();state=self.action('prepare_photo').get_json()
  self.assertFalse(state['confirmation_ready']);self.assertFalse(state['verification_id'])
 def test_clock_selects_latest_due_slot_and_manual_override_is_explicit(self):
  self.action('save_list',medications=[dict(name='A',strength='5 mg',dose='1 tablet',time=t) for t in ['08:00','12:00','20:00']])
  moment=datetime(2026,11,10,10,30,tzinfo=ZoneInfo('Asia/Hong_Kong'))
  with patch('mediconfirm.mobile_server._moment',return_value=moment):
   self.phone.select_automatic_time();self.assertEqual(self.phone.app.selected_time,'08:00')
   self.action('time',value='20:00');self.phone.select_automatic_time();self.assertEqual(self.phone.app.selected_time,'20:00')
   state=self.action('automatic_time').get_json();self.assertEqual(state['selected_time'],'08:00');self.assertEqual(state['schedule_mode'],'automatic')
 def test_active_photo_is_not_reassigned_by_clock_tick(self):
  self.photo();self.phone.app.medications.append(dict(name='B',strength='5 mg',dose='1 tablet',time='20:00'))
  with patch('mediconfirm.mobile_server._moment',return_value=datetime(2026,11,10,21,tzinfo=ZoneInfo('Asia/Hong_Kong'))):
   self.phone.select_automatic_time()
  self.assertEqual(self.phone.app.selected_time,'12:00');self.assertTrue(self.phone.app.confirmation_ready)

class NotebookControlsTests(unittest.TestCase):
 def test_time_picker_adds_and_edits_daily_times(self):
  picker=IntakeTimes('08:00;20:00')
  try:
   self.assertEqual(len(picker._pairs),2)
   picker._pairs[1]['minute'].value='30';self.assertEqual(picker.value,'08:00;20:30')
   picker.add.click();self.assertEqual(picker.value,'08:00;20:30;08:00')
  finally:picker.close()
 def test_notebook_settings_history_and_demo_timeout(self):
  with tempfile.TemporaryDirectory() as tmp:
   meds=[dict(name='Demo',strength='5 mg',dose='1 tablet',time='08:00')]
   app=SimpleCameraApp('fake',medications=meds,selected_time='08:00',voice=False,log_path=Path(tmp)/'intake_records.json')
   controls=NotebookDashboard(app,Path(tmp))
   try:
    controls.timeout.value=30;controls.repeat.value=15;controls.email.value='family@example.com';controls.save()
    self.assertEqual(app.confirmation_timeout_seconds,30)
    app._on_simulation({'new':{'action':'remind'}})
    controls.tick();self.assertIn('Pending',controls.history.value)
    from mediconfirm.plan_actions import process_plan
    process_plan(app.log_path,app.medications,app.selected_time,advance_minutes=1)
    controls.tick();self.assertIn('Unconfirmed',controls.history.value);self.assertIn('family@example.com',controls.history.value)
   finally:controls.close()
