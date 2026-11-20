"""OCR + TTS classroom baseline; no matching, medical advice or language model."""
import base64
import csv
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anywidget
import traitlets
from PIL import Image, ImageOps


def orientation_score(data):
    """Rank OCR directions using engine confidence, never a medication dictionary."""
    evidence = 0.0
    characters = 0
    for text, confidence in zip(data.get('text', []), data.get('conf', [])):
        letters = sum(c.isalnum() for c in str(text))
        if letters < 2:
            continue
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            continue
        if confidence < 0:
            continue
        weight = min(letters, 15)
        characters += weight
        evidence += max(confidence - 35, 0) * weight
    return evidence / max(characters, 1) ** 0.5


def extract_label(image):
    import pytesseract
    color_image = ImageOps.exif_transpose(image).convert('RGB')
    image = ImageOps.autocontrast(ImageOps.grayscale(color_image))
    # Enlarge small labels without creating unnecessarily huge camera images.
    scale = min(2.0, 1600 / max(image.size)) if max(image.size) < 1000 else min(1.0, 2600 / max(image.size))
    if scale > 1.05 or scale < 1:
        image = image.resize(tuple(max(1, round(n * scale)) for n in image.size), Image.Resampling.LANCZOS)
    candidates = []
    for angle in (0, 90, 180, 270):
        rotated = image.rotate(angle, expand=True, fillcolor=255)
        data = pytesseract.image_to_data(rotated, lang='eng', config='--psm 11',
                                        output_type=pytesseract.Output.DICT, timeout=30)
        candidates.append((orientation_score(data), rotated, data, angle))
    score, selected, selected_data, selected_angle = max(candidates, key=lambda item: item[0])
    if score <= 0:
        return {'text': '', 'summary': '', 'field_status': 'no_text'}
    from ocr_layout import layout_summary, rows_from_data, name_text, STRENGTH
    summary, field_status = layout_summary(selected_data)
    recovered_lines = []
    if field_status == 'fields_not_found':
        # Local colour-channel OCR increases contrast for white lettering on
        # coloured strength bands. Work from the original pixels: enlarging the
        # complete package first can blur short strings such as "5 mg".
        channels = [ImageOps.autocontrast(color_image.getchannel(channel)).rotate(
            selected_angle, expand=True, fillcolor=255) for channel in ('G', 'B')]
        rows = rows_from_data(selected_data)
        headings = sorted([r for r in rows if name_text(r['text'])], key=lambda r: r['height'], reverse=True)[:4]
        combined = {k: list(selected_data.get(k, [])) for k in ('text','left','top','width','height','conf')}
        for heading in headings:
            h = heading['height']
            # Medication layouts commonly place the strength one to three
            # heading-heights below the name, after a dosage-form line.
            box = (max(0, int((heading['left']-.3*h)/scale)),
                   max(0, int((heading['bottom']+1.0*h)/scale)),
                   min(channels[0].width, int((heading['right']+1.5*h)/scale)),
                   min(channels[0].height, int((heading['bottom']+2.7*h)/scale)))
            single_line = {}
            observed = {}
            for channel in channels:
                crop = channel.crop(box).resize((1600, 300), Image.Resampling.BICUBIC)
                for mode in (13, 6, 7, 11, 12):
                    local_text = pytesseract.image_to_string(
                        crop, lang='eng', config=f'--psm {mode}', timeout=30)
                    for match in STRENGTH.finditer(local_text):
                        value = f'{match.group(1)} {match.group(2)}'
                        target = single_line if mode == 13 else observed
                        target[value.lower()] = value
            # PSM 13 treats the coloured band as one line and avoids nearby
            # gradients turning a leading 5 into 9. Fall back to the other
            # sparse-text modes only when PSM 13 returns no valid strength.
            if len(single_line) == 1:
                observed = single_line
            if len(observed) != 1:
                continue
            value = next(iter(observed.values()))
            entry = dict(text=value, left=heading['left'],
                         top=heading['bottom']+1.5*h,
                         width=max(h*2, heading['right']-heading['left']),
                         height=h, conf=80)
            if any(abs(entry['top']-existing['top']) < h*.6 and STRENGTH.search(existing['text']) for existing in rows):
                continue
            for key, field in entry.items():
                combined[key].append(field)
            rows.append(dict(entry, right=entry['left']+entry['width'],
                             bottom=entry['top']+entry['height']))
            recovered_lines.append(value)
        summary, field_status = layout_summary(combined)
    text = pytesseract.image_to_string(selected, lang='eng', config='--psm 11', timeout=30).strip()
    if recovered_lines:
        text += '\n\nAdditional OCR from label regions:\n' + '\n'.join(recovered_lines)
    return {'text': text, 'summary': summary, 'field_status': field_status}


def extract_text(image):
    return extract_label(image)['text']


def label_summary(text):
    """Conservatively read adjacent label fields; no drug list or spelling repair."""
    strength_pattern = re.compile(r"(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)\s*(mcg|mg|g|mL|units|%)(?![A-Za-z])", re.I)
    skip = re.compile(r"\b(ndc|rx|only|tablets?|capsules?|usp|count|film.coated|oral|net|contents?)\b", re.I)
    unsafe = re.compile(r"\b(each|contains?|take|store|warning|keep|manufactured|distributed|information|expiry|expires|lot|dosage|directions|www|http|safety|prescribing)\b", re.I)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        match = strength_pattern.search(line)
        if not match or unsafe.search(line):
            continue
        fragments = [line[:match.start()]]
        # Package headings are commonly separated from the strength by dosage form lines.
        for previous in reversed(lines[max(0, index-4):index]):
            if unsafe.search(previous) or strength_pattern.search(previous):
                break
            if re.search(r"\b(NDC|Rx)\b",previous,re.I) or re.search(r"\d",previous):
                break
            candidate = skip.sub(' ', previous).strip(' ,;:()-')
            if not candidate:
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z '\-(),/]{1,79}", candidate):
                break
            fragments.insert(0, candidate)
            if len(fragments) >= 3:
                break
        name = ' '.join(skip.sub(' ', fragment).strip(' ,;:()-') for fragment in fragments)
        name = re.sub(r'\s+', ' ', name).strip()
        if unsafe.search(name) or not re.fullmatch(r"[A-Za-z][A-Za-z '\-(),/]{1,99}", name):
            continue
        if len(name.split()) > 8:
            continue
        # Do not truncate a combination strength or concentration into a single strength.
        if re.match(r"\s*/",line[match.end():]) or len(strength_pattern.findall(line)) > 1:
            continue
        return f"{name}, {match.group(1)} {match.group(2)}"
    return ''


def speak_text(text):
    from gtts import gTTS
    buffer = io.BytesIO()
    gTTS(text=text, lang='en', tld='co.uk').write_to_fp(buffer)
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class BaselineReader(anywidget.AnyWidget):
    _esm = Path(__file__).with_name('baseline_camera.mjs')
    _css = 'button,.upload {display:inline-block;padding:12px;margin:5px;font-size:18px;cursor:pointer;border:1px solid #aaa;border-radius:6px} video,img {width:100%;max-width:720px} audio {width:100%} [data-r="text"] {white-space:pre-wrap;font-size:22px} p {line-height:1.5}'
    request = traitlets.Dict(default_value={}).tag(sync=True)
    label_text = traitlets.Unicode('').tag(sync=True)
    summary_text = traitlets.Unicode('').tag(sync=True)
    status = traitlets.Unicode('Open the camera or choose a photo.').tag(sync=True)
    audio_data = traitlets.Unicode('').tag(sync=True)
    busy = traitlets.Bool(False).tag(sync=True)
    can_finish = traitlets.Bool(False).tag(sync=True)

    def __init__(self, folder=None, ocr=None, tts=None):
        super().__init__()
        self.folder = Path(folder or Path(__file__).parent / 'baseline_records')
        self.ocr = ocr or extract_label
        self.tts = tts or speak_text
        self.task = None
        self.observe(self._handle, names='request')

    def _new_task(self, identifier):
        self.task = {'task_id': identifier or str(uuid.uuid4()), 'condition': 'OCR_TTS',
                     'started_at': datetime.now(timezone.utc).isoformat(),
                     'status': 'in_progress', 'photo_attempts': 0, 'attempt_results': [],
                     'clicks': [], 'click_count': 0, 'click_rate': None}
        self._started = time.perf_counter()

    def _persist(self):
        if not self.task:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / 'tasks.json'
        values = json.loads(path.read_text()) if path.exists() else []
        values = [v for v in values if v['task_id'] != self.task['task_id']] + [self.task]
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(values, indent=2) + '\n')
        os.replace(temporary, path)
        keys = ['task_id', 'condition', 'status', 'started_at', 'finished_at', 'elapsed_seconds',
                'client_elapsed_ms', 'photo_attempts', 'click_count']
        with (self.folder / 'summary.csv').open('w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(values)

    def _handle(self, change):
        if self.busy:
            return
        request = change['new']
        action = request.get('action')
        if action not in {'photo', 'finish', 'cancel'}:
            return
        if action == 'photo' and (not self.task or self.task['status'] != 'in_progress'):
            self._new_task(request.get('task_id'))
        if self.task and request.get('task_id') != self.task['task_id']:
            self.status = 'This task is no longer active. Start a new photo task.'
            return
        if self.task:
            self.task['clicks'] = request.get('clicks', [])
            self.task['click_count'] = sum(item.get('action') != 'audio_play' for item in self.task['clicks'])
        if action in {'finish', 'cancel'}:
            if not self.task or self.task['status'] != 'in_progress':
                return
            if action == 'finish' and not self.can_finish:
                self.status = 'Read a label before finishing the task.'
                return
            self.task.update(status='completed' if action == 'finish' else 'cancelled',
                             finished_at=datetime.now(timezone.utc).isoformat(),
                             elapsed_seconds=round(time.perf_counter()-self._started, 3),
                             client_elapsed_ms=request.get('client_elapsed_ms'))
            self._persist()
            self.can_finish = False
            self.audio_data = ''
            self.status = 'Selection recorded. Correctness must be scored by the evaluator.' if action == 'finish' else 'Task cancelled.'
            return
        self.busy = True
        self.can_finish = False
        self.audio_data = ''
        self.label_text = ''
        self.summary_text = ''
        self.status = 'Reading the label…'
        self.task['photo_attempts'] += 1
        result = 'error'
        try:
            data = request.get('photo', '').split(',', 1)[-1]
            if len(data) > 20_000_000:
                raise ValueError('Photo too large')
            raw = base64.b64decode(data, validate=True)
            with Image.open(io.BytesIO(raw)) as original:
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGB')
            extracted = self.ocr(image)
            text = extracted.get('text', '') if isinstance(extracted, dict) else extracted
            self.label_text = text
            if text:
                result = 'text_returned'
                self.can_finish = True
                try:
                    summary = extracted.get('summary', '') if isinstance(extracted, dict) else label_summary(text)
                    self.summary_text = summary or 'Medication name or strength could not be extracted reliably.'
                    narration = summary or 'I could not extract the medication name and strength. Please check the displayed label text or take another photo.'
                    self.audio_data = self.tts(narration)
                    self.status = 'Compare the extracted fields with your reference list. OCR can contain errors.' if summary else ('OCR found several possible names or strengths. Photograph one label only.' if isinstance(extracted, dict) and extracted.get('field_status') == 'multiple_field_pairs' else 'OCR read text, but could not associate a medication name with a nearby strength. Review the full text or retake a closer photo.')
                except Exception:
                    self.status = 'Label text extracted, but speech generation failed. Read the text or try another photo.'
                    result = 'text_returned_tts_failed'
            else:
                result = 'no_text'
                self.status = 'No text was extracted. You may take another photo.'
        except Exception:
            self.status = 'OCR could not finish. Check that Tesseract is installed and the image is readable, then retry.'
        finally:
            self.task['attempt_results'].append({'attempt': self.task['photo_attempts'],
                'result': result, 'at': datetime.now(timezone.utc).isoformat()})
            self.busy = False
            self._persist()
