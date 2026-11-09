import hashlib
import json
import re
from pathlib import Path
from .core import atomic_json, normalized, strength_key

def clean_time(value):
    value = str(value).strip()
    if not re.fullmatch('\\d{1,2}:\\d{2}', value):
        raise ValueError(f'Invalid time {value!r}. Use the 24-hour HH:MM format, such as 08:00.')
    hour, minute = map(int, value.split(':'))
    if hour > 23 or minute > 59:
        raise ValueError(f'Time {value!r} is outside the valid range.')
    return f'{hour:02d}:{minute:02d}'

def validate_entries(rows):
    if not isinstance(rows, list):
        raise ValueError('The medication list must be a list of entries.')
    result, seen = ([], set())
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Medication entry {index} has an invalid format.')
        entry = {}
        for field in ('name', 'time', 'strength', 'dose'):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Entry {index} is missing {field}. All four fields are required.')
            entry[field] = value.strip()
        times = entry['time'].replace(';', ';').split(';')
        for value in times:
            time = clean_time(value)
            key = (normalized(entry['name']), strength_key(entry['strength']), time)
            if key in seen:
                raise ValueError(f"Duplicate entry: {entry['name']} / {entry['strength']} / {time}. Keep one entry and check the dose.")
            seen.add(key)
            identifier = hashlib.sha256('|'.join(key).encode()).hexdigest()[:16]
            result.append({**entry, 'time': time, 'medication_id': identifier})
    return sorted(result, key=lambda item: (item['time'], normalized(item['name']), item['strength']))

def save_medication_entries(rows, path):
    entries = validate_entries(rows)
    if not entries:
        raise ValueError('Add at least one medication before saving the list.')
    atomic_json(path, {'schema_version': 1, 'medications': entries})
    return entries

def load_saved_medications(path):
    path = Path(path)
    if not path.exists():
        return []
    saved = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(saved, dict):
        raise ValueError('The saved medication list has an invalid format. The file was not changed.')
    return validate_entries(saved.get('medications'))
