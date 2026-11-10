"""Persist web preferences and render explicitly unsent caregiver emails."""
import math
import re
from .core import atomic_json
from .intake_store import _LOCK, _load, _moment

DEFAULTS = {'timezone': 'Asia/Hong_Kong', 'timeout_seconds': 600, 'repeat_seconds': 300,
            'reminders_enabled': False, 'caregiver_email': '', 'notification_mode': 'email', 'real_email_enabled': False}


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError('Settings must be an object.')
    timeout = value.get('timeout_seconds', 600)
    if isinstance(timeout, bool):
        raise ValueError('Enter a timeout in seconds.')
    timeout = float(timeout)
    if not math.isfinite(timeout) or not 1 <= timeout <= 86400:
        raise ValueError('Choose a timeout between 1 and 86400 seconds.')
    repeat = value.get('repeat_seconds', min(300, timeout / 2))
    if isinstance(repeat, bool):
        raise ValueError('Enter a repeat reminder delay in seconds.')
    repeat = float(repeat)
    if not math.isfinite(repeat) or not 0 < repeat < timeout:
        raise ValueError('The repeat reminder must be earlier than the alert timeout.')
    enabled = value.get('reminders_enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('Reminder setting must be on or off.')
    email = value.get('caregiver_email', '')
    if not isinstance(email, str):
        raise ValueError('Enter a valid caregiver email address.')
    email = email.strip()
    if email and (len(email) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', email)):
        raise ValueError('Enter a valid caregiver email address.')
    live = value.get('real_email_enabled', False)
    if not isinstance(live, bool):raise ValueError('Email setting must be on or off.')
    return {**DEFAULTS, 'real_email_enabled': live, 'timeout_seconds': timeout, 'repeat_seconds': repeat, 'reminders_enabled': enabled,
            'caregiver_email': email}


def attach_email_previews(path, recipient):
    """Freeze recipient and content when an alert is first handled; never send email."""
    if not path.exists():
        return
    with _LOCK:
        store = _load(path)
        changed = False
        for item in store.get('simulated_notifications', {}).values():
            if 'delivery_status' in item:
                continue
            item.update(recipient=recipient or 'No caregiver email saved', simulated=True,
                        sent=False, delivery_status='simulated_not_sent',
                        subject='MediConfirm: ' + ('Urgent check-in requested' if item['type'] == 'severe_discomfort' else 'Medication confirmation overdue'))
            changed = True
        if changed:
            atomic_json(path, store)


def read_history(folder):
    events, notifications = [], []
    paths = [folder / 'intake_records.json']
    for path in paths:
        if not path.exists():
            continue
        with _LOCK:
            store = _load(path)
        demo = path.parent.name == 'demo_runs'
        for item in store['events'].values():
            events.append({**item, 'demo': demo})
        for item in store.get('simulated_notifications', {}).values():
            notifications.append({**item, 'demo': demo})
    events.sort(key=lambda item: item.get('updated_at', ''), reverse=True)
    notifications.sort(key=lambda item: item.get('at', ''), reverse=True)
    return events, notifications
