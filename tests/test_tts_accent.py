from pathlib import Path


def test_all_tts_paths_use_the_same_british_english_voice():
    root = Path(__file__).resolve().parents[1]
    files = [
        root / 'src/mediconfirm/simple_ui.py',
        root / 'src/mediconfirm/mobile_server.py',
        root / 'baselines/vqa_tts/vqa_baseline.py',
        root / 'baselines/ocr_tts/baseline.py',
    ]
    for path in files:
        source = path.read_text()
        calls = [part.split(')', 1)[0] for part in source.split('gTTS(')[1:]]
        assert calls, f'No gTTS call found in {path}'
        assert all("lang='en'" in call and "tld='co.uk'" in call for call in calls), path
