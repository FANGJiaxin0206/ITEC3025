# MediConfirm architecture

## User interface

The desktop navigation is Home, Chat and Me. Me opens medication management, reminder settings, history or family notifications. A package check is a task entered from a Home medication card, rather than a main navigation item. There are no visible demo controls or separate test-log creation actions.

The browser owns camera/microphone access. `web/desktop_camera.mjs` releases streams on capture, close, cancellation and navigation, and discards late permission responses. `web/app.js` sends photos and reviewed speech/text to Python. The API key never enters the frontend.

## Existing endpoints

| Endpoint | Contract |
| --- | --- |
| `GET /api/state` | Current controller state, daily plan, settings, history and notifications |
| `POST /api/action` | A JSON action described below |
| `POST /api/photo` | Multipart `photo`; invalidates earlier verification before decoding input |
| `POST /api/speech` | Multipart `audio`; returns editable transcription without saving intake |

Open the launcher's access link to authorize a browser. Every authorized browser uses the same local controller and storage; cookies do not select separate records.

### JSON actions

| Action | Additional fields | Behavior |
| --- | --- | --- |
| `select_event` | `event_id` | Validate today's event, select its medication and enter the check flow |
| `prepare_photo` | None | Invalidate the earlier verification before camera capture or upload |
| `confirm` | `verification_id`, `status` or reviewed `text` | Explicit intake self-report tied to the current verification |
| `flow` | `value` | Existing navigation/cancellation actions |
| `chat` | `text` | Grounded conversation with optional package context |
| `uses` | None | General-use explanation backed by the matching official source |
| `save_list` | `medications` | Validate and save the whole shared list |
| `settings` | `settings` | Validate and save shared preferences |
| `replay`, `clear_chat`, `playback_error` | None | Response replay, conversation clearing and audio failure handling |

Private compatibility helpers may remain in Python for regression tests, but the web API rejects the old `simulation` action.

Settings include `repeat_seconds`, `timeout_seconds`, `reminders_enabled`, `caregiver_email` and `real_email_enabled`. Defaults are 300 and 600 seconds. The repeat delay must be positive and smaller than the timeout. Each new event snapshots its repeat delay and deadline, so later settings changes do not silently extend an existing event.

State adds `daily_plan`, `history_records`, `family_notifications`, `target_medication_id`, `verification_status`, `server_time` and `settings` to existing interaction fields. Daily plan entries include an `event_id`, schedule, medication details and display status. A plan not yet started is displayed as Scheduled; persistent intake states remain Pending, Taken and Unconfirmed.

When two medications share a time, selecting one card restricts photo matching to that medication ID. A matching package for a different event must not enable confirmation for the selected event.

## Shared persistence

`shared_storage.py` prepares `data/personal_medications.json`, `data/settings.json` and `data/intake_records.json`. The website and Notebook use these same paths. Regular legacy browser logs are merged once, deduplicating event IDs and preserving explicit Taken reports over unconfirmed records. Original files and backups are retained. Legacy test-run files are not inserted into daily history. A migration report records skipped malformed files.

`storage_lock.py` uses a reentrant thread lock and a macOS/Linux file lock shared by the Notebook and web processes. Read-modify-write event transactions and atomic JSON writes use this lock. Reminder checks share the controller lock with web actions. Tests verify that concurrent processes do not lose each other's events.

On each web refresh, medication and setting changes made through the Notebook are reloaded. A changed list invalidates stale verification. The Notebook dashboard reloads external settings; rerun/refresh its form after external list edits.

## Clock and notifications

The clock is the computer clock represented in Asia/Hong_Kong. The web launcher runs a periodic worker for the initialized shared controller. It starts schedule slots matching the current minute, asks again after the event's repeat delay, and marks an unanswered event Unconfirmed at its deadline. Taken stops further reminders for that event. Restarting reconciles saved deadlines; this is not an OS alarm service and does not backfill earlier unstarted slots.

`web_settings.py` freezes the caregiver email and content of each unsent notification. `email_delivery.py` submits enabled notifications through the locally configured SMTP sender. Credentials are never returned in browser state. A predefined severe-discomfort report pauses the normal flow and records a notification without waiting for a successful email delivery.

## Secrets and runtime data

The local API configuration, shared records, migration backups and cookie signing key are ignored by Git. The repository includes example configuration and code, not personal runtime data. The original MediConfirm project remains separate from mediconfirm_v2.

## Scoped audio and current-plan selection

State includes current_plan_time and current_plan_kind, computed from the Hong Kong clock rather than selected_time. The read_plan action builds narration from the highlighted schedule's saved facts.

Web speech outputs are retained as bounded audio clips with an ID, page scope, target and transcript. GET /api/audio/<clip_id> returns authenticated MP3 data. State exposes clip metadata and URLs rather than repeating base64 audio on every poll. replay_clip regenerates a known clip only; arbitrary narration text is not accepted.

Chat messages have message_id values for attaching their voice control; UI metadata is stripped before sending chat history to the model. Plan, reminder, result, confirmation and help clips have distinct targets. single_audio.mjs owns one audio element, moves it into the corresponding response, and pauses it on page changes or another clip. Browser visibility and same-origin BroadcastChannel coordination reduce duplicate playback from multiple tabs. Separate browser profiles or the Notebook cannot be controlled by the website.

## Email and evaluation endpoints

- `send_test_email`: creates a generic test notification, requiring a configured sender, saved recipient and explicit real-email enablement.
- `retry_email`: requires `notification_id`; explicitly retries eligible failed or unsent notifications.
- `POST /api/metrics`: submits task button-click details.
- `GET /api/evaluation.csv`: exports task summaries; detailed records remain in `data/evaluation_metrics.json`.
- `POST /api/audio/claim`: claims reminder playback so polling does not repeatedly autoplay it.

SMTP submission is asynchronous and persistently claimed before sending. Submitted means provider acceptance, not inbox delivery. Historical previews are never silently sent. The website is the interface for enabling real email and sending a connection test; the Notebook reuses the shared settings.

For UI merges, keep the existing action payloads, current verification ID, event selection, shared persistence and single-audio ownership intact. Replace presentation inside `src/mediconfirm/web/`; do not move credentials into frontend code. Automated metrics currently cover the website, not Notebook interactions.
