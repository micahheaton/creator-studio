const f=(label,value,multiline=false)=>({label,value,multiline});
const nums=(value,count,{allowNegative=false}={})=>{
 const parts=String(value??'').trim().split(/[\s,×x]+/);const out=parts.map(Number);
 if(parts.length!==count||parts.some(p=>p==='')||out.some(n=>!Number.isFinite(n)||(!allowNegative&&n<0)))return null;
 return out;
};
const lines=s=>String(s??'').trim().split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
const round=x=>Number(x.toFixed(2));
const integer=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
export const toolsR=[
{
 id:'RP01',title:'Crop Window Lab',
 problem:'Know what a centered or biased portrait crop will cut off before rendering.',
 prompt:'Calculate the largest source crop that fits this target aspect ratio. Bias the crop as requested and report which edge pixels will be lost. Use plain pixel coordinates and state that this is geometric only.',
 baseline:'Draw a target-aspect rectangle over the source image, then calculate crop coordinates manually.',
 fields:[f('Source width × height (px)','1920 × 1080'),f('Target width × height (px)','1080 × 1920'),f('Horizontal and vertical bias, 0 to 1','0.5 0.5')],
 run([src,dest,anchor]){
  const s=nums(src,2),d=nums(dest,2),a=nums(anchor,2);
  if(!s||!d||!a||[...s,...d].some(v=>!integer(v,1,100000))||a.some(v=>v>1))return 'Enter positive whole-pixel dimensions and two biases between 0 and 1.';
  const [w,h]=s,[dw,dh]=d,[ax,ay]=a,k=Math.min(w/dw,h/dh),cw=dw*k,ch=dh*k;
  const x=(w-cw)*ax,y=(h-ch)*ay;
  return ['Source window: '+round(cw)+' × '+round(ch)+' px','Origin: ('+round(x)+', '+round(y)+') from top left','Removed L/R: '+round(x)+' / '+round(w-cw-x)+' px','Removed T/B: '+round(y)+' / '+round(h-ch-y)+' px','Gives geometry only. Inspect the actual image for subjects and text.'].join('\n');
 },
 verify:r=>r.includes('607.5 × 1080')&&r.includes('(656.25, 0)')&&r.includes('656.25 / 656.25')
},
{
 id:'RP02',title:'Phone Overlay Collision',
 problem:'Spot which titles or subtitles sit under measured phone-player controls.',
 prompt:'Compare named element rectangles against supplied player exclusion margins. Compute the pixels of overlap on each edge, without guessing permanent rules for any social platform.',
 baseline:'Layer guides on a phone screenshot and measure each title or caption manually.',
 fields:[f('Canvas W H and excluded left top right bottom (px)','1080 1920 70 110 170 280'),f('Label | x y width height, one per line','Header | 90 150 800 115\nCaption | 120 1570 780 145\nBadge | 810 310 190 130',true)],
 run([canvas,items]){
  const v=nums(canvas,6);
  if(!v||v.some(n=>!integer(n,0,100000)))return 'Enter six whole-pixel values.';
  const [w,h,l,t,r,b]=v;
  if(w<=l+r||h<=t+b)return 'No positive safe rectangle remains.';
  const warnings=lines(items).map(row=>{
   const [name,part]=row.split('|').map(x=>x.trim()),q=nums(part,4);
   if(!name||!q||q[2]<=0||q[3]<=0)return 'Invalid element: '+row;
   const [x,y,ww,hh]=q,c=[l-x,t-y,x+ww-(w-r),y+hh-(h-b)];
   const hit=c.flatMap((n,i)=>n>0?[[['left','top','right','bottom'][i],round(n)+'px'].join(' ')]:[]);
   return name+': '+(hit.join(', ')||'within bounds');
  });
  return ['Safe rectangle: ('+l+', '+t+') to ('+(w-r)+', '+(h-b)+')',...warnings,'Margins come from your supplied overlay; platforms may change them.'].join('\n');
 },
 verify:r=>r.includes('(70, 110) to (910, 1640)')&&r.includes('Header: within bounds')&&r.includes('Caption: bottom 75px')&&r.includes('Badge: right 90px')
},
{
 id:'RP03',title:'QR Print Fit',
 problem:'Check whether a planned QR label can preserve its white border and enough pixels per module.',
 prompt:'Calculate the grid, quiet zone and printer-dot budgets for the supplied QR version, finished side length and DPI. Do not claim the physical QR was scanned.',
 baseline:'Look up grid size and quiet zone, then do print-resolution conversions by hand.',
 fields:[f('QR version (1–40), side length in mm, printer DPI','4 22 300')],
 run([settings]){
  const n=nums(settings,3);
  if(!n||!integer(n[0],1,40)||n[1]<=0||n[2]<=0)return 'Enter QR version 1 to 40, positive side length and positive DPI.';
  const [version,mm,dpi]=n,data=17+4*version,side=data+8,dot=mm*dpi/25.4/side,whole=Math.floor(dot);
  return ['Data grid: '+data+' × '+data,'Full grid with four quiet modules per side: '+side+' × '+side,'Module pitch: '+round(mm/side)+' mm; '+round(dot)+' printer dots/module','Largest whole-dot pitch within given side: '+whole+' dots/module',
   'Quiet zone per edge at planned size: '+round(4*mm/side)+' mm',whole<3?'Review: below a conservative 3-dot planning target.':'Planning target met (at least 3 whole dots per module).','Not a scan guarantee. Print and test the actual label with intended devices.'].join('\n');
 },
 verify:r=>r.includes('33 × 33')&&r.includes('41 × 41')&&r.includes('6.34 printer dots/module')&&r.includes('6 dots/module')
},
{
 id:'RP04',title:'Motion Keyframe Baker',
 problem:'Turn an eased movement into frame-accurate samples for a video or browser animation.',
 prompt:'Produce sampled values for an ease-out cubic movement. Honor the requested frame rate, round duration to a real frame boundary and include the exact endpoints.',
 baseline:'Lay out a spreadsheet of elapsed fractions and compute cubic easing and frame indices per row.',
 fields:[f('Start value, end value, duration in seconds, FPS','0 100 1 24'),f('Sample every N frames','6')],
 run([values,spacing]){
  const n=nums(values,4,{allowNegative:true}),s=nums(spacing,1);
  if(!n||!s||n[2]<=0||!integer(n[3],1,240)||!integer(s[0],1,100000))return 'Enter valid endpoints, duration, integer FPS and positive sample spacing.';
  const [from,to,sec,fps]=n, frames=Math.max(1,Math.round(sec*fps)),stride=s[0];
  if(frames/stride>2000||frames>1e7)return 'Too many samples. Increase spacing or reduce duration.';
  const at=i=>{const p=i/frames;return i+' | '+round(i/fps)+'s | '+round(from+(to-from)*(1-(1-p)**3));};
  const runs=[];for(let i=0;i<frames;i+=stride)runs.push(at(i));runs.push(at(frames));
  return ['Ease-out cubic | '+frames+' frame intervals | '+round(frames/fps)+'s actual','Frame | time | value',...runs].join('\n');
 },
 verify:r=>r.includes('24 frame intervals')&&r.includes('6 | 0.25s | 57.81')&&r.includes('24 | 1s | 100')
},
{
 id:'RP05',title:'Sprite Sheet Packer',
 problem:'Budget a flipbook or pixel-art atlas without accidentally exceeding the chosen texture dimensions.',
 prompt:'Plan a fixed-cell atlas, keeping the requested padding around each sprite. Show dimensions, capacity, maximum pages and estimated uncompressed RGBA memory.',
 baseline:'Count rows and columns manually, then multiply texture width by height and bytes per pixel.',
 fields:[f('Sprite width height, count, padding each side, max atlas side','220 160 150 2 2048')],
 run([spec]){
  const n=nums(spec,5);if(!n||!n.every((x,i)=>integer(x,i===3?0:1,100000)))return 'Enter five valid whole numbers; only padding can be zero.';
  const [w,h,count,p,max]=n,x=w+2*p,y=h+2*p,cols=Math.floor(max/x),rows=Math.floor(max/y);
  if(!cols||!rows)return 'A padded sprite cannot fit in the selected atlas.';
  const cap=cols*rows,pages=Math.ceil(count/cap),used=count%cap||Math.min(count,cap);
  const page=k=>[Math.min(cols,k)*x,Math.ceil(k/cols)*y];
  const [fw,fh]=page(Math.min(cap,count)),[lw,lh]=page(used),mib=(fw*fh*(pages-1)+lw*lh)*4/1048576;
  return ['Cell: '+x+' × '+y+' px','Grid capacity: '+cols+' × '+rows+' = '+cap+' sprites/page','Pages: '+pages,'First page: '+fw+' × '+fh+' px','Last page: '+lw+' × '+lh+' px','Estimated RGBA8 texture memory: '+round(mib)+' MiB (no mipmaps).','Planning only; exports, runtime limits and compression are not tested.'].join('\n');
 },
 verify:r=>r.includes('9 × 12 = 108')&&r.includes('Pages: 2')&&r.includes('Last page: 2016 × 820')
},
{
 id:'RP06',title:'Boss Fight Beat Grid',
 problem:'Give a playful browser-game reveal a usable cue sheet without counting bars by hand.',
 prompt:'Lay out beat-numbered moves for a tiny boss reveal. Convert one-based bar and beat to elapsed seconds at a constant tempo, parse subdivisions and sort cues by time.',
 baseline:'Count beats in a metronome or editor, then calculate timestamps for each move.',
 fields:[f('Tempo BPM and beats per bar','120 4'),f('Bar | beat (decimals allowed) | cue','1 | 1 | Curtain opens\n2 | 3.5 | Boss winks\n2 | 1 | Intro sting\n3 | 1 | Confetti bot escapes',true)],
 run([tempo,cues]){
  const v=nums(tempo,2);if(!v||v[0]<=0||!integer(v[1],1,32))return 'Enter a positive tempo and whole beats per bar (1 to 32).';
  const [bpm,beats]=v, good=[],bad=[];
  for(const row of lines(cues)){
   const parts=row.split('|').map(x=>x.trim()), [bar,beat,label]=parts,b=Number(bar),s=Number(beat);
   if(parts.length!==3||!integer(b,1,100000)||!Number.isFinite(s)||s<1||s>=beats+1||!label){bad.push('Invalid cue: '+row);continue;}
   good.push({label,b,s,time:((b-1)*beats+s-1)*60/bpm});
  }
  return ['Boss beat grid | '+bpm+' BPM | '+beats+' beats/bar',...good.sort((a,b)=>a.time-b.time).map(c=>c.time.toFixed(3)+'s | '+c.b+':'+c.s+' | '+c.label),...bad,'Timing only: point cues assume a constant tempo.'].join('\n');
 },
 verify:r=>r.includes('0.000s | 1:1 | Curtain opens')&&r.includes('3.250s | 2:3.5 | Boss winks')&&r.indexOf('Intro sting')<r.indexOf('Boss winks')
}
];
