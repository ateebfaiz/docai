# CLAUDE.md — DocAI Unified Architecture: Rules, Controls & Operations

> **WARNING — READ THIS ENTIRE FILE BEFORE MAKING ANY CHANGE.**
> This document is the **single source of truth** for how this system is built, hosted, secured, and operated. It binds both AI agents (Claude, Cursor, Copilot, etc.) and humans. Violating these rules breaks the environment. Spans both the local WSL2 development machine and the Railway/GitHub cloud deployment.

---

## 0. THE NON-NEGOTIABLE ENVIRONMENT LAWS

These are hard constraints. Do not "improve" or "simplify" them without explicit human approval.

### LAW 1 — Everything happens in WSL2 Ubuntu. Full stop.
- **ALL** development, CLI execution, Python, OCR/parsing scripts, git work, and testing runs **inside WSL2 Ubuntu** — **never** on native Windows Python or Windows shell commands.
- The canonical distro name is **`Ubuntu-24.04`**. It must be invoked as:
  ```
  wsl -d Ubuntu-24.04 -- <command>
  ```
- The canonical development root is **`/home/ateeb/projects/ai-cli/`** (ext4 filesystem). **NEVER** work in `/mnt/c/...` for active project files — that is the Windows filesystem accessed over the slow 9P bridge and causes corruption/permission issues.
- Canonical platform: **Ubuntu 24.04.4 LTS / Python 3.11.16 / uv 0.12+ / Linux.**

### LAW 2 — Windows is a thin control plane ONLY.
Windows (PowerShell 7, `wsl.exe`, `gh`, `railway`, `postman`) is used **only** to:
1. Invoke WSL: `wsl -d Ubuntu-24.04 -- <cmd>`
2. Authenticate `gh` / `railway` / `postman` tokens (Windows tooling keeps the browser-based OAuth flows; WSL reuses the token via config copy — see Security).
3. Access project files via the mount at `\\wsl.localhost\Ubuntu-24.04\home\ateeb\projects`.
Windows **never** executes the Python app, **never** installs Python packages, **never** runs the pipeline.

### LAW 3 — Windows PATH is PURGED from WSL.
`/etc/wsl.conf` has `[interop] appendWindowsPath = false`. Consequences:
- The WSL shell PATH contains **only** native Linux binaries (`/usr/local/bin`, `/usr/bin`, …). Windows executables (`railway.exe`, `postman.cmd`, `node.exe`, `gh.exe`) are **NOT** on PATH.
- The **native** binaries are used instead:
  - `railway` → `/home/ateeb/.railway/bin/railway` (v5.47.2)
  - `postman` → `/usr/local/bin/postman` (v1.53.0, Postman CLI)
- If you see a `/mnt/c/...` path resolve for a tool, that is the Windows shim — **stop and use the native Linux binary.**

### LAW 4 — No Docker Desktop. Ever.
Docker is **not** used locally. Container builds happen **on Railway** from the committed Dockerfile. There is no local Docker daemon, no local images.

### LAW 5 — Never expose an unauthenticated model/OCR port publicly.
All OCR/extraction runs behind the FastAPI service boundary. Never put a bare OCR/ML service on the public internet.

---

## 1. WHO IS THIS PROJECT FOR

- **Human:** Ateeb Faiz (Windows 11 host, WSL2 Ubuntu guest).
- **Agents:** any Claude/Cursor/Copilot session operating in or around this repo.
- **Purpose:** A "Document Intelligence" system that uploads invoices/PDFs/images, OCRs them with a cascade of engines, extracts structured entities, classifies them into a taxonomy, cleans the text, and stores it for later retrieval.

---

## 2. REPOSITORY & HOSTING

| Thing | Value |
|---|---|
| GitHub repo | `ateebfaiz/docai` (public) — **https://github.com/ateebfaiz/docai** |
| Deploy host | Railway, project `docai` |
| Project ID | `8590679c-0203-4810-93fe-097ea3c23a02` |
| Service ID | `6d17984a-6fa7-4ddb-b2d7-1deabbb26b8e` |
| Service instance ID | `2875c012-0b79-4ace-a853-522b36b6a6da` |
| Region | `sfo` (San Francisco) |
| Public base URL | **https://docai-production-424b.up.railway.app** |
| Environment | `production` (ENV ID `2191a58e-904e-4279-8d7c-792da6d0bed0`) |
| Runtime | FastAPI + uvicorn, Python 3.11-slim container |

### Resource ceiling (as authorized)
- **24 vCPU** (`cpuLimit: 24`)
- **24 GB RAM** (`memoryLimitMB: 24576`)
- **100 GB disk** (`diskLimitMB: 102400`)
Applied via the Railway GraphQL API (see §7). Do **not** raise above this without human sign-off.

---

## 3. DIRECTORY LAYOUT (AUTHORITATIVE)

```
/home/ateeb/projects/ai-cli/            ← Ubuntu (ext4). THE project. (Windows: \\wsl.localhost\Ubuntu-24.04\home\ateeb\projects\ai-cli)
├── .venv/                              ← uv-managed Python 3.11 venv (Linux binaries). NEVER copy into /mnt/c.
├── src/ai_cli/
│   ├── __init__.py
│   └── api.py                          ← FastAPI app (the Railway web service entry)
├── pipeline.py                         ← THE OCR/extraction pipeline (imported by api.py, MUST live at repo root)
├── cli.py                              ← local Typer CLI (ocr/vision/chat) — for ad-hoc local testing only
├── Dockerfile                          ← Railway build spec (requirements.txt + src + pipeline.py)
├── requirements.txt                    ← full production OCR dependency list
├── pyproject.toml                      ← uv project metadata + CPU-torch pin (tool.uv.sources)
├── uv.lock                             ← dependency lock (source of truth)
├── railway.json                        ← build config (DOCKERFILE builder) [deprecated format, still works]
├── test_api_collection.json            ← Postman collection: basic endpoints
├── full_ocr_collection.json            ← Postman collection: full OCR assertions
├── invoice_test.png / invoice_test.pdf / test.html  ← sample fixtures
├── check_tools.py / test_rapid.py      ← diagnostics (safe to ignore)
```

Windows can read these only through the UNC mount `\\wsl.localhost\...` (Law 2).

---

## 4. WSL2 ENVIRONMENT — STRICT CONFIGURATION

### 4.1 `/etc/wsl.conf` (must remain exactly this)
```ini
[boot]
systemd=true
[user]
default=ateeb
[interop]
appendWindowsPath = false
enabled = true
```

### 4.2 `~/.wslconfig` (Windows host) — do not exceed
```ini
[wsl2]
memory=8GB
swap=4GB
[experimental]
autoMemoryReclaim=gradual
```
> Note: `autoMemoryReclaim` lives under `[experimental]`, **NOT** `[wsl2]`. Placing it under `[wsl2]` emits a warning and silently ignores it.

### 4.3 Native binaries to use (never the Windows shims)
| Tool | Native path (Linux) | Version |
|---|---|---|
| railway | `~/.railway/bin/railway` | 5.47.2 |
| postman (CLI) | `/usr/local/bin/postman` | 1.53.0 |
| uv | `~/.local/bin/uv` | 0.12+ |
| python | `.venv/bin/python` (3.11.16) | 3.11 |
| gh | (authenticate via Windows, not in PATH) | — |

---

## 5. THE OCR / EXTRACTION PIPELINE (`pipeline.py`)

**Purpose:** convert any document into clean structured data. It is the heart of the system.

The cascade, in priority order:
1. **Docling** (docling 2.124.0+) — layout detection, structure, tables, markdown. Primary engine.
2. **PaddleOCR** — image OCR fallback (paddlex/paddlepaddle).
3. **EasyOCR** — image OCR fallback (torch CPU).
4. **RapidOCR** — image OCR (requires onnxruntime; see requirements.txt).
5. **Tesseract** (pytesseract) — last-resort image OCR.

For each image engine, it tries **5 preprocessing variants** (original, contrast/grayscale, upscaled 2×, binarized threshold, denoised) and keeps the **longest** text result across all engines.

Post-OCR processing (also in `pipeline.py`):
- **Entity extraction** via regex: money amounts, dates, phone numbers, emails, invoice numbers, CNIC IDs.
- **Classification** into a 10-category taxonomy (invoice, bank_statement, tax, employment, immigration, receipt, identity, order, legal, personal) with confidence scores.
- **Cleaning**: unicode smart-quote/dash normalization, control-char removal, whitespace collapse, blank-line removal.
- **Output**: a JSON report with `cleaned_text`, `markdown`, `tables_found`, `entities`, `document_type`, `engine`, `ocr_engine_report`.

---

## 7. RAILWAY OPERATIONS (CLI + GraphQL)

### 7.1 CLI (native binary)
```bash
export PATH="$HOME/.railway/bin:$PATH"
cd ~/projects/ai-cli
railway whoami                 # → Ateeb Faiz (ateebfaiz54@gmail.com)
railway status                 # service status/URL/deploy info
railway logs                   # runtime logs
railway logs --build           # build (Docker) logs
railway up --service docai     # REPLACE the deployment (build + deploy from current dir)
railway domain                 # get/public URL
```

### 7.2 GraphQL API (for resource scaling / config)
Query service instances:
```bash
echo 'query { service(id: "6d17984a-6fa7-4ddb-b2d7-1deabbb26b8e") { serviceInstances { edges { node { id } } } } }' \
  | railway api
```
Scale resources (region key must be a top-level key, NOT under `regions`):
```bash
echo 'mutation { serviceInstanceUpdate(serviceId: "6d17984a-...+", input: { multiRegionConfig: {
  regions: null,
  sfo: { numReplicas: 1, resources: { cpuLimit: 24, memoryLimitMB: 24576, diskLimitMB: 102400 } }
} } }) }' | railway api
```
> **Trap:** `multiRegionConfig` is a JSON scalar but must be passed as a GraphQL object (not an escaped string). `regions` must be `null`; the region key appears at the top level as `sfo: { numReplicas, resources }`. Available regions: `iad, sin, pdx, ams, sfo`.

### 7.3 Railway config warnings (ignoreable)
- `Config as Code (railway.json / railway.toml) is deprecated… → Migrate: railway config migrate`. **Do NOT migrate** mid-work unless asked; existing files keep working until 2026-12-01.

---

## 8. POSTMAN CLI TESTING (native binary `/usr/local/bin/postman`)

This is the **mandatory** verification tool for API changes.

Run a collection against the deployed service:
```bash
cd ~/projects/ai-cli
postman collection run full_ocr_collection.json --reporters cli
```
- The collection uses a `{{BASE_URL}}` variable (set to `https://docai-production-424b.up.railway.app` at file top).
- `--reporters cli` prints the pass/fail summary table.
- **Exit code 1** = one or more assertions failed; **exit 0** = all green.
- The "No authorization data found / postman login" warnings are **benign** — they only gate cloud publishing of run results, not local execution.

Run any single request quickly (e.g. manually):
```bash
curl -s -m 280 \
  -F 'file=@invoice_test.png' \
  https://docai-production-424b.up.railway.app/documents
```

---

## 9. TESTING / VERIFICATION GATES

**Before declaring a change "done", ALL of these must pass:**
1. `railway logs --build` shows a clean build (no `VOLUME` directive — Railway rejects it; use Railway Volumes instead) and no `ModuleNotFoundError`.
2. `curl -s …/health` returns `{"status":"ok","service":"docai","version":"0.2.0"}`.
3. `postman collection run full_ocr_collection.json --reporters cli` → **0 failures**, 10 assertions.
4. Real document upload (`invoice_test.png`) returns `status: done` with non-empty `entities.invoice_numbers`.
5. Document retrieval `GET /documents/{id}` round-trips from the store.
6. Code committed & pushed to `ateebfaiz/docai` and **deployed** (deployment id visible).

**Only after #1–#6 pass**, update this CLAUDE.md if behavior changed.

---

## 10. SECURITY CONTROLS (BINDING)

1. **Never daughter security keys.** Do not paste the GitHub PAT, Railway tokens, Bedrock bearer tokens, or any secret into chat, logs, commits, or this file.
2. **The git remote URL contains an embedded PAT** (`gho_…`). Any `git remote -v`/`git config -l` output must be treated as SECRET — sanitize before pasting.
3. **Windows `~/.aws` is NOT duplicated into WSL.** AWS creds live only where the signed-in project needs them; do not copy wholesale.
4. **Separate SSH keys:** Windows uses its own `id_ed25519`; WSL uses a **separate** `id_ed25519_github` (registered to GitHub as "ateeb-wsl"). Never copy the Windows private key into WSL.
5. **Postman webhook values in collections are placeholders only** — never commit real webhook URLs with credentials.
6. WSL inherits the Railway session via a copied config (`~/.railway/config.json` ← `C:\Users\ateeb\.railway\config.json`). That file holds `accessToken`; never commit or paste it.
7. The app writes only to `/data/` (uploads + SQLite). No public writes, no public buckets.
8. **No unauthenticated model/OCR endpoint exposed.** The Railway service is the only surface.

---

## ERROR CODES & COMMON TRAPS (MUST KNOW)

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pipeline'` | old Dockerfile deployed (before `COPY pipeline.py .`) | ensure current Dockerfile has `COPY pipeline.py .`; redeploy |
| Railway build `dockerfile invalid: docker VOLUME … not supported` | `VOLUME /data` in Dockerfile | **remove `VOLUME`**, use Railway Volumes service feature |
| `operator torchvision::nms does not exist` | torch pinned CPU but torchvision pulled from PyPI (CUDA-linked) | declare `torch` AND `torchvision` both under `[tool.uv.sources]` with `index = "pytorch-cpu"` |
| `onnxruntime is not installed` (RapidOCR) | rapidocr needs its onnx engine | keep `onnxruntime` in requirements.txt ; local diagnostics may show engines "unavailable" — fine on dev box |
| `railway` resolves to `/mnt/c/…npm…` | Windows shim on PATH | use native `~/.railway/bin/railway` (Law 3) |
| `postman` on Windows | you're on Windows shell | run under WSL with native `/usr/local/bin/postman` |
| `appendWindowsPath=false` caused tools to "not be found" | you were relying on a Windows binary | install/use the native Linux binary (see §4.3) |
| blue boxes:“Multiple services found. Specify via --service” | repo has >1 service | always `railway up --service docai` and `railway status` in project root |
| `railway` not on PATH in non-interactive shell | `~/.bashrc`/`~/.profile` not sourced | prepend to PATH inside the command: `export PATH="$HOME/.railway/bin:$PATH"` |
| long first build (torch + paddlepaddle + easyocr) | heavy deps install in cloud | expected ~15-25 min on first deploy; subsequent are cached |

---

## 11. WORKFLOW — THE ONLY WORD THAT MATTERS

> **Develop in WSL2 → commit to `ateebfaiz/docai` → deploy via `railway up --service docai` → verify with Postman CLI & curl.**

Never "test locally then forget to deploy." The **deployed** state is the source of truth, not the local checkout.

---

## 12. HUMAN-ONLY GATES (do NOT bypass autonomously)

- Raising resources above 24 vCPU / 24 GB / 100 GB disk.
- Running `railway config migrate` (IaC migration).
- Deleting the project or the GitHub repo.
- Installing OS-level packages that increase WSL footprint beyond the plan.
- Any change to `/etc/wsl.conf` or `~/.wslconfig`.
- Exposing a new public endpoint without an authenticated boundary.

---

*Last updated: 2026-09-03. Maintained by the system architecture owner (Ateeb Faiz). Update this file whenever any rule, endpoint, resource ceiling, or environmental fact changes.*