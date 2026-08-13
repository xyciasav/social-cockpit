import copy
import json
import time
import uuid
from pathlib import Path

import requests


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    """Small client for ComfyUI's API prompt/history/view endpoints."""

    def __init__(self, base_url, workflow_path, mapping_path, timeout=600):
        self.base_url = base_url.rstrip("/")
        self.workflow_path = Path(workflow_path)
        self.mapping_path = Path(mapping_path)
        self.timeout = timeout

    def configured(self):
        return self.workflow_path.exists() and self.mapping_path.exists()

    def _load(self):
        if not self.configured():
            raise ComfyUIError("ComfyUI workflow is not configured. Add workflows/asset-generator.json and its node mapping.")
        workflow = json.loads(self.workflow_path.read_text(encoding="utf-8"))
        mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        required = ("positive_prompt", "negative_prompt", "seed", "output")
        if any(not mapping.get(key, {}).get("node") for key in required):
            raise ComfyUIError("ComfyUI node mapping is incomplete.")
        return workflow, mapping

    @staticmethod
    def _inject(workflow, spec, value):
        node = workflow.get(str(spec["node"]))
        if not node or "inputs" not in node:
            raise ComfyUIError(f"Workflow node {spec['node']} was not found")
        node["inputs"][spec.get("input", "text")] = value

    def generate(self, positive, negative, seed, width=1024, height=1024, on_status=None):
        workflow, mapping = self._load()
        workflow = copy.deepcopy(workflow)
        for key, value in (("positive_prompt", positive), ("negative_prompt", negative), ("seed", seed)):
            self._inject(workflow, mapping[key], value)
        for key, value in (("width", width), ("height", height)):
            if mapping.get(key, {}).get("node"):
                self._inject(workflow, mapping[key], value)
        client_id = str(uuid.uuid4())
        try:
            response = requests.post(self.base_url + "/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
            response.raise_for_status()
            prompt_id = response.json()["prompt_id"]
            if on_status:
                on_status("generating")
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                history_response = requests.get(self.base_url + f"/history/{prompt_id}", timeout=30)
                history_response.raise_for_status()
                history = history_response.json().get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise ComfyUIError("ComfyUI generation failed")
                    outputs = history.get("outputs", {})
                    output_node = outputs.get(str(mapping["output"]["node"]), {})
                    images = output_node.get(mapping["output"].get("field", "images"), [])
                    if images:
                        image = images[0]
                        if on_status:
                            on_status("downloading")
                        result = requests.get(self.base_url + "/view", params={"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}, timeout=120)
                        result.raise_for_status()
                        return result.content
                time.sleep(1)
            raise ComfyUIError("ComfyUI generation timed out")
        except requests.RequestException as exc:
            raise ComfyUIError(f"Asset generation service is unavailable: {exc}") from exc
