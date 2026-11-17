import { DesktopCamera } from '/assets/desktop_camera.mjs';
import { SingleAudioPlayer } from '/assets/single_audio.mjs';

const $ = id => document.getElementById(id);
const pages = new Set(['home', 'check', 'chat', 'me', 'list', 'settings', 'history', 'family']);
const clientId = globalThis.crypto?.randomUUID?.() || `client-${Math.random().toString(36).slice(2)}`;
let state = null;
let tab = 'home';
let busy = false;
let refreshing = false;
let renderEpoch = 0;
let planSignature = '';
let historySignature = '';
let messageSignature = '';
let settingsDirty = false;
let clockOffset = 0;
let previewUrl = '';
let taskMetrics = null;
let recorder = null;
let microphone = null;
let recordingTimer = null;
let microphoneGeneration = 0;
let recordingPending = false;
let cancelWanted = false;
let lastServerDraft = '';
const seenAudio = new Set();
const failedAudio = new Set();

function readableEnglish(value){return String(value||'').replace(/\b([A-Za-z]+)[ \t\u00a0\u2009\u202f\u200b]*['’‘＇ʼ][ \t\u00a0\u2009\u202f\u200b]*(m|re|ve|ll|d|s|t)\b/gi,"$1'$2").replace(/([A-Za-z0-9])[ \t\u00a0\u2009\u202f]+,/g,'$1,').replace(/([A-Za-z]),[ \t]*(?=[A-Za-z0-9])/g,'$1, ').replace(/([A-Za-z])，[ \t]*(?=[A-Za-z0-9])/g,'$1, ');}

if (location.search) history.replaceState(null, '', location.pathname);

const player = new SingleAudioPlayer($('audio'), $('audioParking'), {
  channel: typeof BroadcastChannel === 'function' ? new BroadcastChannel('mediconfirm-audio') : null
});
const camera = new DesktopCamera($('cameraVideo'), {
  changed: (active, opening) => {
    $('cameraPanel').hidden = !active && !opening;
    $('openCamera').hidden = active || opening;
    $('capturePhoto').hidden = !active;
    $('closeCamera').hidden = !active;
    $('cameraStatus').textContent = opening
      ? 'Waiting for camera permission…'
      : active
        ? 'Live preview. Keep the whole label in view.'
        : 'Camera is off.';
    updateControls();
  }
});

function notice(message) {
  $('notice').textContent = message || '';
}

function setBusy(value) {
  busy = value;
  $('busy').hidden = !value;
  document.body.classList.toggle('is-busy', value);
  document.querySelectorAll('button, input, select, textarea').forEach(control => {
    if (value) {
      if (!control.disabled) control.dataset.wasEnabled = 'true';
      control.disabled = true;
    } else if (control.dataset.wasEnabled === 'true') {
      control.disabled = false;
      delete control.dataset.wasEnabled;
    }
  });
  updateControls();
  if (!value && cancelWanted) queueMicrotask(cancelSession);
}

function updateControls() {
  $('openCamera').disabled = busy || camera.opening;
  $('capturePhoto').disabled = busy || !camera.stream || camera.opening;
  $('closeCamera').disabled = busy || !camera.stream;
  $('record').hidden = !!recorder;
  $('stopRecord').hidden = !recorder;
  $('record').disabled = busy || recordingPending || !!recorder || !navigator.mediaDevices?.getUserMedia;
  $('stopRecord').disabled = busy || !recorder;
  $('send').disabled = busy || !$('draft').value.trim();
  $('sendTestEmail').disabled = busy || !state?.mail_ready ||
    !state?.settings?.real_email_enabled || !state?.settings?.caregiver_email;
  $('cancel').disabled = false;
}

async function request(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('The server returned an unreadable response. Please try again.');
  }
  if (!response.ok) throw new Error(data.error || 'Please try again.');
  return data;
}

function metricsPayload() {
  if (!taskMetrics) return null;
  return {
    task_id: taskMetrics.id,
    client_elapsed_ms: performance.now() - taskMetrics.start,
    clicks: taskMetrics.clicks.slice(-100)
  };
}

function beginLocalTask() {
  if (!taskMetrics) {
    taskMetrics = {
      id: globalThis.crypto?.randomUUID?.() || `task-${Math.random().toString(36).slice(2)}`,
      start: performance.now(),
      clicks: []
    };
  }
}

function finishLocalTask() {
  taskMetrics = null;
}

document.addEventListener('click', event => {
  if (!taskMetrics) return;
  const button = event.target.closest?.('button');
  if (!button || button.disabled) return;
  taskMetrics.clicks.push({
    id: `${clientId}-${taskMetrics.clicks.length}`,
    button: button.id || button.dataset.nav || button.dataset.go || button.textContent.trim().slice(0, 80),
    offset_ms: performance.now() - taskMetrics.start,
    page: tab,
    verification_status: state?.verification_status || ''
  });
}, true);

async function act(action, extras = {}) {
  if (busy) return false;
  $('busy').textContent = action === 'chat'
    ? 'MediConfirm is thinking and preparing audio…'
    : 'Please wait…';
  setBusy(true);
  if (action === 'chat') showChatPending(extras.text);
  renderEpoch++;
  notice('');
  try {
    const data = await request('/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...extras, client_id: clientId, metrics: metricsPayload() })
    });
    render(data, { autoplay: true });
    if (action === 'confirm' && state?.flow_page === 'done') finishLocalTask();
    if (action === 'flow' && extras.value === 'cancel') finishLocalTask();
    return true;
  } catch (error) {
    document.querySelectorAll('.pending-message').forEach(message => message.remove());
    notice(error.message);
    return false;
  } finally {
    setBusy(false);
  }
}

function showChatPending(text) {
  const container = $('messages');
  const user = document.createElement('article');
  user.className = 'message user pending-message';
  user.textContent = readableEnglish(text || '');
  const assistant = document.createElement('article');
  assistant.className = 'message assistant pending-message';
  assistant.setAttribute('role', 'status');
  assistant.textContent = 'MediConfirm is thinking and preparing the spoken reply…';
  container.append(user, assistant);
  assistant.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function showTab(name, sync = true) {
  if (!pages.has(name)) return;
  if (name !== tab) player.stop();
  if (name !== 'check') camera.stop();
  if (name !== 'chat') stopRecording(false);
  if (!['home', 'check', 'chat'].includes(name)) $('audio').pause();
  tab = name;
  document.querySelectorAll('[data-tab]').forEach(page => {
    page.hidden = page.dataset.tab !== name;
  });
  document.querySelectorAll('[data-nav]').forEach(button => {
    const activeTab = ['list', 'settings', 'history', 'family'].includes(name)
      ? 'me'
      : name === 'check' ? 'home' : name;
    button.classList.toggle('active', button.dataset.nav === activeTab);
  });
  $('footerControls').hidden = name !== 'check';
  $('sourceCard').hidden = !state?.source_status || !['check', 'chat'].includes(name);
  if (sync) syncAudio(false);
}

function setText(id, value) {
  $(id).textContent = readableEnglish(value);
}

function render(data, { autoplay = false } = {}) {
  const previousFlow = state?.flow_page;
  state = data;
  setText('result', data.result_text);
  setText('liveReminderText', data.reminder_text);
  $('liveReminder').hidden = !data.reminder_text;
  setText('confirmStatus', data.confirmation_status);
  setText('completion', data.completion_text);
  setText('help', data.help_text);
  setText('context', data.package_context);
  $('context').hidden = !data.package_context;
  $('resultCard').hidden = !data.has_current_photo &&
    !data.result_text?.startsWith('Recognition could not') &&
    !data.result_text?.startsWith('Unable to read');
  $('confirmation').hidden = !data.confirmation_ready;
  $('completionCard').hidden = data.flow_page !== 'done';
  $('helpCard').hidden = data.flow_page !== 'help';
  $('resultBadge').textContent = data.verification_status || 'Check result';
  setText('speechStatus', data.speech_status ||
    (!navigator.mediaDevices?.getUserMedia ? 'Live recording needs HTTPS. You can type or upload a recording here.' : ''));

  renderPlan();
  renderHistory();
  renderMessages(data.dialogue_messages || []);
  renderSources(data);
  syncSettings(data.settings);
  updateClock(data.server_time);
  renderSelectedMedication(data);

  if (data.flow_page !== previousFlow && ['help', 'done'].includes(data.flow_page)) {
    camera.stop();
    showTab('check', false);
  }
  syncAudio(autoplay);
  updateControls();
}

function historyCard(title, lines) {
  const card = document.createElement('article');
  card.className = 'card history-card';
  const heading = document.createElement('h2');
  heading.textContent = title;
  card.appendChild(heading);
  for (const line of lines) {
    const paragraph = document.createElement('p');
    paragraph.textContent = line;
    card.appendChild(paragraph);
  }
  return card;
}

function renderPlan() {
  if (!state) return;
  const plan = state.daily_plan || [];
  const signature = JSON.stringify([plan, state.current_plan_time, state.current_plan_kind]);
  if (signature === planSignature) return;
  planSignature = signature;
  const container = $('dailyPlan');
  container.replaceChildren();
  const sorted = [...plan].sort((a, b) =>
    (a.time === state.current_plan_time ? 0 : 1) -
    (b.time === state.current_plan_time ? 0 : 1) || a.time.localeCompare(b.time));
  let readAdded = false;
  for (const event of sorted) {
    const current = event.time === state.current_plan_time;
    const status = event.status === 'Taken'
      ? 'Taken — confirmed'
      : event.status === 'Pending' ? 'Awaiting confirmation'
        : event.status === 'Unconfirmed' ? 'Unconfirmed' : 'Scheduled';
    const card = historyCard(`${event.name} · ${event.strength}`, [
      `Scheduled for ${event.time} · ${event.dose}`,
      status
    ]);
    card.className = `plan-card${current ? ' current-plan' : ''}`;
    const label = document.createElement('p');
    label.className = current ? 'plan-label' : 'small';
    label.textContent = current
      ? state.current_plan_kind === 'upcoming' ? 'NEXT SCHEDULE' : 'CURRENT SCHEDULE'
      : event.time < state.current_plan_time ? 'Earlier today' : 'Later today';
    card.prepend(label);

    const actions = document.createElement('div');
    actions.className = 'plan-actions';
    const check = document.createElement('button');
    check.className = event.status === 'Taken' ? 'secondary' : 'primary';
    check.textContent = event.status === 'Taken' ? 'View record' : 'Check medication';
    check.addEventListener('click', async () => {
      if (event.status === 'Taken') {
        $('historyFilter').value = 'Taken';
        historySignature = '';
        renderHistory();
        showTab('history');
        return;
      }
      if (await act('select_event', { event_id: event.event_id })) {
        finishLocalTask();
        clearPreview();
        showTab('check');
      }
    });
    actions.appendChild(check);
    if (current && !readAdded) {
      readAdded = true;
      const read = document.createElement('button');
      read.className = 'quiet';
      read.textContent = 'Read this plan aloud';
      read.addEventListener('click', () => act('read_plan'));
      actions.appendChild(read);
      const slot = document.createElement('div');
      slot.id = 'planAudio';
      slot.dataset.planTime = event.time;
      slot.className = 'response-audio';
      card.appendChild(slot);
    }
    card.appendChild(actions);
    container.appendChild(card);
  }
  if (!plan.length) {
    container.textContent = 'No medications saved yet. Add your medication list in Me.';
  }
}

function renderHistory() {
  if (!state) return;
  const filter = $('historyFilter').value;
  const signature = JSON.stringify([state.history_records, state.family_notifications, filter]);
  if (signature === historySignature) return;
  historySignature = signature;
  const container = $('historyRecords');
  container.replaceChildren();
  const records = (state.history_records || []).filter(event => filter === 'all' || event.status === filter);
  for (const event of records) {
    const reason = String(event.display_reason || 'No confirmation was received before the time limit')
      .trim()
      .replace(/\.$/, '');
    const status = event.status === 'Unconfirmed'
      ? `${event.status} - ${reason}`
      : event.status;
    const card = historyCard(`${event.name} · ${event.strength}`, [
      status,
      `Scheduled: ${event.display_scheduled} (Hong Kong)`,
      `Dose in list: ${event.recorded_dose}`,
      `Last update: ${event.display_updated}`
    ]);
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Status changes';
    details.appendChild(summary);
    for (const change of event.history || []) {
      const paragraph = document.createElement('p');
      paragraph.textContent = `${change.display_at} — ${change.status}: ${change.display_reason}`;
      details.appendChild(paragraph);
    }
    card.appendChild(details);
    container.appendChild(card);
  }
  if (!records.length) container.textContent = 'No matching records yet.';

  const notices = $('notificationRecords');
  notices.replaceChildren();
  for (const item of state.family_notifications || []) {
    const card = historyCard(item.subject || 'Family notification', [
      deliveryLabel(item.delivery_status),
      `To: ${item.recipient || 'No recipient saved'}`,
      displayTime(item.at),
      item.message || ''
    ]);
    if (['failed', 'not_configured', 'not_enabled'].includes(item.delivery_status)) {
      const retry = document.createElement('button');
      retry.className = 'secondary';
      retry.textContent = 'Retry email';
      retry.addEventListener('click', () => act('retry_email', { notification_id: item.notification_id }));
      card.appendChild(retry);
    }
    notices.appendChild(card);
  }
  if (!notices.childNodes.length) notices.textContent = 'No family notifications yet.';
}

function deliveryLabel(status) {
  return {
    submitted: 'Submitted to the email provider',
    sending: 'Sending email…',
    failed: 'Email failed — retry available',
    delivery_unknown: 'Delivery uncertain — check the inbox before retrying',
    not_enabled: 'Not sent — real email alerts are off',
    not_configured: 'Not sent — sender or recipient is not configured',
    legacy_not_sent: 'Not sent — historical notification',
    simulated_not_sent: 'Not sent — historical preview'
  }[status] || 'Not sent';
}

function displayTime(value) {
  if (!value) return 'Time not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time not recorded';
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Hong_Kong',
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
}

function renderMessages(messages) {
  const signature = JSON.stringify(messages);
  if (signature !== messageSignature) {
    messageSignature = signature;
    const container = $('messages');
    container.replaceChildren();
    for (const message of messages) {
      const article = document.createElement('article');
      article.className = `message ${message.role === 'user' ? 'user' : 'assistant'}`;
      const body = document.createElement('div');
      const parts = String(message.content || '').split(/(\*\*[^*]+\*\*)/g);
      for (const part of parts) {
        const bold = part.startsWith('**') && part.endsWith('**');
        const node = document.createElement(bold ? 'strong' : 'span');
        node.textContent = readableEnglish(bold ? part.slice(2, -2) : part);
        body.appendChild(node);
      }
      article.appendChild(body);
      if (message.role === 'assistant' && message.message_id) {
        const audio = document.createElement('div');
        audio.dataset.messageId = message.message_id;
        audio.className = 'response-audio';
        article.appendChild(audio);
      }
      container.appendChild(article);
    }
  }
  if (state?.draft_text !== lastServerDraft) {
    lastServerDraft = state?.draft_text || '';
    $('draft').value = lastServerDraft;
  }
}

function renderSources(data) {
  const sources = $('sources');
  sources.replaceChildren();
  for (const source of data.source_links || []) {
    try {
      const url = new URL(source.url);
      if (url.protocol !== 'https:' || url.hostname !== 'dailymed.nlm.nih.gov') continue;
      const link = document.createElement('a');
      link.href = url.href;
      link.textContent = source.title;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      sources.appendChild(link);
    } catch {
      continue;
    }
  }
  setText('sourceStatus', data.source_status);
  setText('excerpt', data.source_excerpt);
  $('sourceCard').hidden = !data.source_status || !['check', 'chat'].includes(tab);
}

function renderSelectedMedication(data) {
  const target = (data.medications || []).filter(med =>
    med.time === data.selected_time &&
    (!data.target_medication_id || med.medication_id === data.target_medication_id));
  setText('selectedMedication', target.map(med =>
    `${med.name} · ${med.strength} · ${med.dose} · ${med.time}`).join('\n'));
  setText('mailStatus', data.mail_ready
    ? 'Sender account configured on this computer.'
    : 'Sender account is not configured. Run configure_email.py once on this computer.');
}

function audioSlot(clip) {
  if (clip.scope === 'home') {
    if (clip.target === 'reminder') return $('reminderAudio');
    const slot = $('planAudio');
    return slot && clip.target === `plan:${slot.dataset.planTime}` ? slot : null;
  }
  if (clip.scope === 'check') {
    return $({
      result: 'resultAudio',
      confirmation: 'confirmationAudio',
      completion: 'completionAudio',
      help: 'helpAudio'
    }[clip.target] || 'resultAudio');
  }
  if (clip.scope === 'chat') {
    return [...document.querySelectorAll('[data-message-id]')]
      .find(element => element.dataset.messageId === clip.target) || null;
  }
  return null;
}

function syncAudio(autoplay) {
  if (!state) return;
  const clips = state.audio_clips || [];
  const valid = new Set(clips.map(clip => clip.id));
  if (player.activeId && !valid.has(player.activeId)) player.stop();
  for (const slot of document.querySelectorAll('.response-audio')) {
    if (slot.dataset.clipId && !valid.has(slot.dataset.clipId)) {
      slot.replaceChildren();
      delete slot.dataset.clipId;
    }
  }
  let latest = null;
  for (const clip of clips) {
    const slot = audioSlot(clip);
    const unseen = !seenAudio.has(clip.id);
    seenAudio.add(clip.id);
    if (!slot) continue;
    if (slot.dataset.clipId !== clip.id) {
      slot.dataset.clipId = clip.id;
      slot.replaceChildren();
      const listen = document.createElement('button');
      const isReminder = clip.scope === 'home' && clip.target === 'reminder';
      const preparing = clip.status === 'preparing';
      listen.className = isReminder ? 'reminder-listen' : 'quiet';
      listen.textContent = preparing ? 'Preparing audio…' : 'Listen';
      listen.disabled = preparing;
      listen.addEventListener('click', async () => {
        if (preparing) return;
        if (clip.note || failedAudio.has(clip.id)) {
          await act('replay_clip', { clip_id: clip.id });
          return;
        }
        try {
          await player.play(clip, slot);
        } catch (error) {
          notice(error.message);
        }
      });
      slot.appendChild(listen);
      if (clip.note) {
        const note = document.createElement('p');
        note.className = 'small';
        note.textContent = clip.note;
        slot.appendChild(note);
      }
    }
    player.restore(clip, slot);
    if (unseen && clip.scope === tab && clip.status !== 'preparing' && !clip.note) {
      latest = { clip, slot };
    }
  }
  if (latest && latest.clip.target !== 'reminder' && autoplay &&
      document.visibilityState !== 'hidden') {
    const requested = latest;
    request('/api/audio/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clip_id: requested.clip.id })
    }).then(result => {
      if (result.allowed && tab === requested.clip.scope) {
        return player.play(requested.clip, requested.slot).catch(error => notice(error.message));
      }
      return undefined;
    }).catch(error => notice(error.message));
  }
}

function updateClock(serverTime) {
  if (serverTime) clockOffset = Date.parse(serverTime) - Date.now();
  $('clock').textContent = `${new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Hong_Kong',
    dateStyle: 'medium',
    timeStyle: 'medium'
  }).format(new Date(Date.now() + clockOffset))} · Hong Kong`;
}

function clearPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = '';
  $('preview').removeAttribute('src');
  $('preview').hidden = true;
}

async function preparePhoto() {
  player.stop();
  const success = await act('prepare_photo');
  if (success) {
    $('confirmation').hidden = true;
    clearPreview();
  }
  return success;
}

async function uploadPhoto(file) {
  if (!file || busy) return;
  camera.stop();
  if (!await preparePhoto()) return;
  setBusy(true);
  notice('');
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const ratio = Math.min(1, 1600 / Math.max(image.width, image.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.width * ratio));
    canvas.height = Math.max(1, Math.round(image.height * ratio));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('The selected photo could not be prepared.');
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
    if (!blob) throw new Error('Photo conversion failed. Choose another image and try again.');
    clearPreview();
    previewUrl = URL.createObjectURL(blob);
    $('preview').src = previewUrl;
    $('preview').hidden = false;
    const body = new FormData();
    body.append('photo', blob, 'photo.jpg');
    beginLocalTask();
    body.append('task_id', taskMetrics.id);
    body.append('client_id', clientId);
    const data = await request('/api/photo', { method: 'POST', body });
    render(data, { autoplay: true });
    if (state?.flow_page === 'done') finishLocalTask();
    showTab('check');
  } catch (error) {
    notice(error.message || 'Choose a JPEG or PNG photo.');
    $('confirmation').hidden = true;
    $('resultCard').hidden = true;
  } finally {
    URL.revokeObjectURL(url);
    setBusy(false);
  }
}

async function uploadAudio(file) {
  if (!file || busy) return;
  setBusy(true);
  notice('');
  try {
    const body = new FormData();
    body.append('audio', file, file.name || 'recording');
    render(await request('/api/speech', { method: 'POST', body }), { autoplay: true });
  } catch (error) {
    notice(error.message);
  } finally {
    setBusy(false);
  }
}

async function stopRecording(submit = true) {
  microphoneGeneration++;
  recordingPending = false;
  clearTimeout(recordingTimer);
  recordingTimer = null;
  if (recorder && recorder.state === 'recording') {
    recorder.discard = !submit;
    recorder.stop();
  }
  if (microphone) microphone.getTracks().forEach(track => track.stop());
  microphone = null;
  updateControls();
}

async function startRecording() {
  if (recorder || busy || recordingPending) return;
  const generation = ++microphoneGeneration;
  recordingPending = true;
  updateControls();
  try {
    $('audio').pause();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (generation !== microphoneGeneration) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    microphone = stream;
    recorder = new MediaRecorder(stream);
    const parts = [];
    recorder.addEventListener('dataavailable', event => {
      if (event.data.size) parts.push(event.data);
    });
    recorder.addEventListener('stop', async () => {
      const finished = recorder;
      const type = finished?.mimeType || 'audio/webm';
      recorder = null;
      if (microphone) microphone.getTracks().forEach(track => track.stop());
      microphone = null;
      $('speechStatus').textContent = '';
      updateControls();
      if (finished && !finished.discard) await uploadAudio(new Blob(parts, { type }));
    }, { once: true });
    recorder.start();
    recordingPending = false;
    $('speechStatus').textContent = 'Recording. Tap Stop when finished.';
    updateControls();
    recordingTimer = setTimeout(() => stopRecording(true), 10000);
  } catch (error) {
    await stopRecording(false);
    notice(error.message || 'Recording unavailable. Type or upload a recording instead.');
  } finally {
    recordingPending = false;
    updateControls();
  }
}

function timeWheel(value = '08:00') {
  const wrap = document.createElement('div');
  wrap.className = 'time-wheel';
  const parts = value.split(':');
  for (const [kind, total, initial] of [
    ['hour', 24, parts[0]],
    ['minute', 60, parts[1]]
  ]) {
    const select = document.createElement('select');
    select.dataset.timePart = kind;
    select.size = 3;
    select.setAttribute('aria-label', kind === 'hour' ? 'Hour' : 'Minute');
    for (let i = 0; i < total; i++) {
      const option = document.createElement('option');
      option.value = String(i).padStart(2, '0');
      option.textContent = option.value;
      select.appendChild(option);
    }
    select.value = initial || '00';
    wrap.appendChild(select);
    if (kind === 'hour') {
      const separator = document.createElement('span');
      separator.className = 'time-separator';
      separator.textContent = ':';
      wrap.appendChild(separator);
    }
  }
  return wrap;
}

function makeIcon(paths) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  for (const value of paths) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', value);
    svg.appendChild(path);
  }
  return svg;
}

function addMedicationRow(medication = {}) {
  const row = document.createElement('div');
  row.className = 'med-row';
  const fields = document.createElement('div');
  fields.className = 'med-fields';
  for (const [key, labelText, placeholder] of [
    ['name', 'Medication name', 'As printed on the label'],
    ['strength', 'Strength', '50 mg'],
    ['dose', 'Dose per intake', '1 tablet']
  ]) {
    const label = document.createElement('label');
    label.textContent = labelText;
    const input = document.createElement('input');
    input.dataset.field = key;
    input.value = medication[key] || '';
    input.placeholder = placeholder;
    label.appendChild(input);
    fields.appendChild(label);
  }
  const times = document.createElement('div');
  times.className = 'intake-times';
  const timesTitle = document.createElement('p');
  timesTitle.className = 'intake-times-title';
  timesTitle.textContent = 'Add alarm';
  times.appendChild(timesTitle);
  for (const time of (medication.time || '08:00').split(';')) times.appendChild(timeWheel(time));
  const addTime = document.createElement('button');
  addTime.type = 'button';
  addTime.textContent = '+ Add intake time';
  addTime.className = 'secondary add-time';
  const removeTime = document.createElement('button');
  removeTime.type = 'button';
  removeTime.className = 'quiet remove-time';
  removeTime.append(makeIcon(['M5 12h14']), document.createTextNode('Remove time'));
  removeTime.disabled = times.querySelectorAll('.time-wheel').length === 0;
  removeTime.addEventListener('click', () => {
    const wheels = times.querySelectorAll('.time-wheel');
    wheels[wheels.length - 1]?.remove();
    removeTime.disabled = wheels.length <= 1;
  });
  addTime.addEventListener('click', () => {
    times.appendChild(timeWheel());
    removeTime.disabled = false;
  });
  const removeMedication = document.createElement('button');
  removeMedication.type = 'button';
  removeMedication.className = 'quiet remove-medication';
  removeMedication.append(
    makeIcon(['M3 6h18m-2 0-.8 14H5.8L5 6m4 0V4h6v2', 'M10 11v5m4-5v5']),
    document.createTextNode('Remove medication')
  );
  removeMedication.addEventListener('click', () => row.remove());
  const actions = document.createElement('div');
  actions.className = 'med-row-actions';
  actions.append(addTime, removeTime, removeMedication);
  row.append(fields, times, actions);
  $('medRows').appendChild(row);
}

function fillMedicationList() {
  $('medRows').replaceChildren();
  const groups = new Map();
  for (const medication of state?.medications || []) {
    const key = JSON.stringify([medication.name, medication.strength, medication.dose]);
    if (!groups.has(key)) groups.set(key, { ...medication });
    else groups.get(key).time += `;${medication.time}`;
  }
  for (const medication of groups.values()) addMedicationRow(medication);
  if (!groups.size) addMedicationRow();
}

function readMedicationRows() {
  return [...document.querySelectorAll('.med-row')].map(row => {
    const result = {};
    for (const input of row.querySelectorAll('input[data-field]')) {
      result[input.dataset.field] = input.value.trim();
    }
    result.time = [...row.querySelectorAll('.time-wheel')]
      .map(wheel => [...wheel.querySelectorAll('select')]
        .map(select => select.value).join(':'))
      .filter(Boolean)
      .join(';');
    return result;
  });
}

function syncSettings(settings) {
  if (!settings || settingsDirty) return;
  $('autoReminders').checked = settings.reminders_enabled;
  $('timeoutSeconds').value = settings.timeout_seconds;
  $('repeatSeconds').value = settings.repeat_seconds;
  $('caregiverEmail').value = settings.caregiver_email;
  $('realEmailEnabled').checked = settings.real_email_enabled;
}

async function savePreferences() {
  const timeout = Number($('timeoutSeconds').value);
  const repeat = Number($('repeatSeconds').value);
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 86400 ||
      !Number.isFinite(repeat) || repeat <= 0 || repeat >= timeout) {
    notice('Enter positive delays in seconds. The repeat reminder must be earlier than the notification timeout.');
    return;
  }
  if (!$('caregiverEmail').checkValidity()) {
    $('caregiverEmail').reportValidity();
    return;
  }
  const settings = {
    real_email_enabled: $('realEmailEnabled').checked,
    timeout_seconds: timeout,
    repeat_seconds: repeat,
    reminders_enabled: $('autoReminders').checked,
    caregiver_email: $('caregiverEmail').value.trim()
  };
  if (await act('settings', { settings })) {
    settingsDirty = false;
    syncSettings(state.settings);
    setText('settingsStatus', 'Settings saved. New events use these delays.');
    setText('familyStatus', 'Email settings saved. Check the delivery status below.');
  }
}

function cancelSession() {
  camera.stop();
  stopRecording(false);
  $('audio').pause();
  clearPreview();
  if (busy) {
    cancelWanted = true;
    notice('Cancelling. Please wait for the current request to finish.');
    return;
  }
  cancelWanted = false;
  act('flow', { value: 'cancel' }).then(success => {
    if (success) showTab('home');
  });
}

async function refresh() {
  if (busy || recorder || recordingPending || refreshing) return;
  refreshing = true;
  const epoch = renderEpoch;
  try {
    const data = await request('/api/state');
    if (!busy && epoch === renderEpoch) {
      render(data);
      setBusy(false);
    }
  } catch (error) {
    if (!state) notice(error.message);
  } finally {
    refreshing = false;
  }
}

document.querySelectorAll('[data-nav]').forEach(button => {
  button.addEventListener('click', () => showTab(button.dataset.nav));
});
document.querySelectorAll('[data-go]').forEach(button => {
  button.addEventListener('click', () => {
    const destination = button.dataset.go;
    if (destination === 'list') fillMedicationList();
    showTab(destination);
  });
});
document.querySelectorAll('[data-flow]').forEach(button => {
  button.addEventListener('click', async () => {
    if (button.dataset.flow === 'resume' && !state?.has_current_photo) {
      showTab('home');
      return;
    }
    const success = await act('flow', { value: button.dataset.flow });
    if (!success) return;
    if (button.dataset.flow === 'end') showTab('home');
    else if (button.dataset.tabGo) showTab(button.dataset.tabGo);
  });
});

$('openCamera').addEventListener('click', async () => {
  if (busy || !await preparePhoto()) return;
  try {
    await camera.open();
  } catch (error) {
    $('cameraStatus').textContent = error.message;
  }
});
$('closeCamera').addEventListener('click', () => camera.stop());
$('capturePhoto').addEventListener('click', async () => {
  if (busy) return;
  try {
    const photo = await camera.capture(document.createElement('canvas'));
    if (photo) await uploadPhoto(photo);
  } catch (error) {
    $('cameraStatus').textContent = error.message;
  }
});
$('uploadPhoto').addEventListener('change', event => {
  const file = event.target.files[0];
  event.target.value = '';
  uploadPhoto(file);
});
$('chooseImage').addEventListener('click', () => $('uploadPhoto').click());
$('uploadAudio').addEventListener('click', () => $('audioFile').click());
$('audioFile').addEventListener('change', event => {
  const file = event.target.files[0];
  event.target.value = '';
  uploadAudio(file);
});
$('uses').addEventListener('click', async () => {
  showTab('chat');
  await act('uses');
});
$('taken').addEventListener('click', () =>
  act('confirm', { status: 'Taken', verification_id: state?.verification_id }));
$('pending').addEventListener('click', () =>
  act('confirm', { status: 'Pending', verification_id: state?.verification_id }));
$('submitReport').addEventListener('click', () =>
  act('confirm', { text: $('report').value, verification_id: state?.verification_id }));
$('record').addEventListener('click', startRecording);
$('stopRecord').addEventListener('click', () => stopRecording(true));
$('draft').addEventListener('input', updateControls);
$('send').addEventListener('click', async () => {
  const value = $('draft').value.trim();
  if (!value) return;
  if (await act('chat', { text: value }) && state?.chat_status?.startsWith('Reply ready')) {
    $('draft').value = '';
    lastServerDraft = '';
  }
});
$('clearChat').addEventListener('click', () => {
  player.stop();
  act('clear_chat');
});
$('cancel').addEventListener('click', cancelSession);
$('addMed').addEventListener('click', () => addMedicationRow());
$('saveList').addEventListener('click', async () => {
  if (await act('save_list', { medications: readMedicationRows() })) {
    setText('listStatus', 'Medication list saved.');
    notice('');
  }
});
$('historyFilter').addEventListener('change', () => {
  historySignature = '';
  renderHistory();
});
$('saveSettings').addEventListener('click', savePreferences);
$('saveFamily').addEventListener('click', savePreferences);
$('sendTestEmail').addEventListener('click', () => act('send_test_email'));
for (const id of ['autoReminders', 'repeatSeconds', 'timeoutSeconds', 'caregiverEmail', 'realEmailEnabled']) {
  $(id).addEventListener('input', () => {
    settingsDirty = true;
    updateControls();
  });
}
$('audio').addEventListener('error', () => {
  if (player.activeId) failedAudio.add(player.activeId);
  const slot = $('audio').parentNode;
  if (slot && slot !== $('audioParking')) {
    const message = document.createElement('p');
    message.className = 'small';
    message.textContent = 'Audio could not play. Read the text or select Listen to retry.';
    slot.appendChild(message);
  }
});
window.addEventListener('pagehide', () => {
  camera.stop();
  stopRecording(false);
  $('audio').pause();
});

setInterval(() => {
  const metrics = metricsPayload();
  if (metrics?.clicks.length) {
    request('/api/metrics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(metrics)
    }).catch(error => notice(error.message));
  }
}, 1000);
setInterval(refresh, 1000);
setInterval(() => updateClock(), 1000);
refresh();
