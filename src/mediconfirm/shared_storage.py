"""One local medication list, settings file and intake log for this installation."""
import json
import shutil
from pathlib import Path
from .core import atomic_json
from .intake_store import _LOCK, _load
from .bulk_medications import load_saved_medications
from .web_settings import validate_settings


def prepare_shared_storage(root):
    folder = Path(root) / 'data'
    marker = folder / 'shared_storage_migration.json'
    with _LOCK:
        if marker.exists():
            return folder
        folder.mkdir(parents=True, exist_ok=True)
        canonical = folder / 'intake_records.json'
        store = _load(canonical)
        report = {'schema_version': 1, 'imported_logs': [], 'skipped_files': [],
                  'archived_test_runs': 'Legacy demo_runs files are preserved but not added to the daily log.'}
        # Backups retain the exact original files before combining regular logs.
        backup = folder / 'before_shared_storage'
        for name in ('intake_records.json', 'personal_medications.json', 'settings.json'):
            source = folder / name
            if source.exists():
                backup.mkdir(exist_ok=True)
                if not (backup / name).exists():
                    shutil.copy2(source, backup / name)
        for path in sorted((folder / 'mobile_runs').glob('*/intake_records.json')):
            try:
                old = _load(path)
                for key, event in old['events'].items():
                    previous = store['events'].get(key)
                    if previous is None:
                        store['events'][key] = event
                        continue
                    candidates = [previous, event]
                    taken = [e for e in candidates if e.get('status') == 'Taken']
                    chosen = dict(max(taken or candidates, key=lambda e: e.get('updated_at', '')))
                    history = {json.dumps(h, sort_keys=True): h for e in candidates for h in e.get('history', [])}
                    chosen['history'] = sorted(history.values(), key=lambda h: h.get('at', ''))
                    store['events'][key] = chosen
                for key, item in old.get('simulated_notifications', {}).items():
                    store.setdefault('simulated_notifications', {}).setdefault(key, item)
                report['imported_logs'].append(str(path.relative_to(folder)))
            except (ValueError, OSError, KeyError, TypeError):
                report['skipped_files'].append(str(path.relative_to(folder)))
        atomic_json(canonical, store)
        medication_path = folder / 'personal_medications.json'
        if not medication_path.exists():
            candidates = sorted((folder / 'mobile_runs').glob('*/medications.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            candidates += [Path(root) / 'evaluation' / 'demo_medications.json']
            for source in candidates:
                try:
                    rows = load_saved_medications(source)
                    if rows:
                        atomic_json(medication_path, {'schema_version': 1, 'medications': rows})
                        report['medication_source'] = str(source.relative_to(root))
                        break
                except (ValueError, OSError, TypeError):
                    report['skipped_files'].append(str(source))
        settings_path = folder / 'settings.json'
        if not settings_path.exists():
            candidates = [folder / 'notebook_settings.json', *list((folder / 'mobile_runs').glob('*/settings.json'))]
            candidates = sorted((p for p in candidates if p.exists()), key=lambda p: p.stat().st_mtime, reverse=True)
            for source in candidates:
                try:
                    legacy = json.loads(source.read_text())
                    if 'repeat_seconds' not in legacy:
                        legacy.update(timeout_seconds=600, repeat_seconds=300)
                    atomic_json(settings_path, validate_settings(legacy))
                    report['settings_source'] = str(source.relative_to(folder))
                    break
                except (ValueError, OSError, TypeError):
                    report['skipped_files'].append(str(source.relative_to(folder)))
        atomic_json(marker, report)
        return folder
