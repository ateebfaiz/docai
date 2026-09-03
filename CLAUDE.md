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

### OCR cascade (priority order)
1. **Docling** (2.124.0+) — layout/structure/markdown. Primary engine, run with a **fast path**: `PdfPipelineOptions(do_ocr=False, do_table_structure=False)` — cuts a 4-page PDF from ~90s to ~25s. If the fast path throws or returns nothing, it **falls back to full default conversion** (never fails silently).
2. **PaddleOCR** → **EasyOCR** → **RapidOCR** (needs onnxruntime) → **Tesseract** — image OCR fallbacks; each tries 5 preprocessing variants (original, contrast/grayscale, 2× upscale, binarized, denoised), keeping the longest text result.

### Scanned-PDF handling (no text layer)
- pypdf text extraction first (instant)
- Then PyMuPDF (fitz) rasterizes pages @200dpi → OCR cascade per page

### Text-based files
`.json/.md/.csv/.txt/.xml/.html/.log` are read directly via `_read_fallback()` — NEVER through image OCR (which caused `cannot identify image file` 500s historically).

Post-OCR processing (also in `pipeline.py`):
- **Entity extraction** via regex: money amounts, dates, phone numbers, emails, invoice numbers, CNIC IDs, account numbers, order numbers, registration numbers, names.
- **Content-adaptive classification** into an 11-category taxonomy (invoice, bank_statement, tax, employment, immigration, receipt, identity, order, legal, personal, **metadata**) using:
  - Weighted keyword scoring (distinctive terms carry higher weight)
  - Negative signals (e.g., "order to make" down-ranks `order`; "master guide" down-ranks `tax`/`identity`)
  - Entity hints (extracted `registration_numbers` boost `tax`; `invoice_numbers` boost `invoice`)
  - `_MIN_CONFIDENCE = 0.50` — below this, batch processor quarantines
- **Typed field extraction** per document type: invoice → `invoice_number/total_amount/due_date/vendor`; tax → `registration_no/tax_year/taxpayer`; bank → `account_no`; etc. Only non-empty fields returned.
- **Cleaning**: unicode smart-quote/dash normalization, control-char removal, whitespace collapse, blank-line removal.
- **Output**: a JSON report with `cleaned_text`, `markdown`, `tables`, `tables_found`, `page_count`, `entities`, `fields`, `document_type`, `classification_confidence`, `engine`, `ocr_engine_report`.

**Text-based file routing:** see "Text-based files" above.

---

## 5b. BATCH PROCESSOR (`batch_processor.py`)

**Purpose:** walk the entire document corpus (555+ files), send each to the Railway OCR pipeline, and auto-organize/rename by content.

- **Folder-aware classification correction**: uses the existing taxonomy folder as a prior. If the classifier confidence < 0.70 AND the source folder maps to a doc_type, the folder wins (e.g., file in `2. Taxation_and_FBR` → `tax` regardless of classifier noise).
- **Quarantine rule**: confidence < 0.50 → `uncategorized` → routed to `00. _QUARANTINE` for human review.
- **Content-driven rename**: e.g., `Tax_3410422179127.pdf`, `Invoice_YS-2026-0042.pdf`, `Meta_<original_name>.md` for metadata files.
- **State file**: `.docai_batch_state.json` tracks processed docs by SHA256 digest (idempotent re-runs).
- **Dry-run mode**: `--dry-run` calls the API for classification but doesn't move files.
- **Issue rollup**: prints LOW-CONF, UNCATEGORIZED, and HTTP error summary at end.

Usage:
```bash
cd ~/projects/ai-cli
# Classification dry-run (API calls, no file changes):
.venv/bin/python batch_processor.py '<src>' '<dest>' --dry-run
# Apply stored classifications — copy+rename into taxonomy folders (no API calls):
.venv/bin/python batch_processor.py '<src>' '<dest>' --organize-only
# Full live pass (classify + copy):
.venv/bin/python batch_processor.py '<src>' '<dest>'
```

- **Parallel workers:** `BATCH_WORKERS=8` (default 6) via env var; uploads run concurrently against Railway.
- **Async-aware:** uploads return `201 {status: queued}` → batch polls `GET /documents/{id}` every 5s until `done`/`failed` (15-min per-doc deadline). Handles legacy sync responses too.
- **Idempotent:** SHA256-digest state file `.docai_batch_state.json` — successful docs are never re-sent; failures auto-retry on next run.
- **PERFORMANCE (measured 2026-09-03):** ~25s/doc single-stream, ~170 docs/min with 8 workers → 555-file corpus in ~8 min.
- **--organize-only:** replays stored `folder`/`new_name` from state; collision-safe (`_1`, `_2` suffixes — needed because multiple docs of the same person share a CNIC/registration).

---

## 5b-2. THE ORGANIZED CORPUS (current state, 2026-09-03)

- **Source:** `C:\Users\ateeb\OneDrive\Documents\Documents\` (555 files, 12 taxonomy folders, NEVER modified).
- **Organized copy:** `C:\Users\ateeb\OneDrive\Documents\Documents_organized\` — **547 files** copied + renamed; originals untouched.
- 8 SHA256-duplicate files intentionally excluded (identical content already filed).
- 364 collision-renames (`_1`, `_2`…) — expected: same-person docs share CNIC/registration.
- Distribution: tax 127, legal 103, identity 86, bank_statement 74, immigration 49, education 34, invoice 31, personal 25, corporate 7, medical 6, metadata 5, order/receipt/employment 4. Quarantine holds `Meta_*` planning manifests.
- **The state file is the classification source of truth.** Deleting it forces a full re-classification; keep it.
- All 547 docs are also rows in Postgres with entities/fields/cleaned_text — searchable via `/search`.

---

## 5c. SEMANTIC STORAGE & SEARCH (LIVE — Postgres)

- **Status: ACTIVE.** Health endpoint reports `"storage": "postgres"` (SQLite fallback only when `DATABASE_URL` unset, e.g. local dev).
- **Wiring:** `DATABASE_URL` on the `docai` service = reference `${{ Postgres.DATABASE_URL }}` — resolved by Railway, no secrets in code. Set via `railway variable set 'DATABASE_URL=${{ Postgres.DATABASE_URL }}' --service docai`.
- **NOTE:** two Postgres services exist in the project (`Postgres` f59f9ecd…, `Postgres-WbT1` b2b9ada4…) from an accidental double `railway add`. The reference targets `Postgres`. Cleanup pending (HUMAN GATE — confirm before deleting either).
- `documents` table: `id, name, status(queued/done/failed), created_at, doc_type, classification_confidence, fields(json), entities(json), tables(json), cleaned_text, markdown, source_format`.
- **`/search?q=<term>&doc_type=<type>`** — matches across entities/fields/cleaned_text/filename (ILIKE on Postgres, LIKE on SQLite).
- Async status lifecycle: `queued → (background pool) → done | failed`. `GET /documents/{id}` reflects live status.

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

Run any single request quickly:
```bash
# ASYNC (default, any file size — returns 201 queued instantly, poll for result):
curl -s -F 'file=@big_55page.pdf' https://docai-production-424b.up.railway.app/documents
# → {"id":"doc-…","status":"queued","poll":"/documents/doc-…"}
curl -s https://docai-production-424b.up.railway.app/documents/doc-…   # poll until status=done

# SYNC (small files — blocks until full result):
curl -s -F 'file=@invoice_test.png' 'https://docai-production-424b.up.railway.app/documents?sync=true'
```

---

## 9. TESTING / VERIFICATION GATES

**Before declaring a change "done", ALL of these must pass:**
1. `railway logs --build` shows a clean build (no `VOLUME` directive — Railway rejects it) and no `ModuleNotFoundError`.
2. `curl -s …/health` returns `{"status":"ok","service":"docai","version":"0.3.0","storage":"postgres"}`.
3. `postman collection run full_ocr_collection.json --reporters cli` → **0 failures**.
4. Real upload returns `201 queued` (async) and `GET /documents/{id}` reaches `status: done` with non-empty entities.
5. Small-file sync check: `?sync=true` returns full result with `entities.invoice_numbers` non-empty.
6. Code committed & pushed to `ateebfaiz/docai` and **deployed** (deployment id visible in `railway status`).

**Only after #1–#6 pass**, update this CLAUDE.md if behavior changed.

---

## 10. SECURITY CONTROLS (BINDING)

1. **Never paste secrets** (GitHub PATs, Railway tokens, Bedrock bearer tokens) into chat, logs, commits, or this file.
2. **Git remote is SSH** (`git@github.com:ateebfaiz/docai.git`) via the WSL `id_ed25519_github` key. **NEVER revert to an HTTPS URL with an embedded PAT** — that was a real credential leak that got fixed (2026-09-03). If you ever see `https://gho_…@github.com` in a remote, treat it as an incident.
3. **Windows `~/.aws` is NOT duplicated into WSL.** AWS creds live only where the signed-in project needs them.
4. **Separate SSH keys:** Windows uses its own `id_ed25519`; WSL uses a **separate** `id_ed25519_github` (registered to GitHub as "ateeb-wsl"). Never copy the Windows private key into WSL.
5. Postman collection values are placeholders only — never commit real webhook URLs with credentials.
6. Railway auth lives in `~/.railway/config.json` (copied from Windows). It holds `accessToken`/`refreshToken` — never commit, paste, or print it.
7. The app writes only to `/data/` (uploads + SQLite) and Postgres. No public writes, no public buckets.
8. **No unauthenticated model/OCR endpoint exposed.** The Railway service is the only surface.
9. **PII corpus:** the Documents folder contains CNICs, passports, bank statements, legal complaints. Treat filenames, extracted text, and search results as sensitive; never dump full OCR text of real documents into logs or commits.

---

## ERROR CODES & COMMON TRAPS (MUST KNOW)

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pipeline'` | old Dockerfile deployed (before `COPY pipeline.py .`) | ensure current Dockerfile has `COPY pipeline.py .`; redeploy |
| Railway build `dockerfile invalid: docker VOLUME … not supported` | `VOLUME /data` in Dockerfile | **remove `VOLUME`** |
| `operator torchvision::nms does not exist` | torch pinned CPU but torchvision pulled CUDA-linked from PyPI | declare `torch` AND `torchvision` both under `[tool.uv.sources]` with `index = "pytorch-cpu"` |
| `onnxruntime is not installed` (RapidOCR direct) | rapidocr's own engine needs it | keep `onnxruntime` in requirements.txt; docling's internal RapidOCR path works regardless |
| `cannot identify image file … .pdf` | OCR cascade fired on a PDF (docling returned empty text) | CURRENT CODE FIXED: fast-path fallback + pypdf/PyMuPDF; if you reintroduce it, check `run_full_pipeline` guards |
| Docling suddenly slow (60-90s/PDF) | table-structure model + internal OCR enabled | verify fast path (`do_ocr=False, do_table_structure=False`) is applied and its try/except fallback didn't trigger |
| **HTTP 502 "Application failed to respond"** on big uploads | synchronous processing exceeded Railway edge timeout | USE ASYNC: default upload → `201 queued` → poll. Never `?sync=true` for large files |
| `railway` resolves to `/mnt/c/…npm…` | Windows shim on PATH | use native `~/.railway/bin/railway` (Law 3) |
| "Multiple services found. Specify via --service" | repo has >1 service | always `railway up --service docai` |
| `railway` not on PATH in non-interactive shell | `.bashrc` not sourced | `export PATH="$HOME/.railway/bin:$PATH"` inline |
| `railway add --database postgres` hangs | interactive prompt | it may still create the service — check `railway api` service list; avoid double-adds |
| `/tmp/…` files vanish between WSL calls | WSL VM recycled /tmp | write temp files to `$HOME` or `/mnt/c/…` scratchpad instead |
| wsl.exe background output logs empty | output buffering quirk | redirect inside WSL to a file (`> /home/ateeb/x.log`) and read that file |
| First deploy slow (torch + paddlepaddle + easyocr) | heavy deps in cloud | expected 15-25 min; cached after |

---

## 11. WORKFLOW — THE ONLY WORD THAT MATTERS

> **Develop in WSL2 → commit to `ateebfaiz/docai` → deploy via `railway up --service docai` → verify with Postman CLI & curl.**

Never "test locally then forget to deploy." The **deployed** state is the source of truth, not the local checkout.

---

## 12. HUMAN-ONLY GATES (do NOT bypass autonomously)

- Raising resources above 24 vCPU / 24 GB / 100 GB disk.
- Running `railway config migrate` (IaC migration).
- Deleting the project, the GitHub repo, or either Postgres service (`Postgres` / `Postgres-WbT1`).
- **Running the batch WITHOUT `--dry-run` against the corpus** (i.e., live classify+copy) — the 2026-09-03 organize pass was explicitly approved; new passes need new approval.
- Deleting or regenerating `.docai_batch_state.json` (it is the classification source of truth).
- Installing OS-level packages that increase WSL footprint beyond the plan.
- Any change to `/etc/wsl.conf` or `~/.wslconfig`.
- Exposing a new public endpoint without an authenticated boundary.

---

*Last updated: 2026-09-03. Maintained by the system architecture owner (Ateeb Faiz). Update this file whenever any rule, endpoint, resource ceiling, or environmental fact changes.*