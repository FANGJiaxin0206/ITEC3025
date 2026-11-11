# MediConfirm

MediConfirm is an ITEC3025 project for older adults with low vision. It checks a photographed medication package against a saved medication plan, offers optional English conversation and voice feedback, and records explicit self-reported intake. This repository includes both the **desktop website** and **Jupyter Notebook**.

## 1. Install

Python 3.10 or newer is required. macOS/Linux is the supported environment because the shared JSON store uses a Unix file lock. Windows has not been validated; use WSL if needed. Anaconda is supported.

```bash
cd mediconfirm_v2
python -m pip install -r requirements.txt
```

Use the same Python environment for installation, launch and the Notebook kernel. Restart Jupyter after installing widget dependencies. Whisper downloads its model on first use; this requires internet and may take time. Microphone recording and gTTS speech generation also need their relevant local permissions or network services.

## 2. Configure the HKBU API once

Copy `config.example.json` to `config.local.json` in this folder and replace the placeholder locally:

```json
{
  "api_key": "YOUR_HKBU_API_KEY",
  "model": "gpt-4.1",
  "api_version": "2025-04-01-preview"
}
```

Use your authorized HKBU GenAI API key. `HKBU_API_KEY` is an alternative environment variable and takes precedence over the file key. The backend calls the HKBU deployment chat-completions endpoint; changing the model requires a model available to your account with the necessary vision support. API quota, availability and network access are required. Model inference is real API inference, not a simulated recognition result.

The key is loaded by Python and is never sent to the browser. The local configuration is reused on restart. Each collaborator configures their own computer; example files do not contain working credentials.

## 3. Run the desktop website

```bash
python main.py web
```

Open the **full Computer URL** printed in the terminal, including `?access=...`. Keep the terminal open. Use localhost for computer camera and microphone permissions. The token can change after a restart. This is a local development server, not public hosting; uploading to GitHub does not publish a running Python website.

- **Home:** current Hong Kong schedule and medication cards; open a package check.
- **Chat:** optional English conversation, reviewed Whisper transcription and spoken replies.
- **Me:** medication input, reminders, history, evaluation export and family email settings.

Open camera, capture the complete label, and submit it for verification. Uploading an image is a fallback. Results are **Match**, **Mismatch** or **Uncertain**. Only a valid matching verification followed by an explicit intake self-report can save **Taken**. Rephotographing or changing the selected medication invalidates the earlier verification.

The clock uses Asia/Hong_Kong. Defaults are **300 seconds** before asking again and **600 seconds** before marking an unanswered event Unconfirmed. Both delays are configurable in Me; the repeat delay must be shorter than the timeout. New settings apply to new events. Reminders require the process to keep running and the computer to stay awake; this is not an operating-system alarm service.

The internal filename `run_mobile.py` and legacy `python main.py mobile` command remain compatible; both launch the same desktop website. They do not indicate a separate mobile application.

## 4. Run the Notebook

```bash
python main.py notebook
```

Alternatively, open `MediConfirm.ipynb` in Jupyter using your configured environment. Run cells in order, starting with the installation/configuration cells. Saved outputs have been cleared for sharing. Allow camera and microphone access when prompted. After changing Python modules, restart the kernel and rerun the relevant cells.

Both interfaces use the same medication list, settings and intake history. Refresh the medication form or rerun it after editing the list in the other interface. Long-running cells can delay Notebook reminders. Configure the real-email switch and send the connection test in the website; the Notebook reuses the shared setting. Website evaluation click/timing instrumentation does not cover Notebook interactions.

## 5. Configure real Gmail alerts

API credentials and email credentials are separate. Real email is **off by default**. The team uses a MediConfirm Gmail sender; each backend computer needs its own local authorization.

1. Sign in to the team Gmail account, enable Google 2-Step Verification and create a Google app password. Do not use the ordinary account password.
2. Run `python configure_email.py` and enter the sender address and 16-character app password locally. Hidden password input is normal.
3. In the website, open **Me → Family notifications**, save the recipient address, enable **Send real email alerts to this address**, and save.
4. Click **Send test email** and check both the delivery record and the recipient inbox/spam folder.

The setup script writes `mail.local.json` with owner-only permissions. It is reused on restart and must never be uploaded or sent through chat. For another backend computer, create a separate app password for the same sender and repeat setup locally. A central deployment would configure the sender only on that server.

Sending uses Python `smtplib`, Gmail SMTP and verified TLS. No paid email library is required. **Submitted** means the provider accepted the message; it does not guarantee inbox delivery. Failed or uncertain delivery is displayed, and uncertain submissions are not automatically repeated. Timeout or predefined severe-discomfort notifications can send real email only after enablement. Email is not an emergency response service. See [MAIL_SETUP.md](MAIL_SETUP.md) for details.

A direct SMTP connection test reached a test QQ mailbox during local validation. A school mailbox did not confirm receipt. The full timeout/severe-discomfort-to-inbox workflow still needs acceptance testing on the computer used for presentation. No personal test addresses or authorizations are included.

## 6. Data and evaluation

Runtime files are created locally and excluded from Git:

| File | Purpose |
| --- | --- |
| `data/personal_medications.json` | Saved medication plan |
| `data/settings.json` | Reminder delays, recipient and switches |
| `data/intake_records.json` | Pending / Taken / Unconfirmed, changes and notifications |
| `data/evaluation_metrics.json` | Website task time, photo attempts and button clicks |

This is a single-user local store shared by all authorized browsers and the Notebook. Duplicate confirmations do not create another Taken event. Unconfirmed does not prove a missed dose.

Website task timing starts at the first submitted photo and ends at accepted explicit Taken confirmation. Retakes stay in the same task. Button clicks within that interval are recorded; opening the camera before the first submission is outside it. Cancelled/unfinished attempts remain distinguishable. In **Me → History → Evaluation data**, export the summary CSV; detailed events remain in JSON. Click rate is not calculated until its numerator and denominator are defined.

`evaluation/` contains a fictitious reference plan, five package images, source metadata and printable test boxes. See [evaluation/README.md](evaluation/README.md). These materials are for classroom tasks, not prescribing or real administration.

## 7. Project layout and UI collaboration

```text
main.py                    Launch website or Notebook
MediConfirm.ipynb           Notebook interface
run_mobile.py              Desktop web launcher (legacy filename)
configure_email.py         One-time local Gmail setup
config.example.json        HKBU configuration template
mail.example.json          SMTP configuration template
src/mediconfirm/
  web/                     HTML, CSS, JavaScript and camera/audio controls
  mobile_server.py         Flask endpoints and shared controller
  simple_ui.py             Verification and conversation controller
  simple_service.py        Label extraction and comparison
  integrations.py          HKBU API client
  dialogue.py              Conversation prompts and context
  speech_tools.py          Speech recognition helpers
  medication_form.py       Notebook medication form
  notebook_dashboard.py    Notebook settings and history
  intake_store.py          Intake events and status transitions
  plan_actions.py          Reminder and timeout rules
  email_delivery.py        SMTP delivery and persisted send claims
  evaluation_log.py        Website evaluation records
  resources/drug_labels/   Source-backed general-use material
evaluation/                Classroom plan, images and printable boxes
tests/                     Automated regression checks
docs/ARCHITECTURE.md        UI integration and API contract
```

UI collaborators should start with `src/mediconfirm/web/` and preserve the contracts in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Keep verification IDs, explicit confirmation, shared storage, evaluation events and single-audio handling when merging a new UI. Frontend exports from design tools need integration with the existing Python endpoints; they do not replace the backend automatically.

## 8. Checks and remaining acceptance tests

```bash
python tests/run_tests.py
```

JavaScript regression checks require Node.js and can be run with `node tests/test_desktop_camera.mjs` and the other `tests/test_*.mjs` files. Automated tests mock camera, model or SMTP behavior where appropriate; they do not establish real recognition accuracy or inbox delivery.

Before presentation, test the actual camera/microphone, model connection, audio playback, explicit confirmation, configurable reminders and email receipt end to end. No diagnosis, personalized treatment decision or physical swallowing verification is provided. General-use explanations do not establish a personal prescribing reason.

## 9. GitHub publishing

Upload this prepared folder only after review. Never commit `config.local.json`, `mail.local.json`, `.env` files, runtime records, photos/recordings, backups or Notebook outputs containing private information. `.gitignore` excludes standard local paths; it cannot remove secrets already committed in history. GitHub stores source code; public access to a running app requires separate deployment.

## VQA + TTS comparison baseline

A separate, simple label reader is available in [baselines/vqa_tts](baselines/vqa_tts/README.md). Open [VQA_TTS_Baseline.ipynb](baselines/vqa_tts/VQA_TTS_Baseline.ipynb), install its dependencies and enter an authorized HKBU API key in its configuration cell. It displays and reads the visible medication name and strength without a medication list, automatic matching or health conversation. Participants compare with a separately supplied reference list and confirm their selection. Local task time and click records are excluded from Git. Restore the API placeholder and clear outputs before sharing an edited Notebook. The full website and main Notebook remain unchanged.
