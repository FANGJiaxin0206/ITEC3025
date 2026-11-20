import unittest
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import test_mobile
from mediconfirm.dialogue import Dialogue

class AudioUXTests(unittest.TestCase):
 setUp=test_mobile.MobileTests.setUp
 tearDown=test_mobile.MobileTests.tearDown
 action=test_mobile.MobileTests.action
 photo=test_mobile.MobileTests.photo
 def test_current_plan_is_independent_of_old_selected_event(self):
  self.phone.manual_time=True;self.phone.app.selected_time='08:00'
  moment=datetime(2026,11,10,12,30,tzinfo=ZoneInfo('Asia/Hong_Kong'))
  with patch('mediconfirm.mobile_server._moment',return_value=moment):
   result=self.action('read_plan').get_json()
  self.assertEqual(result['current_plan_time'],'12:00')
  clip=result['audio_clips'][-1]
  self.assertEqual(clip['scope'],'home');self.assertEqual(clip['target'],'plan:12:00')
  self.assertIn('12:00',clip['text']);self.assertNotIn('08:00',clip['text'])
 def test_chat_clip_belongs_to_the_assistant_message(self):
  result=self.action('chat',text='Hello').get_json()
  clip=result['audio_clips'][-1];message=result['dialogue_messages'][-1]
  self.assertEqual(clip['scope'],'chat');self.assertEqual(clip['target'],message['message_id'])
 def test_web_returns_text_while_audio_is_still_preparing(self):
  class DeferredThread:
   started=False
   def __init__(self,*args,**kwargs):pass
   def start(self):DeferredThread.started=True
  self.phone.app.voice=True
  with patch('mediconfirm.mobile_server.threading.Thread',DeferredThread):
   self.phone.audio_scope='home';self.phone.audio_target='plan:08:00'
   self.phone.app._speak('Your saved plan for 08:00 is ready.')
  clip=self.phone.state()['audio_clips'][-1]
  self.assertTrue(DeferredThread.started)
  self.assertEqual(clip['status'],'preparing')
  self.assertIn('Your saved plan',clip['text'])
 def test_retaking_clears_old_result_audio(self):
  self.photo();self.assertTrue(any(c['scope']=='check' for c in self.phone.state()['audio_clips']))
  result=self.action('prepare_photo').get_json()
  self.assertFalse(any(c['scope']=='check' for c in result['audio_clips']))
 def test_audio_endpoint_requires_authorization(self):
  self.assertEqual(self.app.test_client().get('/api/audio/unknown').status_code,401)
  self.assertEqual(self.client.get('/api/audio/unknown').status_code,404)
 def test_audio_endpoint_supports_progress_bar_range_requests(self):
  clip_id='seekable-audio'
  self.phone.audio_clips['check:result']={
   'id':clip_id,'scope':'check','target':'result','text':'Test',
   'data':base64.b64encode(b'0123456789').decode('ascii'),'note':'','status':'ready'}
  response=self.client.get('/api/audio/'+clip_id,headers={'Range':'bytes=2-5'})
  self.assertEqual(response.status_code,206)
  self.assertEqual(response.data,b'2345')
  self.assertEqual(response.headers.get('Accept-Ranges'),'bytes')
 def test_prompt_requests_plain_explanation_and_strips_ui_metadata(self):
  captured=[]
  class Client:
   def request(self,messages):captured.extend(messages);return 'Hello.'
  dialogue=Dialogue();dialogue.add('assistant','Earlier response')
  dialogue.answer(Client(),'Explain this medicine','conversation',[], '',None)
  self.assertIn('In everyday terms',captured[0]['content'])
  self.assertIn('Keep source limitations',captured[0]['content'])
  self.assertTrue(all(set(message)<= {'role','content'} for message in captured))
