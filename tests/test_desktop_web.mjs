import vm from 'node:vm';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {SingleAudioPlayer} from '../src/mediconfirm/web/single_audio.mjs';
import {DesktopCamera} from '../src/mediconfirm/web/desktop_camera.mjs';
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.hidden=false;this.value='';this.disabled=false;this.classList={toggle(){}};this.style={};}
 prepend(e){this.children.unshift(e);}appendChild(e){this.children.push(e);return e;}append(...nodes){nodes.forEach(n=>this.appendChild(n));}replaceChildren(...nodes){this.children=nodes;}get options(){return this.children;}get childNodes(){return this.children;}
 addEventListener(){}setAttribute(){}pause(){this.paused=true;}removeAttribute(){}play(){this.playCalls=(this.playCalls||0)+1;this.paused=false;return Promise.resolve();}
}
const html=fs.readFileSync(new URL('../src/mediconfirm/web/index.html',import.meta.url),'utf8');
const elements=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element()]));elements.historyFilter.value='all';
const tabs=['home','check','chat','me','list','history','settings','family'].map(name=>{const e=new Element();e.dataset.tab=name;return e;});
const context={DesktopCamera,SingleAudioPlayer,console,location:{search:'',pathname:'/'},history:{replaceState(){}},navigator:{},window:{addEventListener(){}},Intl,Date,URL,Blob,JSON,Number,String,queueMicrotask,setTimeout,clearTimeout,setInterval(){},document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag),addEventListener(){},querySelectorAll:selector=>selector==='[data-tab]'?tabs:[]},fetch:async(path)=>({ok:true,json:async()=>path==='/api/audio/claim'?{allowed:true}:base()})};
function base(){return {flow_page:'check',result_text:'',draft_text:'',audio_data:'',times:['08:00'],selected_time:'08:00',settings:{timeout_seconds:600,repeat_seconds:300,caregiver_email:'',reminders_enabled:false},daily_plan:[],dialogue_messages:[],source_links:[],history_records:[],family_notifications:[],server_time:'2026-11-10T10:00:00+08:00',schedule_mode:'automatic'};}
vm.createContext(context);vm.runInContext(fs.readFileSync(new URL('../src/mediconfirm/web/app.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/gm,''),context);
await new Promise(resolve=>setImmediate(resolve));
context.data={...base(),draft_text:'I feel tired'};vm.runInContext('render(data)',context);elements.draft.value='I feel tired today';vm.runInContext('render(data)',context);assert.equal(elements.draft.value,'I feel tired today');
context.data={...base(),flow_page:'done'};vm.runInContext('render(data);showTab("history");render(data)',context);assert.equal(tabs.find(t=>t.dataset.tab==='history').hidden,false);
context.data={...base(),verification_status:'Uncertain'};vm.runInContext('render(data)',context);assert.equal(elements.resultBadge.textContent,'Uncertain');
assert.match(html,/<video id="cameraVideo"/);assert.doesNotMatch(html,/capture="environment"/);
assert.equal((html.match(/<audio /g)||[]).length,1);
console.log('Desktop web checks passed: edited transcript preserved, History stays open, explicit result states, real video controls.');

context.data={...base(),has_current_photo:true,audio_clips:[{id:'clip-once',scope:'check',target:'result',url:'/api/audio/clip-once'}]};vm.runInContext('showTab("check");render(data)',context);await new Promise(resolve=>setImmediate(resolve));assert.equal(elements.audio.playCalls||0,0);
context.data.audio_clips[0].id='clip-actor';vm.runInContext('render(data,{autoplay:true})',context);await new Promise(resolve=>setImmediate(resolve));assert.equal(elements.audio.playCalls,1);vm.runInContext('render(data)',context);await new Promise(resolve=>setImmediate(resolve));assert.equal(elements.audio.playCalls,1);
console.log('Background polling does not replay responses.');
