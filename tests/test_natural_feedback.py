import unittest
from mediconfirm.speech_tools import spoken_text

class SpeechFormattingTests(unittest.TestCase):

    def test_markdown_removed_without_changing_drug_facts(self):
        self.assertEqual(spoken_text('For **08:00**, your list shows **Metoprolol Tartrate, 50 mg, one tablet**.'), 'For 08:00, your list shows Metoprolol Tartrate, 50 mg, one tablet.')

    def test_plain_text_preserved(self):
        self.assertEqual(spoken_text('Have you taken it yet?'), 'Have you taken it yet?')

    def test_links_headings_and_lists(self):
        self.assertEqual(spoken_text('## Next step\n- Read [the label](https://example.com).'), 'Next step Read the label.')
