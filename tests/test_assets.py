import os
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="social-cockpit-tests-"))
import app
from asset_processing import isolate_background, vectorize_png


def test_transparency_and_real_svg(tmp_path):
    original=tmp_path/"original.png"; transparent=tmp_path/"transparent.png"; svg=tmp_path/"asset.svg"
    image=Image.new("RGB",(128,128),"white");draw=ImageDraw.Draw(image);draw.ellipse((24,18,104,112),fill="black");image.save(original)
    isolate_background(original,transparent)
    result=Image.open(transparent)
    assert result.mode=="RGBA" and result.getpixel((0,0))[3]==0 and result.getpixel((64,64))[3]>0
    vectorize_png(transparent,svg)
    root=ET.parse(svg).getroot();tags=[node.tag.rsplit("}",1)[-1] for node in root.iter()]
    assert "path" in tags and "image" not in tags and "rect" not in tags


def test_batch_and_partial_offline_failure():
    client=app.app.test_client()
    response=client.post("/api/assets/generate",json={"prompt":"punk halloween skeleton vibe","asset_type":"Mixed","visual_style":"Punk / DIY","color_mode":"Black + white"})
    assert response.status_code==202 and len(response.json["created"])==6
    state=client.get("/api/state").json
    batch=[a for a in state["assets"] if a["batch_id"]==response.json["batch_id"]]
    assert len(batch)==6 and len({a["seed"] for a in batch})==6 and len({a["sub_prompt"] for a in batch})==6


def test_rejects_bad_controls():
    client=app.app.test_client()
    response=client.post("/api/assets/generate",json={"prompt":"test","asset_type":"anything"})
    assert response.status_code==400
