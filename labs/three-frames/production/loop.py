"""Animate the fictional source layers, with one manually directed focal journey."""
import argparse
import base64
from pathlib import Path
import subprocess
import tempfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
def run(args):subprocess.run(args,check=True)
def build(url,out,chromium):
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as d, sync_playwright() as p:
        tmp=Path(d);br=p.chromium.launch(executable_path=chromium,args=["--no-sandbox"])
        page=br.new_page();page.goto(url+"/?capture");page.wait_for_selector("body[data-ready=true]")
        for i in range(96):
            data=page.evaluate("""i=>{
                const t=i/24, phase=(1-Math.cos(2*Math.PI*t/4))/2;
                const canvas=document.createElement('canvas'); Frames.draw(canvas,'feed',{...Frames.initial,a:-.6+1.6*phase},t);
                return canvas.toDataURL().split(',')[1];
            }""",i)
            (tmp/f"{i:03}.png").write_bytes(base64.b64decode(data))
        br.close()
        encoding=["ffmpeg","-v","error","-y","-framerate","24","-i",str(tmp/"%03d.png"),"-an","-vf","scale=640:800"]
        run(encoding+["-c:v","libx264","-preset","veryfast","-threads","2","-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(out/"loop.mp4")])
        run(encoding+["-c:v","libvpx-vp9","-threads","2","-row-mt","1","-cpu-used","5","-crf","34","-b:v","0",str(out/"loop.webm")])
        run(["ffmpeg","-v","error","-y","-i",str(out/"loop.mp4"),"-filter_complex_threads","1","-vf","fps=10,scale=320:400:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer","-loop","0",str(out/"loop.gif")])
        run(["ffmpeg","-v","error","-y","-i",str(tmp/"048.png"),"-vf","scale=640:800","-frames:v","1",str(out/"poster.png")])
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("output",type=Path);ap.add_argument("--url",default="http://127.0.0.1:8765");ap.add_argument("--chromium",default="/usr/bin/chromium");a=ap.parse_args();build(a.url,a.output,a.chromium)
