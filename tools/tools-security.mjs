const rows = (value) => String(value ?? '').replace(/\r/g,'').split('\n').map((v) => v.trim()).filter(Boolean);
function pairs(value, length) {
  const data = rows(value).map((line) => line.split('|').map((v) => v.trim()));
  if (!data.length || data.length > 100 || data.some((r) => r.length !== length || r.some((v) => !v))) throw new Error(`Enter 1 to 100 rows, each with ${length} nonempty fields separated by |.`);
  return data;
}
function unique(values, kind) {
  const set = new Set(values);
  if (set.size !== values.length) throw new Error(`Each ${kind} must be unique.`);
  return set;
}
const text = (label, value, multiline = false) => ({label, value, ...(multiline ? {multiline:true} : {})});
const wrap = ({id,title,problem,baseline,prompt,fields,solve,test}) => ({
  id,title,tag:'Security.ink field tool',problem,baseline,prompt,fields,
  run(values) {
    try {
      if (values.length !== fields.length || values.some((v) => typeof v !== 'string' || v.length > 25000)) throw new Error('Check field count and keep each field at 25,000 characters or fewer.');
      return JSON.stringify({tool:title,...solve(values)},null,2);
    } catch (e) { return 'Input error: ' + e.message; }
  },
  verify(result) { try { const o = JSON.parse(result); return o.tool === title && test(o); } catch { return false; } },
});
const equalSet = (a,b) => a.length === b.length && a.every((v,i) => v === b[i]);

export const toolsS = [
wrap({
 id:'SI01',title:'Receipt Coverage Audit',
 problem:'A draft sounds supported until you discover its strongest claim points at nothing.',
 baseline:'Open references one by one and manually compare them with the claim list.',
 prompt:'Compare a claim-to-receipt map with an inventory of available evidence IDs. Surface unlinked claims, dangling references and unused receipts. Never grade truth or assume a named receipt supports the claim.',
 fields:[text('Claim | proposed receipt ID, or NONE','Reduced reading time | R02\nClearer handoff ownership | R04\nNo setup required | NONE',true),text('Available receipt IDs, one per line','R01\nR02',true)],
 solve([claims,available]){
  const data=pairs(claims,2), ids=unique(rows(available),'receipt ID');
  const inspected=data.map(([claim,id])=>({claim,id,state:id.toUpperCase()==='NONE'?'Unlinked':ids.has(id)?'Linked, substance unverified':'Missing receipt'}));
  return {inspected,unused:[...ids].filter(id=>!data.some(r=>r[1]===id)),linked:inspected.filter(r=>r.state==='Linked, substance unverified').length};
 },
 test(o){return Array.isArray(o.inspected)&&o.inspected.length>0&&o.inspected.every(r=>r.claim&&['Unlinked','Linked, substance unverified','Missing receipt'].includes(r.state))&&o.linked===o.inspected.filter(r=>r.state==='Linked, substance unverified').length&&Array.isArray(o.unused);}
}),
wrap({
 id:'SI02',title:'UTC Contact Sheet',
 problem:'A source brief and a captured event use different clocks, making the timeline easy to misread.',
 baseline:'Convert each timestamp in a separate tab and hope the day boundaries were carried across.',
 prompt:'Convert explicitly offset ISO-8601 timestamps to UTC, validate the calendar date, and sort by UTC. Reject date-only or offsetless strings. Show originals to keep provenance; don’t guess a time zone.',
 fields:[text('Label | timestamp with offset','Producer capture | 2026-11-24T16:40:00-08:00\nReviewer note | 2026-11-25T00:12:00Z\nFixture generated | 2026-11-24T15:58:00-08:00',true)],
 solve([source]){
  const moments=pairs(source,2).map(([label,original])=>{
   const m=original.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-](?:0\d|1[0-4]):[0-5]\d)$/);
   if(!m||+m[4]>23||+m[5]>59||+m[6]>59||!Number.isFinite(Date.parse(original))||(m[7].slice(1,3)==='14'&&m[7].slice(-2)!=='00'))throw new Error('Use a complete ISO timestamp with Z or a valid numeric offset.');
   const wall=new Date(original.slice(0,19)+'Z');
   if(wall.toISOString().slice(0,19)!==original.slice(0,19))throw new Error('A timestamp has an invalid date.');
   return {label,original,utc:new Date(original).toISOString()};
  });
  return {moments:moments.sort((a,b)=>a.utc.localeCompare(b.utc))};
 },
 test(o){return Array.isArray(o.moments)&&o.moments.length>0&&o.moments.every((r,i)=>r.label&&Date.parse(r.utc)===Date.parse(r.original)&&r.utc.endsWith('Z')&&(!i||o.moments[i-1].utc<=r.utc));}
}),
wrap({
 id:'SI03',title:'Demo Data Label Check',
 problem:'A shareable example quietly inherits undecided or internal material.',
 baseline:'Rely on a filename or a quick glance to remember what each asset contains.',
 prompt:'Check a manually labeled asset manifest. Permit only SYNTHETIC and CLEARED items as review candidates, route INTERNAL, RESTRICTED or UNKNOWN to hold; never grant release approval.',
 fields:[text('Asset | status','demo-fixture.csv | SYNTHETIC\nhero-original.svg | CLEARED\nworking-notes.md | INTERNAL\nraw-reference.mov | UNKNOWN',true)],
 solve([input]){
  const items=pairs(input,2).map(([asset,sourceStatus])=>({asset,sourceStatus:sourceStatus.toUpperCase()}));
  unique(items.map(r=>r.asset),'asset name');
  if(items.some(r=>!['SYNTHETIC','CLEARED','INTERNAL','RESTRICTED','UNKNOWN'].includes(r.sourceStatus)))throw new Error('Use SYNTHETIC, CLEARED, INTERNAL, RESTRICTED or UNKNOWN.');
  const review=[],hold=[];
  for(const row of items)(['SYNTHETIC','CLEARED'].includes(row.sourceStatus)?review:hold).push(row);
  return {review,hold,release:'Not approved. Labels are operator assertions.'};
 },
 test(o){return o.release==='Not approved. Labels are operator assertions.'&&Array.isArray(o.review)&&Array.isArray(o.hold)&&o.review.length+o.hold.length>0&&o.review.every(r=>r.asset&&['SYNTHETIC','CLEARED'].includes(r.sourceStatus))&&o.hold.every(r=>r.asset&&['INTERNAL','RESTRICTED','UNKNOWN'].includes(r.sourceStatus));}
}),
wrap({
 id:'SI04',title:'Fixture Schema Diff',
 problem:'A small field rename breaks the next consumer while both sample files still open.',
 baseline:'Visually inspect two lists and miss a dropped column or a changed type in the middle.',
 prompt:'Compare two named field-and-type lists, reject duplicate names, and report fields added, removed, and changed type. A diff is an inspection, not a compatibility guarantee.',
 fields:[text('Previous field | type','alert_id | string\nevent_time | datetime\ncount | integer',true),text('Current field | type','alert_id | string\nobserved_at | datetime\ncount | string',true)],
 solve([p,n]){
  function schema(s){const data=pairs(s,2);unique(data.map(r=>r[0]),'field');return new Map(data);}
  const a=schema(p),b=schema(n), added=[],removed=[],changed=[];
  for(const [field,type] of b)if(!a.has(field))added.push({field,type});else if(a.get(field)!==type)changed.push({field,from:a.get(field),to:type});
  for(const [field,type] of a)if(!b.has(field))removed.push({field,type});
  return {added,removed,changed,differences:added.length+removed.length+changed.length};
 },
 test(o){const a=[o.added,o.removed,o.changed];return a.every(Array.isArray)&&o.differences===a.reduce((s,arr)=>s+arr.length,0)&&o.changed.every(r=>r.field&&r.to&&r.from&&r.to!==r.from);}
}),
wrap({
 id:'SI05',title:'Decision Brief Check',
 problem:'A review note describes the background without saying what its reader can approve.',
 baseline:'Scan prose for a decision, a named owner, and a follow-up date.',
 prompt:'Structure one requested decision, owner, review date, evidence and uncertainty. Show preflight holes explicitly. Validate the date. Do not invent a decision, source or owner.',
 fields:[text('Requested decision','Approve one synthetic rehearsal.'),text('Decision owner','Training lead'),text('Review date (YYYY-MM-DD)','2026-12-02'),text('Evidence summary','The test uses one fictional case and two views.'),text('Remaining uncertainty','First-look comprehension has not been measured.')],
 solve([decision,owner,date,evidence,unknowns]){
  const brief=Object.fromEntries(Object.entries({decision,owner,date,evidence,unknowns}).map(([k,v])=>[k,v.trim()]));
  const missing=Object.keys(brief).filter(k=>!brief[k]);
  if(brief.date&&(!/^\d{4}-\d{2}-\d{2}$/.test(brief.date)||!Number.isFinite(Date.parse(brief.date))||new Date(brief.date).toISOString().slice(0,10)!==brief.date))throw new Error('Enter a real calendar date as YYYY-MM-DD.');
  return {brief,missing,state:missing.length?'Needs input':'Fields complete; evidence not independently checked.'};
 },
 test(o){return o.brief&&Array.isArray(o.missing)&&equalSet(o.missing,Object.keys(o.brief).filter(k=>!o.brief[k]))&&o.state===(o.missing.length?'Needs input':'Fields complete; evidence not independently checked.');}
}),
wrap({
 id:'SI06',title:'Revision Note Maker',
 problem:'Reviewers download a new draft with no clear way to see which named commitments changed.',
 baseline:'Open two long drafts and skim their changes out of context.',
 prompt:'Compare two small lists of named commitments and generate readable added, removed and changed notes. Use an exact title key; label it current wording, not an approved scope change.',
 fields:[text('Previous item | wording','Demo scope | Use two fictional examples\nExport | Supply a PDF after review',true),text('Current item | wording','Demo scope | Use one fictional example\nExport | Supply a PDF after review\nFollow-up | Collect first-read feedback',true)],
 solve([before,after]){
  const asMap=(v)=>{const a=pairs(v,2);unique(a.map(r=>r[0]),'item');return new Map(a);};
  const a=asMap(before),b=asMap(after), changes=[];
  for(const [item,value] of a)if(!b.has(item))changes.push({item,kind:'Removed',before:value});else if(b.get(item)!==value)changes.push({item,kind:'Changed',before:value,after:b.get(item)});
  for(const [item,value] of b)if(!a.has(item))changes.push({item,kind:'Added',after:value});
  return {changes,unchanged:a.size-changes.filter(r=>r.kind!=='Added').length,approval:'Draft comparison only.'};
 },
 test(o){return o.approval==='Draft comparison only.'&&Number.isInteger(o.unchanged)&&o.unchanged>=0&&Array.isArray(o.changes)&&o.changes.every(r=>r.item&&((r.kind==='Changed'&&r.before&&r.after&&r.after!==r.before)||(r.kind==='Added'&&r.after&&!r.before)||(r.kind==='Removed'&&r.before&&!r.after)));}
}),
wrap({
 id:'SI07',title:'Missing Signal Counter',
 problem:'Averages from the readings that arrived can hide a feed that stopped sending data.',
 baseline:'Count observations and assume the feed had nothing else to report.',
 prompt:'Compare expected reading IDs with observed IDs. Report missing readings, duplicates and unexpected readings separately, with the expected denominator. Never count missing values as zero or assert why data is missing.',
 fields:[text('Expected reading IDs','slot-01\nslot-02\nslot-03\nslot-04',true),text('Observed reading IDs (can repeat)','slot-01\nslot-02\nslot-02\nslot-05',true)],
 solve([expected,observed]){
  const list=rows(expected);if(!list.length||list.length>1000)throw new Error('Provide 1 to 1000 expected IDs.');
  const want=unique(list,'expected ID'), counts=new Map();
  for(const id of rows(observed))counts.set(id,(counts.get(id)??0)+1);
  const missing=list.filter(id=>!counts.has(id));
  return {expected:list.length,present:list.length-missing.length,missing,duplicates:[...counts].filter(([,n])=>n>1).map(([id,count])=>({id,count})),unexpected:[...counts.keys()].filter(id=>!want.has(id))};
 },
 test(o){return Number.isSafeInteger(o.expected)&&o.expected>0&&Number.isSafeInteger(o.present)&&o.present>=0&&Array.isArray(o.missing)&&o.present+o.missing.length===o.expected&&Array.isArray(o.unexpected)&&Array.isArray(o.duplicates)&&o.duplicates.every(r=>r.id&&r.count>1);}
}),
];
