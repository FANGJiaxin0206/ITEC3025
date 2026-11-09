import unittest
from mediconfirm.drug_sources import extract_matching_uses
BASE=b'''<document xmlns="urn:hl7-org:v3"><code code="34391-3"/><manufacturedProduct><name>Metoprolol Tartrate</name><formCode displayName="TABLET, FILM COATED"/><ingredient classCode="ACTIB"><quantity><numerator value="50" unit="mg"/><denominator value="1" unit="1"/></quantity></ingredient></manufacturedProduct>BODY<section><code code="34068-7"/><text>Do not include directions.</text></section></document>'''
FIELDS=dict(name='Metoprolol Tartrate',strength='50 mg',dosage_form='tablet, film coated')
class SectionTests(unittest.TestCase):
 def test_highlight_nested_uses_are_read(self):
  x=BASE.replace(b'BODY',b'<section><code code="34067-9"/><excerpt><highlight><text>For hypertension.</text></highlight></excerpt></section>')
  self.assertEqual(extract_matching_uses(x,FIELDS)['general_uses_text'],'For hypertension.')
 def test_subsection_uses_are_read(self):
  x=BASE.replace(b'BODY',b'<section><code code="34067-9"/><component><section><text>For hypertension.</text></section></component></section>')
  self.assertEqual(extract_matching_uses(x,FIELDS)['general_uses_text'],'For hypertension.')
 def test_form_synonyms_work_without_release_substitution(self):
  x=BASE.replace(b'BODY',b'<section><code code="34067-9"/><text>For hypertension.</text></section>')
  self.assertIsNotNone(extract_matching_uses(x,{**FIELDS,'dosage_form':'film-coated tablet'}))
  self.assertIsNone(extract_matching_uses(x,{**FIELDS,'dosage_form':'tablet, extended release'}))
  self.assertIsNone(extract_matching_uses(x,{**FIELDS,'strength':'100 mg'}))
