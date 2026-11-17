"""Injected component checks; no actual OCR, network, camera or speech."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from baseline import BaselineReader

class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        buffer = io.BytesIO()
        Image.new('RGB', (30,30), 'white').save(buffer, 'PNG')
        self.photo = 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        self.reader = BaselineReader(Path(self.tmp.name), ocr=lambda image:'Example label 50 mg', tts=lambda text:'fake-audio')
    def tearDown(self):
        self.reader.close()
        self.tmp.cleanup()
    def send(self, action, **extra):
        self.reader._handle({'new':dict(action=action, task_id='task-1', **extra)})
    def records(self):
        return json.loads((Path(self.tmp.name)/'tasks.json').read_text())
    def test_ocr_is_read_without_matching_and_confirmation_is_explicit(self):
        self.send('photo', photo=self.photo)
        self.assertEqual(self.reader.label_text,'Example label 50 mg')
        self.assertEqual(self.records()[0]['status'],'in_progress')
        self.send('finish', clicks=[{'action':'submit_photo'},{'action':'audio_play'},{'action':'confirm_selection'}],client_elapsed_ms=123)
        record=self.records()[0]
        self.assertEqual(record['status'],'completed')
        self.assertEqual(record['click_count'],2)
        self.assertNotIn('correct',record)
        self.send('finish')
        self.assertEqual(len(self.records()),1)
    def test_failed_retake_invalidates_previous_selection(self):
        self.send('photo', photo=self.photo)
        self.send('photo', photo='invalid')
        self.assertFalse(self.reader.can_finish)
        self.send('finish')
        self.assertEqual(self.records()[0]['status'],'in_progress')
        self.assertEqual(self.records()[0]['photo_attempts'],2)
        self.assertEqual(self.reader.audio_data,'')
    def test_tts_failure_keeps_text_available_and_cancellation_is_separate(self):
        def fail(text):raise RuntimeError('network')
        self.reader.tts=fail
        self.send('photo', photo=self.photo)
        self.assertTrue(self.reader.can_finish)
        self.assertIn('speech generation failed',self.reader.status)
        self.send('cancel')
        self.assertEqual(self.records()[0]['status'],'cancelled')
    def test_empty_ocr_does_not_claim_selection_or_save_label_content(self):
        self.reader.ocr=lambda image:''
        self.send('photo', photo=self.photo)
        self.assertFalse(self.reader.can_finish)
        record=self.records()[0]
        self.assertEqual(record['attempt_results'][0]['result'],'no_text')
        self.assertNotIn('photo',record)
        self.assertNotIn('label_text',record)

if __name__=='__main__':unittest.main()
