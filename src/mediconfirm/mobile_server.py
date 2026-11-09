import base64
import io
import json
import os
import secrets
import threading
from pathlib import Path
from flask import Flask, jsonify, request, session, send_from_directory
from PIL import Image, ImageOps, UnidentifiedImageError
from .bulk_medications import load_saved_medications, save_medication_entries
from .simple_ui import SimpleCameraApp


class PhoneSession:
    def __init__(self, root, sid, config):
        self.folder = root / 'data' / 'mobile_runs' / sid
        self.medication_path = self.folder / 'medications.json'
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
        self.lock = threading.Lock()

    def state(self):
        attrs = ['flow_page','result_text','audio_data','audio_note','draft_text','speech_status',
                 'dialogue_messages','chat_status','confirmation_ready','confirmation_status',
                 'verification_id','completion_text','help_text','package_context','has_current_photo',
                 'flow_notice','can_replay','source_status','source_links','schedule_text',
                 'simulation_text','notification_text','reminder_text']
        result = {key:getattr(self.app,key) for key in attrs}
        result['selected_time'] = self.app.selected_time
        result['medications'] = self.app.medications or []
        result['times'] = sorted({m['time'] for m in self.app.medications or []})
        info = self.app._drug_information or {}
        result['source_excerpt'] = info.get('general_uses_text','')[:1600] if info.get('status') == 'found' else ''
        result['source_mode'] = info.get('source_mode','')
        return result


def create_app(root, access_token=None, config=None):
    root = Path(root).resolve()
    if config is None:
        path = root / 'config.local.json'
        config = json.loads(path.read_text()) if path.exists() else {}
        config['api_key'] = os.environ.get('HKBU_API_KEY',config.get('api_key','')).strip()
    if not config.get('api_key'):
        raise ValueError('Configure config.local.json before starting the phone interface.')
    token = access_token or secrets.token_urlsafe(24)
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=secrets.token_hex(32),MAX_CONTENT_LENGTH=12*1024*1024,
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
        sid=session.get('sid')
        if not sid:
            sid=secrets.token_hex(16);session['sid']=sid
        with sessions_lock:
            if sid not in sessions:
                if len(sessions)>=16:
                    raise ValueError('Too many phone sessions. Restart the local server.')
                sessions[sid]=PhoneSession(root,sid,config)
            return sessions[sid]

    @app.get('/')
    def home():
        if secrets.compare_digest(request.args.get('access',''),token):
            session['authorized']=True
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
            phone.app._on_schedule({'new':{'id':'phone-refresh'}})
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
            name=payload.get('action');a=phone.app
            if name=='flow':
                a._on_flow({'new':{'action':payload.get('value')}})
            elif name=='time':
                value=payload.get('value')
                if value not in {m['time'] for m in a.medications or []}:
                    raise ValueError('Choose a time from the medication list.')
                a.set_check_time(value)
            elif name=='chat':
                if a.flow_page!='help':a._on_flow({'new':{'action':'ask-current'}})
                a._on_chat({'new':{'text':payload.get('text','')}})
            elif name=='uses':
                a._on_use({'new':1})
            elif name=='confirm':
                report={'verification_id':payload.get('verification_id','')}
                if 'text' in payload:report['text']=payload['text']
                else:report['status']=payload.get('status')
                a._on_confirm({'new':report})
            elif name=='replay':a._on_replay({'new':1})
            elif name=='clear_chat':a._on_reset({'new':1})
            elif name=='simulation':a._on_simulation({'new':{'action':payload.get('value')}})
            elif name=='save_list':
                rows=save_medication_entries(payload.get('medications'),phone.medication_path)
                a.medications=rows;a.set_check_time(rows[0]['time'])
            else:raise ValueError('Unknown action.')
            return jsonify(phone.state())
        except (ValueError,TypeError,KeyError):
            return jsonify(error='The action could not be completed. Check your inputs and try again.'),400
        finally:phone.lock.release()

    @app.post('/api/photo')
    def photo():
        phone=current()
        if not phone.lock.acquire(blocking=False):return jsonify(error='Please wait for the current request.'),423
        try:
            upload=request.files.get('photo')
            if not upload:raise ValueError()
            with Image.open(upload.stream) as image:
                if image.width*image.height>30_000_000:raise ValueError()
                image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1600,1600))
                buf=io.BytesIO();image.save(buf,format='JPEG',quality=90)
            a=phone.app
            if a.flow_page!='check':a._on_flow({'new':{'action':'check'}})
            a._on_photo({'new':{'image':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}})
            return jsonify(phone.state())
        except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError):
            return jsonify(error='Please choose a readable JPEG or PNG photo and try again.'),400
        finally:phone.lock.release()

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

    app.extensions['mediconfirm_sessions']=sessions
    app.extensions['mediconfirm_access_token']=token
    return app
