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
    assert result.width<128 and result.height<128
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


def test_halloween_batch_uses_concrete_single_subjects():
    concepts=app.concepts_for("punk halloween concert","Mixed")
    assert len(concepts)==6
    assert any("skeleton guitarist" in concept for concept in concepts)
    assert any("skeletal hand" in concept for concept in concepts)
    assert all("one " in concept for concept in concepts)
    prompt=app.asset_prompt("punk halloween concert","Mixed","Punk / DIY","Black + white",concepts[0])
    assert "No typography of any kind" in prompt
    assert "only focal object" in prompt


def test_comfyui_defaults_to_docker_host(monkeypatch):
    monkeypatch.delenv("COMFYUI_URL", raising=False)
    assert app.comfy_url()=="http://host.docker.internal:8188"


def test_saved_comfyui_url_overrides_container_default(monkeypatch):
    monkeypatch.setenv("COMFYUI_URL","http://host.docker.internal:8188")
    client=app.app.test_client()
    state=client.get("/api/state").json
    settings=state["settings"]
    settings["comfyui_url"]="http://10.0.0.156:8188"
    response=client.put("/api/settings",json=settings)
    assert response.status_code==200
    assert app.comfy_url()=="http://10.0.0.156:8188"


def test_comfyui_health_has_actionable_failure(monkeypatch):
    class Failure:
        def __call__(self,*args,**kwargs):
            raise app.requests.ConnectionError("offline")
    monkeypatch.setattr(app.requests,"get",Failure())
    response=app.app.test_client().get("/api/assets/health")
    assert response.status_code==503
    assert "--listen 0.0.0.0 --port 8188" in response.json["error"]
