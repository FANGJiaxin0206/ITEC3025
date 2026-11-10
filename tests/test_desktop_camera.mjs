import assert from 'node:assert/strict';
import {DesktopCamera} from '../src/mediconfirm/web/desktop_camera.mjs';
const makeStream=()=>{const track={stopped:false,stop(){this.stopped=true;}};return {track,getTracks:()=>[track],getVideoTracks:()=>[track]};};
const video=()=>({videoWidth:1280,videoHeight:720,readyState:2,srcObject:null,pause(){},async play(){}});
{
 const streams=[];const v=video();const c=new DesktopCamera(v,{mediaDevices:{async getUserMedia(){const s=makeStream();streams.push(s);return s;}}});
 await c.open();assert.ok(v.srcObject);await c.open();assert.ok(streams[0].track.stopped);c.stop();assert.ok(streams[1].track.stopped);assert.equal(v.srcObject,null);
}
{
 let grant;const c=new DesktopCamera(video(),{mediaDevices:{getUserMedia:()=>new Promise(r=>grant=r)}});const opening=c.open();c.stop();const s=makeStream();grant(s);assert.equal(await opening,false);assert.ok(s.track.stopped);assert.equal(c.stream,null);
}
{
 const v=video(),s=makeStream();const c=new DesktopCamera(v,{mediaDevices:{getUserMedia:async()=>s}});await c.open();v.readyState=0;await assert.rejects(c.capture({}),/not ready/);v.readyState=2;let drawn=false;const canvas={getContext:()=>({drawImage(){drawn=true;}}),toBlob:cb=>cb(new Blob(['photo'],{type:'image/jpeg'}))};const photo=await c.capture(canvas);assert.ok(drawn);assert.equal(photo.type,'image/jpeg');assert.equal(canvas.width,1280);assert.ok(s.track.stopped);assert.equal(v.srcObject,null);
}
{
 const c=new DesktopCamera(video(),{mediaDevices:{async getUserMedia(){throw Object.assign(new Error(),{name:'NotAllowedError'});}}});await assert.rejects(c.open(),/permission was denied/);assert.equal(c.opening,false);
}
{
 const v=video(),s=makeStream();const c=new DesktopCamera(v,{mediaDevices:{getUserMedia:async()=>s}});await c.open();let finish;const result=c.capture({getContext:()=>({drawImage(){}}),toBlob:cb=>finish=cb});c.stop();finish(new Blob(['stale']));assert.equal(await result,null);
}
console.log('5 desktop camera lifecycle and capture scenarios passed (fake media; no hardware).');
