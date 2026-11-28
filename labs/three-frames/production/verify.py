"""Exercise normal browser and collector entry points with anonymous, labeled local test traffic."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
def digest(data):return hashlib.sha256(data).hexdigest()
def http(url,body=None,headers=None):
    req=urllib.request.Request(url,data=body,headers=headers or {})
    try:res=urllib.request.urlopen(req,timeout=5)
    except urllib.error.HTTPError as exc:res=exc
    with res:return res.status,res.read()
def verify(out,chromium):
    out.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp);db=folder/"events.sqlite";password=secrets.token_urlsafe(32)
        sock=socket.socket();sock.bind(("127.0.0.1",0));port=sock.getsockname()[1];sock.close()
        url="http://127.0.0.1:"+str(port)
        auth={"Authorization":"Basic "+base64.b64encode(("admin:"+password).encode()).decode()}
        def start():
            proc=subprocess.Popen([sys.executable,str(ROOT/"server.py"),"--port",str(port)],env={**os.environ,"FRAME_ADMIN_PASSWORD":password,"FRAME_DB":str(db)})
            for _ in range(100):
                try:
                    if http(url+"/style.css")[0]==200:return proc
                except OSError:pass
                time.sleep(.05)
            proc.terminate();raise RuntimeError("Server startup failed")
        def stop(proc):proc.terminate();proc.wait(timeout=5)
        proc=start()
        try:
            report={"formats":{},"pages":{},"page_errors":[]}
            with sync_playwright() as p:
                br=p.chromium.launch(executable_path=chromium,args=["--no-sandbox"])
                report["browser"]=br.version;page=br.new_page(viewport={"width":1280,"height":860})
                page.on("pageerror",lambda exc: report["page_errors"].append(str(exc)))
                page.goto(url+"/?traffic=test");page.wait_for_selector("body[data-ready=true]")
                report["fonts"]=page.evaluate("Object.fromEntries([...document.fonts].map(f=>[f.family+' '+f.weight,f.status]))")
                assert all(v=="loaded" for v in report["fonts"].values())
                page.keyboard.press("Tab");assert page.locator(":focus").inner_text()=="Skip to editor";page.keyboard.press("Enter")
                report["skip_link"]=page.evaluate("location.hash")
                def actual_file(selector,name):
                    with page.expect_download() as dl:page.locator(selector).click()
                    dest=folder/name;dl.value.save_as(dest);return dest.read_bytes()
                def canvas_hash():
                    data=page.locator("#view").evaluate("node=>node.toDataURL().split(',')[1]")
                    return digest(base64.b64decode(data))
                for fmt,dims in {"wide":(1920,1080),"tall":(1080,1920),"square":(1080,1080),"feed":(1080,1350)}.items():
                    page.select_option("#format",fmt)
                    page.locator("#a").focus();page.keyboard.press("Home")
                    baseline=actual_file("#png","before.png")
                    page.locator("#a").focus();page.keyboard.press("End")
                    updated=actual_file("#png","after.png")
                    assert digest(baseline)!=digest(updated) and digest(updated)==canvas_hash()
                    with Image.open(folder/"after.png") as im:assert im.size==dims
                    page.select_option("#anchor","top")
                    anchor=canvas_hash();assert anchor!=digest(updated)
                    page.select_option("#anchor","bottom")
                    report["formats"][fmt]={"dimensions":dims,"before_sha256":digest(baseline),"after_sha256":digest(updated),"top_anchor_sha256":anchor}
                page.locator("summary").click()
                saved=actual_file("#save","saved.json")
                page.set_input_files("#load",str(ROOT/"fixtures"/"invalid.json"))
                assert "Invalid scene" in page.locator("#status").inner_text() and canvas_hash()==digest(updated)
                page.reload();page.wait_for_selector("body[data-ready=true]");page.select_option("#format","feed")
                page.set_input_files("#load",str(folder/"saved.json"));page.wait_for_function("document.querySelector('#status').textContent==='Scene restored.'")
                assert canvas_hash()==digest(updated)
                page.set_input_files("#load",{"name":"legacy.json","mimeType":"application/json","buffer":json.dumps({"version":1,"a":0,"b":0,"caption":"Tap a pad. See the result."}).encode()})
                page.wait_for_function("document.querySelector('#a').value==='0'")
                report["scene_roundtrip"]={"saved_json_sha256":digest(saved),"invalid_kept_pixels":True,"fresh_reload_restored_pixels":True,"legacy_v1":True}
                guide=actual_file('article a[href="downloads/guide.pdf"]',"guide.pdf");assert guide==(ROOT/"site"/"downloads"/"guide.pdf").read_bytes() and guide.startswith(b"%PDF")
                report["guide_download_sha256"]=digest(guide)
                for width in [1280,390]:
                    page.set_viewport_size({"width":width,"height":844});page.goto(url+"/?traffic=test");page.wait_for_selector("body[data-ready=true]")
                    overflow=page.evaluate("document.documentElement.scrollWidth>innerWidth");assert not overflow
                    page.screenshot(path=out/f"site-{width}.png");report["pages"][str(width)]={"horizontal_overflow":overflow}
                page.goto(url+"/?capture&traffic=test");page.wait_for_selector("body[data-ready=true]")
                with sqlite3.connect(db) as conn:prior=conn.execute("select count(*) from events").fetchone()[0]
                page.select_option("#format","wide");actual_file("#png","private.png");page.wait_for_timeout(200)
                with sqlite3.connect(db) as conn:assert conn.execute("select count(*) from events").fetchone()[0]==prior
                report["private_capture_added_events"]=0;br.close()
            anon=http(url+"/admin")[0];wrong=http(url+"/admin",headers={"Authorization":"Basic invalid"})[0]
            assert anon==wrong==401
            assert http(url+"/events",b'{"name":"page_view","notes":"synthetic excluded input"}',{"Content-Type":"application/json"})[0]==400
            pre=http(url+"/admin",headers=auth);assert pre[0]==200
            with sqlite3.connect(db) as conn:
                rows=conn.execute("SELECT name,content,variant,campaign,traffic,count(*) FROM events GROUP BY 1,2,3,4,5 ORDER BY 1").fetchall()
                assert {r[0] for r in rows}=={"page_view","demo_start","download_clicked","export_completed"} and all(r[4]=="test" for r in rows)
            stop(proc);proc=start()
            post=http(url+"/admin",headers=auth)
            assert post==pre and all(row[0].encode() in post[1] for row in rows)
            (out/"admin-readback.html").write_bytes(post[1].replace(b'href=/style.css',b'href=../source/site/style.css'))
            report["admin"]={"anonymous_http":anon,"wrong_auth_http":wrong,"authorized_before_restart":pre[0],"authorized_after_restart":post[0],"response_sha256_before_and_after":digest(pre[1]),"event_rows_before_restart":rows,"same_html_after_restart":True,"unlisted_event_payload_http":400}
            assert not report["page_errors"];(out/"functional.json").write_text(json.dumps(report,indent=2))
        finally:stop(proc)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("output",type=Path);p.add_argument("--chromium",default="/usr/bin/chromium");a=p.parse_args();verify(a.output,a.chromium)
