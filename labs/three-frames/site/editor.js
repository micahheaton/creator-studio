const el = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const privateCapture = params.has('capture');
if (privateCapture) document.body.classList.add('capture');
let scene = {...Frames.initial};
let clipUrl = '', busy=false, started=false;
const formats={tall:'9:16',square:'1:1',wide:'16:9',feed:'4:5'};
const loadedFonts = Promise.all([document.fonts.load('20px Knewave'),document.fonts.load('400 20px "Source Sans 3"'), document.fonts.load('700 20px "Source Sans 3"')]);
function eventRecord(name) {
  if (privateCapture || !/^https?:$/.test(location.protocol)) return;
  const value={name,content:'three-frames',variant:'signal-desk',campaign:'field-notes',traffic:params.get('traffic')==='test'?'test':'standard'};
  fetch('/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value),keepalive:true}).catch(()=>{});
}
function startDemo(){if(!started){started=true;eventRecord('demo_start');}}
function live() {
  el('player').pause();el('player').hidden=true;el('view').hidden=false;el('edit').hidden=true;
  const f=el('format').value;
  if(f==='crop')Frames.crop(el('view'),scene,.85);else Frames.draw(el('view'),f,scene,.85);
  el('stage-name').textContent=f==='crop'?'Center slice of the wide scene':formats[f]+' · Live canvas';
  el('liveflag').textContent='Live editor';el('motion').disabled=el('png').disabled=f==='crop'||busy;
  el('aval').value=scene.a.toFixed(1);el('bval').value=scene.b.toFixed(1);
}
function clearClip(){
  el('player').removeAttribute('src');el('player').load();
  if(clipUrl){URL.revokeObjectURL(clipUrl);clipUrl='';}
  el('play').hidden=el('download-clip').hidden=true;
}
function sync(){
  for(const key of ['a','b','anchor','caption'])el(key).value=scene[key];
  live();
}
function download(blob,name) {
  const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),5000);
}
function status(line){el('status').textContent=line;}
for(const id of ['a','b','anchor','caption','format']){
  el(id).addEventListener('input',()=>{
    startDemo();clearClip();
    if(id!=='format')scene=Frames.validate({...scene,[id]:id==='a'||id==='b'?Number(el(id).value):el(id).value});
    live();status(el('format').value==='crop'?'The center slice loses both devices.':'Both devices have a place. Render the clip to check the saved result.');
  });
}
el('png').onclick=async()=>{startDemo();await loadedFonts;const f=el('format').value;el('view').toBlob(blob=>{if(blob){download(blob,'signal-'+f+'.png');eventRecord('export_completed');status('PNG exported.');}});};
el('save').onclick=()=>download(new Blob([JSON.stringify(scene,null,2)],{type:'application/json'}),'signal-scene.json');
el('load').onchange=async()=>{
  try {const file=el('load').files[0];if(!file||file.size>4096)throw Error();const next=Frames.validate(JSON.parse(await file.text()));clearClip();scene=next;sync();status('Scene restored.');}
  catch{status('Invalid scene. Your current settings are intact.');}finally{el('load').value='';}
};
function setBusy(value){
  busy=value;for(const id of ['format','a','b','anchor','caption','load','png','motion'])el(id).disabled=value;
}
el('motion').onclick=async()=>{
  if(busy)return;startDemo();const f=el('format').value,s={...scene},c=el('view');let stream;
  setBusy(true);clearClip();status('Rendering the two-second signal…');
  try{
    await loadedFonts;
    const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/mp4'].find(m=>window.MediaRecorder?.isTypeSupported(m));
    if(!mime||!c.captureStream)throw Error();
    Frames.draw(c,f,s,0);stream=c.captureStream(30);
    const rec=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:4500000}),parts=[];
    const complete=new Promise((res,rej)=>{rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data);};rec.onstop=res;rec.onerror=rej;});
    rec.start();const begin=performance.now();
    await new Promise(resolve=>{function frame(now){const t=(now-begin)/1000;Frames.draw(c,f,s,Math.min(t,1.999));if(t>=2)resolve();else requestAnimationFrame(frame);}requestAnimationFrame(frame);});
    rec.stop();await complete;
    const blob=new Blob(parts,{type:rec.mimeType});if(!blob.size)throw Error();
    clipUrl=URL.createObjectURL(blob);el('player').src=clipUrl;el('download-clip').href=clipUrl;el('download-clip').download='signal-'+f+(mime.includes('mp4')?'.mp4':'.webm');el('play').hidden=el('download-clip').hidden=false;
    status('Clip rendered. Play the exported file.');eventRecord('export_completed');
  }catch{status('Motion export unavailable in this browser. PNG export is available.');}
  finally{if(stream)stream.getTracks().forEach(t=>t.stop());setBusy(false);}
};
el('play').onclick=async()=>{
  if(!clipUrl)return;const p=el('player');p.hidden=false;el('view').hidden=true;el('edit').hidden=false;
  el('liveflag').textContent='Saved file';el('stage-name').textContent=formats[el('format').value]+' · Export playback';p.currentTime=0;try{await p.play();status('Playing the rendered file.');}catch{status('Use the player controls to play the rendered file.');}
};
el('edit').onclick=()=>{live();status('Editing the scene.');};
for(const a of document.querySelectorAll('[data-download]'))a.addEventListener('click',()=>eventRecord('download_clicked'));
loadedFonts.then(()=>{sync();document.body.dataset.ready='true';});
eventRecord('page_view');
