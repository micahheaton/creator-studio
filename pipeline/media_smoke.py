#!/usr/bin/env python3
"""Render diagnostic before/after stills; verify encodes without claiming creative QA.

Requires Python standard library, FFmpeg/ffprobe with libx264/AAC/drawtext,
and a discoverable TrueType font (or --font). No network operations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


PROFILES = (("vertical_1080x1920", 1080, 1920),
            ("portrait_1080x1350", 1080, 1350),
            ("landscape_1920x1080", 1920, 1080))


def sha256(path):
    result = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def execute(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n{result.stderr[-6000:]}")
    return result


def choose_font(explicit):
    if explicit:
        font = Path(explicit).expanduser().resolve()
        if not font.is_file():
            raise ValueError(f"Font does not exist: {font}")
        return font
    candidates = [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                  Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                  Path("C:/Windows/Fonts/arial.ttf")]
    if shutil.which("fc-match"):
        match = subprocess.run(["fc-match", "-f", "%{file}", "DejaVu Sans"], capture_output=True, text=True)
        if match.returncode == 0 and match.stdout:
            candidates.insert(0, Path(match.stdout))
    for font in candidates:
        if font.is_file():
            return font.resolve()
    raise ValueError("No font found; supply --font /path/to/readable.ttf")


def probe(ffprobe, path):
    return json.loads(execute([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(before, after, output, font=None):
    before, after, output = Path(before).resolve(), Path(after).resolve(), Path(output).resolve()
    for path in (before, after):
        if not path.is_file():
            raise ValueError(f"Input does not exist: {path}")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("FFmpeg and ffprobe must be on PATH")
    font = choose_font(font)
    # FFmpeg filter quoting, separate from shell quoting; subprocess never uses a shell.
    font_filter = str(font).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "purpose": "MEDIA_PLUMBING_DIAGNOSTIC_ONLY",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_ready": False,
        "edited_episode": False,
        "publication_quality_claimed": False,
        "powerpoint_ui_demonstrated": False,
        "listening_qa_performed": False,
        "creative_qa_performed": False,
        "independent_motion_qa_performed": False,
        "durable_upload_readback_performed_by_this_script": False,
        "sequence": [{"start_seconds": 0, "end_seconds": 2, "view": "supplied before PNG"},
                     {"start_seconds": 2, "end_seconds": 4, "view": "supplied after PNG"}],
        "visual_treatment": "Static images aspect-fit inside explicit dark letterboxing; persistent diagnostic labels; a hard cut at 2 seconds.",
        "audio": {"source": "FFmpeg-generated 440 Hz sine test signal", "duration_seconds": 4,
                  "sample_rate": 48000, "channels": 2, "volume_multiplier": 0.0632456,
                  "purpose": "Quiet encoding/decoding signal only; not narration, music, or creative audio.",
                  "listening_inspected": False},
        "runtime": {"python": sys.version.split()[0],
                    "ffmpeg": execute([ffmpeg, "-version"]).stdout.splitlines()[0],
                    "ffprobe": execute([ffprobe, "-version"]).stdout.splitlines()[0],
                    "font": str(font)},
        "inputs": [], "exports": [], "plumbing_passed": False}
    for role, path in (("before", before), ("after", after)):
        information = probe(ffprobe, path)
        stream = next(s for s in information["streams"] if s["codec_type"] == "video")
        report["inputs"].append({"role": role, "path": str(path), "sha256": sha256(path),
                                 "byte_length": path.stat().st_size,
                                 "width": stream["width"], "height": stream["height"]})
    save_json(output / "report.json", report)
    for name, width, height in PROFILES:
        target = output / f"{name}.mp4"
        label_size = 44 if width == 1080 else 52
        header_y = 42 if height > 1080 else 24
        inner_width, inner_height = width - 96, height - 230
        common = (f"scale={inner_width}:{inner_height}:force_original_aspect_ratio=decrease:"
                  f"force_divisible_by=2:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101827,"
                  "setsar=1,fps=30,trim=duration=2,setpts=PTS-STARTPTS")
        overlay = (f"drawtext=fontfile='{font_filter}':text='PIPELINE DIAGNOSTIC':"
                   f"fontsize={label_size}:fontcolor=0xFBBF24:x=(w-tw)/2:y={header_y},"
                   f"drawtext=fontfile='{font_filter}':text='BEFORE - supplied static PNG':"
                   f"fontsize=28:fontcolor=white:x=(w-tw)/2:y=h-136:enable='lt(t,2)',"
                   f"drawtext=fontfile='{font_filter}':text='AFTER - supplied static PNG':"
                   f"fontsize=28:fontcolor=white:x=(w-tw)/2:y=h-136:enable='gte(t,2)',"
                   f"drawtext=fontfile='{font_filter}':text='Quiet generated test tone - encoding check only':"
                   "fontsize=24:fontcolor=0xCBD5E1:x=(w-tw)/2:y=h-92,"
                   f"drawtext=fontfile='{font_filter}':text='Not an episode or a PowerPoint UI recording':"
                   "fontsize=24:fontcolor=0xCBD5E1:x=(w-tw)/2:y=h-54")
        filters = (f"[0:v]{common}[before];[1:v]{common}[after];"
                   f"[before][after]concat=n=2:v=1:a=0,{overlay}[video];"
                   "[2:a]volume=0.0632456,afade=t=in:st=0:d=0.05,afade=t=out:st=3.95:d=0.05[audio]")
        command = [ffmpeg, "-hide_banner", "-y", "-filter_complex_threads", "2",
                   "-loop", "1", "-framerate", "30", "-t", "2", "-i", str(before),
                   "-loop", "1", "-framerate", "30", "-t", "2", "-i", str(after),
                   "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                   "-filter_complex", filters, "-map", "[video]", "-map", "[audio]", "-t", "4",
                   "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac", "-b:a", "128k",
                   "-ar", "48000", "-ac", "2", "-movflags", "+faststart",
                   "-metadata", "title=PIPELINE DIAGNOSTIC - not publication ready",
                   "-metadata", "comment=Supplied static PNG sequence and quiet generated test tone; no PowerPoint UI or creative QA.",
                   str(target)]
        started = time.monotonic()
        encoded = execute(command)
        elapsed = round(time.monotonic() - started, 3)
        (output / f"{name}.encode.log").write_text(encoded.stderr, encoding="utf-8")
        information = probe(ffprobe, target)
        save_json(output / f"{name}.ffprobe.json", information)
        videos = [s for s in information["streams"] if s["codec_type"] == "video"]
        audios = [s for s in information["streams"] if s["codec_type"] == "audio"]
        if len(videos) != 1 or len(audios) != 1:
            raise RuntimeError(f"{name}: expected exactly one video and audio stream")
        video, audio = videos[0], audios[0]
        checks = {"dimensions": (video["width"], video["height"]) == (width, height),
                  "frame_rate_30": Fraction(video["avg_frame_rate"]) == 30,
                  "duration_4_seconds": abs(float(information["format"]["duration"]) - 4) < 0.05,
                  "video_duration_4_seconds": abs(float(video["duration"]) - 4) < 0.05,
                  "audio_duration_4_seconds": abs(float(audio["duration"]) - 4) < 0.05,
                  "h264_video": video["codec_name"] == "h264",
                  "aac_audio": audio["codec_name"] == "aac",
                  "yuv420p": video["pix_fmt"] == "yuv420p",
                  "video_frames_120": int(video["nb_frames"]) == 120,
                  "audio_48khz_stereo": int(audio["sample_rate"]) == 48000 and audio["channels"] == 2}
        decoded = execute([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode",
                           "-i", str(target), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
        (output / f"{name}.decode.log").write_text(decoded.stderr, encoding="utf-8")
        checks["full_video_and_audio_decode"] = decoded.returncode == 0 and not decoded.stderr.strip()
        volume = execute([ffmpeg, "-hide_banner", "-i", str(target), "-vn", "-af", "volumedetect", "-f", "null", "-"])
        (output / f"{name}.audio_signal.log").write_text(volume.stderr, encoding="utf-8")
        peak_match = re.search(r"max_volume:\s+([-\d.]+) dB", volume.stderr)
        peak = float(peak_match.group(1)) if peak_match else None
        checks["quiet_nonzero_audio_signal"] = peak is not None and math.isfinite(peak) and -80 < peak < -25
        entry = {"profile": name, "path": str(target), "filename": target.name,
                 "sha256": sha256(target), "byte_length": target.stat().st_size,
                 "width": video["width"], "height": video["height"], "frame_rate": video["avg_frame_rate"],
                 "duration_seconds": float(information["format"]["duration"]),
                 "video_codec": video["codec_name"], "audio_codec": audio["codec_name"],
                 "encoded_video_frames": int(video["nb_frames"]), "measured_audio_peak_dbfs": peak,
                 "encode_elapsed_seconds": elapsed, "command": command, "checks": checks,
                 "plumbing_passed": all(checks.values()), "production_ready": False}
        report["exports"].append(entry)
        save_json(output / "report.json", report)
        if not entry["plumbing_passed"]:
            raise RuntimeError(f"{name}: diagnostic checks failed: {checks}")
        print(f"{name}: {width}x{height}, 4.000s, 30fps, H.264/AAC, 120 frames; full decode passed", flush=True)
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["plumbing_passed"] = len(report["exports"]) == 3 and all(x["plumbing_passed"] for x in report["exports"])
    save_json(output / "report.json", report)
    return report


def main():
    base = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", default=str(base / "pilot_assets/r11_v1_before.png"))
    parser.add_argument("--after", default=str(base / "pilot_assets/r11_v1_after.png"))
    parser.add_argument("--output", default=str(base / "media_diagnostic"))
    parser.add_argument("--font")
    args = parser.parse_args()
    try:
        report = run(args.before, args.after, args.output, args.font)
        print(json.dumps({"report": str(Path(args.output).resolve() / "report.json"),
                          "plumbing_passed": report["plumbing_passed"], "production_ready": False}, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        output = Path(args.output).resolve()
        output.mkdir(parents=True, exist_ok=True)
        save_json(output / "failure.json", {"plumbing_passed": False, "production_ready": False, "error": str(error)})
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
