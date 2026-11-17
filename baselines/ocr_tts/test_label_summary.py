import unittest
from baseline import label_summary

class SummaryTests(unittest.TestCase):
    def test_fields_on_separate_lines(self):
        self.assertEqual(label_summary('NDC 62584-267\nMetoprolol Tartrate\nTablets, USP\n50 mg\n100 Tablets'),'Metoprolol Tartrate, 50 mg')
    def test_same_line(self):
        self.assertEqual(label_summary('Amlodipine Besylate 5 mg'),'Amlodipine Besylate, 5 mg')
    def test_missing_name_or_strength_is_not_invented(self):
        self.assertEqual(label_summary('50 mg'),'')
        self.assertEqual(label_summary('Metoprolol Tartrate'),'')
    def test_warning_and_concentration_are_not_shortened(self):
        self.assertEqual(label_summary('Each tablet contains 50 mg'),'')
        self.assertEqual(label_summary('Example Medicine 5 mg / 5 mL'),'')

if __name__=='__main__':unittest.main()
