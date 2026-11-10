import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
for(const path of ['../src/mediconfirm/simple_camera.mjs','../src/mediconfirm/web/app.js']){
 const source=fs.readFileSync(new URL(path,import.meta.url),'utf8');
 const line=source.split('\n').find(l=>l.startsWith('function readableEnglish('));
 const context={};vm.createContext(context);vm.runInContext(line,context);
 assert.equal(context.readableEnglish('I’ m sorry you’ re dizzy. I can’ t assess whether it’ s suitable.'),"I'm sorry you're dizzy. I can't assess whether it's suitable.");
 assert.equal(context.readableEnglish('Tartrate ,50 mg,one tablet. 1,000 units.\n\n0.5 mg.'),'Tartrate, 50 mg, one tablet. 1,000 units.\n\n0.5 mg.');
}
console.log('Notebook and web typography checks passed.');
