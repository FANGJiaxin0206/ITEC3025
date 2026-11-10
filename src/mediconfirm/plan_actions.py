"""Finite demo reminders and persisted, explicitly unsent family notifications."""
from datetime import datetime
import math
from .intake_store import _LOCK, _load, _moment, start_plan
from .core import atomic_json

def _notice(store, key, kind, text, moment, **details):
    notices = store.setdefault('simulated_notifications', {})
    if key in notices:
        return None
    item = {'notification_id': key, 'requires_delivery': True, 'type': kind, 'at': moment.isoformat(timespec='seconds'), 'simulated': True, 'sent': False, 'channel': 'email_simulation', 'recipient': 'Family / caregiver (simulation only)', 'message': text, **details}
    notices[key] = item
    return item

def process_plan(path, medications, selected_time, timeout_seconds=600, start=False, advance_minutes=0, now=None, repeat_seconds=None):
    moment = _moment(now)
    advance = float(advance_minutes)
    if not math.isfinite(advance) or advance < 0 or advance > 1440:
        raise ValueError('Advance must be between 0 and 1440 simulated minutes.')
    if start:
        start_plan(path, medications, selected_time, timeout_seconds, moment, repeat_seconds=repeat_seconds)
    with _LOCK:
        store = _load(path)
        changed = False
        messages = []
        for e in store['events'].values():
            if e.get('status') == 'Taken' or e.get('interrupted') or (not e.get('started_at')):
                continue
            selected = e.get('date') == moment.date().isoformat() and e.get('scheduled_time') == selected_time
            if advance and selected:
                e['simulated_elapsed_minutes'] = e.get('simulated_elapsed_minutes', 0) + advance
                changed = True
            offset = float(e.get('simulated_elapsed_minutes', 0))
            elapsed = (moment - datetime.fromisoformat(e['started_at'])).total_seconds() + offset * 60
            duration = (datetime.fromisoformat(e['deadline_at']) - datetime.fromisoformat(e['started_at'])).total_seconds()
            stamp = moment.isoformat(timespec='seconds')
            if start and selected and (e.get('status') == 'Pending') and (not e.get('first_reminder_at')):
                e['first_reminder_at'] = stamp
                messages.append(f"It is time to check your {e['scheduled_time']} medication: {e['name']}, {e['strength']}. When you are ready, please take a photo of the package.")
                changed = True
            if e.get('status') == 'Pending' and elapsed >= duration:
                e.update(status='Unconfirmed', reason='confirmation_timeout', source='timer', updated_at=stamp, unconfirmed_at=stamp)
                e.setdefault('history', []).append({'at': stamp, 'status': 'Unconfirmed', 'reason': 'confirmation_timeout', 'source': 'timer', 'simulated_elapsed_minutes': offset})
                changed = True
            if e.get('status') == 'Unconfirmed' and e.get('reason') == 'confirmation_timeout':
                msg = f"The {e['scheduled_time']} intake of {e['name']}, {e['strength']} has not been confirmed. Please check in with the person. This does not establish that a dose was missed."
                notice = _notice(store, e['event_id'] + ':timeout', 'timeout', msg, moment, event_id=e['event_id'], simulated_elapsed_minutes=offset)
                if notice:
                    messages.append(f"I have not received confirmation for {e['name']} yet. Its status is unconfirmed. A family notification has been created. Check its delivery status in Me.")
                    changed = True
            elif e.get('status') == 'Pending' and elapsed >= e.get('repeat_after_seconds', duration / 2) and (not e.get('repeat_reminder_at')):
                e['repeat_reminder_at'] = stamp
                e.setdefault('reminder_history', []).append({'at': stamp, 'kind': 'repeat_question', 'simulated_elapsed_minutes': offset})
                messages.append(f"Have you taken your {e['scheduled_time']} {e['name']} yet? Please select Already taken or Not yet.")
                changed = True
        if changed:
            atomic_json(path, store)
        return (list(store['events'].values()), list(store.get('simulated_notifications', {}).values()), messages)

def report_severe(path, selected_time, report, session_id, now=None):
    moment = _moment(now)
    with _LOCK:
        store = _load(path)
        stamp = moment.isoformat(timespec='seconds')
        for e in store['events'].values():
            if e.get('date') == moment.date().isoformat() and e.get('scheduled_time') == selected_time and (e.get('status') != 'Taken'):
                if not e.get('interrupted'):
                    e.update(interrupted=True, reason='preset_severe_discomfort_report', updated_at=stamp)
                    e.setdefault('history', []).append({'at': stamp, 'status': e['status'], 'reason': 'preset_severe_discomfort_report', 'source': 'health_report'})
        notice = _notice(store, session_id + ':severe', 'severe_discomfort', 'The user reported a predefined severe-discomfort scenario. The routine medication check was paused. Please check on them and help them obtain urgent medical assistance.', moment, selected_time=selected_time, user_report=report)
        atomic_json(path, store)
        return (list(store.get('simulated_notifications', {}).values()), notice)
