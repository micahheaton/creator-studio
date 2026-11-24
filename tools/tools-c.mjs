const problem = message => { throw Error(message); };
const dollars = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
const lines = input => input.split(/\r?\n/).map(x => x.trim()).filter(Boolean);

function parseLedger(data, label) {
  const map = new Map();
  lines(data).forEach((line,i) => {
    const pieces = line.split(',').map(x => x.trim());
    if (pieces.length !== 2 || !pieces[0] || !/^\d{1,9}(\.\d{1,2})?$/.test(pieces[1])) problem(label + ' row ' + (i+1) + ': use ID, amount with at most two decimals.');
    const [whole, frac=''] = pieces[1].split('.');
    const cents = Number(whole)*100 + Number(frac.padEnd(2,'0'));
    const id = pieces[0].toUpperCase();
    if (map.has(id)) problem(label + ': duplicate ID ' + id + '. Fix it rather than guessing.');
    map.set(id,cents);
  });
  if (!map.size) problem(label + ' is empty.');
  return map;
}

const audit = {
  id:'08', title:'Invoice Crosscheck', tag:'OPERATIONS',
  problem:'Find missing, unexpected, and amount-mismatched invoice lines before a batch is paid.',
  baseline:'A totals-only check can miss offsetting errors or mismatched invoice IDs.',
  prompt:'Compare expected and received invoice ledgers by unique invoice ID. Report missing, extra, and changed invoices with signed differences; use exact decimal arithmetic and reconcile the totals. Do not guess at duplicates.',
  fields:[
    {label:'Expected IDs and amounts',value:'A100, 140.00\nA101, 89.95\nA102, 50.00\nA103, 20.00',multiline:true},
    {label:'Received IDs and amounts',value:'A100, 145.00\nA101, 89.95\nA103, 20.00\nA104, 45.00',multiline:true}
  ],
  run([expected,received]){
    const a=parseLedger(expected,'Expected'), b=parseLedger(received,'Received');
    const tally = m => [...m.values()].reduce((sum,n)=>sum+n,0);
    const net=tally(b)-tally(a);
    let matched=0;
    const differences=[];
    for(const id of [...new Set([...a.keys(),...b.keys()])].sort()){
      const x=a.get(id), y=b.get(id);
      if(x===y) {matched++;continue;}
      if(y===undefined) differences.push('MISSING  '+id+'  '+ dollars(-x));
      else if(x===undefined) differences.push('EXTRA  '+id+'  '+dollars(y));
      else differences.push('CHANGED  '+id+'  '+dollars(x)+' → '+dollars(y)+'  (Δ '+dollars(y-x)+')');
    }
    return [
      differences.length ? 'REVIEW • '+differences.length+' exceptions' : 'MATCH • no exceptions',
      'Expected '+dollars(tally(a))+' | Received '+dollars(tally(b))+' | Net '+dollars(net),
      (differences.length && net===0 ? 'Balanced totals, but the invoice lines do not match.' : ''),
      ...differences, 'Exact matches: '+matched
    ].filter(Boolean).join('\n');
  },
  verify(out){return ['3 exceptions','Balanced totals','CHANGED  A100','MISSING  A102','EXTRA  A104','Exact matches: 2'].every(s=>out.includes(s));}
};

const minute = input => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(input.trim());
  if(!m||+m[1]>23||+m[2]>59) problem('Use a 24-hour time, like 09:30.');
  return 60*Number(m[1])+Number(m[2]);
};
const clock = m => [Math.floor(m/60),m%60].map(n=>String(n).padStart(2,'0')).join(':');
const agenda = {
  id:'09', title:'Run of Show', tag:'CREATOR',
  problem:'Fit a live segment into a hard stop without silently sacrificing audience Q&A or teardown.',
  baseline:'A flat agenda adds up minutes but gives no plan for what to shorten when the room runs late.',
  prompt:'Convert a timed agenda to a live cue sheet. Preserve locked segments and flexible minimums. If necessary, compress flexible segments from bottom to top, then show timing changes and remaining headroom. Never hide an overrun.',
  fields:[
    {label:'Start (24h)',value:'09:30'},
    {label:'Hard stop (24h)',value:'09:55'},
    {label:'Segments: Name | planned minutes | minimum minutes (or lock)',value:'Cold open | 3 | lock\nWalkthrough | 8 | 6\nLive demo | 10 | 7\nAudience Q&A | 4 | lock\nReset and teardown | 3 | lock',multiline:true}
  ],
  run([start,end,rows]){
    const first=minute(start), last=minute(end);
    if(last<=first) problem('Hard stop must be later than start on the same day.');
    const agenda=lines(rows).map((line,i)=>{
      const p=line.split('|').map(s=>s.trim());
      if(p.length!==3||!p[0]||!/^\d{1,3}$/.test(p[1])||!(/^(lock|\d{1,3})$/i.test(p[2]))) problem('Segment '+(i+1)+': use name | minutes | minimum or lock.');
      const plan=+p[1], min=p[2].toLowerCase()==='lock'?plan:+p[2];
      if(plan<1 || min<1 || min>plan) problem('Segment '+(i+1)+': minimum must be between 1 and planned minutes.');
      return {name:p[0],plan,min,length:plan};
    });
    if(!agenda.length) problem('Add at least one segment.');
    const window=last-first, planned=agenda.reduce((sum,s)=>sum+s.plan,0);
    let excess=Math.max(0,planned-window);
    for(const s of [...agenda].reverse()){
      const take=Math.min(excess,s.plan-s.min);
      s.length-=take; excess-=take;
    }
    let time=first;
    const rowsOut=agenda.map(s=>{
      const prev=time; time+=s.length;
      return clock(prev)+' to '+clock(time)+'  '+s.name+'  '+s.length+' min'+(s.length<s.plan?' (cut '+(s.plan-s.length)+')': s.plan===s.min?' (locked)':'');
    });
    const remaining=last-time;
    return [clock(first)+' to '+clock(last)+' hard window | '+(excess?'OVERRUN '+excess+' min':remaining+' min spare'), ...rowsOut, excess?'Cannot fit without changing a locked segment, a minimum, or the hard stop.': planned>window?'Recovered '+(planned-window)+' min without cutting locked segments.':'No cuts needed.'].join('\n');
  },
  verify(out){return ['09:41 to 09:48  Live demo  7 min (cut 3)','09:48 to 09:52  Audience Q&A  4 min (locked)','0 min spare','Recovered 3 min'].every(s=>out.includes(s));}
};

const recipes=[
  {name:'Chickpea Crunch Tacos',need:['chickpeas','tortilla','cabbage'],lift:['lime','hot sauce','cilantro'],method:'Drain canned chickpeas, mash roughly, and warm through. Fill warm tortillas and top with finely sliced cabbage.'},
  {name:'The Midnight Melt',need:['bread','cheese'],lift:['tomato','mustard','pickles'],method:'Toast bread with sliced cheese in a covered skillet until the cheese melts and both sides crisp.'},
  {name:'Lemon Bean Smash',need:['white beans','lemon','bread'],lift:['olive oil','parsley','pepper'],method:'Mash drained canned beans with lemon juice. Spoon over toast and finish with any listed extras.'},
  {name:'Cocoa Banana Bites',need:['banana','cocoa','oats'],lift:['peanut butter','cinnamon'],method:'Slice banana, dust with cocoa, and roll in toasted oats. Eat right away.'},
  {name:'Cucumber Hummus Boats',need:['cucumber','hummus'],lift:['paprika','lemon','olive oil'],method:'Halve the cucumber and scoop a shallow channel. Spoon in hummus and finish with any listed extras.'},
  {name:'Peanut Noodle Reboot',need:['noodles','peanut butter','soy sauce'],lift:['lime','scallions','hot sauce'],method:'Cook noodles as directed. Thin peanut butter with a splash of warm water and stir in soy sauce. Toss with hot noodles.'}
];
const toSet = t => new Set(t.toLowerCase().split(/[\n,]/).map(s=>s.trim()).filter(Boolean));
const fridge = {
  id:'10', title:'Fridge Side Quest', tag:'PLAYFUL',
  problem:'Turn an unpromising list of leftovers into one achievable snack or dinner idea.',
  baseline:'A generic recipe suggestion often assumes ingredients you don’t actually have.',
  prompt:'Pick a fridge side quest using available ingredients. Show which base ingredients are on hand, identify optional extras separately, and flag any missing ingredient. Never treat an excluded ingredient as an option.',
  fields:[
    {label:'Ingredients on hand (comma separated)',value:'cabbage, chickpeas, tortilla, lime, hot sauce, cucumber'},
    {label:'Ingredients to exclude (comma separated)',value:'peanut butter'}
  ],
  run([have,avoid]){
    const stock=toSet(have), skip=toSet(avoid);
    if(!stock.size) problem('Add at least one ingredient.');
    for(const item of skip) stock.delete(item);
    const options=recipes.filter(r=>r.need.every(i=>!skip.has(i))).map(r=>({...r,missing:r.need.filter(i=>!stock.has(i)),extras:r.lift.filter(i=>stock.has(i))})).filter(r=>r.missing.length<r.need.length).sort((a,b)=>a.missing.length-b.missing.length || b.extras.length-a.extras.length || b.need.length-a.need.length);
    if(!options.length) return 'NO QUEST FOUND\nNo recipes in this six-recipe deck match your available ingredients. Add more pantry items or use the exact ingredient names.';
    const r=options[0];
    return [r.missing.length?'SIDE QUEST • SHOP FIRST':'SIDE QUEST • READY NOW',r.name,'On hand: '+r.need.filter(i=>stock.has(i)).join(', '),'Missing: '+(r.missing.join(', ')||'none'),'Optional upgrades on hand: '+(r.extras.join(', ')||'none'),r.method,skip.size?'Only exact excluded ingredient names are filtered. For allergies, check labels and cross-contact separately.':''].filter(Boolean).join('\n');
  },
  verify(out){return ['READY NOW','Chickpea Crunch Tacos','Missing: none','Optional upgrades on hand: lime, hot sauce'].every(s=>out.includes(s));}
};

export const toolsC=[audit,agenda,fridge];
