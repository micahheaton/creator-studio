"""Six editable guide pages and draft platform copy for the fictional demonstration."""
from pathlib import Path
import argparse
import html
from playwright.sync_api import sync_playwright
from guide import font_style, brush, txt, device, INK, CREAM, MINT, GOLD, PINK

PAGES=[
 ("Find the pair.","A useful demo shows a cause and an effect.","Point to the pad. Point to the scope. If either is missing, the signal has no story."),
 ("Try the bad crop.","A center cut can keep the least useful part.","In this wide source, the 9:16 slice is about 608 pixels wide. Both devices land outside it."),
 ("Stack the action.","Vertical needs a reading order.","Place the input above the result. Follow the wire down and watch the pulse arrive."),
 ("Move one thing.","Hold the scope and caption still.","Change the pad focal point. Compare the two exports at the same moment in the signal."),
 ("Save caption room.","Set the band before the last export.","Try the upper and lower anchors. Preview the caption alongside the destination controls."),
 ("Play the file.","The editor preview is only half the check.","Open the saved file on your phone. Name the input, find its result and read the caption in one pass.")]
POSTS={
 "linkedin":("4:5 feed","The center crop kept the cable. The pad and the screen it controlled were apparently optional.\n\nOne Story, Three Frames uses a fictional hardware demo to show how a good wide layout can lose its meaning in a feed. Place the input and result first, choose a caption band, then play the saved file. The fourth composition is a 4:5 LinkedIn cut.\n\nThe six-page guide walks through the same check.","Save the PDF with your demo checklist."),
 "shorts":("9:16 vertical","Your vertical version deserves more than the middle of your video.\n\nA manual frame lab moves one pad, renders its signal and plays the actual changed file. The center crop misses both ends of the story.","Save this Short and try the input/result check on your next demo."),
 "reels":("9:16 vertical","A perfect crop of the cable. A slightly less perfect demo.\n\nThe companion guide shows what disappears in a center cut and how to stack the input over the result.","Save the guide and compare the exported frame at phone size."),
 "tiktok":("9:16 vertical","Crop a widescreen demo to the middle and sometimes all you get is a very photogenic wire. Move the pad, keep the scope, then play the file. One fictional scene, manually composed.","Pause on the crop check. Can you point to the input and its result?")}
def build(out,chromium):
    out.mkdir(parents=True,exist_ok=True);cards=out/"cards";cards.mkdir(exist_ok=True)
    fs=font_style();svgs=[]
    from PIL import ImageFont
    from guide import SITE
    measure=ImageFont.truetype(str(SITE/"fonts/SourceSans3.ttf"),40)
    def lines(text,width=890):
        result=[""]
        for word in text.split():
            s=(result[-1]+" "+word).strip()
            if result[-1] and measure.getlength(s)>width:result.append(word)
            else:result[-1]=s
        return result
    for i,(headline,lead,detail) in enumerate(PAGES):
        title=brush(70,252,html.escape(headline),76)
        content=txt(70,80,"REPLITEERS  /  FRAME LAB",26,GOLD,700)+txt(1000,80,f"{i+1} / 6",26,MINT,700,'text-anchor="end"')+title
        if i in [0,1,3]:
            content+=f'<path d="M180 522h720" stroke="{PINK}" stroke-width="8"/>'+device(95,442,"pad",1.5)+device(740,442,"screen",1.5)
            if i==1:content+=f'<rect x="384" y="369" width="312" height="329" fill="none" stroke="{CREAM}" stroke-width="4" stroke-dasharray="12 8"/>'
            if i==3:content+=f'<path d="M99 660h177l-20 -15m20 15 -20 15" fill="none" stroke="{PINK}" stroke-width="5"/>'
        else:
            content+=f'<path d="M525 415v222" stroke="{PINK}" stroke-width="8"/>'+device(400,350,"pad",1.7)+device(423,562,"screen",1.7)
            if i==4:content+=f'<rect x="260" y="755" width="560" height="45" rx="7" fill="{CREAM}"/>'+txt(540,785,"Tap a pad. See the result.",29,INK,700,'text-anchor="middle"')
        yy=875
        for line in lines(lead):content+=txt(72,yy,line,42,CREAM,700);yy+=56
        yy+=36
        for line in lines(detail):content+=txt(72,yy,line,40);yy+=55
        content+=txt(72,1290,"ONE STORY, THREE FRAMES   /   FICTIONAL SCENE",25,MINT,700)
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350">{fs}<rect width="1080" height="1350" fill="{INK}"/>{content}</svg>'
        svgs.append(svg);(cards/f"{i+1:02}.svg").write_text(svg)
    with sync_playwright() as p:
        br=p.chromium.launch(executable_path=chromium,args=["--no-sandbox"]);pg=br.new_page(viewport={"width":1080,"height":1350})
        style="<style>*{margin:0}svg{display:block;break-after:page}svg:last-child{break-after:auto}@page{size:1080px 1350px;margin:0}</style>"
        for i,svg in enumerate(svgs):
            pg.set_content(style+svg);pg.evaluate("document.fonts.ready");pg.screenshot(path=cards/f"{i+1:02}.jpg",type="jpeg",quality=92)
        pg.set_content(style+"".join(svgs));pg.evaluate("document.fonts.ready");pg.pdf(path=out/"field-guide-six-pages.pdf",print_background=True,prefer_css_page_size=True);br.close()
    for channel,(ratio,post,cta) in POSTS.items():
        dest=out/channel;dest.mkdir(exist_ok=True)
        (dest/"post.md").write_text("# One Story, Three Frames\n\n"+post+"\n\n"+cta+"\n")
        (dest/"packaging.md").write_text("Private file package. "+ratio+". Deliberate silent text-led cut. Native draft and account preview pending.\n\nCover alt text: Mint brush lettering reads More than the middle beside the hook about a vertical version of a demo.\n\nCompanion alt: A centered crop of a wide pad-and-scope diagram keeps only the cable. A vertical stack restores the two devices.\n")
    (cards/"alt-text.txt").write_text("\n".join(f"{i+1}. {h} {l} {d}" for i,(h,l,d) in enumerate(PAGES)))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("output",type=Path);p.add_argument("--chromium",default="/usr/bin/chromium");a=p.parse_args();build(a.output,a.chromium)
