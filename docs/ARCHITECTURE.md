# Architecture and UI integration

## What this project does

MediConfirm helps a user compare one photographed medication package with a saved medication list. It can answer grounded questions, speak responses, and save an explicit intake self-report. It does not prescribe medication or verify swallowing.

## Entry points

| Entry | Purpose |
| --- | --- |
| `python main.py` | Open the Notebook demonstration using the current Python environment. |
| `python main.py mobile` | Start the local phone web interface. |
| `python main.py --check` | Check files, dependencies and key availability without network or hardware access. |
| `MediConfirm.ipynb` | Install, configure, edit the list and demonstrate the Notebook UI. |

`main.py` only selects an interface. It contains no matching, medical or logging rules.

## Main flow

1. Load a saved list with medication name, package strength, schedule time and dose per intake.
2. Select a schedule manually and start its pending events.
3. Capture or upload one package image.
4. `HKBUClient.extract()` reads visible fields without seeing the expected medication.
5. `identify_photo()` and `check_medication_list()` compare those fields with the selected list.
6. The UI displays and speaks Match, Mismatch or Uncertain, with the relevant explanation.
7. A current Match enables explicit confirmation. It does not itself save Taken.
8. A button or reviewed confirmation text is validated against the current verification token, date, schedule and list.
9. `record_intake()` saves the self-report and prevents duplicate Taken events.

Retaking a photo, changing a schedule or updating a list invalidates previous confirmation evidence.

## Modules and responsibilities

| Module | Responsibility |
| --- | --- |
| `core.py` | Pure verification helpers, normalization, finite severe-phrase and confirmation rules, atomic JSON writes. |
| `bulk_medications.py` | Validate the list, expand daily times, produce IDs, load and save entries. |
| `simple_service.py` | Extract a photo and compare it with the selected schedule; explain mismatches. |
| `integrations.py` | Make authenticated HKBU requests and parse structured label extraction. |
| `drug_sources.py` | Match official DailyMed evidence and retrieve general-use text. |
| `resources/drug_labels/` | Dated official label snapshots and their source URLs for demo reproducibility. |
| `dialogue.py` | Build grounded conversation context and request a reply. |
| `speech_tools.py` | Decode audio, transcribe English with Whisper, remove display formatting from spoken text. |
| `intake_store.py` | Save Pending/Taken/Unconfirmed events, reasons and history. |
| `plan_actions.py` | Initial/repeat reminders, simulated elapsed time, and deduplicated unsent notifications. |
| `simple_ui.py` | Coordinate the current workflow, confirmation eligibility, speech output and UI state. |
| `medication_form.py` | Notebook medication-list input form. |
| `simple_camera.mjs` | Notebook browser camera, microphone and controls. |
| `mobile_server.py` | Authenticated phone sessions, uploads, JSON actions and state responses. |
| `web/` | Phone HTML, CSS and browser JavaScript. |

## Notebook and phone relationship

The Notebook and phone interface are separate views. Both currently use `SimpleCameraApp` as their workflow controller, which in turn calls the shared services above. The phone adapter creates a Python controller per browser session and exposes selected state through Flask. It does not deliver the Notebook widget itself to the phone.

This is not yet a fully UI-independent application layer: `SimpleCameraApp` inherits from AnyWidget. A larger future UI merge can extract that controller into a plain Python session class while keeping the service functions and storage rules. A visual-only phone redesign can replace `web/` without that refactor.

## Phone API contract

All `/api/` routes require the local access-link session. POST requests from another origin are rejected. The API key is used only by the server.

| Endpoint | Input | Behavior |
| --- | --- | --- |
| `GET /api/state` | Browser session cookie | Refresh deadlines and return safe UI state. |
| `POST /api/photo` | Multipart `photo` | Validate and convert the image, verify it, and return the result. |
| `POST /api/speech` | Multipart `audio` | Return an editable transcript; never auto-confirm intake. |
| `POST /api/action` | JSON `action` and fields | Perform the operations below. |

Action examples:

```json
{"action":"time","value":"08:00"}
{"action":"chat","text":"Is this my morning medication?"}
{"action":"uses"}
{"action":"confirm","status":"Taken","verification_id":"CURRENT_TOKEN"}
{"action":"confirm","text":"I have not taken it.","verification_id":"CURRENT_TOKEN"}
{"action":"flow","value":"cancel"}
{"action":"simulation","value":"new_demo"}
{"action":"simulation","value":"advance"}
```

The state includes `result_text`, `confirmation_ready`, `verification_id`, `dialogue_messages`, `source_status`, `source_links`, `audio_data`, `schedule_text` and `notification_text`. Render model content as text or explicitly supported formatting, never executable HTML.

## Rules to preserve during a UI merge

- The server decides Match/Mismatch/Uncertain and whether confirmation is allowed. The frontend must not manufacture a Match or reuse an old token.
- Automatic transcription and ordinary chat do not save Taken. Confirmation is a separate user action after a valid Match.
- Name, strength, time and per-intake dose are distinct fields.
- Pending means awaiting confirmation. Unconfirmed means no confirmation was received, not proven non-adherence.
- Repeated requests must not create duplicate Taken records or duplicate simulated notices.
- General uses come from the displayed official source. A source lookup never overrides package matching or determines personal prescribing reasons. An unverified coating must not be described as fully verified.
- Severe-demo reports pause the normal flow and invalidate confirmation. The rules cover finite examples, not medical triage.
- Keep keys and health records off the frontend and out of Git.

## Storage

| Path | Contents | Included in Git |
| --- | --- | --- |
| `config.example.json` | Placeholder configuration | Yes |
| `config.local.json` | Local key/model configuration | No |
| `data/personal_medications.json` | Local Notebook medication list | No |
| `data/intake_records.json` | Notebook events and simulated notices | No |
| `data/demo_runs/` | Separate Notebook demo rounds | No |
| `data/mobile_runs/` | Separate phone lists and logs | No |
| `evaluation/demo_medications.json` | Fictional demonstration list | Yes |
| `evaluation/` | Current printable props and public source images | Yes |

The upload copy contains an empty runtime `data/` directory and a clean Notebook without outputs or saved widget state. The working local Notebook and runtime data remain intact.

## Current scope

The phone interface is a local prototype awaiting visual refinement. It is not a native app or public deployment. Real background scheduling, real email delivery, bilingual voice support, the OCR baseline and formal user-study analysis are not implemented. HTTP phone connections support photo selection/upload and typing; live browser microphone recording requires a secure context.
