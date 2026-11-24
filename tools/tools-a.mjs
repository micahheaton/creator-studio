const lines = s => String(s ?? '').split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
const field = (label,value,multiline=true) => ({label,value,multiline});
const unique = xs => [...new Set(xs)];
export const toolsA = [
 {
  id:'01',title:'Caption Fit Check',tag:'Video / accessibility',
  problem:'Find caption cues that viewers may not have time to read.',
  baseline:'Read the captions while playing the clip, then manually calculate any suspect reading rates.',
  prompt:'Run a caption legibility pass on these SRT or VTT cues. Flag timing errors, overlapping cues, long lines and fast reading rates. Preserve wording and timing unless separately asked to edit.',
  fields:[field('SRT or VTT captions','1\n00:00:01,000 --> 00:00:02,000\nHere’s everything you need to get started.\n\n2\n00:00:01,900 --> 00:00:04,200\nFirst, open the demo.\n\n3\n00:00:07,000 --> 00:00:06,000\nThat’s it.')],
  run([input]){
   const stamp = s => {
    const m=s.match(/^(?:(\d+):)?([0-5]?\d):([0-5]\d)[.,](\d{3})$/);
    return m ? ((+(m[1]||0)*60+ +m[2])*60+ +m[3])+ +m[4]/1000 : NaN;
   };
   const blocks=String(input??'').trim().split(/\r?\n[\t ]*\r?\n/);
   const cues=blocks.flatMap(block=>{
    const rows=block.split(/\r?\n/);
    if(/^(NOTE|STYLE|REGION)(?:\s|$)/.test(rows[0]))return [];
    const i=rows.findIndex(l=>l.includes('-->'));
    if(i<0)return [];
    const [a,b]=rows[i].split('-->').map(s=>s.trim().split(/\s+/)[0]);
    return [{a:stamp(a),b:stamp(b),text:rows.slice(i+1).map(x=>x.replace(/<[^>]*>/g,'').trim()).filter(Boolean)}];
   });
   let flags=0, end=-Infinity;
   const out=cues.map(({a,b,text},i)=>{
    const issues=[]; const length=s=>[...s].length;
    if(!Number.isFinite(a)||!Number.isFinite(b)||b<=a)issues.push('invalid timing');
    else{
     if(a < end-0.0005)issues.push('overlap or out-of-order');
     end=Math.max(end,b);
     const cps=length(text.join(' '))/(b-a);
     if(cps>20)issues.push(cps.toFixed(1)+' characters/sec');
    }
    if(!text.length)issues.push('missing text');
    if(text.some(l=>length(l)>42))issues.push('line over 42 characters');
    if(text.length>2)issues.push('more than two lines');
    flags+=issues.length;
    return 'Cue '+(i+1)+': '+(issues.join(', ')||'passes checks');
   });
   return 'Caption fit | '+cues.length+' cues | '+flags+' flags\n'+(out.join('\n')||'No timing cues parsed. Use SRT or WebVTT timestamps.')+'\nHeuristics: 20 chars/sec, 42 chars/line, two lines; verify visually.';
  },
  verify(r){return /3 cues/.test(r)&&/characters\/sec/.test(r)&&/overlap/.test(r)&&/invalid timing/.test(r);}
 },
 {
  id:'02',title:'Claim to Evidence Matrix',tag:'Editorial / QA',
  problem:'Stop hype or weak sourcing from slipping into release notes and launch posts.',
  baseline:'Compare every claim alongside the evidence list by hand and record missing or unused references.',
  prompt:'Map each launch claim to explicit evidence IDs. Flag missing records, unused evidence and source owners. Do not treat attached evidence as proof until someone verifies that it supports the claim.',
  fields:[field('Claims: ID | claim | comma-separated evidence IDs','C1 | Works without a server | E1\nC2 | Twice as fast as the old flow | E2\nC3 | Supports keyboard navigation | E1, E3'),field('Evidence: ID | description','E1 | Local demo recording\nE3 | Keyboard QA checklist\nE4 | Old launch screenshot')],
  run([claimRows,evidenceRows]){
   const record=x=>x.split('|').map(s=>s.trim());
   const evidence=new Map(), errors=[];
   for(const row of lines(evidenceRows)){
    const [id,description]=record(row);
    if(!id||!description){errors.push('Malformed evidence: '+row);continue;}
    if(evidence.has(id)){errors.push('Duplicate evidence ID: '+id);continue;}
    evidence.set(id,description);
   }
   const used=new Set(), ids=new Set();let mapped=0, blocked=0;
   const out=[];
   for(const row of lines(claimRows)){
    const [id,claim,refs='']=record(row);
    if(!id||!claim){errors.push('Malformed claim: '+row);continue;}
    if(ids.has(id)){errors.push('Duplicate claim ID: '+id);continue;}
    ids.add(id);
    const refsList=unique(refs.split(',').map(s=>s.trim()).filter(Boolean));
    const missing=refsList.filter(id=>!evidence.has(id));
    const valid=refsList.filter(id=>evidence.has(id));valid.forEach(x=>used.add(x));
    const gaps=!refsList.length?'No evidence references':missing.length?'Missing '+missing.join(', '):'Mapped; verify relevance';
    if(!refsList.length||missing.length)blocked++;else mapped++;
    out.push(id+': '+claim+'\n  '+gaps+(valid.length?'\n  '+valid.map(x=>x+' ('+evidence.get(x)+')').join('; '):''));
   }
   const unused=[...evidence.keys()].filter(id=>!used.has(id));
   return ['Evidence matrix | '+mapped+' mapped | '+blocked+' gaps',...out,'Unused evidence: '+(unused.join(', ')||'none'),...(errors.length?['Input errors:',...errors]:[])].join('\n');
  },
  verify(r){return /2 mapped \| 1 gaps/.test(r)&&r.includes('Missing E2')&&r.includes('Unused evidence: E4');}
 },
 {
  id:'03',title:'Static Route Collision Check',tag:'Web / Content ops',
  problem:'Catch duplicate or orphaned public article routes before committing static content.',
  baseline:'Compare the route list in a spreadsheet; manually cross-check targets, redirects and duplicate slugs.',
  prompt:'Review canonical URLs and proposed redirect mappings for normalized path collisions, unknown destinations, loops and redirect chains. Do not modify routes or publish redirects.',
  fields:[field('Canonical paths, one per line','/notes/first-launch/\n/notes/first-launch\n/guides/recording'),field('Redirects: old path -> new path','/launch -> /notes/first-launch\n/old-guide -> /guide-v1\n/guide-v1 -> /guides/recording\n/broken -> /missing\n/a -> /b\n/b -> /a')],
  run([canon,redirects]){
   const clean=s=>{
    const raw=s?.trim();
    if(!raw||!/^\/(?!\/)/.test(raw)||/[?#\\\s]/.test(raw))return null;
    const path=raw.replace(/\/{2,}/g,'/').replace(/\/+$/,'')||'/';
    return path.split('/').some(x=>x==='.'||x==='..')?null:path;
   };
   const paths=new Set(), edges=new Map(), problems=[];
   lines(canon).forEach(row=>{
    const p=clean(row);
    if(!p)problems.push('Invalid canonical path: '+row);
    else if(paths.has(p))problems.push('Duplicate canonical: '+p);
    else paths.add(p);
   });
   lines(redirects).forEach(row=>{
    const parts=row.split('->').map(clean);
    const [from,to]=parts;
    if(parts.length!==2||!from||!to)return problems.push('Invalid redirect: '+row);
    if(edges.has(from))return problems.push('Duplicate redirect source: '+from);
    if(paths.has(from))problems.push('Redirect also serves canonical path: '+from);
    edges.set(from,to);
   });
   for(const from of edges.keys()){
    const seen=new Set([from]);let target=edges.get(from),loop=false;
    while(edges.has(target)){
     if(seen.has(target)){loop=true;break;}
     seen.add(target);target=edges.get(target);
    }
    if(loop)problems.push('Redirect loop from '+from);
    else if(!paths.has(target))problems.push('Missing destination: '+from+' ends at '+target);
    else if(seen.size>1)problems.push('Redirect chain: '+from+' ends at '+target);
   }
   return 'Route check | '+paths.size+' canonical | '+edges.size+' redirects\n'+(problems.join('\n')||'No issues detected.')+'\nPath-only check; case is preserved. Hosting, encoded URLs and actual responses were not checked.';
  },
  verify(r){return r.includes('Duplicate canonical: /notes/first-launch')&&r.includes('Redirect chain: /old-guide')&&r.includes('Missing destination: /broken')&&r.includes('Redirect loop from /a');}
 },
 {
  id:'04',title:'Clip Time Budget',tag:'Video / Planning',
  problem:'See exactly why a proposed short edit is over time before opening a video editor.',
  baseline:'Add selected durations on a calculator and manually check overlaps against the source timeline.',
  prompt:'Check an edit decision list for invalid ranges, repeated source footage and whether the combined runtime exceeds the target. Keep editorial decisions separate from the timing analysis.',
  fields:[field('Target runtime in seconds','60',false),field('Clips: start | end | label','0:04 | 0:12 | Hook\n0:26 | 0:58 | Setup\n0:49 | 1:12 | Reveal\n1:14 | 1:13 | Ending')],
  run([targetText,clipRows]){
   const num=s=>{
    s=s?.trim()||'';
    if(/^\d+(?:\.\d+)?$/.test(s))return +s;
    const m=s.match(/^(\d+):([0-5]\d(?:\.\d+)?)$/);
    return m ? +m[1]*60+ +m[2] : NaN;
   };
   const goal=num(targetText);if(!Number.isFinite(goal)||goal<=0)return 'Enter a positive target, in seconds or M:SS.';
   const clips=[], errors=[];
   for(const [i,row] of lines(clipRows).entries()){
    const [start,end,label='Clip '+(i+1)]=row.split('|').map(s=>s.trim());
    const a=num(start),b=num(end);
    if(!Number.isFinite(a)||!Number.isFinite(b)||b<=a){errors.push('Invalid source range: '+label);continue;}
    clips.push({a,b,label});
   }
   let total=0,covered=0,edge=-Infinity;
   const listing=clips.map(c=>{
    const from=total;total+=c.b-c.a;
    return c.label+': '+from.toFixed(1)+'s to '+total.toFixed(1)+'s in output';
   });
   for(const {a,b} of [...clips].sort((x,y)=>x.a-y.a)){
    covered+=Math.max(0,b-Math.max(a,edge));edge=Math.max(edge,b);
   }
   const over=total-goal;
   return [
    'Clip budget | '+total.toFixed(1)+'s planned | '+goal.toFixed(1)+'s target',
    Math.abs(over)<1e-6?'At target':Math.abs(over).toFixed(1)+'s '+(over>0?'over target':'under target'),
    (total-covered).toFixed(1)+'s repeated source footage (intentional repeats are allowed).',
    ...listing,...errors,'Hard-cut estimate; transitions, speed changes and handles are not included.'
   ].join('\n');
  },
  verify(r){return r.includes('63.0s planned')&&r.includes('3.0s over target')&&r.includes('9.0s repeated')&&r.includes('Invalid source range: Ending');}
 }
];
