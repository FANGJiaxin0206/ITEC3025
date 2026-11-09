import assert from 'node:assert/strict';
import component from '../src/mediconfirm/simple_camera.mjs';

function fixture(getUserMedia, dark = false, page = 'check') {
  const elements = new Map();
  function element() {
    return {
      hidden: false, disabled: false, textContent: '', src: '', srcObject: null,
      value: '', children: [],
      videoWidth: 640, videoHeight: 480, readyState: 4,
      listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      removeEventListener() {},
      replaceChildren(...children) { this.children = children; },
      appendChild(child) { this.children.push(child); },
      pause() {}, async play() {},
      removeAttribute(key) { delete this[key]; },
      requestVideoFrameCallback(fn) { queueMicrotask(fn); },
    };
  }
  globalThis.window = { isSecureContext: true, addEventListener() {}, removeEventListener() {} };
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia } } });
  globalThis.document = { createElement() { return { ...element(),
    getContext() { return { drawImage() {}, getImageData() { return { data: new Uint8Array(16).fill(dark ? 0 : 30) }; } }; },
    toDataURL() { return 'data:image/jpeg;base64,actual-captured-image'; },
  }; } };
  const values = { busy: false, result_text: '', audio_data: '', audio_note: '', flow_page:page };
  const handlers = new Map();
  let sends = 0;
  const model = {
    get(name) { return values[name]; }, set(name, value) { values[name] = value; },
    save_changes() { sends++; }, on(name, fn) { handlers.set(name, fn); }, off(name) { handlers.delete(name); },
  };
  const el = { innerHTML: '', querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, element());
    return elements.get(selector);
  } };
  const cleanup = component.render({ model, el });
  return { elements, values, handlers, cleanup, get sends() { return sends; },
    click(action) { return elements.get(`[data-action="${action}"]`).listeners.click(); } };
}

let stops = 0;
const stream = () => ({ getTracks: () => [{ stop() { stops++; } }] });
{
  const f = fixture(async () => stream());
  await f.click('open');
  assert.equal(f.elements.get('video').hidden, false);
  await f.click('capture');
  assert.equal(stops, 1, 'capture must release tracks before backend request');
  assert.equal(f.elements.get('video').srcObject, null);
  assert.equal(f.elements.get('img').src, f.values.request.image);
  assert.equal(f.values.busy, true);
  assert.equal(f.values.request.image, 'data:image/jpeg;base64,actual-captured-image');
  f.click('close'); // Still works with busy Python/backend.
  f.cleanup();
}
{
  let resolve;
  const f = fixture(() => new Promise(r => { resolve = r; }));
  const pending = f.click('open');
  f.click('close');
  resolve(stream());
  await pending;
  assert.equal(stops, 2, 'late permission response must release its tracks');
  assert.equal(f.elements.get('video').srcObject, null);
  f.cleanup();
}
{
  const f = fixture(async () => stream(), true);
  await f.click('open');
  await f.click('capture');
  assert.equal(f.values.request, undefined, 'black frames must not be uploaded');
  assert.match(f.elements.get('[data-role="camera-status"]').textContent, /black/);
  f.click('close');
  f.cleanup();
}
{
  const f = fixture(async () => { throw new Error('Permission denied'); });
  await f.click('open');
  assert.equal(f.elements.get('video').srcObject, null);
  assert.match(f.elements.get('[data-role="camera-status"]').textContent, /Permission denied/);
  f.cleanup();
}
console.log('4 browser-camera lifecycle scenarios passed (fake DOM/media; no hardware).');

class FakeRecorder {
  static isTypeSupported() { return true; }
  constructor(stream, options) { this.state = 'inactive'; this.mimeType = options?.mimeType || 'audio/webm'; }
  start() { this.state = 'recording'; }
  stop() {
    this.state = 'inactive';
    queueMicrotask(() => {
      this.ondataavailable?.({ data: new Blob(['recorded-audio']) });
      this.onstop?.();
    });
  }
}
globalThis.MediaRecorder = FakeRecorder;
globalThis.FileReader = class {
  readAsDataURL() { this.result = 'data:audio/webm;base64,cmVjb3JkZWQ='; queueMicrotask(() => this.onload()); }
};
{
  const startStops = stops;
  const f = fixture(async () => stream());
  await f.click('record');
  assert.equal(f.elements.get('[data-action="stop-record"]').disabled, false);
  f.click('stop-record');
  assert.equal(stops, startStops + 1, 'microphone must stop before Python decoding');
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.match(f.values.speech_request.audio, /^data:audio/);
  assert.equal(f.values.busy, true);
  assert.equal(f.values.chat_request, undefined, 'transcription must not auto-send a question');
  f.cleanup();
}
{
  let resolve;
  const startStops = stops;
  const f = fixture(() => new Promise(r => { resolve = r; }));
  const opening = f.click('record');
  f.click('stop-record');
  resolve(stream());
  await opening;
  assert.equal(stops, startStops + 1, 'late microphone permission must release track');
  assert.equal(f.values.speech_request, undefined);
  f.cleanup();
}
{
  const f = fixture(async () => stream());
  f.elements.get('[data-role="draft"]').value = 'I feel dizzy today';
  f.click('send-chat');
  assert.equal(f.values.chat_request.kind, 'conversation');
  assert.equal(f.values.chat_request.text, 'I feel dizzy today');
  assert.equal(f.values.busy, true);
  f.cleanup();
}
{
  const f = fixture(async () => stream());
  f.elements.get('[data-role="draft"]').value = '';
  f.click('send-chat');
  assert.equal(f.sends, 0);
  f.cleanup();
}
console.log('4 microphone/chat scenarios passed (fake media/backend; no hardware).');
{
  const f = fixture(async () => stream(), false, 'home');
  assert.equal(f.elements.get('[data-page="home"]').hidden, false);
  assert.equal(f.elements.get('[data-page="chat"]').hidden, true);
  f.click('start-chat');
  assert.equal(f.values.flow_request.action, 'chat');
  f.values.flow_page='chat';f.handlers.get('change:flow_page')();
  assert.equal(f.elements.get('[data-page="chat"]').hidden, false);
  f.click('chat-check');
  assert.equal(f.values.flow_request.action, 'resume');
  f.values.flow_page='check';f.handlers.get('change:flow_page')();
  assert.equal(f.elements.get('[data-page="check"]').hidden, false);
  assert.equal(f.elements.get('[data-role="confirm-panel"]').hidden, true);
  f.values.confirmation_ready=true;f.values.verification_id='current-photo-token';
  f.handlers.get('change:confirmation_ready')();
  f.click('taken');
  assert.equal(f.values.confirm_request.status,'Taken');
  assert.equal(f.values.confirm_request.verification_id,'current-photo-token');
  f.values.flow_page='done';f.values.completion_text='Self-report saved';
  f.handlers.get('change:flow_page')();
  assert.equal(f.elements.get('[data-page="done"]').hidden, false);
  assert.equal(f.elements.get('[data-page="check"]').hidden, true);
  f.cleanup();
}
console.log('Home -> optional chat -> photo check -> explicit confirmation -> completion UI passed (fake backend).');
{
  const f = fixture(async () => stream());
  f.values.has_current_photo=true;
  f.values.package_context='Example A / 100 mg / Match';
  f.handlers.get('change:package_context')();
  assert.match(f.elements.get('[data-role="package-context"]').textContent,/Example A/);
  f.elements.get('img').src='captured-current-photo';
  f.elements.get('img').hidden=false;
  f.click('ask-current');
  assert.equal(f.values.flow_request.action,'ask-current');
  f.values.flow_page='chat';f.handlers.get('change:flow_page')();
  f.click('chat-check');
  assert.equal(f.values.flow_request.action,'resume');
  f.values.flow_page='check';f.handlers.get('change:flow_page')();
  assert.equal(f.elements.get('img').src,'captured-current-photo');
  f.cleanup();
}
{
  const f = fixture(async () => stream());
  f.values.can_replay=true;f.values.audio_data='existing-audio';
  f.elements.get('audio').currentTime=7;
  const prior=f.sends;
  f.click('replay');
  assert.equal(f.elements.get('audio').currentTime,0);
  assert.equal(f.sends,prior,'replay should not resubmit confirmation or call API');
  f.cleanup();
}
{
  const before=stops;
  const f = fixture(async () => stream());
  await f.click('open');
  f.values.busy=true; // A network request is currently in progress.
  f.click('cancel-flow');
  assert.equal(stops,before+1);
  assert.equal(f.values.flow_request.action,'cancel');
  assert.equal(f.elements.get('[data-page="check"]').hidden,true);
  f.values.flow_page='home';f.values.busy=false;
  f.handlers.get('change:cancel_ack')();
  assert.equal(f.elements.get('[data-page="home"]').hidden,false);
  f.cleanup();
}
{
  const f = fixture(async () => stream());
  f.values.source_links=[{title:'Label',url:'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test'},
                        {title:'Unsafe',url:'javascript:alert(1)'}];
  f.handlers.get('change:source_links')();
  assert.equal(f.elements.get('[data-role="source-links"]').children.length,1);
  f.values.has_current_photo=true;
  f.click('general-uses');
  assert.equal(f.values.use_request,1);
  f.cleanup();
}
console.log('4 package-context/replay/cancel/source-link UI scenarios passed (fake backend).');
{
 const f=fixture(async()=>stream());
 f.click('refresh-log');assert.ok(f.values.schedule_request.id);
 f.values.schedule_text='A | Pending';f.handlers.get('change:schedule_text')();
 assert.equal(f.elements.get('[data-role="schedule-log"]').textContent,'A | Pending');
 f.cleanup();
}
{
 const f=fixture(async()=>stream());
 f.values.audio_data='broken-audio';f.values.can_replay=true;
 const audio=f.elements.get('audio');audio.error={code:3};audio.listeners.error();
 assert.equal(f.values.playback_request.kind,'error');
 f.click('replay');assert.equal(f.values.replay_request,1,'corrupt audio must regenerate, not replay same broken source');
 assert.equal(f.values.confirm_request,undefined);
 f.cleanup();
}
console.log('2 schedule refresh and audio recovery scenarios passed.');
{
 const f=fixture(async()=>stream());
 f.click('new-demo');assert.equal(f.values.simulation_request.action,'new_demo');
 f.values.busy=false;f.click('start-reminder');assert.equal(f.values.simulation_request.action,'remind');
 f.values.busy=false;f.click('advance-demo');assert.equal(f.values.simulation_request.action,'advance');
 f.values.notification_text='SIMULATED EMAIL - NOT SENT';f.handlers.get('change:notification_text')();
 assert.equal(f.elements.get('[data-role="notifications"]').textContent,'SIMULATED EMAIL - NOT SENT');
 f.cleanup();
}
{
 const f=fixture(async()=>stream());
 f.values.confirmation_ready=true;f.values.verification_id='current';
 const draft=f.elements.get('[data-role="confirm-draft"]');draft.value='I have not taken it.';
 f.click('submit-report');assert.equal(f.values.confirm_request.text,'I have not taken it.');
 assert.equal(f.values.confirm_request.status,undefined,'backend classifies reviewed text without JS positive default');
 assert.equal(f.values.confirm_request.verification_id,'current');f.cleanup();
}
{
 const f=fixture(async()=>stream());
 f.values.confirmation_ready=true;f.values.draft_text='I have taken it.';
 f.handlers.get('change:draft_text')();
 assert.equal(f.elements.get('[data-role="confirm-draft"]').value,'I have taken it.');
 assert.equal(f.values.confirm_request,undefined,'transcription cannot submit automatically');
 f.cleanup();
}
console.log('3 simulation/notification/reviewed-confirmation browser scenarios passed.');

{
 const f=fixture(async()=>stream());
 f.values.dialogue_messages=[{role:'assistant',content:'Your **08:00 schedule** shows **Metoprolol Tartrate, 50 mg**. <img src=x onerror=bad()> '}];
 f.handlers.get('change:dialogue_messages')();
 const reply=f.elements.get('[data-role="dialogue"]').children[0];
 assert.equal(reply.children[1].textContent,'08:00 schedule');
 assert.equal(reply.children[3].textContent,'Metoprolol Tartrate, 50 mg');
 assert.match(reply.children.at(-1).textContent,/<img/,'HTML-like content stays literal text');
 f.cleanup();
}
console.log('Safe bold rendering regression passed.');
