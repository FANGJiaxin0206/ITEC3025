"""Persist self-reported intake and time-limited confirmation events, never swallowing."""
import hashlib
import json
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from .core import atomic_json
_LOCK = threading.RLock()

def _load(path):
    path = Path(path)
    store = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'events': {}}
    if not isinstance(store, dict) or not isinstance(store.get('events'), dict):
        raise ValueError('Existing intake log has an invalid format. It was not overwritten.')
    return store

def _moment(now):
    return now or datetime.now().astimezone()

def _seconds(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Confirmation timeout must be a positive number of seconds.')
    return value

def _key(medication, scheduled_time, moment):
    if medication.get('time') != scheduled_time:
        raise ValueError('The medication does not belong to the selected time.')
    identifier = medication.get('medication_id') or hashlib.sha256((medication['name'] + '|' + medication['strength']).encode()).hexdigest()[:16]
    return (f'{moment.date().isoformat()}:{scheduled_time}:{identifier}', identifier)

def _event(med, time, status, source, reason, moment, previous=None):
    event_id, identifier = _key(med, time, moment)
    timestamp = moment.isoformat(timespec='seconds')
    return {**(previous or {}), 'event_id': event_id, 'date': moment.date().isoformat(), 'scheduled_time': time, 'medication_id': identifier, 'name': med['name'], 'strength': med['strength'], 'recorded_dose': med['dose'], 'status': status, 'source': source, 'reason': reason, 'updated_at': timestamp, 'confirmed_at': timestamp if status == 'Taken' else None, 'self_report_only': True, 'history': list((previous or {}).get('history', [])) + [{'at': timestamp, 'status': status, 'reason': reason, 'source': source}]}

def start_plan(path, medications, scheduled_time, timeout_seconds=600, now=None):
    seconds = _seconds(timeout_seconds)
    moment = _moment(now)
    with _LOCK:
        store = _load(path)
        changed = False
        for med in medications or []:
            if med['time'] != scheduled_time:
                continue
            key, _ = _key(med, scheduled_time, moment)
            previous = store['events'].get(key)
            if previous and (previous.get('status') != 'Pending' or previous.get('deadline_at')):
                continue
            event = _event(med, scheduled_time, 'Pending', 'plan', 'awaiting_confirmation', moment, previous)
            event['started_at'] = moment.isoformat(timespec='seconds')
            event['deadline_at'] = (moment + timedelta(seconds=seconds)).isoformat(timespec='seconds')
            store['events'][key] = event
            changed = True
        if changed:
            atomic_json(path, store)
        return list(store['events'].values())

def record_intake(path, medication, scheduled_time, status, source='button', now=None, reason=None, timeout_seconds=600):
    if status not in {'Taken', 'Pending'}:
        raise ValueError('Invalid self-report status.')
    moment = _moment(now)
    key, _ = _key(medication, scheduled_time, moment)
    reason = reason or ('user_confirmed_taken' if status == 'Taken' else 'user_reported_not_taken')
    with _LOCK:
        store = _load(path)
        previous = store['events'].get(key)
        if previous and previous.get('status') == 'Taken':
            return (previous, False)
        if previous and previous.get('interrupted'):
            raise ValueError('This event was interrupted. Start a new independent demo instead of confirming it.')
        if previous and previous.get('status') == status and (previous.get('reason') == reason):
            return (previous, False)
        event = _event(medication, scheduled_time, status, source, reason, moment, previous)
        if status == 'Pending' and (not previous or previous.get('status') == 'Unconfirmed'):
            event['simulated_elapsed_minutes'] = 0
            event.pop('repeat_reminder_at', None)
            event['started_at'] = moment.isoformat(timespec='seconds')
            event['deadline_at'] = (moment + timedelta(seconds=_seconds(timeout_seconds))).isoformat(timespec='seconds')
        store['events'][key] = event
        atomic_json(path, store)
        return (event, True)

def expire_pending(path, now=None):
    moment = _moment(now)
    with _LOCK:
        store = _load(path)
        changed = False
        for key, old in list(store['events'].items()):
            if old.get('status') != 'Pending' or old.get('interrupted') or (not old.get('deadline_at')):
                continue
            deadline = datetime.fromisoformat(old['deadline_at'])
            if deadline.tzinfo is None or moment.tzinfo is None:
                raise ValueError('Confirmation timestamps must include a timezone.')
            if moment < deadline:
                continue
            timestamp = moment.isoformat(timespec='seconds')
            event = {**old, 'status': 'Unconfirmed', 'reason': 'confirmation_timeout', 'source': 'timer', 'updated_at': timestamp, 'unconfirmed_at': timestamp, 'history': list(old.get('history', [])) + [{'at': timestamp, 'status': 'Unconfirmed', 'reason': 'confirmation_timeout', 'source': 'timer'}]}
            store['events'][key] = event
            changed = True
        if changed:
            atomic_json(path, store)
        return list(store['events'].values())

def record_recovery(path, scheduled_time, reason, now=None):
    moment = _moment(now)
    with _LOCK:
        store = _load(path)
        changed = False
        for event in store['events'].values():
            if event.get('date') != moment.date().isoformat() or event.get('scheduled_time') != scheduled_time or event.get('status') == 'Taken':
                continue
            error = {'at': moment.isoformat(timespec='seconds'), 'reason': reason}
            event['last_error'] = error
            event['recovery_history'] = (list(event.get('recovery_history', [])) + [error])[-100:]
            changed = True
        if changed:
            atomic_json(path, store)
