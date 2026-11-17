import tempfile
import unittest
from pathlib import Path
from ocr_setup import locate_engine

class EngineDetectionTests(unittest.TestCase):
    def test_conda_windows_and_unix_layouts(self):
        for relative in ('Library/bin/tesseract.exe', 'bin/tesseract'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/relative;path.parent.mkdir(parents=True);path.touch()
                self.assertEqual(locate_engine(prefix=temp,environ={},which=lambda _:None),str(path))
    def test_windows_program_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'Tesseract-OCR/tesseract.exe';path.parent.mkdir();path.touch()
            self.assertEqual(locate_engine(prefix=Path(temp)/'env',environ={'ProgramFiles':temp},which=lambda _:None),str(path))
    def test_explicit_path_and_invalid_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'custom-engine';path.touch()
            self.assertEqual(locate_engine(str(path)),str(path))
            with self.assertRaises(FileNotFoundError):locate_engine(str(Path(temp)/'missing'))

if __name__=='__main__':unittest.main()
