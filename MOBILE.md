# Phone interface

Start from this project folder:

```
python run_mobile.py
```

On macOS, `Start_Mobile.command` uses Anaconda automatically. If Flask is missing, run the notebook installation cell again. Keep the terminal open. Connect your phone to the same network as the computer, then open the full Phone link printed in the terminal, including its access code. The code changes each time the server starts. Do not share it with other people.

Use Take a photo to invoke the phone camera, or Choose an image to upload. One clear package per image. Select the schedule, verify, and explicitly confirm intake. Chat can use the current photo. The general-use source card shows the official source even independently of the model's wording. Clear text remains available if audio autoplay is blocked; use the audio Play control.

The phone session is separate from Notebook records. Medication edits and intake logs are saved under data/mobile_runs/. Simulated notifications are never sent. A new demo creates a separate run. The API key remains in Python on the computer and is never included in page state or JavaScript.

Browser microphone recording is available only in a secure context. On ordinary Wi-Fi HTTP, type or upload a short recording. For experimental HTTPS run `python run_mobile.py --https`; the temporary self-signed certificate must be trusted by the phone, and browser permissions still apply. Camera file capture works through the phone's photo picker without requiring live getUserMedia access.

If the phone link does not open, confirm both devices share a network, allow the Python server through the computer firewall, and check whether the Wi-Fi blocks device-to-device connections. A private home Wi-Fi or personal hotspot can avoid campus client isolation. This server is for local testing, not public deployment. Press Ctrl+C in the terminal to stop.

## General-use sources

The demo medicines have dated XML snapshots downloaded from NLM DailyMed, indexed in src/mediconfirm/resources/drug_labels/sources.json. They are real source evidence, not simulated model replies. The parser supports nested indication sections and normalizes USP/plural dosage-form text. Name and strength must match. An unknown coating may support general-use information with an explicit form-unverified note; an explicitly conflicting release form is rejected. No package match, dosing advice or personal prescribing reason is inferred from this lookup. Other medicines still use the bounded online search.

When a source cannot be verified, the Notebook displays the recognized name/strength/form and the reason. This distinguishes missing fields from lack of a usable source. A model reply is not itself the evidence; use the source card/link to inspect the actual label.
