"""MediConfirm: medication-package verification and voice interaction for older adults with low vision."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def check_setup():
    modules = ('notebook', 'anywidget', 'ipywidgets', 'flask', 'requests', 'PIL',
               'gtts', 'whisper', 'numpy', 'imageio_ffmpeg')
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    files = ('MediConfirm.ipynb', 'run_mobile.py', 'src/mediconfirm/simple_ui.py')
    absent = [name for name in files if not (ROOT / name).is_file()]
    key_ready = False
    config_path = ROOT / 'config.local.json'
    if config_path.exists():
        try:
            value = json.loads(config_path.read_text()).get('api_key', '')
            key_ready = isinstance(value, str) and bool(value.strip()) and not value.startswith('YOUR_')
        except (OSError, ValueError, AttributeError):
            pass
    import os
    key_ready = bool(os.environ.get('HKBU_API_KEY', '').strip()) or key_ready
    print('Project files:', 'ready' if not absent else ', '.join(absent))
    print('Dependencies:', 'ready' if not missing else ', '.join(missing))
    print('API configuration:', 'ready' if key_ready else 'copy config.example.json to config.local.json and add your key')
    return 0 if not missing and not absent and key_ready else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('interface', nargs='?', choices=('notebook', 'mobile'), default='notebook')
    parser.add_argument('--check', action='store_true', help='Check local setup without starting a server or calling an API.')
    args, extra = parser.parse_known_args(argv)
    if args.check:
        if extra:
            parser.error('Unexpected arguments with --check.')
        return check_setup()
    if args.interface == 'notebook':
        command = [sys.executable, '-m', 'notebook', str(ROOT / 'MediConfirm.ipynb'), *extra]
    else:
        command = [sys.executable, str(ROOT / 'run_mobile.py'), *extra]
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
