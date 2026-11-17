"""Associate OCR words geometrically, without a drug dictionary or reference list."""
import re

STRENGTH = re.compile(r'(?<![A-Za-z0-9.])(\d+(?:\.\d+)?)\s*(mcg|mg|g|mL|units|%)(?![A-Za-z])', re.I)
FORM = re.compile(r'\b(tablets?|capsules?|usp|film.coated|oral)\b', re.I)
EXCLUDE = re.compile(r'\b(ndc|rx|only|each|contains?|take|store|warning|keep|manufactured|distributed|information|expiry|expires|lot|dosage|directions|www|http|safety|prescribing|count|contents?|net)\b', re.I)


def rows_from_data(data):
    words = []
    for i, text in enumerate(data.get('text', [])):
        text = str(text).strip()
        if not text:
            continue
        try:
            word = {k: float(data[k][i]) for k in ('left', 'top', 'width', 'height', 'conf')}
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if word['conf'] < 30 or word['height'] <= 0:
            continue
        words.append(dict(word, text=text))
    bands = []
    for word in sorted(words, key=lambda w: w['top'] + w['height']/2):
        center = word['top'] + word['height']/2
        band = next((b for b in bands if abs(b['center']-center) <= .5*max(b['height'], word['height'])), None)
        if band is None:
            bands.append({'center': center, 'height': word['height'], 'words': [word]})
        else:
            band['words'].append(word)
            band['height'] = max(band['height'], word['height'])
    rows = []
    for band in bands:
        groups = [[]]
        for word in sorted(band['words'], key=lambda w: w['left']):
            previous = groups[-1][-1] if groups[-1] else None
            if previous and word['left']-(previous['left']+previous['width']) > 5*max(previous['height'], word['height']):
                groups.append([])
            groups[-1].append(word)
        for group in groups:
            left=min(w['left'] for w in group);top=min(w['top'] for w in group)
            right=max(w['left']+w['width'] for w in group);bottom=max(w['top']+w['height'] for w in group)
            rows.append({'text': ' '.join(w['text'] for w in group), 'left': left, 'top': top,
                         'right': right, 'bottom': bottom, 'height': bottom-top, 'conf': sum(w['conf'] for w in group)/len(group)})
    return sorted(rows, key=lambda r: (r['top'],r['left']))


def name_text(text):
    if EXCLUDE.search(text) or STRENGTH.search(text):
        return ''
    text = re.sub(r'\s+', ' ', FORM.sub(' ', text)).strip(' ,;:()-')
    if not re.fullmatch(r"[A-Za-z][A-Za-z '\-(),/]{1,99}", text) or len(text.split()) > 8:
        return ''
    return text


def nearby(a,b):
    overlap = min(a['right'], b['right'])-max(a['left'], b['left'])
    return overlap > .25*min(a['right']-a['left'], b['right']-b['left'])


def layout_summary(data):
    rows = rows_from_data(data)
    pairs = {}
    for strength in rows:
        text = strength['text']
        matches = list(STRENGTH.finditer(text))
        if len(matches) != 1 or EXCLUDE.search(text):
            continue
        match = matches[0]
        if re.match(r'\s*/',text[match.end():]):
            continue
        name = name_text(text[:match.start()])
        if not name:
            candidates = [r for r in rows if r is not strength and r['bottom'] <= strength['top']+strength['height']*.3
                          and strength['top']-r['bottom'] <= 8*max(strength['height'],r['height'])
                          and nearby(r,strength) and name_text(r['text'])]
            if not candidates:
                continue
            selected = min(candidates, key=lambda r: strength['top']-r['bottom'])
            name = name_text(selected['text'])
            # Rejoin a heading split over two neighboring lines of similar text size.
            above = [r for r in rows if r['bottom'] <= selected['top'] and nearby(r,selected)
                     and selected['top']-r['bottom'] < .8*selected['height']
                     and .7 < r['height']/selected['height'] < 1.4 and name_text(r['text'])]
            if above:
                previous = min(above,key=lambda r: selected['top']-r['bottom'])
                joined = name_text(previous['text']+' '+name)
                if joined:name=joined
        value=f"{name}, {match.group(1)} {match.group(2)}"
        pairs[value.lower()] = value
    if len(pairs) == 1:
        return next(iter(pairs.values())), 'fields_extracted'
    if len(pairs) > 1:
        return '', 'multiple_field_pairs'
    return '', 'fields_not_found'
