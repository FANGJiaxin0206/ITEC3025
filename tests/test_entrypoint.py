import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mediconfirm_entry', root / 'main.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)

class EntryPointTests(unittest.TestCase):
    def test_default_opens_notebook(self):
        with patch.object(entry.subprocess, 'call', return_value=0) as call:
            self.assertEqual(entry.main([]), 0)
            args = call.call_args.args[0]
            self.assertEqual(args[1:3], ['-m', 'notebook'])
            self.assertEqual(Path(args[3]).name, 'MediConfirm.ipynb')
    def test_mobile_forwards_options(self):
        with patch.object(entry.subprocess, 'call', return_value=0) as call:
            self.assertEqual(entry.main(['mobile', '--port', '9876']), 0)
            self.assertEqual(Path(call.call_args.args[0][1]).name, 'run_mobile.py')
            self.assertEqual(call.call_args.args[0][-2:], ['--port', '9876'])
    def test_setup_check_does_not_launch_a_server(self):
        with patch.object(entry, 'check_setup', return_value=0), patch.object(entry.subprocess, 'call') as call:
            self.assertEqual(entry.main(['--check']), 0)
            call.assert_not_called()

    def test_web_alias_launches_existing_server(self):
        with patch.object(entry.subprocess, 'call', return_value=0) as call:
            self.assertEqual(entry.main(['web']), 0)
            self.assertEqual(Path(call.call_args.args[0][1]).name, 'run_mobile.py')
