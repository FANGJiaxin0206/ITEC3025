import unittest
from mediconfirm.simple_service import identify_photo

class FakeClient:

    def __init__(self, fields):
        self.fields = fields
        self.calls = 0

    def extract(self, path):
        self.calls += 1
        return self.fields

class SimpleServiceTests(unittest.TestCase):

    def test_readable_label_without_target_is_not_medication_clearance(self):
        client = FakeClient({'name': 'Example A', 'strength': '100 mg'})
        result = identify_photo('example.jpg', client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(result['status'], 'Recognized')
        self.assertIn('No personal medication list was checked', result['text'])

    def test_missing_strength_requires_retake(self):
        result = identify_photo('example.jpg', FakeClient({'name': 'Example A', 'strength': None}))
        self.assertEqual(result['status'], 'Uncertain')

    def test_missing_name_requires_retake(self):
        result = identify_photo('example.jpg', FakeClient({'name': None, 'strength': '100 mg'}))
        self.assertEqual(result['status'], 'Uncertain')

    def test_optional_target_matches(self):
        result = identify_photo('example.jpg', FakeClient({'name': 'Example A', 'strength': '100mg'}), 'Example A', '100 mg')
        self.assertEqual(result['status'], 'Match')

    def test_wrong_strength_is_rejected(self):
        result = identify_photo('example.jpg', FakeClient({'name': 'Example A', 'strength': '200 mg'}), 'Example A', '100 mg')
        self.assertEqual(result['status'], 'Mismatch')

    def test_incomplete_target_is_configuration_error(self):
        client = FakeClient({})
        with self.assertRaises(ValueError):
            identify_photo('example.jpg', client, 'Example A', '')
        self.assertEqual(client.calls, 0)

    def test_api_failure_is_not_mock_success(self):

        class Broken:

            def extract(self, path):
                raise RuntimeError('API unavailable')
        with self.assertRaises(RuntimeError):
            identify_photo('example.jpg', Broken())
