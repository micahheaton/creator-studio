"""Build a live-text, font-embedded SVG field guide and portable print/download files."""
import argparse
import base64
import html
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/"site"
OUT=SITE/"downloads"
INK="#11292e"; CREAM="#fff0cf"; PINK="#eb4585"; MINT="#81d6ba"; GOLD="#ffc47c"
def txt(x,y,string,size=34,color=CREAM,weight=400,extra=""):
    return f'''<text x="{x}" y="{y}" font-family="'Source Sans 3'" font-size="{size}" font-weight="{weight}" fill="{color}" {extra}>{html.escape(string)}</text>'''
def brush(x,y,s,size):
    style=f'font-family="Knewave" font-size="{size}" stroke-linejoin="round"'
    return f'<text x="{x+5}" y="{y+7}" {style} fill="{PINK}">{s}</text><text x="{x}" y="{y}" {style} fill="{MINT}" stroke="{CREAM}" stroke-width="4" paint-order="stroke fill">{s}</text>'
def font_style():
    css=[]
    for file,name,weight in [("Knewave.ttf","Knewave",400),("SourceSans3.ttf","Source Sans 3",400),("SourceSans3-Bold.ttf","Source Sans 3",700)]:
        data=base64.b64encode((SITE/"fonts"/file).read_bytes()).decode()
        css.append(f"@font-face{{font-family:'{name}';font-weight:{weight};src:url(data:font/ttf;base64,{data})}}")
    return "<style>"+"".join(css)+"</style>"
def device(x,y,kind,scale=1):
    content=f'<rect width="142" height="84" rx="8" fill="{CREAM if kind=="pad" else MINT}"/><rect x="6" y="6" width="130" height="70" rx="4" fill="{INK}"/>'
    if kind=="pad":
        content+="".join(f'<rect x="{16+i%4*28}" y="{14+i//4*28}" width="23" height="22" rx="3" fill="{[MINT,GOLD,PINK,CREAM][i%4]}"/>' for i in range(8))
    else:
        content+=f'<path d="M13 42H39l4 -18 7 39 6 -52 6 57 7 -27 6 3h52" fill="none" stroke="{MINT}" stroke-width="4"/>'
    return f'<g transform="translate({x} {y}) scale({scale})">{content}</g>'
def create(chromium):
    OUT.mkdir(exist_ok=True)
    checklist=["Name the input and its visible result.","Check the center crop before you move anything.","Give each subject its own place in each ratio.","Place the caption clear of the action and account controls.","Change one focal point. Export again. Play the saved file at phone size."]
    (OUT/"checklist.txt").write_text("ONE STORY, THREE FRAMES\n\n"+"\n".join("[ ] "+s for s in checklist)+"\n")
    decor=f'<rect width="1080" height="1350" fill="{INK}"/>'
    s=[decor,txt(65,72,"REPLITEERS     /     FIELD GUIDE",26,GOLD,700),brush(65,189,"Save the action.",86),brush(65,295,"Keep the result.",86),
       txt(67,369,"The cause and its effect belong in the same frame.",38),
       f'<path d="M68 402l737 -5 165 3 -98 8 -803 3z" fill="{PINK}"/>',
       txt(67,464,"01   CHECK THE CENTER SLICE",30,GOLD,700),
       f'<rect x="69" y="504" width="943" height="190" rx="6" fill="#24484b"/><path d="M270 596h545" stroke="{PINK}" stroke-width="5"/>',device(125,545,"pad",1.2),device(772,545,"screen",1.2),
       f'<rect x="392" y="507" width="299" height="184" fill="#11292e" fill-opacity=".38" stroke="{CREAM}" stroke-width="4" stroke-dasharray="12 8"/>',
       txt(540,565,"9:16 SLICE",25,CREAM,700,'text-anchor="middle"'),txt(540,739,"A centered crop keeps the wire. Both devices fall outside.",34,CREAM,400,'text-anchor="middle"'),
       txt(67,821,"02   RECOMPOSE THE PAIR",30,GOLD,700),device(85,854,"pad",.92),device(85,949,"screen",.92),
       f'<path d="M152 932v16" stroke="{PINK}" stroke-width="5"/>',txt(255,887,"Stack input over result in a tall frame.",37,CREAM,700),
       txt(255,942,"Move the pad until its active key reads.",33),txt(255,987,"Set the caption in a clear band.",33),
       f'<path d="M68 1064H1010" stroke="#52736f" stroke-width="2"/>',txt(67,1131,"03   PLAY THE FILE",30,GOLD,700),
       txt(67,1194,"Check both subjects and the caption on your phone.",37,CREAM,700),txt(67,1252,"Repeat for 9:16, 1:1, 16:9 and the extra 4:5 feed cut.",33),
       txt(67,1317,"SIGNAL DESK   /   FICTIONAL TWO-LAYER SCENE",24,MINT,700)]
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1350" width="1080" height="1350" role="img" aria-labelledby="title desc"><title id="title">Save the action. Keep the result.</title><desc id="desc">A wide diagram loses both devices to a center crop. A vertical stack retains the pad and its signal display.</desc>'+font_style()+"".join(s)+"</svg>"
    (OUT/"guide.svg").write_text(svg)
    with sync_playwright() as p:
        br=p.chromium.launch(executable_path=chromium,args=["--no-sandbox"])
        page=br.new_page(viewport={"width":1080,"height":1350},device_scale_factor=1)
        page.set_content('<style>*{margin:0}svg{display:block}@page{margin:0;size:1080px 1350px}</style>'+svg)
        page.evaluate("document.fonts.ready");page.screenshot(path=OUT/"guide.png");page.pdf(path=OUT/"guide.pdf",print_background=True,prefer_css_page_size=True)
        br.close()
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--chromium",default="/usr/bin/chromium");create(ap.parse_args().chromium)
