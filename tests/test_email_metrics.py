import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from PIL import Image
from mediconfirm.core import atomic_json
from mediconfirm.email_delivery import EmailDelivery,submit_email
from mediconfirm.evaluation_log import EvaluationLog
from mediconfirm.history_display import display_event
import test_mobile

class InlineThread:
 def __init__(self,target,args,**kwargs):self.target=target;self.args=args
 def start(self):self.target(*self.args)

class EmailTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=self.root/'data/log.json'
  self.config={'smtp_host':'smtp.gmail.com','smtp_port':465,'smtp_security':'ssl','sender_email':'sender@example.com','app_password':'private-test-token'}
  atomic_json(self.root/'mail.local.json',self.config)
  atomic_json(self.path,{'events':{},'simulated_notifications':{'n':{'notification_id':'n','requires_delivery':True,'type':'timeout','at':'2026-11-10T13:00:00+08:00','message':'Test notification.'}}})
  self.settings={'real_email_enabled':True,'caregiver_email':'family@example.com'}
 def tearDown(self):self.tmp.cleanup()
 def notice(self):return json.loads(self.path.read_text())['simulated_notifications']['n']
 def test_send_is_real_transport_and_claimed_only_once(self):
  delivery=EmailDelivery(self.root)
  with patch('mediconfirm.email_delivery.submit_email',return_value=('submitted','accepted_by_email_provider')) as submit,patch('mediconfirm.email_delivery.threading.Thread',InlineThread):
   delivery.process(self.path,self.settings);delivery.process(self.path,self.settings)
  self.assertEqual(submit.call_count,1);self.assertTrue(self.notice()['sent']);self.assertFalse(self.notice()['simulated'])
 def test_missing_sender_is_not_reported_as_sent(self):
  (self.root/'mail.local.json').unlink()
  with patch('mediconfirm.email_delivery.submit_email') as submit:EmailDelivery(self.root).process(self.path,self.settings)
  submit.assert_not_called();self.assertEqual(self.notice()['delivery_status'],'not_configured');self.assertFalse(self.notice()['sent'])
 def test_old_notifications_are_never_sent_on_upgrade(self):
  store=json.loads(self.path.read_text());store['simulated_notifications']['n'].pop('requires_delivery');atomic_json(self.path,store)
  with patch('mediconfirm.email_delivery.submit_email') as submit:EmailDelivery(self.root).process(self.path,self.settings)
  submit.assert_not_called();self.assertEqual(self.notice()['delivery_status'],'legacy_not_sent')
 def test_smtp_uses_tls_and_authorized_sender(self):
  smtp=MagicMock();smtp.send_message.return_value={}
  with patch('mediconfirm.email_delivery.smtplib.SMTP_SSL',return_value=smtp) as client:
   status,_=submit_email(self.config,'family@example.com','Test','Test body')
  self.assertEqual(status,'submitted');self.assertIn('context',client.call_args.kwargs)
  smtp.login.assert_called_once_with('sender@example.com','private-test-token')
 def test_no_automatic_retry_after_uncertain_submission(self):
  delivery=EmailDelivery(self.root)
  with patch('mediconfirm.email_delivery.submit_email',return_value=('delivery_unknown','check_inbox_before_retrying')) as submit,patch('mediconfirm.email_delivery.threading.Thread',InlineThread):
   delivery.process(self.path,self.settings);delivery.process(self.path,self.settings)
  self.assertEqual(submit.call_count,1);self.assertFalse(self.notice()['sent'])
  with self.assertRaises(ValueError):delivery.retry(self.path,'n',self.settings)

class EvaluationTests(unittest.TestCase):
 def test_retake_click_deduplication_and_no_invented_click_rate(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=EvaluationLog(Path(tmp)/'metrics.json');key='task-12345678'
   log.photo(key);log.result(key,'Mismatch');log.photo(key);log.result(key,'Match')
   payload={'task_id':key,'clicks':[{'id':'1','button':'retake','offset_ms':100},{'id':'2','button':'taken','offset_ms':1000}]}
   log.clicks(payload);log.clicks(payload);log.finish(key,'completed',1000)
   task=json.loads(log.path.read_text())['tasks'][key]
   self.assertEqual(task['photo_count'],2);self.assertEqual(task['click_count'],2);self.assertIsNone(task['click_rate'])
   self.assertIn('client_duration_ms',log.csv())
 def test_readable_history_does_not_rewrite_raw_timestamp(self):
  event={'updated_at':'2026-11-10T13:04:31+08:00','date':'2026-11-10','scheduled_time':'08:00','reason':'user_reported_not_taken','history':[]}
  result=display_event(event)
  self.assertEqual(result['display_updated'],'10 Nov 2026, 1:04 PM');self.assertIn('Not yet',result['display_reason'])
  self.assertEqual(event['updated_at'],'2026-11-10T13:04:31+08:00')

class WebEvaluationTests(unittest.TestCase):
 setUp=test_mobile.MobileTests.setUp
 tearDown=test_mobile.MobileTests.tearDown
 action=test_mobile.MobileTests.action
 def test_photo_to_explicit_confirmation_is_measured(self):
  data=io.BytesIO();Image.new('RGB',(20,20),'white').save(data,format='JPEG');data.seek(0)
  state=self.client.post('/api/photo',data={'photo':(data,'photo.jpg'),'task_id':'task-abcdefgh','client_id':'client-a'}).get_json()
  self.action('confirm',status='Taken',verification_id=state['verification_id'],client_id='client-a',metrics={'task_id':'task-abcdefgh','client_elapsed_ms':1250,'clicks':[{'id':'c1','button':'taken','offset_ms':1250}]})
  task=json.loads(self.phone.evaluation.path.read_text())['tasks']['task-abcdefgh']
  self.assertEqual(task['status'],'completed');self.assertEqual(task['client_duration_ms'],1250);self.assertEqual(task['click_count'],1)
 def test_autoplay_clip_is_claimed_once_across_browsers(self):
  state=self.action('read_plan').get_json();clip=state['audio_clips'][-1]
  first=self.client.post('/api/audio/claim',json={'clip_id':clip['id']}).get_json()
  other=self.app.test_client();other.get('/?access=test-access')
  second=other.post('/api/audio/claim',json={'clip_id':clip['id']}).get_json()
  self.assertTrue(first['allowed']);self.assertFalse(second['allowed'])
 def test_mail_credentials_never_enter_frontend_state(self):
  atomic_json(self.root/'mail.local.json',{'sender_email':'sender@example.com','app_password':'private-password-value'})
  state=self.client.get('/api/state').get_data(as_text=True)
  self.assertNotIn('private-password-value',state);self.assertNotIn('app_password',state)
