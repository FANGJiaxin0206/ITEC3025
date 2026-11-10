import unittest,tempfile,io,json
from pathlib import Path
from PIL import Image
from mediconfirm.mobile_server import create_app
from mediconfirm.bulk_medications import save_medication_entries
from mediconfirm.drug_sources import DailyMedSource,_form,_general_evidence

class CachedLabelTests(unittest.TestCase):
 def test_usp_and_plural_forms(self):
  self.assertEqual(_form('Tablets, USP'),'tablet')
  self.assertEqual(_form('Film-coated tablets USP'),'tablet, film coated')
 def test_test_medicines_work_without_live_search(self):
  from unittest.mock import patch
  with patch('requests.Session',side_effect=AssertionError('unexpected live search')):
   for name,strength in [('Metoprolol Tartrate','50 mg'),('Amlodipine Besylate','5 mg'),('Atorvastatin Calcium','40 mg')]:
    r=DailyMedSource().lookup(dict(name=name,strength=strength,dosage_form='Tablets, USP'))
    self.assertEqual(r['status'],'found');self.assertEqual(r['source_mode'],'stored_official_label')
    self.assertTrue(r['general_uses_text']);self.assertTrue(r['url'].startswith('https://dailymed.nlm.nih.gov/'))
 def test_unknown_form_is_not_claimed_verified(self):
  r=DailyMedSource().lookup(dict(name='Amlodipine Besylate',strength='5 mg',dosage_form=None))
  self.assertEqual(r['status'],'found');self.assertFalse(r['form_verified'])
 def test_explicit_release_conflict_is_not_accepted(self):
  from mediconfirm.drug_sources import _cached_lookup
  self.assertIsNone(_cached_lookup(dict(name='Metoprolol Tartrate',strength='50 mg',dosage_form='tablet, extended release')))
 def test_unsafe_xml_not_reparsed_in_fallback(self):
  self.assertIsNone(_general_evidence(b'<!DOCTYPE document><document/>',dict(name='A',strength='5 mg',dosage_form=None)))

class MobileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  save_medication_entries([dict(name='Amlodipine Besylate',strength='5 mg',time='12:00',dose='1 tablet')],(self.root/'data/personal_medications.json').resolve())
  self.app=create_app(self.root,access_token='test-access',config=dict(api_key='fake-private-key',model='gpt-4.1'))
  self.client=self.app.test_client();self.client.get('/?access=test-access');self.client.get('/api/state')
  self.phone=next(iter(self.app.extensions['mediconfirm_sessions'].values()));self.phone.app.voice=False
  class Client:
   def extract(self,p):return dict(name='Amlodipine Besylate',strength='5 mg',dosage_form='Tablets, USP')
   def request(self,messages):return 'Amlodipine is used to lower high blood pressure.'
  self.phone.app.client=Client()
 def tearDown(self):
  for p in self.app.extensions['mediconfirm_sessions'].values():p.app.close()
  self.tmp.cleanup()
 def action(self,action,**kwargs):return self.client.post('/api/action',json=dict(action=action,**kwargs))
 def photo(self):
  b=io.BytesIO();Image.new('RGB',(20,20),'white').save(b,format='JPEG');b.seek(0)
  return self.client.post('/api/photo',data={'photo':(b,'photo.jpg')})
 def test_auth_required(self):
  c=self.app.test_client();self.assertEqual(c.get('/api/state').status_code,401)
  self.assertEqual(c.get('/?access=wrong').status_code,401)
 def test_key_never_in_state(self):self.assertNotIn('fake-private-key',self.client.get('/api/state').get_data(as_text=True))
 def test_photo_enables_but_does_not_save_taken(self):
  s=self.photo().get_json();self.assertTrue(s['confirmation_ready']);self.assertTrue(s['verification_id'])
  data=json.loads(self.phone.app.log_path.read_text());self.assertTrue(all(e['status']=='Pending' for e in data['events'].values()))
 def test_confirm_needs_current_token(self):
  s=self.photo().get_json();self.action('confirm',status='Taken',verification_id='stale')
  self.assertNotEqual(self.phone.app.flow_page,'done')
  s=self.action('confirm',status='Taken',verification_id=s['verification_id']).get_json();self.assertEqual(s['flow_page'],'done')
 def test_general_uses_has_cached_source_and_excerpt(self):
  self.photo();s=self.action('uses').get_json()
  self.assertEqual(s['source_mode'],'stored_official_label');self.assertTrue(s['source_links'])
  self.assertIn('hypertension',s['source_excerpt'].lower());self.assertIn('high blood pressure',s['dialogue_messages'][-1]['content'])
 def test_severe_report_blocks_further_photo_confirmation(self):
  self.photo();s=self.action('chat',text='I have chest pain').get_json();self.assertEqual(s['flow_page'],'help')
  self.assertIn('NOT SENT',s['notification_text']);self.assertFalse(s['confirmation_ready'])
  self.assertFalse(self.photo().get_json()['confirmation_ready'])
 def test_browsers_share_one_local_profile(self):
  c=self.app.test_client();c.get('/?access=test-access');c.get('/api/state')
  self.assertEqual(len(self.app.extensions['mediconfirm_sessions']),1)
  folders=[str(x.app.log_path) for x in self.app.extensions['mediconfirm_sessions'].values()];self.assertEqual(len(set(folders)),1)
 def test_cross_origin_post_rejected(self):
  self.assertEqual(self.client.post('/api/action',json={'action':'replay'},headers={'Origin':'https://example.com'}).status_code,403)
 def test_web_edit_updates_the_shared_medication_list(self):
  before=((self.root/'data/personal_medications.json').resolve()).read_bytes()
  self.action('save_list',medications=[dict(name='B',strength='10 mg',time='08:00',dose='1 tablet')])
  self.assertNotEqual(((self.root/'data/personal_medications.json').resolve()).read_bytes(),before)
  self.assertEqual(self.phone.medication_path,(self.root/'data/personal_medications.json').resolve())
 def test_timeout_has_unsent_notice_in_the_same_log(self):
  from mediconfirm.plan_actions import process_plan
  self.action('start_reminder');self.phone.app.voice=False
  process_plan(self.phone.app.log_path,self.phone.app.medications,self.phone.app.selected_time,advance_minutes=11)
  state=self.client.get('/api/state').get_json()
  self.assertIn('Unconfirmed',state['schedule_text']);self.assertIn('NOT SENT',state['notification_text'])
  self.assertEqual(self.phone.app.log_path,(self.root/'data/intake_records.json').resolve())
 def test_invalid_photo_no_confirmation(self):
  s=self.client.post('/api/photo',data={'photo':(io.BytesIO(b'not a photo'),'bad.jpg')})
  self.assertEqual(s.status_code,400);self.assertFalse(self.phone.app.confirmation_ready)
