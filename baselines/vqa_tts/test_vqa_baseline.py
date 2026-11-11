import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from vqa_baseline import VQAClient, VQALabelReader

class VQABaselineTests(unittest.TestCase):
    def test_structured_fields_without_medication_list(self):
        response=SimpleNamespace(status_code=200,json=lambda:{'choices':[{'message':{'content':'{"name":"Example Medicine","strength":"50 mg"}'}}]})
        with patch('requests.post',return_value=response) as post:
            result=VQAClient('test-only-key').identify(Image.new('RGB',(20,20)))
        self.assertEqual(result['summary'],'Example Medicine, 50 mg')
        payload=post.call_args.kwargs['json']
        self.assertNotIn('medications',payload)
        self.assertEqual(len(payload['messages']),1)
    def test_partial_field_does_not_enable_a_complete_result(self):
        response=SimpleNamespace(status_code=200,json=lambda:{'choices':[{'message':{'content':'{"name":"Example Medicine","strength":null}'}}]})
        with patch('requests.post',return_value=response):
            result=VQAClient('test-only-key').identify(Image.new('RGB',(20,20)))
        self.assertEqual(result['summary'],'')
    def test_confirmation_is_explicit_and_no_api_key_in_widget_state(self):
        with tempfile.TemporaryDirectory() as folder:
            reader=VQALabelReader(folder=folder,recognizer=lambda image:{'text':'Example Medicine, 50 mg','summary':'Example Medicine, 50 mg'},tts=lambda text:'audio')
            buffer=io.BytesIO();Image.new('RGB',(20,20)).save(buffer,'PNG')
            photo=base64.b64encode(buffer.getvalue()).decode()
            reader._handle({'new':{'action':'photo','task_id':'one','photo':photo}})
            self.assertTrue(reader.can_finish)
            self.assertEqual(json.loads((Path(folder)/'tasks.json').read_text())[0]['status'],'in_progress')
            self.assertNotIn('api_key',reader.get_state())
            reader._handle({'new':{'action':'finish','task_id':'one','client_elapsed_ms':100,'clicks':[{'action':'confirm_selection'}]}})
            record=json.loads((Path(folder)/'tasks.json').read_text())[0]
            self.assertEqual(record['condition'],'VQA_TTS')
            self.assertEqual(record['status'],'completed')
            reader.close()
    def test_unreadable_retake_invalidates_previous_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            reader=VQALabelReader(folder=folder,recognizer=lambda image:{'text':'','summary':''},tts=lambda text:'audio')
            reader.can_finish=True
            buffer=io.BytesIO();Image.new('RGB',(20,20)).save(buffer,'PNG')
            reader._handle({'new':{'action':'photo','task_id':'one','photo':base64.b64encode(buffer.getvalue()).decode()}})
            self.assertFalse(reader.can_finish)
            reader._handle({'new':{'action':'finish','task_id':'one'}})
            self.assertEqual(json.loads((Path(folder)/'tasks.json').read_text())[0]['status'],'in_progress')
            reader.close()

if __name__=='__main__':unittest.main()
