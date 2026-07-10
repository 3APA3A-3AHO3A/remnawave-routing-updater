# Remnawave Routing Auto Updater

🌐 **English** | [Русский](./README.ru.md)

[![CI](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml/badge.svg)](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

A standalone Python + Docker microservice that automatically keeps routing databases (`geoip`, `geosite`) up to date for **Happ** and **INCY** clients in the [Remnawave](https://github.com/remnawave) control panel.

The script talks to the **official Remnawave API** to update subscription settings, which makes it as safe as possible — no direct database access whatsoever. Logs are rotated automatically by Docker's built-in mechanism.

## Features
* Lightweight image based on `Alpine Linux`.
* Works through the official Remnawave API (token-based).
* Independent toggles for Happ and INCY support.
* Auto-creates a default INCY response rule if none exists.
* Automatically generates the `routing.json` file for INCY's `autorouting` feature.
* Automatic retries on network failures and graceful shutdown on `docker stop`.

## 🧠 How it works

It may look like the script downloads and stores the databases itself — it doesn't, and that's the elegant part.

The links to `geoip.dat` and `geosite.dat` (e.g. the Loyalsoldier repository) are baked right into your template and are **refreshed daily on GitHub's side**. The Happ/INCY clients download those databases themselves via the link — but only when they "notice" that the routing configuration has changed.

The script's job is to swap the `LastUpdated` timestamp in the configuration once per interval. That changes the resulting Base64 string, the client considers the routing updated and re-fetches the fresh databases from the links. In other words, the service stores and downloads nothing on its own — it merely "nudges" the clients to pull the latest databases. That keeps both load and risk to a minimum.

## ⚙️ Client support

Each client type is controlled by its own toggle in `.env`, so you enable only what you need.

**Happ (`ENABLE_HAPP`, on by default).** Works out of the box: the script writes the built-in top-level `happRouting` field, so Happ clients are covered without any extra setup. If you also keep a response rule whose name contains `Happ`, its `routing` header is updated too.

**INCY (`ENABLE_INCY`, off by default).** When enabled, the script updates the `routing` and `autorouting` headers of **every** response rule whose name looks like `Incy` (case-insensitive). If no such rule exists, it **creates a default one automatically**, so manual panel setup is optional. A newly created rule uses `responseType: XRAY_BASE64` (closest to the panel default); rules that already exist keep their own `responseType` untouched — override the created-rule type via `INCY_RESPONSE_TYPE`. INCY also requires `AUTOROUTING_URL` to point at your served `routing.json` (see the reverse proxy section below).

> 💡 You can still pre-create an `Incy` rule manually if you need custom match conditions — the script will fill in and keep its headers up to date. See [response_rules.example.json](./response_rules.example.json) for the structure.

To use the API, create a token under **Remnawave Settings → API Tokens** with `Read/Write` permissions for the *Subscription Template* section and copy it into your `.env` file.

## 🔧 Environment variables

All parameters live in the `.env` file (created from `.env.example`):

| Variable | Purpose | Default |
| --- | --- | --- |
| `PANEL_URL` | Your panel URL (with `https://`, no trailing slash) | `http://remnawave:3000` |
| `API_TOKEN` | Remnawave API token (required) | — |
| `ENABLE_HAPP` | Enable Happ support | `true` |
| `ENABLE_INCY` | Enable INCY support (updates or creates the Incy rule) | `false` |
| `INCY_RESPONSE_TYPE` | `responseType` for the auto-created INCY rule only | `XRAY_BASE64` |
| `AUTOROUTING_URL` | URL your web server serves `routing.json` from (needed for INCY) | `https://sub.your-domain.com/routing.json` |
| `UPDATE_INTERVAL_SECONDS` | Update interval in seconds | `21600` (6 hours) |
| `REQUEST_TIMEOUT_SECONDS` | HTTP request timeout for the API | `30` |
| `RETRY_ATTEMPTS` | Number of retries on a network error | `3` |
| `GEO_MIRROR_ENABLED` | Download `geoip.dat` / `geosite.dat` to this server | `false` |
| `GEOIP_URL` / `GEOSITE_URL` | Public `.dat` URLs handed to clients (empty = template default) | — |
| `GEOIP_SOURCE_URL` / `GEOSITE_SOURCE_URL` | Upstream the server pulls the databases from | Loyalsoldier GitHub |
| `STAMP_MODE` | `LastUpdated` bump: `interval` or `on_geo_change` | `interval` |

## 🚀 Installation and launch

1. Clone the repository:
   ```bash
   git clone https://github.com/3APA3A-3AHO3A/remnawave-routing-updater.git
   cd remnawave-routing-updater
   ```

2. Set up the configuration:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Paste your `API_TOKEN`, set `PANEL_URL`, and enable the clients you need (`ENABLE_HAPP` / `ENABLE_INCY`). For INCY, also set `AUTOROUTING_URL`.*

3. Create your own routing template from the example and edit it:
   ```bash
   cp template.json my-template.json
   nano my-template.json
   ```
   Add your own rules (`DirectSites`, bypass databases, etc.). **Note:** do not add the `LastUpdated` field — the script generates it automatically.
   > 💡 We work with `my-template.json` (which is not tracked by git) so your edits don't conflict when you update the project via `git pull`. The `template.json` file stays as the reference.

4. Start the service:
   ```bash
   docker compose up -d --build
   ```

5. View the logs:
   ```bash
   docker logs -f remna-routing-updater
   ```

## ✅ Verifying it works

On a successful start you'll see lines like these in the logs:
```
Service started. Interval: 21600 sec. | API: https://panel.your-domain.com | Happ: on, Incy: off
File /app/output/routing.json saved successfully.
✅ Remnawave database updated successfully! Happ: field set, 1 rule(s) updated
```
The `./output/routing.json` file should appear on disk, and `https://sub.your-domain.com/routing.json` (after setting up the reverse proxy below) should serve valid JSON.

## 🐞 Troubleshooting

* **`CRITICAL ERROR: API_TOKEN is not set`** — `API_TOKEN` is empty in `.env`.
* **`CRITICAL ERROR: both ENABLE_HAPP and ENABLE_INCY are disabled`** — enable at least one client in `.env`.
* **`AUTOROUTING_URL not changed (using example.com)`** — set a real link in `.env` for INCY.
* **`API error: 'response' object not found`** — wrong `PANEL_URL` or a token without the required permissions (`Subscription Template: Read/Write`).
* **`/routing.json` returns HTML instead of JSON** — the reverse proxy is intercepting the request; check the setup below (Caddy requires a `handle` block, Traefik needs higher router priority).

## 🌐 Web server (Reverse Proxy) setup for INCY

**Why is this needed?** INCY's `autorouting` feature periodically downloads a JSON file from a direct link. The script generates a fresh file into the local `./output` folder; your web server has to expose it at a public URL.

Serve it from your **subscription domain** — the client already refreshes its subscription there, so the routing file belongs on the same host. All examples use `https://sub.your-domain.com/routing.json`.

> ⚠️ **The public URL must exactly match `AUTOROUTING_URL` in your `.env`,** or autorouting silently fails.

These examples extend the official Remnawave reverse-proxy setups ([docs.rw/install/reverse-proxies](https://docs.rw/install/reverse-proxies/)), which document **Caddy, Nginx, Traefik and Angie**. Remnawave itself must stay on the domain root (it does not support running under a sub-path), but serving one extra static file at the `/routing.json` path next to it is fine — the subscription page stays at `/`, we just carve out a single path. Every example sets `Cache-Control: no-store` so clients always get the latest file, and assumes the official subscription container `remnawave-subscription-page` on port `3010`.

> Running HAProxy in front? It's usually a TCP/port balancer rather than an HTTP proxy — terminate HTTPS on the Nginx/Caddy/Angie behind it and serve `/routing.json` there using the matching example below.

After setup, verify:
```bash
curl -I https://sub.your-domain.com/routing.json
# Expect: HTTP/2 200, Content-Type: application/json, Cache-Control: no-store
```

### 🟢 Nginx & 🟣 Angie

Angie is an Nginx fork, so the same block works for both. Add it to the `server { ... }` that serves your subscription domain, *before* the main `location /`.

#### Option A: proxy on the host (no Docker)
```nginx
location = /routing.json {
    alias /opt/remnawave-routing-updater/output/routing.json;
    types { } default_type application/json;
    add_header Cache-Control "no-store" always;
}
```
*Apply:* `nginx -s reload` (or `angie -s reload`)

#### Option B: proxy running in Docker
1. Mount the output folder into the proxy container (its `docker-compose.yml`):
```yaml
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/nginx/routing_output:ro
```
*Recreate:* `docker compose up -d`
2. Point the location at the internal path:
```nginx
location = /routing.json {
    alias /usr/share/nginx/routing_output/routing.json;
    types { } default_type application/json;
    add_header Cache-Control "no-store" always;
}
```
*Apply:* reload the proxy container (`docker exec <proxy> nginx -s reload`).

---

### 🔵 Caddy

> ⚠️ **Important:** wrap the file serving in a `handle` block, otherwise `reverse_proxy` intercepts the request.

#### Option A: Caddy on the host (no Docker)
```caddyfile
https://sub.your-domain.com {
    # 1. Serve the static JSON
    @routing path /routing.json
    handle @routing {
        root * /opt/remnawave-routing-updater/output
        file_server
        header Content-Type application/json
        header Cache-Control no-store
    }

    # 2. Everything else goes to the subscription page
    reverse_proxy * http://127.0.0.1:3010
}
```
*Apply:* `systemctl reload caddy`

#### Option B: Caddy in Docker
1. Mount the output folder into the Caddy container:
```yaml
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/caddy/routing_output:ro
```
*Recreate:* `docker compose up -d`
2. Point `root *` at the mounted path and proxy to the subscription container by name:
```caddyfile
https://sub.your-domain.com {
    @routing path /routing.json
    handle @routing {
        root * /usr/share/caddy/routing_output
        file_server
        header Content-Type application/json
        header Cache-Control no-store
    }

    reverse_proxy * http://remnawave-subscription-page:3010
}
```
*Apply:* `docker exec -w /etc/caddy your_caddy_container caddy reload`

---

### 🟠 Traefik

Traefik is a proxy, not a file server, so run a tiny static-file container on the same `remnawave-network` and route `/routing.json` to it:
```yaml
  routing-file:
    image: nginx:alpine
    container_name: remna-routing-file
    restart: unless-stopped
    networks:
      - remnawave-network
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/nginx/html:ro
```
The official Remnawave Traefik setup uses the **file provider** (a dynamic-config file), so add a router there:
```yaml
http:
  routers:
    routing-json:
      rule: "Host(`sub.your-domain.com`) && Path(`/routing.json`)"
      entryPoints:
        - https
      service: routing-json
      priority: 1000          # win over the subscription router for this path
      tls:
        certResolver: letsencrypt
      middlewares:
        - routing-nostore
  services:
    routing-json:
      loadBalancer:
        servers:
          - url: "http://remna-routing-file:80"
  middlewares:
    routing-nostore:
      headers:
        customResponseHeaders:
          Cache-Control: "no-store"
```
Match `entryPoints`/`certResolver` to your `traefik.yml`. *Recreate:* `docker compose up -d`

> If your Traefik instead uses the Docker label provider, drop the YAML above and put equivalent labels on the `routing-file` service: the `...routers.routing-json.rule`, `...priority=1000`, `...service=routing-json`, `...loadbalancer.server.port=80`, and the `routing-nostore` middleware.

## 🗺️ Geo database mirror (for regions where GitHub is blocked)

Happ/INCY clients download `geoip.dat` / `geosite.dat` from the URLs in your template
(`Geoipurl` / `Geositeurl`) — by default from GitHub. In Russia these GitHub downloads
often fail, which breaks routing on the client. This service can mirror both databases
onto your own server (next to `routing.json`) and hand clients your domain instead.

**How it works.** Each cycle the service downloads the databases from upstream (GitHub is
reachable from most servers) with a conditional request — unchanged files return `304` and
are skipped. Files are written atomically, so the reverse proxy never serves a half-written
file. The client still downloads the **full** file and trims it locally (`UseChunkFiles`),
so you only ever host **two static files** — no chunk manifests, no special naming.

**Enable it** in `.env`:
```dotenv
GEO_MIRROR_ENABLED=true
GEOIP_URL=https://sub.your-domain.com/geoip.dat
GEOSITE_URL=https://sub.your-domain.com/geosite.dat
```
`GEOIP_URL` / `GEOSITE_URL` are what clients receive; leave them empty to keep the
template's GitHub defaults. Keep `template.json` pointing at GitHub so non-RU deployments
work out of the box — the switch lives entirely in `.env`.

### Serving the `.dat` files

The databases land in the same `./output` folder as `routing.json`, so you just extend the
[reverse-proxy setup above](#-web-server-reverse-proxy-setup-for-incy) with two more files.
Unlike `routing.json` they change rarely, so they can be cached.

**Nginx & Angie** — add next to the `/routing.json` location:
```nginx
location ~ ^/(geoip|geosite)\.dat$ {
    root /opt/remnawave-routing-updater/output;   # or the mounted path when in Docker
    default_type application/octet-stream;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri =404;
}
```

**Caddy** — add another `handle` inside the same site block:
```caddyfile
@geo path /geoip.dat /geosite.dat
handle @geo {
    root * /opt/remnawave-routing-updater/output   # or the mounted path when in Docker
    file_server
    header Content-Type application/octet-stream
    header Cache-Control "public, max-age=86400"
}
```

**Traefik** — the `remna-routing-file` nginx container already serves the `./output`
folder, so just widen the router rule to include the databases:
```yaml
rule: "Host(`sub.your-domain.com`) && (Path(`/routing.json`) || Path(`/geoip.dat`) || Path(`/geosite.dat`))"
```

Verify (ideally from within Russia):
```bash
curl -I https://sub.your-domain.com/geoip.dat
# Expect: HTTP/2 200, Content-Type: application/octet-stream, a few MB Content-Length
```

### Re-stamp only when the database changes (optional)

By default (`STAMP_MODE=interval`) the `LastUpdated` stamp — which tells clients to
re-download the geo files — is bumped every cycle. With the mirror on you can switch to
`STAMP_MODE=on_geo_change`: the stamp advances (and the panel is patched) **only when the
upstream database actually changed**. That change is detected for free from the mirror's
conditional request, so you can lower `UPDATE_INTERVAL_SECONDS` to poll more often without
re-writing the panel or nudging every client on each cycle. One interval covers both jobs —
no separate poll setting is needed.

## 📄 License

Distributed under the MIT License — see the [LICENSE](./LICENSE) file.
