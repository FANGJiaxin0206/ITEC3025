import unittest
from mediconfirm.drug_sources import extract_matching_uses, is_use_question, DailyMedSource
XML = b'<document xmlns="urn:hl7-org:v3"><code code="34390-5"/>\n<manufacturedProduct><name>EXAMPLE A</name><formCode displayName="TABLET"/>\n<asEntityWithGeneric><genericMedicine><name>Example ingredient</name></genericMedicine></asEntityWithGeneric>\n<ingredient classCode="ACTIB"><quantity><numerator value="100" unit="mg"/><denominator value="1" unit="1"/></quantity></ingredient>\n</manufacturedProduct><section><code code="34067-9"/><text>Fictional uses for tests only.</text></section>\n<section><code code="34068-7"/><text>Directions must not enter general-use evidence.</text></section></document>'
FIELDS = {'name': 'Example A', 'strength': '100 mg', 'dosage_form': 'tablet'}

class SourceTests(unittest.TestCase):

    def test_exact_label_fields_allow_general_uses_only(self):
        result = extract_matching_uses(XML, FIELDS)
        self.assertEqual(result['general_uses_text'], 'Fictional uses for tests only.')
        self.assertNotIn('Directions', result['general_uses_text'])

    def test_wrong_strength_rejected(self):
        self.assertIsNone(extract_matching_uses(XML, {**FIELDS, 'strength': '200 mg'}))

    def test_wrong_name_rejected(self):
        self.assertIsNone(extract_matching_uses(XML, {**FIELDS, 'name': 'Similar A'}))

    def test_missing_or_different_form_not_guessed(self):
        self.assertIsNone(extract_matching_uses(XML, {**FIELDS, 'dosage_form': None}))
        self.assertIsNone(extract_matching_uses(XML, {**FIELDS, 'dosage_form': 'tablet, extended release'}))

    def test_combination_label_rejected(self):
        combo = XML.replace(b'</manufacturedProduct>', b'<ingredient classCode="ACTIB"/></manufacturedProduct>')
        self.assertIsNone(extract_matching_uses(combo, FIELDS))

    def test_animal_label_rejected(self):
        self.assertIsNone(extract_matching_uses(XML.replace(b'34390-5', b'animal'), FIELDS))

    def test_general_use_intents_detected(self):
        self.assertTrue(is_use_question('What is this medicine used for?'))
        self.assertTrue(is_use_question('Why was I prescribed this?'))
        self.assertFalse(is_use_question('I feel tired today'))

    def test_missing_fields_does_not_trigger_network(self):
        result = DailyMedSource().lookup({'name': 'Example A', 'strength': None})
        self.assertEqual(result['status'], 'unavailable')
