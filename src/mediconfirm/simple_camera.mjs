function render({ model, el }) {
  el.innerHTML = `
    <div class="mc-simple">
      <h3>MediConfirm</h3>
      <div data-page="home">
        <p>Check your medication package, or have an optional conversation first.</p>
        <button data-action="start-check" style="font-size:22px">Start medication check</button>
        <button data-action="start-chat">Talk with AI (optional)</button>
      </div>
      <div data-page="check" hidden>
      <h3>Check a medication package</h3>
      <p>Open the camera, show one package label, then take a photo. The camera turns off after capture.</p>
      <div class="mc-actions">
        <button data-action="open">Open camera / Retake</button>
        <button data-action="capture" disabled>Capture and check</button>
        <button data-action="close">Close camera</button>
      </div>
      <p data-role="camera-status" aria-live="polite">The camera is off.</p>
      <video autoplay muted playsinline hidden style="max-width:640px;width:100%;background:#eee"></video>
      <img alt="Photo submitted for verification" hidden style="max-width:640px;width:100%" />
      <p data-role="result" aria-live="polite" style="font-size:20px;white-space:pre-wrap"></p>
      <button data-action="ask-current" disabled>Ask about this package</button>
      <div data-role="confirm-panel" hidden>
        <h3>Have you taken this medication yet?</h3>
        <p>A package match does not record intake. Please confirm your status.</p>
        <button data-action="taken">I have taken it - Save</button>
        <button data-action="not-taken">Not yet taken</button>
        <p>You can also record or type your status. Review the text before submitting.</p>
        <textarea data-role="confirm-draft" rows="2" placeholder="I have taken it. / I have not taken it." style="width:100%;font-size:18px"></textarea>
        <button data-action="record-confirm">Record my status</button>
        <button data-action="stop-confirm" disabled>Stop recording</button>
        <button data-action="submit-report">Submit this status</button>
        <p data-role="confirm-speech-status" aria-live="polite"></p>
      </div>
      <p data-role="confirmation-status" aria-live="polite"></p>
      <button data-action="check-home">Back to home</button>
      </div>
      <div data-page="chat" hidden>
      <h3>Talk with AI (optional)</h3>
      <p>Type or record a message. Replies appear here and are read aloud.</p>
      <p data-role="package-context" style="white-space:pre-wrap;padding:12px;border:1px solid #c8d5e4" aria-live="polite"></p>
      <button data-action="general-uses" disabled>Look up general uses</button>
      <p data-role="source-status" aria-live="polite"></p>
      <div data-role="source-links"></div>
      <div data-role="dialogue" aria-live="polite" style="max-height:300px;overflow:auto"></div>
      <textarea data-role="draft" rows="3" placeholder="Type a message or record English. Review the text, then Send." style="width:100%;max-width:640px;font-size:18px"></textarea>
      <div>
        <button data-action="record">Record in English</button>
        <button data-action="stop-record" disabled>Stop recording</button>
        <button data-action="send-chat">Send</button>
        <button data-action="clear-chat">Clear conversation</button>
      </div>
      <p data-role="speech-status" aria-live="polite"></p>
      <p data-role="chat-status" aria-live="polite"></p>
      <small>Record up to 10 seconds, then review the transcript. Chat messages do not save intake records.</small>
      <div><button data-action="chat-check">Start medication check</button><button data-action="new-check" hidden>Take a new photo</button><button data-action="chat-home">Back to home</button></div>
      </div>
      <div data-page="done" hidden>
        <h3>Intake record</h3><p data-role="completion" style="white-space:pre-wrap;font-size:20px"></p>
        <button data-action="next-check">Check another medication</button><button data-action="done-home">Back to home</button>
      </div>
      <div data-page="help" hidden>
        <h3>Medication check paused</h3><p data-role="help" style="white-space:pre-wrap;font-size:20px"></p>
        <button data-action="end-session">End session and return home</button>
      </div>
      <p data-role="reminder" style="white-space:pre-wrap;font-size:19px" aria-live="polite"></p>
      <details><summary>Demo reminders and family notifications</summary>
      <button data-action="new-demo">New demo (separate log)</button>
      <button data-action="start-reminder">Start schedule reminder</button>
      <button data-action="advance-demo">Advance 5 simulated minutes</button>
      <button data-action="normal-log">Return to regular log</button>
      <p data-role="simulation-status" aria-live="polite"></p>
      <p data-role="notifications" style="white-space:pre-wrap" aria-live="polite"></p>
      </details>
      <details><summary>Status and log</summary>
      <p data-role="schedule-log" style="white-space:pre-wrap" aria-live="polite"></p>
      <button data-action="refresh-log">Refresh status</button></details>
      <audio controls hidden></audio><p data-role="audio-note"></p>
      <div><button data-action="replay">Replay last response</button><button data-action="cancel-flow">Cancel session</button></div>
      <p data-role="flow-notice" aria-live="polite"></p>
      <p data-role="cancel-notice" hidden aria-live="polite">Devices are off. Cancelling the session; please wait for any current request to finish.</p>
    </div>`;
  const video = el.querySelector("video");
  const photo = el.querySelector("img");
  const audio = el.querySelector("audio");
  const openButton = el.querySelector('[data-action="open"]');
  const captureButton = el.querySelector('[data-action="capture"]');
  const closeButton = el.querySelector('[data-action="close"]');
  const cameraStatus = el.querySelector('[data-role="camera-status"]');
  const result = el.querySelector('[data-role="result"]');
  const audioNote = el.querySelector('[data-role="audio-note"]');
  const dialogueBox = el.querySelector('[data-role="dialogue"]');
  const draft = el.querySelector('[data-role="draft"]');
  const recordButton = el.querySelector('[data-action="record"]');
  const stopRecordButton = el.querySelector('[data-action="stop-record"]');
  const sendChatButton = el.querySelector('[data-action="send-chat"]');
  const clearChatButton = el.querySelector('[data-action="clear-chat"]');
  const speechStatus = el.querySelector('[data-role="speech-status"]');
  const chatStatus = el.querySelector('[data-role="chat-status"]');
  const pages = Object.fromEntries(["home", "check", "chat", "done", "help"].map(page => [page, el.querySelector(`[data-page="${page}"]`)]));
  const confirmDraft = el.querySelector('[data-role="confirm-draft"]');
  const confirmSpeechStatus = el.querySelector('[data-role="confirm-speech-status"]');
  const recordConfirmButton = el.querySelector('[data-action="record-confirm"]');
  const stopConfirmButton = el.querySelector('[data-action="stop-confirm"]');
  const submitReportButton = el.querySelector('[data-action="submit-report"]');
  const reminder = el.querySelector('[data-role="reminder"]');
  const simulationStatus = el.querySelector('[data-role="simulation-status"]');
  const notifications = el.querySelector('[data-role="notifications"]');
  const simulationButtons = ['new-demo','start-reminder','advance-demo','normal-log'].map(a=>el.querySelector(`[data-action="${a}"]`));
  const confirmPanel = el.querySelector('[data-role="confirm-panel"]');
  const confirmStatus = el.querySelector('[data-role="confirmation-status"]');
  const takenButton = el.querySelector('[data-action="taken"]');
  const notTakenButton = el.querySelector('[data-action="not-taken"]');
  const completion = el.querySelector('[data-role="completion"]');
  const help = el.querySelector('[data-role="help"]');
  const packageContext = el.querySelector('[data-role="package-context"]');
  const askCurrentButton = el.querySelector('[data-action="ask-current"]');
  const resumeCheckButton = el.querySelector('[data-action="chat-check"]');
  const newCheckButton = el.querySelector('[data-action="new-check"]');
  const generalUsesButton = el.querySelector('[data-action="general-uses"]');
  const sourceStatus = el.querySelector('[data-role="source-status"]');
  const sourceLinks = el.querySelector('[data-role="source-links"]');
  const replayButton = el.querySelector('[data-action="replay"]');
  const cancelButton = el.querySelector('[data-action="cancel-flow"]');
  const flowNotice = el.querySelector('[data-role="flow-notice"]');
  const cancelNotice = el.querySelector('[data-role="cancel-notice"]');
  const routeButtons = ["start-check", "start-chat", "check-home", "chat-check", "chat-home", "next-check", "done-home", "end-session", "new-check"]
    .map(action => el.querySelector(`[data-action="${action}"]`));
  let displayedPage = null;
  let cancelRequested = false;
  let stream = null;
  let generation = 0;
  let opening = false;
  let capturing = false;
  let disposed = false;
  let micStream = null;
  let recorder = null;
  let micOpening = false;
  let micFinishing = false;
  let micGeneration = 0;
  let recordingTimer = null;

  function updateButtons() {
    const busy = Boolean(model.get("busy"));
    const micActive = micOpening || micFinishing || recorder?.state === "recording";
    openButton.disabled = busy || opening || capturing || micActive;
    captureButton.disabled = busy || !stream || opening || capturing || micActive;
    closeButton.disabled = false;
    recordButton.disabled = busy || micActive || opening || capturing;
    stopRecordButton.disabled = !(micOpening || recorder?.state === "recording");
    sendChatButton.disabled = busy || micActive;
    clearChatButton.disabled = busy || micActive;
    draft.disabled = busy || micActive;
    for (const button of routeButtons) button.disabled = busy || micActive;
    takenButton.disabled = busy || micActive || !model.get("confirmation_ready");
    notTakenButton.disabled = busy || micActive || !model.get("confirmation_ready");
    askCurrentButton.disabled = busy || micActive || !model.get("has_current_photo");
    generalUsesButton.disabled = busy || micActive || !model.get("has_current_photo");
    replayButton.disabled = busy || micActive || !model.get("can_replay") || cancelRequested;
    cancelButton.disabled = false;
    recordConfirmButton.disabled = busy || micActive || !model.get("confirmation_ready");
    stopConfirmButton.disabled = !(micOpening || recorder?.state === "recording");
    submitReportButton.disabled = busy || micActive || !model.get("confirmation_ready");
    confirmDraft.disabled = busy || micActive;
    for (const b of simulationButtons) b.disabled = busy || micActive;
  }

  function stopCamera(message = "The camera is off.") {
    generation += 1;
    opening = false;
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
    video.pause();
    video.srcObject = null;
    video.hidden = true;
    cameraStatus.textContent = message;
    updateButtons();
  }

  async function openCamera() {
    stopCamera();
    audio.pause();
    model.set("confirmation_ready", false);
    model.set("has_current_photo", false);
    model.set("photo_clear_request", { id: String(Date.now()) + Math.random().toString(36) });
    model.save_changes();
    showConfirmation();
    const requestGeneration = generation;
    opening = true;
    updateButtons();
    cameraStatus.textContent = "Waiting for camera permission...";
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("Open this notebook through localhost, 127.0.0.1, or HTTPS.");
      }
      const requested = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      if (disposed || generation !== requestGeneration) {
        requested.getTracks().forEach(track => track.stop());
        return;
      }
      stream = requested;
      video.srcObject = stream;
      video.hidden = false;
      photo.hidden = true;
      await video.play();
      if (disposed || generation !== requestGeneration) return;
      opening = false;
      cameraStatus.textContent = "Live preview. Keep the full medication name and strength in view.";
      updateButtons();
    } catch (error) {
      if (generation !== requestGeneration || disposed) return;
      stopCamera("The camera could not be opened: " + (error.message || error.name) + ". Allow browser access and close other camera sessions.");
    }
  }

  async function capture() {
    if (!stream || model.get("busy") || capturing) return;
    const captureGeneration = generation;
    capturing = true;
    updateButtons();
    try {
      await new Promise((resolve, reject) => {
        if (video.requestVideoFrameCallback) {
          const timer = setTimeout(() => reject(new Error("No new frame received. Close and reopen the camera.")), 3000);
          video.requestVideoFrameCallback(() => { clearTimeout(timer); resolve(); });
        } else {
          setTimeout(resolve, 150);
        }
      });
      if (!stream || generation !== captureGeneration || disposed) return;
      if (!video.videoWidth || !video.videoHeight || video.readyState < 2) {
        throw new Error("The camera is not ready. Please wait and try again.");
      }
      const canvas = document.createElement("canvas");
      const ratio = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
      canvas.width = Math.round(video.videoWidth * ratio);
      canvas.height = Math.round(video.videoHeight * ratio);
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let dark = true;
      for (let i = 0; i < pixels.length; i += 256) {
        if (pixels[i] > 5 || pixels[i + 1] > 5 || pixels[i + 2] > 5) { dark = false; break; }
      }
      if (dark) throw new Error("The captured image is black. Check the lens and permissions, or close other camera applications.");
      const data = canvas.toDataURL("image/jpeg", 0.9);
      photo.src = data;
      photo.hidden = false;
      stopCamera("Photo captured; camera off. The image below is the one submitted for verification.");
      audio.pause();
      audio.hidden = true;
      audio.removeAttribute("src");
      result.textContent = "Checking the photo...";
      audioNote.textContent = "";
      model.set("busy", true);
      model.set("confirmation_ready", false);
      showConfirmation();
      model.set("request", { image: data, id: String(Date.now()) + Math.random().toString(36) });
      model.save_changes();
    } catch (error) {
      cameraStatus.textContent = error.message || String(error);
    } finally {
      capturing = false;
      updateButtons();
    }
  }

  const logText = el.querySelector('[data-role="schedule-log"]');
  const logButton = el.querySelector('[data-action="refresh-log"]');
  function showSchedule() { logText.textContent = model.get("schedule_text") || ""; }
  function refreshSchedule() {
    if (disposed || model.get("busy")) return;
    model.set("schedule_request", {id: String(Date.now()) + Math.random().toString(36)});
    model.save_changes();
  }
  logButton.addEventListener("click", refreshSchedule);
  const scheduleTimer = setInterval(refreshSchedule, 15000);
  function audioFailed() {
    if (disposed || cancelRequested || !model.get("audio_data")) return;
    audioNote.textContent = "Audio playback failed. The text is available; select Replay to retry.";
    model.set("playback_request", {kind:"error", id:String(Date.now()) + Math.random().toString(36)});
    model.save_changes();
  }
  audio.addEventListener("error", audioFailed);
  function showResult() { result.textContent = model.get("result_text") || ""; }
  function showAudio() {
    const data = model.get("audio_data");
    audioNote.textContent = model.get("audio_note") || "";
    if (!data) { audio.pause(); audio.removeAttribute("src"); audio.hidden = true; return; }
    audio.src = "data:audio/mpeg;base64," + data;
    audio.hidden = false;
    audio.play().catch(() => { audioNote.textContent = "Automatic playback was blocked. Select the audio play button."; });
  }
  function onMessage(message) {
    if (message?.type === "stop_camera") { stopCamera(); stopMic(false); }
  }

  function mirrorSpeechStatus() { confirmSpeechStatus.textContent = speechStatus.textContent; }
  function releaseMicTracks() {
    if (micStream) micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }

  function stopMic(submit = true) {
    micGeneration += 1;
    micOpening = false;
    clearTimeout(recordingTimer);
    if (recorder && recorder.state === "recording") {
      recorder.submitTranscript = submit;
      micFinishing = submit;
      recorder.stop();
    }
    releaseMicTracks();
    updateButtons();
  }

  async function startMic() {
    if (model.get("busy") || micOpening || micFinishing || recorder?.state === "recording") return;
    audio.pause();
    stopCamera("Camera off. Ready to record in English.");
    const requestGeneration = ++micGeneration;
    micOpening = true;
    speechStatus.textContent = "Waiting for microphone permission..."; mirrorSpeechStatus();
    updateButtons();
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        throw new Error("Recording is unavailable. Use localhost or HTTPS, or type your message.");
      }
      const requested = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      if (disposed || requestGeneration !== micGeneration) {
        requested.getTracks().forEach(track => track.stop());
        return;
      }
      micStream = requested;
      const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"]
        .find(type => MediaRecorder.isTypeSupported(type));
      const rec = new MediaRecorder(micStream, mime ? { mimeType: mime } : {});
      recorder = rec;
      rec.submitTranscript = true;
      const chunks = [];
      rec.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      rec.onerror = () => {
        rec.submitTranscript = false;
        stopMic(false);
        micFinishing = false;
        speechStatus.textContent = "Recording failed. Try again or type your message."; mirrorSpeechStatus();
        updateButtons();
      };
      rec.onstop = async () => {
        const stoppedGeneration = micGeneration;
        releaseMicTracks();
        clearTimeout(recordingTimer);
        recorder = null;
        try {
          if (disposed || !rec.submitTranscript) return;
          micFinishing = true;
          const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
          if (!blob.size) throw new Error("No audio was recorded. Please try again.");
          const data = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = () => reject(new Error("The recording could not be read."));
            reader.readAsDataURL(blob);
          });
          if (disposed || micGeneration !== stoppedGeneration) return;
          speechStatus.textContent = "Microphone off. Transcribing; the model may download on first use..."; mirrorSpeechStatus();
          model.set("busy", true);
          model.set("speech_request", { audio: data, id: String(Date.now()) + Math.random().toString(36) });
          model.save_changes();
        } catch (error) {
          speechStatus.textContent = error.message || String(error); mirrorSpeechStatus();
        } finally {
          micFinishing = false;
          updateButtons();
        }
      };
      micOpening = false;
      draft.value = "";confirmDraft.value = "";
      rec.start();
      speechStatus.textContent = "Recording in English. Select Stop when finished; maximum 10 seconds."; mirrorSpeechStatus();
      recordingTimer = setTimeout(() => stopMic(true), 10000);
      updateButtons();
    } catch (error) {
      micOpening = false;
      stopMic(false);
      speechStatus.textContent = "Recording unavailable: " + (error.message || error.name) + " You can type instead."; mirrorSpeechStatus();
      updateButtons();
    }
  }

  function sendChat() {
    const text = (draft.value || "").trim();
    if (model.get("busy") || !text) {
      if (!text) chatStatus.textContent = "Type a message or finish transcribing a recording first.";
      return;
    }
    chatStatus.textContent = "Sending...";
    audio.pause();
    model.set("busy", true);
    model.set("chat_request", { text, kind: "conversation", id: String(Date.now()) + Math.random().toString(36) });
    model.save_changes();
    draft.value = "";
    updateButtons();
  }

  function showConversation() {
    dialogueBox.replaceChildren();
    for (const message of model.get("dialogue_messages") || []) {
      const line = document.createElement("p");
      line.className = "mc-message " + (message.role === "user" ? "mc-user" : "mc-assistant");
      const content = (message.role === "user" ? "You: " : "MediConfirm: ") + String(message.content || "");
      if (message.role === "assistant" && /\*\*[^*]+\*\*/.test(content)) {
        const parts = content.split(/(\*\*[^*]+\*\*)/g);
        for (const part of parts) {
          if (!part) continue;
          const bold = part.startsWith("**") && part.endsWith("**");
          const node = document.createElement(bold ? "strong" : "span");
          node.textContent = bold ? part.slice(2,-2) : part;
          line.appendChild(node);
        }
      } else {
        line.textContent = content;
      }
      dialogueBox.appendChild(line);
    }
    dialogueBox.scrollTop = dialogueBox.scrollHeight;
  }
  function showDraft() { draft.value = model.get("draft_text") || ""; confirmDraft.value = draft.value; }
  function showSpeechStatus() {
    speechStatus.textContent = model.get("speech_status") || "";
    confirmSpeechStatus.textContent = speechStatus.textContent;
  }
  function showChatStatus() { chatStatus.textContent = model.get("chat_status") || ""; }
  function goTo(action) {
    if (model.get("busy")) return;
    stopCamera();
    stopMic(false);
    audio.pause();
    model.set("flow_request", { action, id: String(Date.now()) + Math.random().toString(36) });
    model.save_changes();
  }
  function showConfirmation() {
    confirmPanel.hidden = !model.get("confirmation_ready") || model.get("flow_page") !== "check";
    confirmStatus.textContent = model.get("confirmation_status") || "";
    updateButtons();
  }
  function showPage() {
    const page = model.get("flow_page") || "home";
    for (const [name, element] of Object.entries(pages)) element.hidden = cancelRequested || name !== page;
    cancelNotice.hidden = !cancelRequested;
    flowNotice.textContent = model.get("flow_notice") || "";
    cancelButton.hidden = page === "home" && !cancelRequested;
    if (page !== displayedPage) {
      stopCamera();
      stopMic(false);
      audio.pause();
      if (page === "check" && !model.get("has_current_photo")) { photo.hidden = true; photo.removeAttribute("src"); }
      displayedPage = page;
    }
    completion.textContent = model.get("completion_text") || "";
    help.textContent = model.get("help_text") || "";
    showConfirmation();
  }
  function confirm(status) {
    if (model.get("busy") || !model.get("confirmation_ready")) return;
    model.set("busy", true);
    model.set("confirm_request", { status, verification_id: model.get("verification_id"), id: String(Date.now()) + Math.random().toString(36) });
    model.save_changes();
    updateButtons();
  }
  function showPackageContext() {
    packageContext.textContent = model.get("package_context") || "No package has been checked yet.";
    resumeCheckButton.textContent = model.get("has_current_photo") ? "Return to this check / Confirm" : "Start medication check";
    newCheckButton.hidden = !model.get("has_current_photo");
    updateButtons();
  }
  function showSources() {
    sourceStatus.textContent = model.get("source_status") || "";
    sourceLinks.replaceChildren();
    for (const source of model.get("source_links") || []) {
      try {
        const url = new URL(source.url);
        if (url.protocol !== "https:" || url.hostname !== "dailymed.nlm.nih.gov") continue;
        const link = document.createElement("a");
        link.href = url.href;
        link.textContent = "Source: " + source.title + (source.date ? " (" + source.date + ")" : "");
        link.target = "_blank";link.rel = "noopener noreferrer";
        sourceLinks.appendChild(link);
      } catch (_) {  }
    }
  }
  function cancelFlow() {
    cancelRequested = true;
    stopCamera();stopMic(false);audio.pause();
    model.set("flow_request", { action: "cancel", id: String(Date.now()) + Math.random().toString(36) });
    model.save_changes();
    showPage();
  }
  function onCancelAcknowledged() { cancelRequested = false;showPage(); }
  function replay() {
    if (model.get("busy") || !model.get("can_replay")) return;
    if (model.get("audio_data") && !audio.error) {
      audio.currentTime = 0;
      audio.play().catch(() => { audioNote.textContent = "Select the audio play button."; });
    } else {
      model.set("busy", true);
      model.set("replay_request", (model.get("replay_request") || 0) + 1);
      model.save_changes();updateButtons();
    }
  }
  openButton.addEventListener("click", openCamera);
  captureButton.addEventListener("click", capture);
  const onClose = () => stopCamera();
  closeButton.addEventListener("click", onClose);
  recordButton.addEventListener("click", startMic);
  const onStopRecord = () => stopMic(true);
  stopRecordButton.addEventListener("click", onStopRecord);
  const onSendQuestion = () => sendChat();
  const onClearChat = () => {
    if (model.get("busy")) return;
    model.set("reset_request", (model.get("reset_request") || 0) + 1);
    model.save_changes();
  };
  sendChatButton.addEventListener("click", onSendQuestion);
  const routes = {"start-check": "check", "start-chat": "chat", "check-home": "home", "chat-check": "resume", "chat-home": "home", "next-check": "check", "done-home": "home", "end-session": "end", "new-check": "check"};
  for (const [name, action] of Object.entries(routes)) el.querySelector(`[data-action="${name}"]`).addEventListener("click", () => goTo(action));
  askCurrentButton.addEventListener("click", () => goTo("ask-current"));
  generalUsesButton.addEventListener("click", () => {
    if (model.get("busy") || !model.get("has_current_photo")) return;
    model.set("busy", true);
    model.set("use_request", (model.get("use_request") || 0) + 1);
    model.save_changes();updateButtons();
  });
  replayButton.addEventListener("click", replay);
  cancelButton.addEventListener("click", cancelFlow);
  recordConfirmButton.addEventListener("click", startMic);
  stopConfirmButton.addEventListener("click", onStopRecord);
  submitReportButton.addEventListener("click", () => {
    if (model.get("busy") || !model.get("confirmation_ready")) return;
    const text = (confirmDraft.value || "").trim();
    if (!text) { confirmStatus.textContent = "Enter or record your status, then review the text."; return; }
    model.set("busy", true);
    model.set("confirm_request", {text, verification_id:model.get("verification_id"), id:String(Date.now())+Math.random().toString(36)});
    model.save_changes();updateButtons();
  });
  function simulate(action) {
    if (model.get("busy")) return;
    stopCamera();stopMic(false);audio.pause();
    model.set("busy",true);
    model.set("simulation_request", {action,id:String(Date.now())+Math.random().toString(36)});
    model.save_changes();updateButtons();
  }
  for (const [button, action] of Object.entries({'new-demo':'new_demo','start-reminder':'remind','advance-demo':'advance','normal-log':'normal_log'})) {
    el.querySelector(`[data-action="${button}"]`).addEventListener("click",()=>simulate(action));
  }
  function showSimulation() {
    reminder.textContent=model.get("reminder_text") || "";
    simulationStatus.textContent=model.get("simulation_text") || "";
    notifications.textContent=model.get("notification_text") || "";
  }
  for (const field of ['reminder_text','simulation_text','notification_text']) model.on('change:'+field,showSimulation);
  showSimulation();
  takenButton.addEventListener("click", () => confirm("Taken"));
  notTakenButton.addEventListener("click", () => confirm("Pending"));
  clearChatButton.addEventListener("click", onClearChat);
  const onPageHide = () => { stopCamera(); stopMic(false); };
  window.addEventListener("pagehide", onPageHide);
  model.on("change:busy", updateButtons);
  model.on("change:result_text", showResult);
  model.on("change:audio_data", showAudio);
  model.on("change:audio_note", showAudio);
  model.on("msg:custom", onMessage);
  model.on("change:dialogue_messages", showConversation);
  model.on("change:draft_text", showDraft);
  model.on("change:speech_status", showSpeechStatus);
  model.on("change:chat_status", showChatStatus);
  model.on("change:flow_page", showPage);
  model.on("change:confirmation_ready", showConfirmation);
  model.on("change:confirmation_status", showConfirmation);
  model.on("change:completion_text", showPage);
  model.on("change:help_text", showPage);
  model.on("change:package_context", showPackageContext);
  model.on("change:has_current_photo", showPackageContext);
  model.on("change:source_status", showSources);
  model.on("change:source_links", showSources);
  model.on("change:can_replay", updateButtons);
  model.on("change:cancel_ack", onCancelAcknowledged);
  model.on("change:flow_notice", showPage);
  model.on("change:schedule_text", showSchedule);
  showSchedule();
  showResult();
  showConversation();
  showDraft();
  showSpeechStatus();
  showChatStatus();
  showPage();
  showPackageContext();
  showSources();
  updateButtons();
  return () => {
    disposed = true;
    clearInterval(scheduleTimer);
    for (const field of ['reminder_text','simulation_text','notification_text']) model.off('change:'+field,showSimulation);
    logButton.removeEventListener("click", refreshSchedule);
    audio.removeEventListener("error", audioFailed);
    model.off("change:schedule_text", showSchedule);
    stopCamera();
    stopMic(false);
    audio.pause();
    window.removeEventListener("pagehide", onPageHide);
    model.off("change:busy", updateButtons);
    model.off("change:result_text", showResult);
    model.off("change:audio_data", showAudio);
    model.off("change:audio_note", showAudio);
    model.off("msg:custom", onMessage);
    model.off("change:dialogue_messages", showConversation);
    model.off("change:draft_text", showDraft);
    model.off("change:speech_status", showSpeechStatus);
    model.off("change:chat_status", showChatStatus);
    model.off("change:flow_page", showPage);
    model.off("change:confirmation_ready", showConfirmation);
    model.off("change:confirmation_status", showConfirmation);
    model.off("change:completion_text", showPage);
    model.off("change:help_text", showPage);
    model.off("change:package_context", showPackageContext);
    model.off("change:has_current_photo", showPackageContext);
    model.off("change:source_status", showSources);
    model.off("change:source_links", showSources);
    model.off("change:can_replay", updateButtons);
    model.off("change:cancel_ack", onCancelAcknowledged);
    model.off("change:flow_notice", showPage);
  };
}
export default { render };
