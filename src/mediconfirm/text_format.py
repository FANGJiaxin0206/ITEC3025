"""Repair English typography without changing doses, numbers or paragraph breaks."""
import re

_GAP = r'[ \t\u00a0\u2009\u202f\u200b]*'
_CONTRACTION = re.compile(r"\b([A-Za-z]+)" + _GAP + r"['’‘＇ʼ]" + _GAP + r"(m|re|ve|ll|d|s|t)\b", re.I)


def readable_english(value):
    text = _CONTRACTION.sub(r"\1'\2", str(value))
    text = re.sub(r'(?<=[A-Za-z0-9])[ \t\u00a0\u2009\u202f]+,', ',', text)
    text = re.sub(r'(?<=[A-Za-z]),[ \t]*(?=[A-Za-z0-9])', ', ', text)
    text = re.sub(r'(?<=[A-Za-z])，[ \t]*(?=[A-Za-z0-9])', ', ', text)
    return text
