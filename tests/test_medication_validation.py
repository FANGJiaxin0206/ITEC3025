import tempfile
import unittest
from pathlib import Path
from mediconfirm.bulk_medications import validate_entries, save_medication_entries, load_saved_medications
from mediconfirm.simple_service import check_medication_list

class MedicationValidationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(name="A", strength="50 mg", time="08:00;20:00", dose="1 tablet"),
                     dict(name="B", strength="5 mg", time="08:00", dose="2 tablets")]
    def test_multiple_times_expand_with_distinct_event_ids(self):
        rows = validate_entries(self.rows)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["medication_id"] for r in rows}), 3)
    def test_all_drugs_at_same_schedule_are_valid(self):
        rows = validate_entries(self.rows)
        result = check_medication_list(dict(name="B",strength="5mg"),rows,"08:00")
        self.assertEqual(result["status"], "Match")
        self.assertEqual(result["matched_medication"]["dose"], "2 tablets")
    def test_partial_and_duplicate_records_rejected(self):
        with self.assertRaises(ValueError): validate_entries([dict(name="A",time="08:00")])
        with self.assertRaises(ValueError): validate_entries([self.rows[0],self.rows[0]])
    def test_invalid_times_rejected(self):
        for time in ["24:00", "08:80", "morning"]:
            with self.assertRaises(ValueError):validate_entries([{**self.rows[0],"time":time}])
    def test_invalid_save_does_not_replace_existing_list(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"meds.json"
            save_medication_entries(self.rows,path)
            previous=path.read_bytes()
            with self.assertRaises(ValueError):save_medication_entries([dict(name="A")],path)
            self.assertEqual(path.read_bytes(),previous)
            self.assertEqual(len(load_saved_medications(path)),3)
