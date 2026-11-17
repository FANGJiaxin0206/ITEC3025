# OCR + TTS baseline

## Setup on Windows, macOS or Linux

Anaconda/Miniconda is the recommended common setup. In Terminal (macOS/Linux) or Anaconda Prompt (Windows), run:

```bash
conda env create -f environment.yml
conda activate mediconfirm-baseline
jupyter notebook
```

Open `OCR_TTS_Baseline.ipynb` and select this environment's kernel. The environment installs both the Tesseract executable and the Python wrappers; no Homebrew is required. For an existing Anaconda notebook environment, run notebook cells in order: the engine-check cell installs a missing Tesseract through Conda into the active kernel's prefix. Dependency solving may take time and needs internet. Restart Jupyter/kernel if newly installed widget extensions are not loaded.

Keep `baseline.py`, `ocr_setup.py` and `baseline_camera.mjs` beside the notebook. Detection searches the active Conda environment, PATH, Windows installation directories, and common macOS/Linux paths. Use TESSERACT_PATH for custom installations; Windows paths should use a raw string such as `r"C:\Program Files\Tesseract-OCR\tesseract.exe"`.

Without Conda, install Python dependencies with requirements.txt, and install the separate engine using the [official Tesseract installation instructions](https://tesseract-ocr.github.io/tessdoc/Installation.html). pip alone does not install the engine.

The setup includes platform-aware detection but has not been run on physical Windows/Linux computers here. Camera/microphone permission and actual OCR/TTS must be checked on each test computer. This standalone baseline does not import the main application's Unix file-lock module.


Capture/upload one label, read or listen to its OCR text, manually compare with the supplied reference list, then confirm selection. No model API, automatic matching, health conversation, medication advice or email is included. gTTS requires internet. English OCR is selected.

Local records: `baseline_records/tasks.json` and `baseline_records/summary.csv`. Task duration is from first submitted image to explicit simulated selection confirmation; initial search time is excluded. The evaluator supplies the same medication list used for MediConfirm and separately scores correctness. Same participants should use both conditions with order balanced or randomized and equivalent tasks. Completed does not mean correct. Do not actually take medication.

Button actions and audio-play events have separate types. Click rate is undefined. These records are independent of MediConfirm intake history and must not be uploaded as participant data. Only one active baseline widget should write to each records folder.

Core behavior can be tested offline with `python test_baseline.py`; this injects OCR/TTS responses and does not test actual OCR quality, sound or hardware.

Sources: [Tesseract](https://github.com/tesseract-ocr/tesseract), [pytesseract](https://github.com/madmaze/pytesseract), [gTTS](https://gtts.readthedocs.io/).

## OCR image handling

OCR applies EXIF orientation, grayscale, autocontrast, bounded resizing and four right-angle rotations. The direction is selected using Tesseract confidence, without medication names, a reference list or a language model. Sparse-text segmentation reads labels with separated blocks. This takes longer than a single OCR pass. Strong perspective, glare, blur, tiny text or a label photographed from a screen may still produce errors; frame the label closely and upright. Include the same preprocessing for every baseline participant.

## Short narration

The main result and narration contain only the medication name and strength extracted by fixed adjacent-line rules. Full uncorrected OCR text remains in a collapsible section. The parser does not query a drug dictionary, a medication list or GPT, and does not repair OCR spelling. Missing/unsupported fields produce a short retry message. Combination strengths and concentrations are deliberately not shortened. This is field extraction, not verification; evaluate failures as part of the baseline.

## Coordinate-based field association

The live OCR pipeline now retains word bounding boxes and confidence. It groups nearby words geometrically and associates a detected strength with an overlapping heading above it, skipping dosage-form lines. Identical repeated panels are deduplicated; conflicting field pairs are not silently selected. It does not depend on the OCR text stream's line order. Selected label regions also receive a local blue-channel OCR pass to help with warm backgrounds. These heuristics do not guarantee field detection, and low-confidence words can be dropped.

The full-text section includes any additional region OCR. The older text-only parser remains for injected test responses; actual images use coordinates. No drug spelling correction or expected medication list is used. The supplied screen-photo example still did not reliably yield its white-on-orange strength during local verification; this remains a real OCR limitation, not a successful test. Try a close, direct photo of the printed label rather than a photo of a screen.
