"""Capture the working editor in real time and exercise its actual download actions."""
import argparse
import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
async def capture(url, output, chromium):
    output.mkdir(parents=True,exist_ok=True)
    evidence = output / "proof"
    evidence.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(executable_path=chromium,args=["--no-sandbox","--disable-dev-shm-usage","--autoplay-policy=no-user-gesture-required"])
        page=await browser.new_page(viewport={"width":592,"height":575},device_scale_factor=1)
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        await page.goto(url+"/?capture")
        await page.wait_for_selector('body[data-ready=true]')
        await page.add_style_tag(content="body.capture .controls label:nth-child(5),body.capture #png,body.capture #download-clip,body.capture #edit{display:none!important}body.capture .controls{font-size:19px;gap:12px}body.capture #motion,body.capture #play{font-size:20px}body.capture .labtop h2{font-size:36px}")
        async def file_click(selector,dest):
            async with page.expect_download() as item:
                await page.locator(selector).evaluate("(node)=>node.click()")
            await (await item.value).save_as(dest)
        async def save_canvas(path):
            blob=await page.locator("#view").evaluate("(node)=>node.toDataURL('image/png').split(',')[1]")
            path.write_bytes(base64.b64decode(blob))
        await save_canvas(output/"blind.png")
        timeline=[]
        started=time.monotonic()
        done=asyncio.Event()
        async def record():
            index=0
            while not done.is_set():
                t=time.monotonic()-started
                await page.screenshot(path=str(evidence/f"{index:04}.jpg"),type="jpeg",quality=94,animations="allow")
                timeline.append(round(t,4));index+=1
                await asyncio.sleep(max(0,started+index/12-time.monotonic()))
        task=asyncio.create_task(record())
        marks={}
        async def mark(name): marks[name]=round(time.monotonic()-started,4)
        await asyncio.sleep(2)
        await mark("choose_vertical")
        await page.select_option("#format","tall")
        await asyncio.sleep(2)
        await save_canvas(output/"tall-before.png")
        await mark("focus_keyboard")
        await page.locator("#a").focus()
        for _ in range(16):
            await page.keyboard.press("ArrowRight")
            await asyncio.sleep(.075)
        await save_canvas(output/"tall-after.png")
        await asyncio.sleep(1.0);await mark("render_click")
        await page.click("#motion")
        await page.wait_for_selector("#play:not([hidden])",timeout=12000)
        await mark("render_ready");await asyncio.sleep(.7)
        await file_click("#download-clip",output/"tall.webm")
        await page.click("#play");await mark("file_playing")
        await page.wait_for_function("document.querySelector('#player').ended",timeout=6000)
        await mark("file_ended");await asyncio.sleep(1.0)
        done.set();await task
        await file_click("#save",output/"changed.json")
        for fmt in ["wide","square","feed"]:
            await page.select_option("#format",fmt)
            await save_canvas(output/(fmt+"-after.png"))
            await page.click("#motion")
            await page.wait_for_selector("#play:not([hidden])",timeout=12000)
            await file_click("#download-clip",output/(fmt+".webm"))
        artifact_names=["blind.png","tall-before.png","tall-after.png","changed.json"]+[f+".webm" for f in ["wide","square","tall","feed"]]
        report={"browser":browser.version,"capture_fps_target":12,"source_frame_seconds":timeline,"actions":marks,"errors":errors,"sha256":{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in artifact_names}}
        (output/"capture.json").write_text(json.dumps(report,indent=2))
        await browser.close()
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("output",type=Path);ap.add_argument("--url",default="http://127.0.0.1:8765");ap.add_argument("--chromium",default="/usr/bin/chromium");args=ap.parse_args()
    asyncio.run(capture(args.url,args.output,args.chromium))
