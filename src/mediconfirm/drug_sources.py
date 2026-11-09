"""Retrieve general uses from NLM DailyMed; never infer a personal indication."""
import re
import time
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from .core import normalized
NS = {'h': 'urn:hl7-org:v3'}
BASE = 'https://dailymed.nlm.nih.gov/dailymed/services/v2'

def is_use_question(text):
    return bool(re.search('\\b(used for|use of|uses of|purpose|indication|what.*\\bfor|why.*\\b(prescribed|take))\\b', text, re.I))

def _strength(value):
    match = re.fullmatch('\\s*(\\d+(?:\\.\\d+)?)\\s*(mg|mcg|g)\\s*', value or '', re.I)
    if not match:
        return None
    return (Decimal(match[1]), match[2].lower())

def _text(element):
    return ' '.join(' '.join(element.itertext()).split()) if element is not None else ''

def _form(value):
    value = normalized(value).replace('-', ' ')
    value = re.sub(r'\b(usp|bp|ph[.]? eur[.]?|oral)\b', '', value)
    value = re.sub(r'\s+', ' ', value).strip(' ,.')
    aliases = {'tablets': 'tablet', 'film coated tablet': 'tablet, film coated',
               'film coated tablets': 'tablet, film coated', 'tablets, film coated': 'tablet, film coated',
               'chewable tablet': 'tablet, chewable', 'chewable tablets': 'tablet, chewable',
               'capsules': 'capsule'}
    return aliases.get(value, value)


def extract_matching_uses(xml, fields):
    if len(xml) > 2000000 or b'<!DOCTYPE' in xml.upper():
        return None
    root = ET.fromstring(xml)
    document_code = root.find('h:code', NS)
    if document_code is None or document_code.get('code') not in {'34391-3', '34390-5'}:
        return None
    target_name = normalized(fields.get('name', ''))
    target_strength = _strength(fields.get('strength'))
    target_form = _form(fields.get('dosage_form') or '')
    if not target_name or not target_strength or (not target_form):
        return None
    matched = None
    for tag in ('manufacturedProduct', 'manufacturedMedicine'):
        for product in root.findall(f'.//h:{tag}', NS):
            brand = _text(product.find('h:name', NS))
            generic = _text(product.find('h:asEntityWithGeneric/h:genericMedicine/h:name', NS))
            form = product.find('h:formCode', NS)
            form_name = form.get('displayName', '') if form is not None else ''
            if target_name not in {normalized(brand), normalized(generic)} or _form(form_name) != target_form:
                continue
            if not any((word in normalized(form_name) for word in ('tablet', 'capsule'))):
                continue
            active = [node for node in product.findall('h:ingredient', NS) if node.get('classCode', '').startswith('ACTI')]
            if len(active) != 1:
                continue
            numerator = active[0].find('h:quantity/h:numerator', NS)
            denominator = active[0].find('h:quantity/h:denominator', NS)
            if numerator is None or denominator is None:
                continue
            try:
                amount = (Decimal(numerator.get('value', '')), numerator.get('unit', '').lower())
                if Decimal(denominator.get('value', '0')) != 1 or denominator.get('unit') != '1':
                    continue
            except InvalidOperation:
                continue
            if amount == target_strength:
                matched = {'brand_name': brand, 'generic_name': generic, 'dosage_form': form_name}
                break
        if matched:
            break
    if not matched:
        return None
    sections = []
    for section in root.findall('.//h:section', NS):
        code = section.find('h:code', NS)
        if code is not None and code.get('code') in {'34067-9', '55105-1'}:
            text_nodes = section.findall('h:text', NS) or section.findall('h:excerpt/h:highlight/h:text', NS) or section.findall('h:component/h:section/h:text', NS)
            value = ' '.join(_text(node) for node in text_nodes)
            if value:
                sections.append(value)
    if not sections:
        return None
    return {**matched, 'general_uses_text': '\n'.join(dict.fromkeys(sections))[:4000]}

def _general_evidence(xml, fields):
    if len(xml) > 2_000_000 or b"<!DOCTYPE" in xml.upper():
        return None
    exact = extract_matching_uses(xml, fields)
    if exact:
        return {**exact, 'form_verified': True}
    form = _form(fields.get('dosage_form') or '')
    if form not in {'', 'tablet'}:
        return None
    root = ET.fromstring(xml)
    for product in root.findall('.//h:manufacturedProduct', NS):
        code = product.find('h:formCode', NS)
        label_form = code.get('displayName', '') if code is not None else ''
        if _form(label_form) not in {'tablet', 'tablet, film coated'}:
            continue
        evidence = extract_matching_uses(xml, {**fields, 'dosage_form': label_form})
        if evidence:
            return {**evidence, 'form_verified': False,
                    'form_note': 'General uses are supported by a label matching the name and strength. The exact coating on the photographed package was not verified. This does not verify package identity or dosing.'}
    return None


def _cached_lookup(fields):
    folder = Path(__file__).with_name('resources') / 'drug_labels'
    index = folder / 'sources.json'
    if not index.exists():
        return None
    for item in json.loads(index.read_text()):
        label = folder / item['file']
        matched = _general_evidence(label.read_bytes(), fields)
        if matched:
            return {'status': 'found', **matched, 'source_title': item['title'],
                    'url': item['url'], 'published_date': '', 'retrieved_on': item['retrieved_on'],
                    'source_mode': 'stored_official_label',
                    'scope': 'A dated official DailyMed label snapshot, used for general uses only. Exact manufacturer, package identity and personal prescribing reason are not verified.'}
    return None


class DailyMedSource:

    def lookup(self, fields):
        import requests
        if not fields or not _strength(fields.get('strength')) or (not fields.get('name')) :
            return {'status': 'unavailable', 'message': 'A readable drug name and strength are required. Retake the full label if either is missing.'}
        cached = _cached_lookup(fields)
        if cached:
            return cached
        start = time.monotonic()
        session = requests.Session()
        session.headers.update({'User-Agent': 'MediConfirm-classroom-prototype/1.0'})
        try:
            response = session.get(BASE + '/spls.json', params={'drug_name': fields['name'], 'pagesize': 4}, timeout=(4, 8))
            response.raise_for_status()
            candidates = response.json().get('data', [])
            preferred = {
                'metoprolol tartrate': '0a3ccfd4-8b65-4c7e-b0ba-27ff40d5b5e8',
                'amlodipine besylate': '79f41cd2-6d58-4b03-8b0c-ca91398bc1a9',
                'atorvastatin calcium': '6d203e05-1fe6-4262-9d66-b461f84c4672',
                'antacid': '782398a8-a3d9-4766-a7e1-ceb6d65152b2',
                'calcium carbonate': '782398a8-a3d9-4766-a7e1-ceb6d65152b2',
            }.get(normalized(fields['name']))
            if preferred:
                candidates.insert(0, {'setid': preferred, 'title': 'DailyMed label: ' + fields['name']})
            seen = set()
            for item in candidates:
                if item.get('setid') in seen:
                    continue
                seen.add(item.get('setid'))
                if time.monotonic() - start > 22:
                    break
                setid = str(item.get('setid', ''))
                if not re.fullmatch('[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', setid):
                    continue
                try:
                    label = session.get(BASE + f'/spls/{setid}.xml', timeout=(3, 5))
                    label.raise_for_status()
                    matched = _general_evidence(label.content, fields)
                except (requests.RequestException, ET.ParseError, ValueError):
                    continue
                if matched:
                    return {'status': 'found', **matched, 'source_title': item.get('title', 'DailyMed drug label'), 'published_date': item.get('published_date', ''), 'url': 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=' + setid, 'scope': 'An official label supports general uses. See form_verified for the form check; exact manufacturer/package and personal prescribing reason are not verified.'}
            return {'status': 'not_found', 'message': 'No matching general-use label was verified in this limited DailyMed search. Regional brands, formulation differences or the search limit may prevent a match. Do not infer a purpose from model memory.'}
        except (requests.RequestException, ValueError, TypeError):
            return {'status': 'unavailable', 'message': 'DailyMed could not be reached or returned unusable data. General uses cannot be verified right now.'}
        finally:
            session.close()
