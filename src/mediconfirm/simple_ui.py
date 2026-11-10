"""Browser camera/microphone, local Whisper and contextual HKBU dialogue."""
import base64
import io
import tempfile
from datetime import datetime
from uuid import uuid4
from pathlib import Path
import anywidget
import traitlets
from .integrations import HKBUClient
from .simple_service import identify_photo
from .dialogue import Dialogue
from .speech_tools import transcribe_recording, spoken_text
from .intake_store import record_intake, record_recovery, _moment, finish_interrupted_session
from .core import severe_demo_signal, confirmation_intent
from .plan_actions import process_plan, report_severe
from .drug_sources import DailyMedSource, is_use_question

class SimpleCameraApp(anywidget.AnyWidget):
    _esm = Path(__file__).with_name('simple_camera.mjs')
    _css = '.mc-simple {font:16px sans-serif; max-width:760px; padding:12px}\n    .mc-simple button {padding:12px 18px; margin:4px; font-size:17px; cursor:pointer}\n    .mc-simple button:disabled {cursor:default; opacity:.5}\n    .mc-simple audio {width:100%; max-width:640px}\n    .mc-simple .mc-message {padding:12px 16px;margin:10px 0;border-radius:12px;white-space:pre-wrap;line-height:1.5}\n    .mc-simple .mc-user {background:#e6eff9;color:#172b43;margin-left:36px}\n    .mc-simple .mc-assistant {background:#f2f3f5;color:#202428;margin-right:36px}'
    simulation_request = traitlets.Dict(default_value={}).tag(sync=True)
    simulation_text = traitlets.Unicode('Start a new demo with a separate log, then advance simulated time.').tag(sync=True)
    notification_text = traitlets.Unicode('No family notifications yet.').tag(sync=True)
    reminder_text = traitlets.Unicode('').tag(sync=True)
    schedule_request = traitlets.Dict(default_value={}).tag(sync=True)
    schedule_text = traitlets.Unicode('').tag(sync=True)
    playback_request = traitlets.Dict(default_value={}).tag(sync=True)
    request = traitlets.Dict(default_value={}).tag(sync=True)
    busy = traitlets.Bool(False).tag(sync=True)
    result_text = traitlets.Unicode('').tag(sync=True)
    audio_data = traitlets.Unicode('').tag(sync=True)
    audio_note = traitlets.Unicode('').tag(sync=True)
    speech_request = traitlets.Dict(default_value={}).tag(sync=True)
    chat_request = traitlets.Dict(default_value={}).tag(sync=True)
    reset_request = traitlets.Int(0).tag(sync=True)
    draft_text = traitlets.Unicode('').tag(sync=True)
    speech_status = traitlets.Unicode('').tag(sync=True)
    dialogue_messages = traitlets.List(default_value=[]).tag(sync=True)
    chat_status = traitlets.Unicode('').tag(sync=True)
    flow_page = traitlets.Unicode('home').tag(sync=True)
    flow_request = traitlets.Dict(default_value={}).tag(sync=True)
    confirm_request = traitlets.Dict(default_value={}).tag(sync=True)
    confirmation_ready = traitlets.Bool(False).tag(sync=True)
    confirmation_status = traitlets.Unicode('').tag(sync=True)
    verification_id = traitlets.Unicode('').tag(sync=True)
    completion_text = traitlets.Unicode('').tag(sync=True)
    help_text = traitlets.Unicode('').tag(sync=True)
    package_context = traitlets.Unicode('No package has been checked yet. Take a photo to ask about the package.').tag(sync=True)
    has_current_photo = traitlets.Bool(False).tag(sync=True)
    photo_clear_request = traitlets.Dict(default_value={}).tag(sync=True)
    replay_request = traitlets.Int(0).tag(sync=True)
    cancel_ack = traitlets.Int(0).tag(sync=True)
    flow_notice = traitlets.Unicode('').tag(sync=True)
    can_replay = traitlets.Bool(False).tag(sync=True)
    use_request = traitlets.Int(0).tag(sync=True)
    source_status = traitlets.Unicode('').tag(sync=True)
    source_links = traitlets.List(default_value=[]).tag(sync=True)

    def __init__(self, api_key, model='gpt-4.1', api_version='2025-04-01-preview', expected_name='', expected_strength='', voice=True, medications=None, selected_time='', log_path=None, confirmation_timeout_seconds=600, **kwargs):
        self.client = HKBUClient(api_key, model, api_version)
        self.expected_name = expected_name
        self.expected_strength = expected_strength
        self.voice = voice
        self.medications = medications
        self.selected_time = selected_time
        import math
        if not math.isfinite(float(confirmation_timeout_seconds)) or float(confirmation_timeout_seconds) <= 0:
            raise ValueError('Confirmation timeout must be positive seconds.')
        self.confirmation_timeout_seconds = float(confirmation_timeout_seconds)
        self.confirmation_repeat_seconds = None
        self._processing = False
        self.last_result = None
        self.dialogue = Dialogue()
        self.log_path = Path(log_path) if log_path is not None else None
        self._blocked = False
        self._notification_session = uuid4().hex
        self._normal_log_path = self.log_path
        self._simulation = False
        self._normal_confirmation_timeout_seconds = self.confirmation_timeout_seconds
        self._verification_token = ''
        self._verification_date = None
        self._photo_date = None
        self._last_spoken_text = ''
        self.drug_source = DailyMedSource()
        self._drug_information = None
        super().__init__(**kwargs)
        self.dialogue_messages = list(self.dialogue.messages)
        self.observe(self._on_photo, names='request')
        self.observe(self._on_speech, names='speech_request')
        self.observe(self._on_chat, names='chat_request')
        self.observe(self._on_reset, names='reset_request')
        self.observe(self._on_flow, names='flow_request')
        self.observe(self._on_confirm, names='confirm_request')
        self.observe(self._on_photo_clear, names='photo_clear_request')
        self.observe(self._on_replay, names='replay_request')
        self.observe(self._on_use, names='use_request')
        self.observe(self._on_schedule, names='schedule_request')
        self.observe(self._on_simulation, names='simulation_request')
        self.observe(self._on_playback, names='playback_request')
        self._refresh_schedule()

    def _refresh_schedule(self, start=False, advance_minutes=0):
        if self.log_path is None:
            self.schedule_text = 'The intake log path has not been configured.'
            return
        try:
            events, notices, reminders = process_plan(self.log_path, self.medications, self.selected_time, self.confirmation_timeout_seconds, start=start, advance_minutes=advance_minutes, repeat_seconds=self.confirmation_repeat_seconds)
            self._show_notifications(notices)
            if reminders:
                self.reminder_text = '\n'.join(reminders)
                self._speak(' '.join(reminders))
            today = _moment(None).date().isoformat()
            active = sorted((e for e in events if e.get('date') == today), key=lambda e: (e['scheduled_time'], e['name']))
            if any((e.get('interrupted') and e.get('scheduled_time') == self.selected_time for e in active)):
                self._blocked = True
                self._invalidate_verification()
                self.flow_page = 'help'
                self.help_text = 'This event was paused after a severe-symptom report and cannot be confirmed. Please seek medical assistance. Close the current help session to return to your plan.'
            reasons = {'awaiting_confirmation': 'Awaiting confirmation', 'user_reported_not_taken': 'User reported not yet taken', 'user_confirmed_taken': 'User explicitly confirmed intake', 'confirmation_timeout': 'Confirmation deadline passed without a response', 'preset_severe_discomfort_report': 'Preset severe-symptom report; routine flow paused'}
            if self.last_result and self.last_result.get('matched_medication'):
                med = self.last_result['matched_medication']
                current = next((e for e in active if e['scheduled_time'] == self.selected_time and e['name'] == med['name'] and (e['strength'] == med['strength'])), None)
                if current:
                    self.last_result['intake_record'] = {k: current.get(k) for k in ('status', 'confirmed_at', 'updated_at', 'self_report_only', 'reason')}
                    self._refresh_package_context()
            lines = [f'Confirmation window: {self.confirmation_timeout_seconds / 60:g} minutes from the first check started for this schedule.']
            for e in active:
                lines.append(f"{e['scheduled_time']} | {e['name']} {e['strength']} | {e['status']}\nReason: {reasons.get(e.get('reason'), e.get('reason', 'Previous record'))}; updated: {e['updated_at']}")
                if e.get('last_error'):
                    lines.append(f"Latest recovery event: {e['last_error']['reason']} ({e['last_error']['at']})")
            if not active:
                lines.append('No events have been started today. Start a medication check to create Pending events.')
            lines.append('Unconfirmed means no confirmation was received; it does not establish a missed dose. While this page or kernel is closed, no background checks run. Reopening reconciles saved deadlines.')
            self.schedule_text = '\n'.join(lines)
            return True
        except Exception:
            self.schedule_text = 'The intake log could not be read or written. Check the file and permissions, then refresh. Existing records were not replaced.'
            return False

    def _show_notifications(self, notices):
        self.notification_text = '\n\n'.join((('EMAIL SUBMITTED\n' if n.get('sent') else 'EMAIL NOT SENT\n') + n['at'] + '\nTo: ' + n['recipient'] + '\nSubject: ' + n['type'] + '\n' + n['message'] for n in notices[-20:])) or 'No family notifications yet.'

    def _on_simulation(self, change):
        if not change['new'] or self._processing:
            return
        self._processing = True
        self.busy = True
        try:
            action = change['new'].get('action')
            if action in {'new_demo', 'normal_log'}:
                if self._normal_log_path is None:
                    raise ValueError('Configure a log path first.')
                self.send({'type': 'stop_camera'})
                self._invalidate_verification()
                self._blocked = False
                self.help_text = ''
                self.dialogue.reset()
                self.dialogue_messages = list(self.dialogue.messages)
                self._notification_session = uuid4().hex
                self._simulation = action == 'new_demo'
                self.confirmation_timeout_seconds = 600 if self._simulation else self._normal_confirmation_timeout_seconds
                self.log_path = self._normal_log_path.parent / 'demo_runs' / (self._notification_session + '.json') if self._simulation else self._normal_log_path
                self.flow_page = 'home'
                self.reminder_text = ''
                self.audio_data = ''
                self.simulation_text = 'A new demo is ready with a separate log. Start a reminder or medication check.' if self._simulation else 'Returned to the regular log.'
                self._refresh_schedule()
            elif action == 'remind':
                if self._blocked:
                    raise ValueError('This session was paused after a severe-symptom report. The routine check cannot continue.')
                if self._refresh_schedule(start=True) and (not self._blocked):
                    self.flow_page = 'check'
            elif action == 'advance':
                if not self._simulation:
                    raise ValueError('Start a new demo first to keep the regular log unchanged.')
                if self._blocked:
                    raise ValueError('This severe-symptom demo is paused. Routine reminders are stopped.')
                if not self.log_path.exists():
                    raise ValueError('Start a reminder or medication check before advancing simulated time.')
                if self._refresh_schedule(advance_minutes=5):
                    self.simulation_text = 'Advanced the selected schedule by 5 simulated minutes. Status and notifications have been refreshed.'
        except Exception as exc:
            self.simulation_text = str(exc)
        finally:
            self.busy = False
            self._processing = False

    def _on_schedule(self, change):
        if change['new'] and (not self._processing):
            self._refresh_schedule()

    def _recovery(self, reason):
        if self.log_path is None:
            return
        try:
            record_recovery(self.log_path, self.selected_time, reason)
        except Exception:
            self.flow_notice = 'The recovery event could not be saved. Check the log path. No Taken record was created.'

    def _on_playback(self, change):
        if change['new'].get('kind') == 'error':
            self.audio_note = 'Audio playback failed. The text is still available. Select Replay to regenerate the audio, or read the text.'
            self._recovery('audio_playback_failed')

    def set_check_time(self, selected_time):
        self.selected_time = selected_time
        self.verification_medication_id = None
        self._invalidate_verification()
        self.result_text = f'Selected {selected_time} medication list. Please take a new photo to verify the package.'
        self.audio_data = ''
        self.audio_note = ''
        if self.flow_page == 'done':
            self.completion_text = ''
            self.flow_page = 'home'

    def _invalidate_verification(self):
        self.last_result = None
        self.confirmation_ready = False
        self.confirmation_status = ''
        self.verification_id = ''
        self._verification_token = ''
        self._verification_date = None
        self._photo_date = None
        self.has_current_photo = False
        self.package_context = 'No package has been checked yet. Take a photo to ask about the package.'
        self._drug_information = None
        self.source_links = []
        self.source_status = ''
        self._last_spoken_text = ''
        self.can_replay = False

    def _on_photo_clear(self, change):
        if change['new'] and (not self._processing):
            self._invalidate_verification()
            self.result_text = 'Ready for a new photo. Capture the package before checking or asking about it.'

    def _refresh_package_context(self):
        if not self.last_result:
            return
        fields = self.last_result.get('fields', {})
        status = self.last_result.get('status')
        labels = {'Match': 'Matches the medication list', 'Mismatch': 'Does not match the medication list', 'Uncertain': 'Unable to confirm', 'Recognized': 'Label read only'}
        lines = [f"Current package: {fields.get('name') or 'Name unreadable'}", f"Strength: {fields.get('strength') or 'Unreadable'}", f'Schedule time: {self.selected_time}', f'Verification result: {labels.get(status, status)}']
        med = self.last_result.get('matched_medication')
        if med:
            lines.append(f"Dose recorded on your list: {med['dose']}")
        record = self.last_result.get('intake_record')
        if record:
            lines.append(f"Self-reported status: {record['status']} (not swallowing verification)")
        self.package_context = '\n'.join(lines)
        self.has_current_photo = True

    def _on_flow(self, change):
        if not change['new'] or self._processing:
            return
        action = change['new'].get('action')
        self.send({'type': 'stop_camera'})
        self.audio_data = ''
        if action == 'cancel':
            already_saved = self.flow_page == 'done'
            self._recovery('user_cancelled')
            self._invalidate_verification()
            self.flow_notice = 'This session has been cancelled. The camera and microphone are off. ' + ('Previously saved self-reports have been kept.' if already_saved else 'Cancelling does not create a Taken record.')
            self.flow_page = 'help' if self._blocked else 'home'
            self.draft_text = ''
            self.speech_status = ''
            self.chat_status = ''
            self.busy = False
            self.cancel_ack += 1
            return
        self.flow_notice = ''
        if action == 'end':
            if self.log_path is not None:
                finish_interrupted_session(self.log_path, self.selected_time)
            self._blocked = False
            self.dialogue.reset()
            self.dialogue_messages = list(self.dialogue.messages)
            self._invalidate_verification()
            self.flow_page = 'home'
            self.help_text = ''
            return
        if self._blocked:
            self.flow_page = 'help'
            return
        if action == 'resume':
            if self.last_result and self._photo_date == _moment(None).date().isoformat():
                record = self.last_result.get('intake_record', {})
                self.flow_page = 'done' if record.get('status') == 'Taken' else 'check'
                return
            action = 'check'
        if action == 'check':
            self._refresh_schedule(start=True)
            if self._blocked:
                return
            self._invalidate_verification()
            self.result_text = 'Take a photo of one package to check it against the selected schedule.'
            self.flow_page = 'check'
        elif action in {'chat', 'ask-current'}:
            if self._photo_date and self._photo_date != _moment(None).date().isoformat():
                self._invalidate_verification()
            self.flow_page = 'chat'
            self.chat_status = 'The current package is available in this conversation. You can ask about its result, strength, or recorded schedule.' if self.last_result else 'You can talk about how you feel. To ask about a package in your hand, take a photo first.'
        elif action == 'home':
            self.flow_page = 'home'

    def _interrupt_for_report(self, text):
        self._blocked = True
        self._invalidate_verification()
        self.help_text = 'The routine medication check is paused. Please seek urgent medical help. If symptoms are severe or ongoing, contact your local emergency medical service. This assistant cannot determine the cause.'
        if self.log_path is not None:
            try:
                notices, _ = report_severe(self.log_path, self.selected_time, text, self._notification_session)
                self._show_notifications(notices)
                self.help_text += ' A family notification has been recorded. Check its delivery status in Me.'
                self._refresh_schedule()
            except Exception:
                self.help_text += ' The notification could not be saved. Please contact someone directly for help.'
        self.dialogue.health_reports.append(text)
        self.dialogue.add('user', text)
        self.dialogue.add('assistant', 'I am sorry you are feeling unwell. I have paused the medication check. Please seek urgent medical help. If symptoms are severe or ongoing, contact your local emergency medical service.')
        self.dialogue_messages = list(self.dialogue.messages)
        self.send({'type': 'stop_camera'})
        self.flow_page = 'help'
        self._speak(self.dialogue.messages[-1]['content'])

    def _on_confirm(self, change):
        if not change['new'] or self._processing:
            return
        self._processing = True
        self.busy = True
        try:
            payload = change['new']
            report = payload.get('text', '').strip() if isinstance(payload.get('text', ''), str) else ''
            if report and severe_demo_signal(report):
                self._interrupt_for_report(report)
                return
            if self._blocked or self.flow_page != 'check' or (not self.confirmation_ready) or (not self.last_result) or (self.last_result.get('status') != 'Match') or (not self._verification_token) or (payload.get('verification_id') != self._verification_token):
                raise ValueError('Verify the current package before confirming. A previous result cannot confirm a new photo.')
            if self._verification_date != _moment(None).date().isoformat():
                raise ValueError('The date has changed. Please take a new photo to verify the package.')
            medication = self.last_result.get('matched_medication')
            if not medication or medication.get('time') != self.selected_time or (not any((all((row.get(k) == medication.get(k) for k in ('name', 'strength', 'time', 'dose'))) for row in self.medications or []))):
                raise ValueError('The medication list or schedule has changed. Please verify the package again.')
            if self.log_path is None:
                raise ValueError('No intake log path is configured. Nothing was saved.')
            status = payload.get('status')
            source = 'button'
            if 'text' in payload:
                intent = confirmation_intent(report)
                if intent == 'unclear':
                    self.confirmation_status = 'Not saved: this statement does not clearly confirm taken or not yet taken. Edit the text or use the buttons above.'
                    return
                status = 'Taken' if intent == 'taken' else 'Pending'
                source = 'reviewed_text'
            event, created = record_intake(self.log_path, medication, self.selected_time, status, source=source, timeout_seconds=self.confirmation_timeout_seconds, repeat_seconds=self.confirmation_repeat_seconds)
            self._refresh_schedule()
            self.last_result['intake_record'] = {key: event.get(key) for key in ('status', 'confirmed_at', 'updated_at', 'self_report_only')}
            self._refresh_package_context()
            if event['status'] == 'Taken':
                self.confirmation_ready = False
                self.completion_text = ('Your intake self-report has been saved.' if created else 'This event is already recorded as Taken. No duplicate was saved.') + f"\n{event['name']} · {event['strength']} · Scheduled time {event['scheduled_time']}" + f"\nConfirmed at: {event['confirmed_at']}\nThis is a self-report, not verification of swallowing."
                self.flow_page = 'done'
                self._speak('Your self-reported intake is saved. No duplicate record has been created.')
            else:
                self.confirmation_status = 'Recorded as not yet taken (Pending). You can confirm later while this check remains valid. This is not a request to take an extra dose.'
                self._speak('You report that you have not taken it yet. No Taken record has been created.')
        except Exception as exc:
            self.confirmation_status = 'Confirmation not saved: ' + str(exc)
        finally:
            self.busy = False
            self._processing = False

    def _speak(self, text):
        text = spoken_text(text)
        self._last_spoken_text = text
        self.can_replay = bool(text)
        self.audio_data = ''
        self.audio_note = ''
        try:
            if self.voice and text:
                from gtts import gTTS
                audio = io.BytesIO()
                gTTS(text=text, lang='en', timeout=15).write_to_fp(audio)
                self.audio_data = base64.b64encode(audio.getvalue()).decode('ascii')
        except Exception:
            self.audio_note = 'Speech could not be generated. The text is still available. Select Replay to retry, or read the text.'
            self._recovery('tts_generation_failed')

    def _on_replay(self, change):
        if self._processing:
            return
        if not self._last_spoken_text:
            self.busy = False
            return
        self._processing = True
        self.busy = True
        try:
            self._speak(self._last_spoken_text)
        finally:
            self.busy = False
            self._processing = False

    def _on_use(self, change):
        if self._processing:
            return
        self._on_chat({'new': {'text': 'What is this medication generally used for?'}})

    def _lookup_general_uses(self):
        if self._drug_information and self._drug_information.get('status') == 'found':
            return self._drug_information
        self.source_status = 'Looking up general uses on DailyMed. Only the recognized drug name is sent, not your health report.'
        fields = (self.last_result or {}).get('fields', {})
        info = self.drug_source.lookup(fields)
        info['recognized_fields'] = {k: fields.get(k) for k in ('name', 'strength', 'dosage_form')}
        self._drug_information = info
        self.source_links = []
        if info.get('status') == 'found':
            self.source_links = [{'title': info['source_title'], 'url': info['url'], 'date': info.get('published_date', '')}]
            self.source_status = ('Verified general-use source ready. ' + ('Stored official label, retrieved ' + info['retrieved_on'] + '. ' if info.get('retrieved_on') else '') + (info.get('form_note', 'Name, strength and dosage form matched. ')) + 'General uses only; not a personal prescribing reason.')
        else:
            self.source_status = 'No usable source was verified: ' + info.get('message', 'Please try again later.') + f" Recognized fields: name={fields.get('name')}, strength={fields.get('strength')}, form={fields.get('dosage_form')}."
        return info

    def _on_speech(self, change):
        if not change['new'] or self._processing:
            return
        self._processing = True
        self.busy = True
        self.speech_status = 'Whisper is transcribing English. The model may need to download on first use; please wait.'
        self.draft_text = ''
        try:
            text = transcribe_recording(change['new'].get('audio', ''))
            self.draft_text = text
            if not text:
                self._recovery('asr_unclear')
            self.speech_status = 'Transcription ready. Check or edit the text before submitting.' if text else 'The recording was unclear. Record again or type your message.'
        except Exception as exc:
            self._recovery('asr_failed')
            self.speech_status = 'Transcription could not be completed. Record again or type, then review the text before submitting.'
        finally:
            self.speech_request = {}
            self.busy = False
            self._processing = False

    def _on_chat(self, change):
        if not change['new'] or self._processing:
            return
        self._processing = True
        self.busy = True
        payload = change['new']
        self.chat_status = 'Preparing a reply...'
        try:
            text = payload.get('text', '').strip()
            if self._blocked:
                self.flow_page = 'help'
                return
            if severe_demo_signal(text):
                self._interrupt_for_report(text)
                return
            if is_use_question(text):
                self._lookup_general_uses()
            reply = self.dialogue.answer(self.client, text, 'conversation', self.medications, self.selected_time, self.last_result, drug_information=self._drug_information)
            self.dialogue_messages = list(self.dialogue.messages)
            self.chat_status = 'Reply ready. You can continue the conversation.'
            self._speak(reply)
        except Exception as exc:
            self.dialogue_messages = list(self.dialogue.messages)
            self._recovery('chat_api_failed')
            self.draft_text = payload.get('text', '')
            self.chat_status = 'The reply could not be completed: ' + str(exc) + ' Please retry. No simulated answer was substituted.'
        finally:
            self.busy = False
            self._processing = False

    def _on_reset(self, change):
        if self._processing:
            return
        self.dialogue.reset()
        self.dialogue_messages = list(self.dialogue.messages)
        self.draft_text = ''
        self.audio_data = ''
        self._last_spoken_text = ''
        self.can_replay = False
        self.speech_status = ''
        self.chat_status = 'The conversation and health context have been cleared. Your list and photo verification are unchanged.'

    def _on_photo(self, change):
        payload = change['new']
        if not payload or self._processing:
            return
        self._processing = True
        self.busy = True
        self._invalidate_verification()
        self.audio_data = ''
        self.audio_note = ''
        text = ''
        try:
            if self._blocked or self.flow_page != 'check':
                raise ValueError('Select Start medication check first. Routine confirmation is unavailable after a severe-symptom interruption.')
            encoded = payload.get('image', '')
            if not isinstance(encoded, str) or not encoded.startswith('data:image/jpeg;base64,'):
                raise ValueError('Invalid JPEG input. Please retake the photo.')
            if len(encoded) > 12000000:
                raise ValueError('Photo is too large. Please retake it.')
            data = base64.b64decode(encoded.split(',', 1)[1], validate=True)
            with tempfile.TemporaryDirectory(prefix='mediconfirm_photo_') as tmp:
                path = Path(tmp) / 'photo.jpg'
                path.write_bytes(data)
                result = identify_photo(path, self.client, self.expected_name, self.expected_strength, medications=[m for m in self.medications if m.get('medication_id') == self.verification_medication_id] if getattr(self, 'verification_medication_id', None) else self.medications, selected_time=self.selected_time)
            self.last_result = result
            if result['status'] in {'Uncertain', 'Mismatch'}:
                self._recovery('photo_unreadable' if result['status'] == 'Uncertain' else 'package_mismatch')
            self._photo_date = _moment(None).date().isoformat()
            self._refresh_package_context()
            labels = {'Recognized': 'Label recognized', 'Match': 'Package matches', 'Mismatch': 'Does not match the selected schedule', 'Uncertain': 'Unable to confirm; check the label or retake the photo'}
            text = result['text']
            if result['status'] == 'Match' and result.get('matched_medication'):
                self._verification_token = uuid4().hex
                self.verification_id = self._verification_token
                self._verification_date = _moment(None).date().isoformat()
                self.confirmation_ready = True
                text += ' Have you taken it yet?'
            self.result_text = labels[result['status']] + '\n' + text
            self.dialogue.add('assistant', 'Photo verification: ' + text)
            self.dialogue_messages = list(self.dialogue.messages)
        except Exception as exc:
            self._recovery('photo_or_api_failed')
            self.result_text = 'Recognition could not be completed. Retry or take another photo. No Taken status was saved.\n' + str(exc)
            text = 'Recognition could not be completed. Please try again.'
        try:
            self._speak(text)
        finally:
            self.busy = False
            self._processing = False

    def close_camera(self):
        self.send({'type': 'stop_camera'})

    def close(self):
        self.close_camera()
        super().close()
