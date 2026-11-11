# VQA + TTS baseline

A separate English label-reading condition for the MediConfirm evaluation. It reads one photographed medication package and displays/speaks its visible name and strength. It does not receive a medication list, compare a schedule, explain drug uses, offer health conversation or send email. Participants receive the reference list separately and judge the selection themselves. The evaluator scores correctness. No real medication is taken.

## Run

Keep every file in this folder together. Using Anaconda or another Python 3.10+ environment:

```bash
cd baselines/vqa_tts
python -m pip install -r requirements.txt
python -m notebook VQA_TTS_Baseline.ipynb
```

Alternatively open the Notebook from the repository root. It locates the helper files in baselines/vqa_tts. Select the same Python environment as the kernel. Windows, macOS and Linux use the same Python dependencies; no Tesseract is required. Actual browser/hardware behavior must be checked on each computer. Restart Jupyter/kernel if newly installed widget extensions are not loaded.

1. Run the dependency cell.
2. In the configuration cell, replace YOUR_HKBU_API_KEY with your authorized HKBU key. Defaults are gpt-4.1 and API version 2025-04-01-preview; use the same model/version as the full system for comparison.
3. Run the reader cell and allow camera access. Capture or upload a label, listen to the name and strength, and compare with the reference list yourself. Retake/replay/cancel as needed.
4. Click I selected this box — finish task for explicit simulated selection confirmation.

The camera uses browser getUserMedia and requires localhost or HTTPS and permission. Image upload is a fallback. Both HKBU inference and gTTS require internet. Unreadable name/strength causes a retry message, not a Match/Mismatch result. Model recognition can be incorrect even when it returns fields.

## API key

The key is used only in Python HTTP requests, not browser widget state, logs or printed configuration. However, typing a key into a Notebook cell saves it in the notebook source. **Before sharing/committing, restore the placeholder and clear all outputs.** The shipped Notebook contains only a placeholder. .gitignore cannot hide a key embedded in a tracked Notebook. This baseline does not read the main system's config.local.json and does not modify its configuration.

## Evaluation records

Local records are vqa_records/tasks.json and vqa_records/summary.csv. They are ignored by Git. Each task retains attempts, button-click details and completion/cancellation status. Timing starts at the first submitted photo and ends at accepted selection confirmation, including API/TTS waiting, listening and retakes. Initial searching/camera opening is excluded, matching the current full-system website metric. If evaluating the whole search task, separately measure from task instruction to final selection in both conditions.

Button clicks exclude audio-play events; the latter remain separately named in raw records. Click rate is not defined. Completed does not mean correct. No API keys, photos, recordings or model text are included in task logs. Use one active widget per records folder. Records are independent of the main system's medication and intake history.

## Comparison scope

The main user-study comparison can be this VQA+TTS reader versus the full MediConfirm interaction. Supply the same reference-list information, comparable tasks and the same model/voice settings; balance or randomize condition order. An optional OCR-vs-VQA component speed/accuracy test does not require a third full user-study condition.

## Files and checks

- VQA_TTS_Baseline.ipynb: setup, direct API configuration, reader and CSV preview.
- vqa_baseline.py: API extraction, TTS, widget state and task records.
- vqa_camera.mjs: camera/upload controls, single audio player and explicit selection.
- requirements.txt: standalone Python dependencies.
- test_vqa_baseline.py: four offline mocked checks.
- .gitignore: local records, cache and checkpoints.

```bash
python -m unittest discover -p 'test_*.py'
```

Mocked checks do not call the real model or prove camera behavior. The owner reported successful local execution of this baseline; response quality remains an evaluation outcome.
