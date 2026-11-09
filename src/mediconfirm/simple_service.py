"""Minimal photo -> live API -> readable result. Reusable by a future web backend."""
from .core import verify, normalized, strength_key

def identify_photo(path, client, expected_name='', expected_strength='', medications=None, selected_time=''):
    if medications is None and bool(expected_name.strip()) != bool(expected_strength.strip()):
        raise ValueError('Set both EXPECTED_NAME and EXPECTED_STRENGTH, or leave both blank.')
    fields = client.extract(path)
    name, strength = (fields.get('name'), fields.get('strength'))
    if not (isinstance(name, str) and name.strip() and isinstance(strength, str) and strength.strip()):
        return {'status': 'Uncertain', 'fields': fields, 'text': 'I cannot read both the name and strength clearly. Please retake the photo with the full label visible and less glare.'}
    if medications is not None:
        return check_medication_list(fields, medications, selected_time)
    if expected_name.strip():
        checked = verify(fields, {'name': expected_name, 'strength': expected_strength})
        if checked['status'] != 'Match':
            return {'status': checked['status'], 'fields': fields, 'text': f'The label reads {name}, {strength}, but the configured target is {expected_name.strip()}, {expected_strength.strip()}. Please check the package and take another photo.'}
        return {'status': 'Match', 'fields': fields, 'text': f'The visible label reads {name}, {strength}. It matches the configured name and strength.'}
    return {'status': 'Recognized', 'fields': fields, 'text': f'The visible label reads {name}, {strength}. No personal medication list was checked.'}

def check_medication_list(fields, medications, selected_time):
    from .bulk_medications import clean_time
    time = clean_time(selected_time)
    scheduled = [med for med in medications if med['time'] == time]
    if not scheduled:
        return {'status': 'Uncertain', 'fields': fields, 'text': f'No medication is listed for {time}. Please check the selected schedule time.'}
    name, strength = (fields['name'].strip(), fields['strength'].strip())
    same_label = [med for med in medications if normalized(med['name']) == normalized(name) and strength_key(med['strength']) == strength_key(strength)]
    matching = [med for med in same_label if med['time'] == time]
    if matching:
        med = matching[0]
        return {'status': 'Match', 'fields': fields, 'matched_medication': med, 'text': f"This is {name}, {strength}, which matches your {time} medication list. Your list says {med['dose']}."}
    same_name_now = [med for med in scheduled if normalized(med['name']) == normalized(name)]
    same_name_any = [med for med in medications if normalized(med['name']) == normalized(name)]
    if same_name_now:
        expected = ' or '.join(sorted({med['strength'] for med in same_name_now}))
        code = 'strength_mismatch'
        reason = f'Your list for {time} specifies {name}, {expected}, but this package is {strength}.'
    elif same_label:
        listed_times = ', '.join(sorted({med['time'] for med in same_label}))
        code = 'time_mismatch'
        reason = f'Your list schedules {name}, {strength} for {listed_times}, not {time}.'
    elif same_name_any:
        entries = '; '.join(sorted({f"{med['strength']} at {med['time']}" for med in same_name_any}))
        code = 'strength_and_time_mismatch'
        reason = f'Your list includes {name} at {entries}, but it does not list {strength} for {time}.'
    else:
        code = 'name_not_listed'
        reason = f'{name} is not on your saved medication list.'
    due = '; '.join(sorted({f"{med['name']}, {med['strength']}" for med in scheduled}))
    if not same_name_now:
        reason += f' For {time}, your list specifies {due}.'
    return {'status': 'Mismatch', 'fields': fields, 'mismatch_code': code, 'mismatch_reason': reason, 'expected_medications': scheduled, 'text': f'The label reads {name}, {strength}. {reason} Please check the package and take another photo. You can also ask me to explain the difference.'}
