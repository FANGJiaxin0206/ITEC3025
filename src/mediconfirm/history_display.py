"""Human-readable labels; raw timestamps and reason codes stay in the JSON log."""
from datetime import datetime
from zoneinfo import ZoneInfo

REASONS = {
 'awaiting_confirmation': 'Waiting for your confirmation.',
 'user_confirmed_taken': 'You confirmed that you had taken this medication.',
 'user_reported_not_taken': 'You selected Not yet. Confirmation is still pending.',
 'confirmation_timeout': 'No confirmation was received before the time limit.',
 'preset_severe_discomfort_report': 'The check was paused after a serious-discomfort report.',
 'user_ended_interrupted_session': 'You ended the paused session. Intake remains unconfirmed.',
}

def readable_date(value):
    try:
        moment=datetime.fromisoformat(value)
        if moment.tzinfo:moment=moment.astimezone(ZoneInfo('Asia/Hong_Kong'))
        return moment.strftime('%d %b %Y, %I:%M %p').replace(', 0', ', ')
    except (ValueError,TypeError):
        return 'Time not recorded'


def display_event(event):
    return {**event,'display_updated':readable_date(event.get('updated_at')),
        'display_reason':REASONS.get(event.get('reason'),'The record was updated.'),
        'display_scheduled':readable_date(str(event.get('date',''))+'T'+str(event.get('scheduled_time',''))),
        'history':[{**item,'display_at':readable_date(item.get('at')),
          'display_reason':REASONS.get(item.get('reason'),'The record was updated.')} for item in event.get('history',[])]}
