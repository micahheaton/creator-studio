"""Edit and encode a text-led 50-second film from a real editor session and its files."""
import argparse
from bisect import bisect_right
from functools import lru_cache
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
FONTS=ROOT/"site/fonts"
SIZES={"tall":(1080,1920),"square":(1080,1080),"wide":(1920,1080),"feed":(1080,1350)}
RATIO={"tall":"9:16","square":"1:1","wide":"16:9","feed":"4:5"}
INK="#11292e"; DARK="#0b2024"; MINT="#81d6ba"; CREAM="#fff0cf"; PINK="#eb4585"; GOLD="#ffc47c"
CUES=[
 (0,4,"Your vertical version deserves more than the middle of your video."),
 (4,9,"The pad is on the left. Its signal appears on the right."),
 (9,13,"Center the crop and the cable gets a portrait."),
 (13,15.1,"The editor starts with that center slice."),
 (15.1,17,"Choose vertical. Both devices come back."),
 (17,19.4,"Move only the pad focal point."),
 (19.4,22.6,"Render the changed scene."),
 (22.6,23.25,"Play."),
 (23.25,26,"The saved clip keeps the pad where you put it."),
 (26,31,"Three files play together. Watch for the same pulse."),
 (31,34,"Vertical stacks the input above its result."),
 (34,37,"Square fits the pair side by side."),
 (37,40,"Wide leaves room for the wire."),
 (40,43,"For the 4:5 feed, shorten the stack."),
 (43,47,"Name the input. Find the result. Keep the caption clear."),
 (47,50,"Save the crop guide and check the exported file at phone size.")]
def stamp(t,sep):
    ms=round(t*1000);return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}{sep}{ms%1000:03}"
def sidecars(out):
    out.mkdir(parents=True,exist_ok=True)
    for ext,sep in [("srt",","),("vtt",".")]:
        lines=["WEBVTT",""] if ext=="vtt" else []
        for i,(a,b,s) in enumerate(CUES):
            lines.extend([str(i+1),stamp(a,sep)+" --> "+stamp(b,sep),s,""])
        (out/("captions."+ext)).write_text("\n".join(lines)+"\n")
    (out/"transcript.txt").write_text("TEXT-LED FILM · NO AUDIO\n\n"+"\n".join(c[2] for c in CUES)+"\n")
@lru_cache(maxsize=128)
def font(kind,size):
    n={"brush":"Knewave.ttf","body":"SourceSans3.ttf","bold":"SourceSans3-Bold.ttf"}[kind]
    return ImageFont.truetype(str(FONTS/n),size)
def contain(im,rect):
    x,y,w,h=rect
    thumb=ImageOps.contain(im,(max(1,int(w)),max(1,int(h))),Image.Resampling.LANCZOS)
    return thumb,(int(x+(w-thumb.width)/2),int(y+(h-thumb.height)/2))
class Edit:
    def __init__(self,fmt,capture,cache):
        self.fmt=fmt;self.W,self.H=SIZES[fmt];self.w=960 if fmt=="wide" else 540
        self.k=self.W/self.w;self.h=self.H/self.k;self.wide=fmt=="wide"
        self.capture=capture;self.cache=cache
        self.times=json.loads((capture/"capture.json").read_text())["source_frame_seconds"]
    def coord(self,*p):return tuple(round(v*self.k) for v in p)
    def line(self,im,xy,color,width=2):
        ImageDraw.Draw(im).line(self.coord(*xy),fill=color,width=max(1,round(width*self.k)))
    def text(self,im,x,y,s,size,kind="body",color=CREAM,anchor="lt"):
        d=ImageDraw.Draw(im);f=font(kind,round(size*self.k))
        if kind=="brush":
            d.text(self.coord(x+2.7,y+4),s,font=f,fill=PINK,stroke_width=max(1,round(size*.026*self.k)),stroke_fill=PINK,anchor=anchor)
            d.text(self.coord(x,y),s,font=f,fill=MINT,stroke_width=max(1,round(size*.026*self.k)),stroke_fill=CREAM,anchor=anchor)
        else:d.text(self.coord(x,y),s,font=f,fill=color,anchor=anchor)
    def wrap(self,im,x,y,s,limit,size,kind="body",color=CREAM,leading=1.17):
        f=font(kind,round(size*self.k));lines=[""]
        for word in s.split():
            test=(lines[-1]+" "+word).strip()
            if lines[-1] and f.getlength(test)>limit*self.k:lines.append(word)
            else:lines[-1]=test
        for i,line in enumerate(lines):self.text(im,x,y+i*size*leading,line,size,kind,color)
        return len(lines)*size*leading
    def image(self,im,source,rect):
        thumb,pt=contain(source,self.coord(*rect));im.paste(thumb,pt)
    @lru_cache(maxsize=16)
    def still(self,name):return Image.open(self.capture/name).convert("RGB")
    def frame_box(self):
        if self.wide:return (373,62,531,365)
        return (34,self.h*.22,472,self.h*.54)
    def title(self,im,lines,tag):
        x=46 if self.wide else 38
        self.text(im,x,24,tag,17,"bold",GOLD)
        if self.wide:
            for i,s in enumerate(lines):self.text(im,x,127+56*i,s,46,"brush")
        else:
            self.text(im,x,self.h*.085," ".join(lines),33 if len(" ".join(lines))<19 else 28,"brush")
    @lru_cache(maxsize=32)
    def base(self,key):
        im=Image.new("RGB",(self.W,self.H),INK)
        x=47 if self.wide else 40
        if key=="hook":
            self.text(im,x,self.h*.11,"REPLITEERS   /   FRAME LAB",18,"bold",GOLD)
            y=self.h*(.23 if not self.wide else .24)
            size=78 if not self.wide else 92
            self.text(im,x,y,"More than",size,"brush");self.text(im,x,y+size*1.08,"the middle.",size,"brush")
            y2=y+size*2.26
            if self.wide:
                self.wrap(im,550,165,"Your vertical version deserves more than the middle of your video.",333,35,"bold")
            else:self.wrap(im,x,y2+12,"Your vertical version deserves more than the middle of your video.",455,27,"bold")
        elif key=="source":
            self.title(im,["One action.","Two subjects."],"SOURCE   /   16:9")
            self.image(im,self.still("wide-after.png"),self.frame_box())
        elif key=="crop":
            self.title(im,["Nice cable."],"FAILURE   /   CENTER CROP")
            self.image(im,self.still("blind.png"),self.frame_box())
        elif key=="proof":
            self.title(im,["Move the pad."],"LIVE EDITOR   /   CONTINUOUS TAKE")
        elif key=="sync":
            self.title(im,["Same pulse."],"PLAYBACK   /   THREE EXPORTED FILES")
        elif key in SIZES:
            self.title(im,{"tall":["Stack it."],"square":["Pair it."],"wide":["Spread out."],"feed":["Shorter stack."]}[key],"EXPORTED FILE   /   "+RATIO[key]+("   ·   LINKEDIN" if key=="feed" else ""))
        elif key=="end":
            self.text(im,x,self.h*.10,"TAKEAWAY   /   THE CROP CHECK",18,"bold",GOLD)
            self.text(im,x,self.h*.20,"Keep the pair.",56 if self.wide else 49,"brush")
            labels=["Name the input.","Find the result.","Clear the caption."]
            for i,label in enumerate(labels):
                yy=self.h*(.38+i*.10);self.line(im,[x,yy+13,x+18,yy+13],PINK,4);self.text(im,x+31,yy,label,29,"bold")
            self.text(im,x,self.h*.72,"Save the field guide  ↓",26,"bold",MINT)
        return im
    def decoded(self,fmt,t):
        pics=self.cache[fmt]
        return pics[int(t*12)%len(pics)]
    def frame(self,t):
        key=next((k for end,k in [(4,"hook"),(9,"source"),(13,"crop"),(26,"proof"),(31,"sync"),(34,"tall"),(37,"square"),(40,"wide"),(43,"feed"),(50.1,"end")] if t<end),"end")
        im=self.base(key).copy()
        if key=="hook":
            length=min(1,t/.65)*(315 if self.wide else 350);y=self.h*.23+(92 if self.wide else 78)*2.18
            self.line(im,[46,y,46+length,y-2],PINK,4)
        elif key=="source" and t>=6.3:
            # Place the boundaries of the exact centered 9:16 crop over the source.
            r=self.frame_box(); original=self.still("wide-after.png");thumb,(left,top)=contain(original,self.coord(*r))
            cx=left+thumb.width/2; sw=thumb.height*9/16;d=ImageDraw.Draw(im)
            for xx in (cx-sw/2,cx+sw/2):d.line((xx,top,xx,top+thumb.height),fill=PINK,width=round(3*self.k))
        elif key=="proof":
            elapsed=t-13;idx=max(0,bisect_right(self.times,elapsed)-1)
            with Image.open(self.capture/"proof"/f"{idx:04}.jpg") as screenshot:
                if self.wide:
                    r=(382,49,521,401); detail=(48,246,298,135)
                elif self.fmt=="tall":
                    r=(20,205,432,505); detail=(40,132,370,60)
                else:
                    r=(12,self.h*.22,279,self.h*.52); detail=(299,self.h*.37,207,self.h*.23)
                self.image(im,screenshot,r)
                # The second view magnifies pixels from this very same captured frame.
                if elapsed<4: crop=(349,85,583,145)
                elif elapsed<6.4: crop=(349,149,583,206)
                elif elapsed<9.6: crop=(350,328,581,385)
                else: crop=(73,284,286,371)
                self.image(im,screenshot.crop(crop),detail)
                if not self.wide and self.fmt!="tall":
                    self.text(im,detail[0],detail[1]-19,"LIVE DETAIL",15,"bold",GOLD)
        elif key=="sync":
            if self.wide:slots=[(358,92,145,281),(503,113,148,200),(655,100,250,225)]
            else:slots=[(40,self.h*.225,210,self.h*.50),(265,self.h*.225,219,self.h*.26),(260,self.h*.51,230,self.h*.19)]
            for f,r in zip(["tall","square","wide"],slots):
                self.image(im,self.decoded(f,t-26),r)
        elif key in SIZES:self.image(im,self.decoded(key,t-26),self.frame_box())
        return im
    def caption_overlay(self,s):
        # Space is reserved for the caption band in every composition.
        im=Image.new("RGBA",(self.W,self.H),(0,0,0,0))
        if s==CUES[0][2]:return im  # The hook is already printed in full.
        x=45 if not self.wide else 48;y=self.h*(.79 if self.fmt=="tall" else .82 if not self.wide else .845)
        self.line(im,[x,y-8,x+27,y-8],PINK,3)
        self.wrap(im,x,y,s,(self.w*.75 if self.fmt=="tall" else self.w*.80 if not self.wide else self.w*.87),23 if not self.wide else 24,"bold")
        return im
def run(args,**kwargs):subprocess.run(args,check=True,**kwargs)
def read_motion(capture,temp):
    result={}
    for fmt in SIZES:
        where=temp/fmt;where.mkdir(exist_ok=True)
        run(["ffmpeg","-v","error","-y","-i",str(capture/(fmt+".webm")),"-vf","fps=12,scale='min(iw,900)':-2","-threads","1",str(where/"%03d.png")])
        result[fmt]=[Image.open(p).convert("RGB") for p in sorted(where.glob("*.png"))]
    return result
def encode(edit,where,times,with_captions=False):
    W,H=edit.W,edit.H
    args=["ffmpeg","-y","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r","12","-i","-","-an","-vf","fps=30","-c:v","libx264","-threads","3","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-g","60","-use_editlist","0","-movflags","+faststart",str(where)]
    overlays={}
    with subprocess.Popen(args,stdin=subprocess.PIPE) as enc:
        for t in times:
            frame=edit.frame(t)
            if with_captions:
                s=next(c[2] for c in CUES if c[0]<=t<c[1])
                if s not in overlays:overlays[s]=edit.caption_overlay(s)
                frame.paste(overlays[s],mask=overlays[s].getchannel("A"))
            enc.stdin.write(frame.tobytes())
        enc.stdin.close()
        if enc.wait():raise RuntimeError("Encoder failed")
def caption_master(edit,source,target,temp):
    # A sparse subtitle image track uses the exact same fonts and line breaks as the sample.
    rows=[]
    for i,(a,b,s) in enumerate(CUES):
        p=temp/f"caption-{i:02}.png";edit.caption_overlay(s).save(p)
        rows.extend(["file '"+p.name+"'","duration "+str(b-a)])
    rows.append("file '"+p.name+"'")
    listing=temp/"captions.concat";listing.write_text("\n".join(rows)+"\n")
    run(["ffmpeg","-v","error","-y","-i",str(source),"-f","concat","-safe","0","-i",str(listing),"-filter_complex_threads","1","-filter_complex","[1:v]fps=30,format=rgba[sub];[0:v][sub]overlay=eof_action=repeat:format=auto,format=yuv420p","-t","50","-an","-c:v","libx264","-preset","veryfast","-threads","3","-crf","18","-g","60","-use_editlist","0","-movflags","+faststart",str(target)])
def build(mode,capture,out,formats):
    out.mkdir(parents=True,exist_ok=True);sidecars(out)
    with tempfile.TemporaryDirectory() as d:
        temp=Path(d);cache=read_motion(capture,temp)
        if mode=="sample":
            ed=Edit("tall",capture,cache)
            for i,t in enumerate([1.8,16.5,35.2]):
                frame=ed.frame(t);cue=next(x[2] for x in CUES if x[0]<=t<x[1]);cap=ed.caption_overlay(cue);frame.paste(cap,mask=cap.getchannel("A"));frame.save(out/f"frame-{i+1}.png")
            encode(ed,out/"motion-sample.mp4",[13.75+x/12 for x in range(144)],True)
        else:
            for fmt in formats:
                ed=Edit(fmt,capture,cache);folder=out/fmt;folder.mkdir(exist_ok=True)
                encode(ed,folder/"clean.mp4",(i/12 for i in range(600)))
                caption_master(ed,folder/"clean.mp4",folder/"captioned.mp4",temp)
                cover=ed.frame(2);cover.save(folder/"cover.jpg",quality=93)
                run(["ffmpeg","-v","error","-y","-i",str(folder/"captioned.mp4"),"-frames:v","120","-an","-c:v","libx264","-threads","3","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-g","60","-use_editlist","0","-movflags","+faststart",str(folder/"hook.mp4")])
                print("Completed",fmt,flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["sample","full"]);p.add_argument("capture",type=Path);p.add_argument("out",type=Path);p.add_argument("--formats",nargs="+",choices=SIZES,default=list(SIZES));a=p.parse_args();build(a.mode,a.capture,a.out,a.formats)
