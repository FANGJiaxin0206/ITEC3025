import base64
import io
import json
import os
import secrets
import threading
from datetime import timedelta
from pathlib import Path
from flask import Flask, jsonify, request, session, send_from_directory, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from .bulk_medications import load_saved_medications, save_medication_entries
from .simple_ui import SimpleCameraApp
from .core import atomic_json
from .intake_store import _moment, _load, _LOCK
from .plan_actions import process_plan
from .email_delivery import EmailDelivery, mail_config
from .evaluation_log import EvaluationLog
from .history_display import display_event
from .intake_store import _key
from .shared_storage import prepare_shared_storage
from .web_settings import DEFAULTS, validate_settings, attach_email_previews, read_history


class PhoneSession:
    def __init__(self, root, sid, config):
        self.folder = prepare_shared_storage(root)
        self.medication_path = self.folder / 'personal_medications.json'
        initial = self.medication_path if self.medication_path.exists() else root / 'data' / 'personal_medications.json'
        medications = load_saved_medications(initial)
        if not medications:
            template = root / 'evaluation' / 'demo_medications.json'
            if template.exists():
                medications = load_saved_medications(template)
        self.app = SimpleCameraApp(config['api_key'], model=config.get('model', 'gpt-4.1'),
            api_version=config.get('api_version', '2025-04-01-preview'), voice=True,
            medications=medications, selected_time=medications[0]['time'] if medications else '',
            log_path=self.folder / 'intake_records.json')
        self.delivery = EmailDelivery(root)
        self.evaluation = EvaluationLog(self.folder / 'evaluation_metrics.json')
        self.active_tasks = {}
        self.verification_tasks = {}
        self.autoplay_claimed = set()
        self.settings_path = self.folder / 'settings.json'
        self.settings = validate_settings(json.loads(self.settings_path.read_text()) if self.settings_path.exists() else DEFAULTS)
        self.app.confirmation_repeat_seconds = self.settings['repeat_seconds']
        self.app.confirmation_timeout_seconds = self.settings['timeout_seconds']
        self.app._normal_confirmation_timeout_seconds = self.settings['timeout_seconds']
        self.lock = threading.Lock()
        self.manual_time = False
        self.audio_clips = {}
        self.audio_scope = 'home'
        self.audio_target = 'reminder'
        original_speak = self.app._speak
        def speak_for_web(text):
            original_speak(text)
            scope, target = self.audio_scope, self.audio_target
            if self.app.flow_page == 'help' and scope != 'home':
                scope, target = 'check', 'help'
            elif scope == 'chat' and target == 'result' and self.app.dialogue.messages[-1]['role'] == 'assistant':
                target = self.app.dialogue.messages[-1].get('message_id', 'reply')
            elif scope == 'check' and self.app.flow_page == 'done':
                target = 'completion'
            key = scope + ':' + target
            self.audio_clips.pop(key, None)
            self.audio_clips[key] = dict(id=secrets.token_hex(12), scope=scope, target=target,
                text=self.app._last_spoken_text, data=self.app.audio_data, note=self.app.audio_note.replace('Select Replay', 'Select Listen'))
            while len(self.audio_clips) > 12:
                self.audio_clips.pop(next(iter(self.audio_clips)))
        self.app._speak = speak_for_web
        self.select_automatic_time()

    def clear_check_audio(self):
        for key in list(self.audio_clips):
            if key.startswith('check:'):
                self.audio_clips.pop(key)

    def select_automatic_time(self):
        if self.manual_time or self.app._simulation or self.app._blocked:
            return
        # Preserve a result awaiting user confirmation until a new photo is requested.
        if self.app.has_current_photo:
            return
        times = sorted({m['time'] for m in self.app.medications or []})
        if not times:
            return
        now = _moment(None).strftime('%H:%M')
        past = [t for t in times if t <= now]
        selected = past[-1] if past else times[0]
        if self.app.selected_time != selected:
            self.app.set_check_time(selected)

    def tick(self):
        a = self.app
        self.audio_scope, self.audio_target = 'home', 'reminder'
        rows = load_saved_medications(self.medication_path)
        if rows != (a.medications or []):
            a.medications = rows
            a._invalidate_verification()
            a.verification_medication_id = None
            self.manual_time = False
        if self.settings_path.exists():
            settings = validate_settings(json.loads(self.settings_path.read_text()))
            self.settings = settings
            a.confirmation_timeout_seconds = settings['timeout_seconds']
            a._normal_confirmation_timeout_seconds = settings['timeout_seconds']
            a.confirmation_repeat_seconds = settings['repeat_seconds']
        moment = _moment(None)
        self.select_automatic_time()
        if self.settings['reminders_enabled'] and not a._simulation and not a._blocked:
            due = moment.strftime('%H:%M')
            if due in {m['time'] for m in a.medications or []}:
                _, _, messages = process_plan(a.log_path, a.medications, due,
                    a.confirmation_timeout_seconds, start=True, now=moment, repeat_seconds=self.settings['repeat_seconds'])
                if messages:
                    a.reminder_text = '\n'.join(messages)
                    a._speak(' '.join(messages))
        a._refresh_schedule()
        self.delivery.process(a.log_path, self.settings)

    def save_settings(self, payload):
        settings = validate_settings(payload)
        atomic_json(self.settings_path, settings)
        self.settings = settings
        self.app.confirmation_repeat_seconds = settings['repeat_seconds']
        self.app.confirmation_timeout_seconds = settings['timeout_seconds']
        self.app._normal_confirmation_timeout_seconds = settings['timeout_seconds']


    def state(self):
        attrs = ['flow_page','result_text','audio_note','draft_text','speech_status',
                 'dialogue_messages','chat_status','confirmation_ready','confirmation_status',
                 'verification_id','completion_text','help_text','package_context','has_current_photo',
                 'flow_notice','can_replay','source_status','source_links','schedule_text',
                 'simulation_text','notification_text','reminder_text']
        result = {key:getattr(self.app,key) for key in attrs}
        events, notices = read_history(self.folder)
        result['history_records'] = [display_event(e) for e in events]
        result['family_notifications'] = notices
        result['mail_ready'] = mail_config(self.delivery.root) is not None
        result['settings'] = self.settings
        result['server_time'] = _moment(None).isoformat(timespec='seconds')
        result['simulation_active'] = False
        by_id = {e['event_id']: e for e in events}
        plan = []
        for med in self.app.medications or []:
            key, _ = _key(med, med['time'], _moment(None))
            event = by_id.get(key, {})
            plan.append({**med, 'event_id': key, 'status': event.get('status', 'Scheduled'), 'date': _moment(None).date().isoformat()})
        result['daily_plan'] = plan
        times = sorted({m['time'] for m in plan})
        now = _moment(None).strftime('%H:%M')
        past = [t for t in times if t <= now]
        result['current_plan_time'] = past[-1] if past else (times[0] if times else '')
        result['current_plan_kind'] = 'current' if past else 'upcoming'
        result['audio_clips'] = [{k:v for k,v in clip.items() if k != 'data'} for clip in self.audio_clips.values()]
        for clip in result['audio_clips']:
            clip['url'] = '/api/audio/' + clip['id']
        result['schedule_mode'] = 'selected_event' if self.manual_time else 'automatic'
        result['reminders_enabled'] = self.settings['reminders_enabled']
        result['verification_status'] = (self.app.last_result or {}).get('status', '')
        result['target_medication_id'] = getattr(self.app, 'verification_medication_id', None)
        result['selected_time'] = self.app.selected_time
        result['medications'] = self.app.medications or []
        result['times'] = sorted({m['time'] for m in self.app.medications or []})
        info = self.app._drug_information or {}
        result['source_excerpt'] = info.get('general_uses_text','')[:1600] if info.get('status') == 'found' else ''
        result['source_mode'] = info.get('source_mode','')
        return result


def create_app(root, access_token=None, config=None, start_scheduler=False):
    root = Path(root).resolve()
    if config is None:
        path = root / 'config.local.json'
        config = json.loads(path.read_text()) if path.exists() else {}
        config['api_key'] = os.environ.get('HKBU_API_KEY',config.get('api_key','')).strip()
    if not config.get('api_key'):
        raise ValueError('Configure config.local.json before starting the phone interface.')
    token = access_token or secrets.token_urlsafe(24)
    app = Flask(__name__, static_folder=None)
    secret_path = root / 'data' / 'web_session_secret.json'
    if not secret_path.exists():
        atomic_json(secret_path, {'secret': secrets.token_hex(32)})
    cookie_secret = json.loads(secret_path.read_text())['secret']
    app.config.update(SECRET_KEY=cookie_secret, PERMANENT_SESSION_LIFETIME=timedelta(days=30),MAX_CONTENT_LENGTH=12*1024*1024,
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict')
    sessions = {}
    sessions_lock = threading.Lock()
    speech_lock = threading.Lock()
    assets = Path(__file__).with_name('web')

    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob: data:; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
        return response

    @app.before_request
    def check_access():
        if request.path.startswith('/api/'):
            if not session.get('authorized'):
                return jsonify(error='Open the full access link printed on the computer.'),401
            origin=request.headers.get('Origin')
            if request.method=='POST' and origin and origin.rstrip('/')!=request.host_url.rstrip('/'):
                return jsonify(error='Cross-origin requests are not accepted.'),403

    def current():
        with sessions_lock:
            if 'local' not in sessions:
                sessions['local'] = PhoneSession(root, 'local', config)
            return sessions['local']

    @app.get('/')
    def home():
        if secrets.compare_digest(request.args.get('access',''),token):
            session['authorized']=True
            session.permanent=True
        if not session.get('authorized'):
            return 'Open the full access link shown on the computer.',401
        return send_from_directory(assets,'index.html')

    @app.get('/assets/<path:name>')
    def static(name):
        return send_from_directory(assets,name)

    @app.get('/api/state')
    def state():
        phone=current()
        if not phone.lock.acquire(blocking=False):
            return jsonify(error='A request is still in progress.'),423
        try:
            phone.tick()
            return jsonify(phone.state())
        finally:
            phone.lock.release()

    @app.post('/api/action')
    def action():
        phone=current()
        if not phone.lock.acquire(blocking=False):
            return jsonify(error='Please wait for the current request.'),423
        try:
            payload=request.get_json(silent=True) or {}
            phone.evaluation.clicks(payload.get('metrics'))
            name=payload.get('action');a=phone.app
            phone.audio_scope = 'chat' if name in {'chat','uses'} else 'check'
            phone.audio_target = 'confirmation' if name == 'confirm' else 'result'
            if name=='read_plan':
                plan = phone.state()
                time = plan['current_plan_time']
                current_meds = [m for m in plan['daily_plan'] if m['time'] == time]
                if not current_meds:
                    raise ValueError('There are no saved medications to read.')
                lines = [f"Your saved plan for {time} lists:"]
                for med in current_meds:
                    lines.append(f"{med['name']}, {med['strength']}, {med['dose']}." + (' Your record says you have taken it.' if med['status']=='Taken' else ''))
                lines.append('Your check is paused. Please follow the help message.' if a._blocked else 'Choose Check medication to check a package from this plan.')
                phone.audio_scope, phone.audio_target = 'home', 'plan:' + time
                a._speak(' '.join(lines))
            elif name=='replay_clip':
                clip = next((c for c in phone.audio_clips.values() if c['id'] == payload.get('clip_id')), None)
                if not clip:
                    raise ValueError('This response is no longer available.')
                phone.audio_scope, phone.audio_target = clip['scope'], clip['target']
                a._speak(clip['text'])
            elif name=='flow':
                a._on_flow({'new':{'action':payload.get('value')}})
                if payload.get('value')=='cancel':
                    metrics=payload.get('metrics') or {}
                    phone.evaluation.finish(metrics.get('task_id'),'cancelled',metrics.get('client_elapsed_ms'))
            elif name=='time':
                value=payload.get('value')
                if value not in {m['time'] for m in a.medications or []}:
                    raise ValueError('Choose a time from the medication list.')
                phone.manual_time = True
                a.set_check_time(value)
            elif name=='select_event':
                previous_metrics=payload.get('metrics') or {}
                phone.evaluation.finish(previous_metrics.get('task_id'),'cancelled',previous_metrics.get('client_elapsed_ms'))
                phone.clear_check_audio()
                selected = next((m for m in a.medications or [] if _key(m, m['time'], _moment(None))[0] == payload.get('event_id')), None)
                if selected is None:
                    raise ValueError('This event is no longer on today’s medication list.')
                phone.manual_time = True
                a.set_check_time(selected['time'])
                a.verification_medication_id = selected['medication_id']
                a._on_flow({'new': {'action': 'check'}})
            elif name=='automatic_time':
                phone.manual_time = False
                a._on_photo_clear({'new': 1})
                phone.select_automatic_time()
            elif name=='prepare_photo':
                phone.clear_check_audio()
                a._on_photo_clear({'new': 1})
                phone.select_automatic_time()
            elif name=='playback_error':
                a._on_playback({'new': {'kind': 'error'}})
            elif name=='chat':
                if a.flow_page!='help':a._on_flow({'new':{'action':'ask-current'}})
                a._on_chat({'new':{'text':payload.get('text','')}})
            elif name=='uses':
                a._on_use({'new':1})
            elif name=='retry_email':
                phone.delivery.retry(a.log_path,payload.get('notification_id'),phone.settings)
            elif name=='send_test_email':
                if not phone.settings.get('real_email_enabled') or not mail_config(root) or not phone.settings.get('caregiver_email'):
                    raise ValueError('Configure and enable real email first.')
                with _LOCK:
                    store=_load(a.log_path)
                    key='test:'+secrets.token_hex(12)
                    store.setdefault('simulated_notifications',{})[key]={'notification_id':key,'requires_delivery':True,'type':'test','at':_moment(None).isoformat(),'sent':False,'message':'This is a MediConfirm email connection test. No health event is being reported.'}
                    atomic_json(a.log_path,store)
            elif name=='confirm':
                report={'verification_id':payload.get('verification_id','')}
                if 'text' in payload:report['text']=payload['text']
                else:report['status']=payload.get('status')
                confirmation_moment=_moment(None)
                previous_flow=a.flow_page
                verification_owner=phone.verification_tasks.get(report['verification_id'])
                a._on_confirm({'new':report})
                if a.flow_page=='done' and previous_flow!='done':
                    metrics=payload.get('metrics') or {}
                    task=metrics.get('task_id')
                    client=payload.get('client_id','')
                    if task and phone.active_tasks.get(client)==task and verification_owner==(client,task):
                        phone.evaluation.finish(task,'completed',metrics.get('client_elapsed_ms'),now=confirmation_moment)
                        phone.active_tasks.pop(client,None)
            elif name=='replay':a._on_replay({'new':1})
            elif name=='clear_chat':
                a._on_reset({'new':1})
                for key in list(phone.audio_clips):
                    if key.startswith('chat:'):phone.audio_clips.pop(key)
            elif name=='settings':
                phone.save_settings(payload.get('settings'))
            elif name=='start_reminder':
                a._on_simulation({'new':{'action':'remind'}})
            elif name=='save_list':
                rows=save_medication_entries(payload.get('medications'),phone.medication_path)
                a.medications=rows;a.set_check_time(rows[0]['time'])
                phone.select_automatic_time()
            else:raise ValueError('Unknown action.')
            phone.tick()
            return jsonify(phone.state())
        except (ValueError,TypeError,KeyError):
            return jsonify(error='The action could not be completed. Check your inputs and try again.'),400
        finally:phone.lock.release()

    @app.post('/api/photo')
    def photo():
        phone=current()
        if not phone.lock.acquire(blocking=False):return jsonify(error='Please wait for the current request.'),423
        task_id=None
        try:
            med=next((m for m in phone.app.medications or [] if m.get('medication_id')==getattr(phone.app,'verification_medication_id',None)),None)
            event_id=_key(med,med['time'],_moment(None))[0] if med else None
            task_id=phone.evaluation.photo(request.form.get('task_id'),event_id)
            if task_id:phone.active_tasks[request.form.get('client_id','')]=task_id
            phone.clear_check_audio()
            phone.audio_scope, phone.audio_target = 'check', 'result'
            a=phone.app
            a._on_photo_clear({'new': 1})
            phone.select_automatic_time()
            upload=request.files.get('photo')
            if not upload:raise ValueError()
            with Image.open(upload.stream) as image:
                if image.width*image.height>30_000_000:raise ValueError()
                image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1600,1600))
                buf=io.BytesIO();image.save(buf,format='JPEG',quality=90)
            a=phone.app
            if a.flow_page!='check':a._on_flow({'new':{'action':'check'}})
            a._on_photo({'new':{'image':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}})
            if task_id:
                phone.evaluation.result(task_id,(a.last_result or {}).get('status','Error'))
                if a.verification_id:phone.verification_tasks[a.verification_id]=(request.form.get('client_id',''),task_id)
            phone.tick()
            return jsonify(phone.state())
        except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError):
            if task_id:phone.evaluation.result(task_id,'Error')
            a._invalidate_verification()
            a.result_text = 'Unable to read this photo. Please retake it or choose another image.'
            return jsonify(error='Please choose a readable JPEG or PNG photo and try again.'),400
        finally:phone.lock.release()

    @app.post('/api/audio/claim')
    def claim_audio():
        phone=current();payload=request.get_json(silent=True) or {};clip_id=payload.get('clip_id')
        with phone.lock:
            valid=any(c['id']==clip_id for c in phone.audio_clips.values())
            allowed=valid and clip_id not in phone.autoplay_claimed
            if allowed:phone.autoplay_claimed.add(clip_id)
            return jsonify(allowed=allowed)

    @app.post('/api/metrics')
    def metrics():
        phone=current();phone.evaluation.clicks(request.get_json(silent=True) or {})
        return jsonify(saved=True)

    @app.get('/api/evaluation.csv')
    def evaluation_csv():
        return Response(current().evaluation.csv(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=mediconfirm-evaluation.csv'})

    @app.get('/api/audio/<clip_id>')
    def audio(clip_id):
        phone=current()
        with phone.lock:
            clip=next((c for c in phone.audio_clips.values() if c['id']==clip_id),None)
            if not clip or not clip['data']:
                return jsonify(error='Audio is unavailable. Select Listen to retry.'),404
            return Response(base64.b64decode(clip['data']),mimetype='audio/mpeg')

    @app.post('/api/speech')
    def speech():
        phone=current()
        if not phone.lock.acquire(blocking=False):return jsonify(error='Please wait for the current request.'),423
        try:
            upload=request.files.get('audio')
            if not upload:return jsonify(error='Choose an audio recording first.'),400
            data=upload.read(10_000_001)
            if len(data)>10_000_000:return jsonify(error='The recording is too large. Use a short clip.'),400
            mime=upload.mimetype if upload.mimetype.startswith('audio/') else 'audio/mp4'
            with speech_lock:
                phone.app._on_speech({'new':{'audio':f'data:{mime};base64,'+base64.b64encode(data).decode()}})
            return jsonify(phone.state())
        finally:phone.lock.release()

    @app.errorhandler(413)
    def too_large(error):return jsonify(error='File too large. Please use a smaller photo or shorter recording.'),413

    stop_event = threading.Event()
    def scheduler():
        while not stop_event.wait(1):
            with sessions_lock:
                active = list(sessions.values())
            for phone in active:
                if not phone.lock.acquire(blocking=False):
                    continue
                try:
                    phone.tick()
                except Exception:
                    phone.app.flow_notice = 'A reminder could not be updated. Check History and retry.'
                finally:
                    phone.lock.release()
    if start_scheduler:
        threading.Thread(target=scheduler, daemon=True, name='mediconfirm-reminders').start()
    app.extensions['mediconfirm_scheduler_stop'] = stop_event
    app.extensions['mediconfirm_sessions']=sessions
    app.extensions['mediconfirm_access_token']=token
    return app
