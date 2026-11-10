"""Browser recording -> temporary audio -> 16 kHz array -> local Whisper English ASR."""
import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from .text_format import readable_english
_model = None

def decode_recording(data_url):
    import numpy as np
    if not isinstance(data_url, str) or len(data_url) > 12000000 or ',' not in data_url:
        raise ValueError('Invalid recording. Please record again.')
    header, encoded = data_url.split(',', 1)
    if not header.startswith('data:audio/') or ';base64' not in header:
        raise ValueError('Unsupported recording format. Please try another recording.')
    data = base64.b64decode(encoded, validate=True)
    if not data:
        raise ValueError('The recording is empty. Please record again.')
    executable = shutil.which('ffmpeg')
    if not executable:
        try:
            import imageio_ffmpeg
            executable = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            raise RuntimeError('Audio decoder missing. Run the Notebook installation cell to install imageio-ffmpeg.') from None
    with tempfile.TemporaryDirectory(prefix='mediconfirm_recording_') as tmp:
        path = Path(tmp) / 'recording.audio'
        path.write_bytes(data)
        try:
            decoded = subprocess.run([executable, '-nostdin', '-v', 'error', '-i', str(path), '-t', '12', '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '16000', 'pipe:1'], capture_output=True, timeout=25, check=True)
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError('Recording could not be decoded. Please record again or type your message.') from None
    if not decoded.stdout or len(decoded.stdout) % 2:
        raise ValueError('No usable audio. Please record again.')
    return np.frombuffer(decoded.stdout, dtype='<i2').astype(np.float32) / 32768.0

def transcribe_recording(data_url):
    global _model
    import numpy as np
    samples = decode_recording(data_url)
    if len(samples) < 1600 or not np.isfinite(samples).all() or np.sqrt(np.mean(samples ** 2)) < 0.002:
        return ''
    try:
        import whisper
    except ImportError:
        raise RuntimeError('Whisper is not installed. Run the Notebook installation cell.') from None
    if _model is None:
        _model = whisper.load_model('base', device='cpu')
    result = _model.transcribe(samples, language='en', fp16=False, temperature=0)
    segments = result.get('segments', [])
    if segments and all((segment.get('no_speech_prob', 0) > 0.7 for segment in segments)):
        return ''
    return result.get('text', '').strip()

def spoken_text(text):
    import re
    text = readable_english(text)
    text = re.sub('!\\[([^\\]]*)\\]\\([^)]+\\)', '\\1', text)
    text = re.sub('\\[([^\\]]+)\\]\\([^)]+\\)', '\\1', text)
    text = re.sub('(?m)^\\s{0,3}#{1,6}\\s+', '', text)
    text = re.sub('(?m)^\\s*[-*+]\\s+', '', text)
    text = re.sub('\\*{1,3}([^*]+)\\*{1,3}', '\\1', text)
    text = re.sub('_{1,3}([^_]+)_{1,3}', '\\1', text)
    text = text.replace('`', '').replace('**', '')
    return re.sub('\\s+', ' ', text).strip()
