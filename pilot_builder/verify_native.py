"""Inspect native PPTX and SVG objects. This does not exercise PowerPoint UI."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "svg": "http://www.w3.org/2000/svg",
}


def read_native(path):
    with zipfile.ZipFile(path) as archive:
        slides = [n for n in archive.namelist()
                  if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        assert len(slides) == 1, "Expected one slide"
        root = ET.fromstring(archive.read(slides[0]))
        assert not root.findall(".//p:pic", NS), "Unexpected embedded picture"
        assert not root.findall(".//a:blip", NS), "Unexpected image reference"
        objects = {}
        for shape in root.findall(".//p:spTree/p:sp", NS):
            name = shape.find("p:nvSpPr/p:cNvPr", NS).get("name")
            assert name and name not in objects, "Missing or duplicate shape name"
            off = shape.find("p:spPr/a:xfrm/a:off", NS)
            ext = shape.find("p:spPr/a:xfrm/a:ext", NS)
            fill = shape.find("p:spPr/a:solidFill/a:srgbClr", NS)
            geom = shape.find("p:spPr/a:prstGeom", NS)
            objects[name] = {
                "text": "".join(t.text or "" for t in shape.findall(".//a:t", NS)),
                "live_text_runs": len(shape.findall(".//a:t", NS)),
                "x": int(off.get("x")), "y": int(off.get("y")),
                "width": int(ext.get("cx")), "height": int(ext.get("cy")),
                "fill": fill.get("val") if fill is not None else None,
                "geometry": geom.get("prst") if geom is not None else None,
            }
        return objects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="r11_v1")
    args = parser.parse_args()
    if not all(c.isalnum() or c in "_-" for c in args.tag):
        raise ValueError("Invalid build tag")
    builder = Path(__file__).resolve().parent
    assets = builder.parent / "pilot_assets"
    layout = json.loads((builder / "layout.json").read_text())
    edit = layout["programmatic_edit"]
    before_file = assets / f"{args.tag}_before.pptx"
    after_file = assets / f"{args.tag}_after.pptx"
    before = read_native(before_file)
    after = read_native(after_file)
    assert len(before) == len(layout["elements"]) == len(after)
    assert set(before) == {e["id"] for e in layout["elements"]} == set(after)
    changed = []
    for name in before:
        if before[name] != after[name]:
            changed.append(name)
    assert set(changed) == {edit["text"]["id"], edit["shape"]["id"]}, changed
    text_id = edit["text"]["id"]
    assert before[text_id]["text"] == edit["text"]["before"]
    assert after[text_id]["text"] == edit["text"]["after"]
    assert before[text_id]["live_text_runs"] > 0
    assert after[text_id]["live_text_runs"] > 0
    shape_id = edit["shape"]["id"]
    for version, suffix in [(before, "before"), (after, "after")]:
        target = version[shape_id]
        assert target["geometry"] == "ellipse"
        assert target["fill"] == edit["shape"]["fill_" + suffix].lstrip("#")
        assert target["x"] == edit["shape"]["x_" + suffix] * 9525
        assert target["y"] == edit["shape"]["y_" + suffix] * 9525
    for stage in ("before", "after"):
        svg = ET.parse(assets / f"{args.tag}_{stage}.svg").getroot()
        assert not svg.findall(".//svg:image", NS), "SVG contains raster image element"
        assert not svg.findall(".//svg:foreignObject", NS), "Unexpected SVG foreign object"
        svg_objects = {e.get("id"): e for e in svg if e.get("id")}
        assert svg_objects[text_id].tag.endswith("}text")
        assert svg_objects[text_id].text == edit["text"][stage]
        assert svg_objects[shape_id].tag.endswith("}ellipse")
        assert svg_objects[shape_id].get("fill") == edit["shape"]["fill_" + stage]
    report = {
        "status": "PASS_STRUCTURAL_CHECKS_ONLY",
        "build_tag": args.tag,
        "native_object_count": len(before),
        "native_text_object_count": sum(v["live_text_runs"] > 0 for v in before.values()),
        "changed_object_names": changed,
        "untouched_native_objects_verified": len(before) - len(changed),
        "live_text_preserved": True,
        "independent_shape_fill_and_position_preserved": True,
        "svg_embedded_raster_count": 0,
        "pptx_picture_count": 0,
        "before_sha256": hashlib.sha256(before_file.read_bytes()).hexdigest(),
        "after_sha256": hashlib.sha256(after_file.read_bytes()).hexdigest(),
        "powerpoint_ui_test": "BLOCKED_NOT_AVAILABLE",
        "claim_boundary": "XML and programmatic reopen checks prove saved object structure. They do not prove PowerPoint user interaction or platform compatibility.",
    }
    output = assets / f"{args.tag}_native_check.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
