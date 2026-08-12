# Social Cockpit

Simple self-hosted post builder using Qwen through LM Studio and Buffer for approved scheduling.

## Portainer

Deploy a Git-backed stack using this repository, branch `main`, and `docker-compose.yaml`.

The stack pulls the explicitly versioned image:

```text
ghcr.io/xyciasav/social-cockpit:1.0.3
```

Open `http://SERVER_IP:38427`, then configure LM Studio and Buffer under Settings.

LM Studio on the same Docker host normally uses `http://host.docker.internal:1234`. On another machine, use its LAN IP.
