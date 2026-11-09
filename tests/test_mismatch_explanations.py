import unittest
from mediconfirm.simple_service import check_medication_list

class MismatchExplanationTests(unittest.TestCase):

    def setUp(self):
        self.meds = [dict(name='Metoprolol Tartrate', strength='50 mg', time='08:00', dose='1 tablet'), dict(name='Atorvastatin Calcium', strength='40 mg', time='20:00', dose='1 tablet')]

    def check(self, name, strength):
        return check_medication_list(dict(name=name, strength=strength), self.meds, '08:00')

    def test_strength_includes_actual_expected_and_time(self):
        r = self.check('Metoprolol Tartrate', '100 mg')
        self.assertEqual(r['mismatch_code'], 'strength_mismatch')
        for term in ['100 mg', '50 mg', '08:00']:
            self.assertIn(term, r['text'])

    def test_wrong_time_names_recorded_and_selected_times(self):
        r = self.check('Atorvastatin Calcium', '40 mg')
        self.assertEqual(r['mismatch_code'], 'time_mismatch')
        for term in ['20:00', '08:00', 'Metoprolol Tartrate']:
            self.assertIn(term, r['text'])

    def test_unknown_name_not_misreported_as_strength_error(self):
        r = self.check('Antacid', '500 mg')
        self.assertEqual(r['mismatch_code'], 'name_not_listed')
        self.assertIn('not on your saved medication list', r['text'])
        self.assertIn('Metoprolol Tartrate, 50 mg', r['text'])

    def test_wrong_strength_at_wrong_time_includes_both(self):
        r = self.check('Atorvastatin Calcium', '80 mg')
        self.assertEqual(r['mismatch_code'], 'strength_and_time_mismatch')
        for term in ['80 mg', '40 mg', '20:00', '08:00']:
            self.assertIn(term, r['text'])

    def test_correct_label_still_matches(self):
        self.assertEqual(self.check('Metoprolol Tartrate', '50mg')['status'], 'Match')
