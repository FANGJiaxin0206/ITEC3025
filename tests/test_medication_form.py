import tempfile
import unittest
from pathlib import Path
from mediconfirm.medication_form import MedicationListForm
from mediconfirm.bulk_medications import load_saved_medications

class MedicationFormTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'meds.json'
        self.form = MedicationListForm(self.path)

    def tearDown(self):
        self.form.close()
        self.tmp.cleanup()

    def fill(self, row, name='Example A', time='08:00', strength='100 mg', dose='1 tablet'):
        for key, value in dict(name=name, time=time, strength=strength, dose=dose).items():
            row['fields'][key].value = value

    def test_plus_button_adds_row_and_whole_form_saves(self):
        self.fill(self.form.rows[0])
        self.form.add_button.click()
        self.fill(self.form.rows[1], name='Example B', time='20:00', strength='20 mg')
        self.assertFalse(self.path.exists())
        self.form.save_button.click()
        self.assertEqual(len(load_saved_medications(self.path)), 2)

    def test_reload_prepopulates_fields_and_groups_times(self):
        self.fill(self.form.rows[0], time='08:00;20:00')
        self.assertTrue(self.form.save())
        other = MedicationListForm(self.path)
        try:
            self.assertEqual(len(other.rows), 1)
            self.assertEqual(other.rows[0]['fields']['time'].value, '08:00;20:00')
            self.assertEqual(other.rows[0]['fields']['name'].value, 'Example A')
        finally:
            other.close()

    def test_partial_new_row_does_not_replace_saved_list(self):
        self.fill(self.form.rows[0])
        self.form.save()
        before = self.path.read_bytes()
        row = self.form.add_row()
        row['fields']['name'].value = 'Incomplete'
        self.assertFalse(self.form.save())
        self.assertEqual(before, self.path.read_bytes())
        self.assertIn('Could not save', self.form.message.value)

    def test_completely_empty_spare_row_is_ignored(self):
        self.fill(self.form.rows[0])
        self.form.add_button.click()
        self.assertTrue(self.form.save())
        self.assertEqual(len(self.form.medications), 1)

    def test_delete_is_draft_until_save(self):
        self.fill(self.form.rows[0])
        row = self.form.add_row()
        self.fill(row, name='Example B')
        self.form.save()
        row['delete'].click()
        self.assertEqual(len(load_saved_medications(self.path)), 2)
        self.form.save()
        self.assertEqual(len(load_saved_medications(self.path)), 1)

    def test_saved_callback_only_on_valid_save_and_unsubscribe(self):
        calls = []
        unsubscribe = self.form.on_saved(lambda meds: calls.append(meds))
        self.form.save()
        self.assertEqual(calls, [])
        self.fill(self.form.rows[0])
        self.form.save()
        self.assertEqual(len(calls), 1)
        unsubscribe()
        self.form.save()
        self.assertEqual(len(calls), 1)

    def test_unsaved_edits_do_not_change_active_list(self):
        self.fill(self.form.rows[0])
        self.form.save()
        self.form.rows[0]['fields']['strength'].value = '200 mg'
        self.assertEqual(self.form.medications[0]['strength'], '100 mg')
        self.assertIn('unsaved changes', self.form.message.value)
