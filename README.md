# Social Cockpit

Simple self-hosted post builder using Qwen through LM Studio and Buffer for approved scheduling.

## Portainer

Deploy a Git-backed stack using this repository, branch `main`, and `docker-compose.yaml`.

The stack pulls the explicitly versioned image:

```text
ghcr.io/xyciasav/social-cockpit:1.11.0
```

Open `http://SERVER_IP:38427`, then configure LM Studio and Buffer under Settings.

For image scheduling, set the Facebook and Instagram Buffer channel IDs separately. Also set **Public app URL** to the stable public HTTPS address that reaches this container; Buffer must be able to download uploaded images from it when the post publishes.

LM Studio on the same Docker host normally uses `http://host.docker.internal:1234`. On another machine, use its LAN IP.

## Asset Generator

The Asset Generator creates six varied standalone concepts, polls ComfyUI, removes a border-connected background, writes a transparent PNG, and traces an alpha-aware limited-color SVG made from actual paths.

Export your ComfyUI workflow in **API format** to `workflows/asset-generator.json`, then fill in the node IDs in `workflows/asset-generator.mapping.json`. The mapping supports positive prompt, negative prompt, seed, optional width/height, and output nodes.

By default the app derives the ComfyUI host from the configured LM Studio URL and uses `COMFYUI_PORT=8188`. Set `COMFYUI_URL` only if that derivation is not correct (for example, `http://comfyui:8188` on a shared Docker network).
