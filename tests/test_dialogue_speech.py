import json
import types
import unittest
from unittest.mock import patch, Mock
import numpy as np
from mediconfirm import speech_tools
from mediconfirm.dialogue import Dialogue

class DialogueTests(unittest.TestCase):

    def setUp(self):
        self.chat = Dialogue()
        self.client = Mock()
        self.client.request.return_value = 'I can help check your medication list.'
        self.meds = [{'name': 'Example A', 'strength': '100 mg', 'time': '08:00', 'dose': '1 tablet'}]

    def ask(self, text, kind='question', result=None):
        return self.chat.answer(self.client, text, kind, self.meds, '08:00', result)

    def test_health_context_persists_into_followup(self):
        self.ask('I feel dizzy today', 'health')
        self.ask('Is this my morning medication?')
        messages = self.client.request.call_args.args[0]
        self.assertIn('I feel dizzy today', messages[0]['content'])
        self.assertTrue(any((m['role'] == 'user' and m['content'] == 'I feel dizzy today' for m in messages)))

    def test_latest_verification_in_context_and_no_free_medical_knowledge(self):
        result = {'status': 'Mismatch', 'fields': {'name': 'Example B', 'strength': '20 mg'}}
        self.ask('Is this right?', result=result)
        prompt = self.client.request.call_args.args[0][0]['content']
        self.assertIn('Mismatch', prompt)
        self.assertIn('Do not explain drug facts from memory', prompt)
        self.assertIn('do not infer diagnosis', prompt)

    def test_confirmation_is_self_report_not_intake_write(self):
        self.ask('I have taken it.')
        self.client.request.assert_called_once()
        self.assertIn('Never claim to have saved an intake record from chat', self.client.request.call_args.args[0][0]['content'])

    def test_negative_confirmation_is_not_taken(self):
        self.ask('I have not taken it')
        self.assertEqual(self.client.request.call_args.args[0][-1]['content'], 'I have not taken it')

    def test_short_yes_uses_normal_conversation_context(self):
        self.ask('Can we talk about music?')
        self.ask('yes')
        messages = self.client.request.call_args.args[0]
        self.assertEqual(messages[-1]['content'], 'yes')
        self.assertTrue(any((m['content'] == 'Can we talk about music?' for m in messages)))

    def test_reset_clears_health_and_history(self):
        self.ask('Tired today', 'health')
        self.chat.reset()
        self.assertEqual(self.chat.health_reports, [])
        self.assertEqual(len(self.chat.messages), 1)

    def test_failed_api_not_replaced_by_fake_answer(self):
        self.client.request.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            self.ask('What does this label say?')
        self.assertEqual(self.chat.messages[-1]['role'], 'user')

class SpeechTests(unittest.TestCase):

    def test_silence_does_not_load_model(self):
        with patch('mediconfirm.speech_tools.decode_recording', return_value=np.zeros(16000, dtype=np.float32)), patch.dict('sys.modules', {'whisper': Mock()}) as modules:
            self.assertEqual(speech_tools.transcribe_recording('dummy'), '')
            modules['whisper'].load_model.assert_not_called()

    def test_english_transcription_returns_editable_text(self):
        model = Mock()
        model.transcribe.return_value = {'text': ' I have not taken it. ', 'segments': []}
        with patch('mediconfirm.speech_tools.decode_recording', return_value=np.full(16000, 0.05, dtype=np.float32)), patch.object(speech_tools, '_model', model), patch.dict('sys.modules', {'whisper': Mock()}):
            self.assertEqual(speech_tools.transcribe_recording('dummy'), 'I have not taken it.')
            self.assertEqual(model.transcribe.call_args.kwargs['language'], 'en')

    def test_no_speech_segments_request_retry(self):
        model = Mock()
        model.transcribe.return_value = {'text': 'Hallucinated text', 'segments': [{'no_speech_prob': 0.95}]}
        with patch('mediconfirm.speech_tools.decode_recording', return_value=np.full(16000, 0.05, dtype=np.float32)), patch.object(speech_tools, '_model', model), patch.dict('sys.modules', {'whisper': Mock()}):
            self.assertEqual(speech_tools.transcribe_recording('dummy'), '')

    def test_invalid_recording_rejected_before_decoder(self):
        with self.assertRaises(ValueError):
            speech_tools.decode_recording('data:image/jpeg;base64,AAAA')

    def test_decode_passes_explicit_ffmpeg_and_returns_16khz_array(self):
        pcm = np.array([1000, -1000] * 1600, dtype='<i2').tobytes()
        with patch('mediconfirm.speech_tools.shutil.which', return_value='/fake/ffmpeg'), patch('mediconfirm.speech_tools.subprocess.run', return_value=types.SimpleNamespace(stdout=pcm)) as run:
            result = speech_tools.decode_recording('data:audio/webm;base64,YXVkaW8=')
            self.assertEqual(len(result), 3200)
            self.assertEqual(run.call_args.args[0][0], '/fake/ffmpeg')
            self.assertIn('16000', run.call_args.args[0])
