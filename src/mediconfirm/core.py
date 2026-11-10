import json
import os
import re
from .storage_lock import LOCK
from pathlib import Path

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with LOCK:
        _write_json_locked(path, temp, value)

def _write_json_locked(path, temp, value):
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()

def normalized(value):
    return re.sub('\\s+', ' ', str(value).lower().strip())

def strength_key(value):
    return re.sub('\\s+', '', normalized(value))

def verify(extraction, medication):
    if not isinstance(extraction, dict):
        return {'status': 'Uncertain', 'reason': 'Invalid recognition response.'}
    name, strength = (extraction.get('name'), extraction.get('strength'))
    readable_name = isinstance(name, str) and bool(name.strip())
    readable_strength = isinstance(strength, str) and bool(strength.strip())
    accepted = {normalized(medication['name'])}
    accepted.update((normalized(x) for x in medication.get('accepted_names', [])))
    conflicts = []
    if readable_name and normalized(name) not in accepted:
        conflicts.append('The visible name does not match the selected scheduled medication.')
    if readable_strength and strength_key(strength) != strength_key(medication['strength']):
        conflicts.append('The visible strength does not match the medication list.')
    if conflicts:
        return {'status': 'Mismatch', 'reason': ' '.join(conflicts)}
    if not (readable_name and readable_strength):
        return {'status': 'Uncertain', 'reason': 'Name or strength is unreadable. Reposition the label and retake the photo.'}
    return {'status': 'Match', 'reason': 'The visible name and strength match the selected medication-list entry.'}
SEVERE_PHRASES = ('chest pain', 'chest hurts', 'heart hurts', 'trouble breathing', 'cannot breathe', "can't breathe", 'difficulty breathing', 'severe discomfort')

def severe_demo_signal(text):
    text = normalized(text).replace('’', "'")
    if re.search("\\b(no|not|never|without|don't|do not)\\b", text):
        return False
    return any((phrase in text for phrase in SEVERE_PHRASES))

def confirmation_intent(text):
    if '?' in text:
        return 'unclear'
    cleaned = re.sub("[^a-z\\s']", '', normalized(text).replace('’', "'"))
    if cleaned in {'i have taken it', 'i have already taken it', "i've taken it", "i've already taken it", 'i took it', 'i already took it', 'taken', 'already taken'}:
        return 'taken'
    if cleaned in {'not yet', "i haven't taken it", 'i have not taken it', 'i did not take it', 'i will take it later', "i haven't taken it yet"}:
        return 'pending'
    return 'unclear'
