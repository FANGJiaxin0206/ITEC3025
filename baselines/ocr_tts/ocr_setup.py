"""Locate Tesseract in the current Python environment on Windows/macOS/Linux."""
import os
import shutil
import sys
from pathlib import Path


def engine_candidates(prefix=None, environ=None, which=None):
    prefix = Path(prefix or sys.prefix)
    environ = os.environ if environ is None else environ
    which = which or shutil.which
    candidates = [environ.get('TESSERACT_CMD'), which('tesseract')]
    candidates += [str(prefix / relative) for relative in (
        'Library/bin/tesseract.exe', 'Scripts/tesseract.exe', 'tesseract.exe',
        'bin/tesseract', 'Library/bin/tesseract')]
    for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        if environ.get(variable):
            candidates.append(str(Path(environ[variable])/'Tesseract-OCR'/'tesseract.exe'))
    candidates += ['/opt/homebrew/bin/tesseract', '/usr/local/bin/tesseract', '/usr/bin/tesseract']
    return [p for p in candidates if p]


def locate_engine(explicit='', prefix=None, environ=None, which=None):
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError('TESSERACT_PATH does not point to an existing executable.')
        return str(path)
    return next((p for p in engine_candidates(prefix, environ, which) if Path(p).is_file()), None)


def configure_engine(explicit=''):
    import pytesseract
    engine = locate_engine(explicit)
    if engine is None:
        raise RuntimeError('Tesseract was not found. In this notebook run the engine-install cell, or install conda-forge::tesseract in the active environment. Set TESSERACT_PATH for a custom installation.')
    # Conda Windows builds may require DLLs alongside the executable.
    directory = str(Path(engine).parent)
    os.environ['PATH'] = directory + os.pathsep + os.environ.get('PATH', '')
    pytesseract.pytesseract.tesseract_cmd = engine
    version = pytesseract.get_tesseract_version()
    if 'eng' not in pytesseract.get_languages(config=''):
        raise RuntimeError('Tesseract was found but English language data is missing. Install the English tessdata, then rerun this cell.')
    return str(version), engine
