# DocAI Unified Architecture — Agent & Human Rules

> **READ THIS BEFORE ANY CHANGE.** This binds all AI agents and humans. Covers WSL2 dev machine + Railway/GitHub cloud.

## THE ENVIRONMENT LAWS (non-negotiable)

1. **EVERYTHING runs in WSL2 Ubuntu.** All dev, Python, OCR/parsing, git, tests happen inside `Ubuntu-24.04`. Canonical project root: `/home/ateeb/projects/ai-cli/` (ext4). NEVER work in `/mnt/c/…` for active files. Canonical: Ubuntu 24.04.4 LTS / Python 3.11.16 / uv.
2. **Windows is a thin control plane ONLY.** Windows (PowerShell, `wsl.exe`) only: (a) invokes WSL, (b) holds auth tokens for `gh`/`railway`/`postman`, (c) reads files at `\\wsl.localhost\Ubuntu-24.04\home\ateeb\projects`. Windows NEVER runs Python/pipeline.
3. **Windows PATH is purged from WSL** (`[interop] appendWindowsPath=false`). Use native Linux binaries: `~/.railway/bin/railway` (5.47.2), `/usr/local/bin/postman` (1.53.0), `~/.local/bin/uv`. If a tool resolves to `/mnt/c/…`, that's the Windows shim — stop and use native.
4. **No Docker Desktop locally.** Builds happen on Railway from the committed Dockerfile.
5. **Never expose an unauthenticated OCR/model port publicly.** Everything sits behind FastAPI.

## HOSTING FACTS
- GitHub: `ateebfaiz/docai` (public) https://github.com/ateebfaiz/docai
- Railway project `docai`, Project ID `8590679c-0203-4810-93fe-097ea3c23a02`, Service ID `6d17984a-…`, region `sfo`
- Public URL: **https://docai-production-424b.up.railway.app**
- Max resources (authorized): 24 vCPU / 24 GB RAM / 100 GB disk (Railway GraphQL, region key `sfo` top-level).

## HARDWARE / RESOURCE CEILING
`~/.wslconfig`: memory=8GB swap=4GB (autoMemoryReclaim under [experimental]). Railway service: cpuLimit=24, memoryLimitMB=24576, diskLimitMB=102400. Do not exceed without approval.

## FILES
`/home/ateeb/projects/ai-cli/`: `.venv`, `src/ai_cli/api.py` (FastAPI entry), `pipeline.py` (OCR pipeline, MUST be at repo root), `cli.py` (local Typer), `Dockerfile`, `requirements.txt`, `pyproject.toml`, `uv.lock`, Postman collections (`full_ocr_collection.json`, `test_api_collection.json`), fixtures.

## PIPELINE (pipeline.py)
Cascade: Docling → PaddleOCR → EasyOCR → RapidOCR → Tesseract. Each image engine tests 5 preprocessing variants (original, contrast/grayscale, upscale 2x, binarized, denoised), keeps longest text. Then: entity regex (money, dates, phones, emails, invoice numbers, CNIC), 10-category classification, unicode/whitespace cleaning. Output JSON report.

## RAILWAY OPS
- `export PATH="$HOME/.railway/bin:$PATH"`; `railway status`, `railway logs`, `railway logs --build`
- Deploy: `cd ~/projects/ai-cli && railway up --service docai`
- GraphQL scaling: `echo '<mutation>' | railway api` (serviceInstanceUpdate with multiRegionConfig)
- Do NOT run `railway config migrate` without approval (deprecation warnings are benign).

## POSTMAN TESTS
- `cd ~/projects/ai-cli && postman collection run full_ocr_collection.json --reporters cli`
- Exit 1 = failure. "No authorization data" warnings are benign (only gate cloud publish).

## VERIFICATION GATES (all must pass before "done")
1. Clean build (no VOLUME directive, no ModuleNotFoundError)
2. `curl …/health` → `{"status":"ok","service":"docai","version":"0.2.0"}`
3. Postman full_ocr suite → 0 failures (10 assertions)
4. Real upload `invoice_test.png` → `status:done`, non-empty `entities.invoice_numbers`
5. `GET /documents/{id}` round-trip OK
6. Committed + pushed + deployed

## SECURITY (binding)
- NEVER paste GitHub PAT, Railway tokens, or Bedrock bearer token into chat/logs/commits/files.
- **The git remote URL has an embedded PAT (`gho_…`)** — treat any `git remote -v` output as SECRET.
- Windows `~/.aws` NOT duplicated to WSL. Separate SSH keys (WSL uses `id_ed25519_github`, never copy Windows private key).
- Railway config in `~/.railway/config.json` holds accessToken — never commit/paste.
- App writes only to `/data/` (uploads + SQLite). No public buckets, no unauth endpoints.

## COMMON TRAPS
- `ModuleNotFoundError: pipeline` → Dockerfile lacks `COPY pipeline.py .` → add & redeploy
- Build `VOLUME not supported` → remove `VOLUME` from Dockerfile, use Railway Volumes
- `operator torchvision::nms` → pin BOTH torch & torchvision to `pytorch-cpu` index in pyproject.toml
- `railway` resolves to `/mnt/c/…npm…` → use native `~/.railway/bin/railway`
- "Multiple services found" → always `--service docai`
- First deploy slow (torch/paddle/easyocr) ~15-25 min, cached after

## HUMAN-ONLY GATES (do NOT bypass)
Raise resources above 24/24/100; `railway config migrate`; delete project/repo; OS package installs increasing footprint; change .wslconfig/wsl.conf; expose new public endpoint without auth.

*Last updated 2026-09-03. Update whenever any rule/endpoint/resource/environment changes.*