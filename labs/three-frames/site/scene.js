/* Signal desk: one fictional, manually authored scene. Coordinates use a 540-unit artboard. */
const Frames = (() => {
  const sizes = { tall:[1080,1920], square:[1080,1080], wide:[1920,1080], feed:[1080,1350] };
  const captions = ['Tap a pad. See the result.', 'Make a move. Watch it land.'];
  const initial = { version:2, a:-0.6, b:0, caption:captions[0], anchor:'bottom' };
  const C = { ink:'#11292e', deep:'#0a1e23', teal:'#24484b', grid:'#375a59', mint:'#81d6ba', cream:'#fff0cf', pink:'#eb4585', gold:'#ffc47c' };
  function validate(v) {
    if (!v || ![1,2].includes(v.version) || !captions.includes(v.caption)) throw Error('Choose a supported scene.');
    for (const key of ['a','b']) {
      if (!Number.isFinite(v[key]) || Math.abs(v[key])>1 || Math.abs(v[key]*10-Math.round(v[key]*10))>0.00001) throw Error('Invalid focal point.');
    }
    const anchor = v.version===1 ? 'bottom' : v.anchor;
    if (!['top','bottom'].includes(anchor)) throw Error('Invalid anchor.');
    return {version:2,a:v.a,b:v.b,caption:v.caption,anchor};
  }
  function box(c,x,y,w,h,r,color) { c.fillStyle=color; c.beginPath();c.roundRect(x,y,w,h,r);c.fill(); }
  function label(c,str,x,y,size,color=C.cream,bold=false,align='left') {
    c.fillStyle=color;c.textAlign=align;c.font=(bold?'700 ':'400 ')+size+'px "Source Sans 3"';c.fillText(str,x,y);c.textAlign='left';
  }
  function brush(c,str,x,y,size) {
    c.font=size+'px Knewave';c.lineJoin='round';c.lineWidth=size*.052;c.strokeStyle=C.cream;
    c.fillStyle=C.pink;c.fillText(str,x+size*.045,y+size*.08);c.strokeText(str,x,y);c.fillStyle=C.mint;c.fillText(str,x,y);
  }
  function device(c,type,x,y,s,phase) {
    c.save();c.translate(x,y);c.scale(s,s);
    box(c,-115,-63,230,136,13,C.deep);box(c,-115,-70,230,136,12,type==='pad'?C.cream:C.mint);
    box(c,-107,-62,214,119,8,C.ink);
    if (type==='pad') {
      for(let n=0;n<8;n++) {
        const lit=n===2 && phase>0.18 && phase<0.7;
        box(c,-94+(n%4)*48,-47+Math.floor(n/4)*48,39,38,5,n===2?(lit?C.cream:C.pink):n%3===0?C.gold:C.mint);
      }
      for(const x of [-100,100]) {c.fillStyle=C.teal;c.beginPath();c.arc(x,61,2,0,7);c.fill();}
    } else {
      c.strokeStyle=C.grid;c.lineWidth=1;
      for(let i=-82;i<100;i+=24){c.beginPath();c.moveTo(i,-46);c.lineTo(i,43);c.stroke();}
      for(let j=-40;j<48;j+=20){c.beginPath();c.moveTo(-95,j);c.lineTo(94,j);c.stroke();}
      c.beginPath();c.strokeStyle=C.mint;c.lineWidth=5;
      for (let i=0;i<185;i++) {
        const envelope=Math.exp(-Math.pow((i-(phase*230-12))/26,2));
        const py=4+Math.sin(i*.27)*envelope*37;
        if(i===0)c.moveTo(i-92,py);else c.lineTo(i-92,py);
      }
      c.stroke();box(c,68,57,26,3,1,C.ink);
    }
    c.restore();
  }
  function draw(canvas,format,scene,t=0) {
    const [W,H]=sizes[format];if(canvas.width!==W)canvas.width=W;if(canvas.height!==H)canvas.height=H;
    const c=canvas.getContext('2d'),w=format==='wide'?960:540,h=H*w/W;
    c.setTransform(W/w,0,0,W/w,0,0);c.fillStyle=C.ink;c.fillRect(0,0,w,h);
    const wide=format==='wide',sq=format==='square',phase=(t%2)/2;
    const top=scene.anchor==='top', badgeY=top?42:h*.83, headingY=top?122:80;
    label(c,'SIGNAL DESK   /   MANUAL STUDY',w*.08,top?92:39,wide?20:18,C.gold,true);
    brush(c,'Make it play.',w*.08,headingY,wide?46:40);
    const boxHeight=top?h*.93:h*.77;
    const start=top?145:110;
    const middle=(start+boxHeight)/2;
    const xA=wide?w*.20:sq?w*.26:w*.43, xB=wide?w*.80:sq?w*.74:w*.53;
    const yA=wide||sq?middle:start+(boxHeight-start)*.23;
    const yB=wide||sq?middle:start+(boxHeight-start)*.76;
    const s=wide?1.15:sq?.78:Math.min(1.33,(boxHeight-start)/325);
    const delta=wide?37:sq?12:38, ax=xA+scene.a*delta, bx=xB+scene.b*delta;
    c.lineWidth=4;c.strokeStyle=C.pink;c.beginPath();c.moveTo(ax,yA);
    if(wide||sq){c.lineTo(bx,yB);}else{c.lineTo(ax,yA+(yB-yA)*.52);c.lineTo(bx,yA+(yB-yA)*.52);c.lineTo(bx,yB);}c.stroke();
    device(c,'pad',ax,yA,s,phase);device(c,'screen',bx,yB,s,phase);
    label(c,'INPUT / PAD',ax,yA+89*s,wide?24:sq?18:22,C.cream,true,'center');
    label(c,'RESULT / SCOPE',bx,yB+89*s,wide?24:sq?18:22,C.cream,true,'center');
    box(c,w*.08,badgeY-20,w*.84,40,5,C.cream);label(c,scene.caption,w*.5,badgeY+8,wide?25:22,C.ink,true,'center');
  }
  function crop(canvas,scene,time) {
    const src=document.createElement('canvas');draw(src,'wide',scene,time);canvas.width=1080;canvas.height=1920;
    const sw=src.height*9/16;canvas.getContext('2d').drawImage(src,(src.width-sw)/2,0,sw,src.height,0,0,1080,1920);
  }
  return {sizes,captions,initial,validate,draw,crop,C,brush,label,box};
})();
