# MediConfirm v2

An ITEC3025 assistive AI course project for older adults with low vision: medication-package verification, English voice interaction, explicit intake self-reporting, and simulated caregiver notifications.

## Run

After installing dependencies, `python main.py` opens the Notebook. Use `python main.py mobile` for the experimental local phone interface, or `python main.py --check` to check setup without calling an API.

Open `MediConfirm.ipynb` in Anaconda Notebook from this folder. Run section 1 once to install dependencies, restart the kernel, then run sections 2-4. Camera and microphone access require localhost or HTTPS. Whisper may download its model on first use.

The existing API configuration is stored in the ignored `config.local.json`; the key is not embedded in the notebook. On a new computer, copy `config.example.json` to `config.local.json` and configure it once. No credentials or saved notebook outputs are tracked.

## Structure

```
main.py                Unified Notebook / phone launcher
MediConfirm.ipynb       Setup and demonstration
src/mediconfirm/       Application package and browser widget
  simple_ui.py        Notebook workflow
  simple_camera.mjs   Browser camera, microphone and controls
  simple_service.py   Label extraction and list verification
  medication_form.py  Medication list editor
  bulk_medications.py List validation and persistence
  dialogue.py         Contextual conversation
  drug_sources.py     Verified DailyMed general-use lookup
  integrations.py     HKBU API adapter
  speech_tools.py     Whisper transcription and spoken text cleanup
  intake_store.py     Intake events and history
  plan_actions.py     Reminders and simulated notifications
  core.py             Shared verification and persistence rules
data/                 Local list and generated logs
evaluation/           Current printable boxes, original images and sample list
tests/                Relevant offline and browser regression tests
docs/ARCHITECTURE.md   Workflow, module responsibilities and UI merge contract
```

## Demonstrate

1. Save a medication list and select a schedule.
2. Photograph one package. A mismatch explains the name, strength or schedule difference; unreadable labels require a retake.
3. After a match, use an explicit confirmation button or review and submit status text. Ordinary chat and transcription do not save Taken records.
4. In the demo panel, start a new demo and trigger a reminder. Advance 5 minutes for a repeat question and another 5 for Unconfirmed and a simulated family notification.
5. Start a separate demo and submit `I have chest pain` to test interruption and a simulated notification.

New demo runs use independent files under `data/demo_runs/`. Runtime records remain local and are excluded from Git. A fresh clone starts without personal medication lists or intake records; use the fictional list in evaluation/demo_medications.json for a classroom demonstration.

## Test

```
python tests/run_tests.py
node tests/test_simple_camera.mjs
```

Tests use temporary records and fake services/media. They do not measure live recognition accuracy or validate hardware. Test camera permissions, microphone transcription, real API replies and playback in your browser.

## Boundaries

The schedule is selected manually. The browser checks deadlines while open and reconciles them on reopening; there is no always-on background alarm. Notifications are simulated and never sent. Intake records reflect user reports, not swallowing verification. Severe-symptom rules cover only predefined examples. Drug explanations require a matching source and never infer a personal prescribing reason. The OCR baseline, formal evaluation analysis and bilingual support are not implemented. The phone web frontend is a local test interface.

## Phone interface

Run `python run_mobile.py` or open `Start_Mobile.command`. Connect the phone to the same Wi-Fi and use the full printed Phone link. See [MOBILE.md](MOBILE.md) for camera, audio, session and connection details. No public hosting or real notifications are enabled.

## Architecture and future UI work

The Notebook remains the main demonstration interface. The phone UI is experimental and can be redesigned later. See [Architecture and UI integration](docs/ARCHITECTURE.md) for the shared services, current controller coupling, API contract and rules that a replacement UI must preserve.
