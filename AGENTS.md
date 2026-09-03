# DocAI — Agent & Human Rules (condensed)

> Full detail in [CLAUDE.md](./CLAUDE.md). This binds all agents and humans.

## ENVIRONMENT LAWS
1. **Everything runs in WSL2 Ubuntu** (`Ubuntu-24.04`). Project root: `/home/ateeb/projects/ai-cli/` (ext4). NEVER work in `/mnt/c/…` for project files.
2. **Windows = thin control plane only** (wsl.exe invocation, token storage, `\\wsl.localhost` file access). Never runs Python/pipeline.
3. **Windows PATH purged** (`appendWindowsPath=false`). Native binaries only: `~/.railway/bin/railway`, `/usr/local/bin/postman`, `~/.local/bin/uv`.
4. **No Docker Desktop locally** — Railway builds from the committed Dockerfile.
5. **No unauthenticated OCR/model endpoints.** FastAPI is the only public surface.

## HOSTING
- GitHub `ateebfaiz/docai` — remote is **SSH** (`git@github.com:…`). NEVER revert to HTTPS-with-PAT (that was a real leak, fixed 2026-09-03).
- Railway project `docai` (ID `8590679c-…`), service `docai`, region sfo. URL: https://docai-production-424b.up.railway.app
- Resources: 24 vCPU / 24 GB / 100 GB disk (via GraphQL `serviceInstanceUpdate`, region key top-level).
- **Postgres LIVE** — `DATABASE_URL=${{ Postgres.DATABASE_URL }}` reference. Two Postgres services exist (double `railway add`); cleanup is a HUMAN GATE.

## API (v0.3.0)
- `GET /health` → `{"status":"ok","storage":"postgres"}`
- `POST /documents` → **async default**: `201 {id, status:"queued", poll}` → poll `GET /documents/{id}` until `done|failed`. Server-side pool: `PIPELINE_WORKERS` (default 8).
- `POST /documents?sync=true` → blocks with full result. **Never use for large files** (Railway edge 502s long requests — this bit us with a 55-page PDF).
- `GET /documents[/{id}]`, `GET /search?q=&doc_type=` — Postgres-backed, ILIKE over entities/fields/text.

## PIPELINE
Cascade: **Docling fast path** (`do_ocr=False, do_table_structure=False`, fallback to full) → PaddleOCR → EasyOCR → RapidOCR → Tesseract (5 image variants each). Scanned PDFs: pypdf → PyMuPDF rasterize → OCR. Text files (.json/.md/…) read directly — never image-OCR'd.
Adaptive classify: weighted keywords + negatives + entity hints; 11 categories incl. `metadata`; `_MIN_CONFIDENCE=0.50`. Typed fields per type (invoice→invoice_number/total_amount…, tax→registration_no/tax_year/taxpayer…).

## BATCH PROCESSOR
```bash
cd ~/projects/ai-cli && .venv/bin/python batch_processor.py '<src>' '<dest>' [--dry-run|--organize-only]
```
- Parallel (`BATCH_WORKERS=8`), async-aware (polls), idempotent via `.docai_batch_state.json` (SHA256 digests).
- **State file = classification source of truth.** Deleting it forces full re-classification (HUMAN GATE).
- Folder-aware correction: low classifier confidence + existing taxonomy folder → folder wins; <0.5 → quarantine.
- Measured: ~25s/doc, ~170 docs/min at 8 workers.

## CORPUS STATE (2026-09-03)
- Source `Documents/` (555 files) **NEVER modified**. Organized copy `Documents_organized/` holds **547** renamed files (tax 127, legal 103, identity 86, bank 74, immigration 49, …; `Meta_*` manifests quarantined). 8 SHA256 dupes excluded; 364 collision suffixes (`_1`,`_2`) expected (same-person docs share CNIC).
- All 547 rows in Postgres with entities/fields — searchable.

## VERIFICATION GATES (all must pass)
1. Clean build; 2. health = `0.3.0` + `storage:postgres`; 3. Postman `full_ocr_collection.json` 0 failures; 4. async upload→poll→done with entities; 5. sync small-file check; 6. pushed + deployed.

## SECURITY
No secrets in chat/logs/commits/files. Railway config (`~/.railway/config.json`) holds tokens — never print. Windows `~/.aws` never copied to WSL. Separate SSH keys per environment. PII corpus (CNICs/passports/bank statements) — treat extracted text as sensitive.

## KEY TRAPS (full table in CLAUDE.md)
502 on big uploads → use async. `cannot identify image file .pdf` → OCR fired on PDF; fast-path fallback guards exist, don't remove. `/tmp` vanishes between WSL calls → use `$HOME`. wsl.exe background logs empty → redirect inside WSL to a file. `VOLUME` in Dockerfile rejected by Railway. torchvision must be CPU-pinned alongside torch.

## HUMAN-ONLY GATES
Raise resources; `railway config migrate`; delete project/repo/Postgres services; **live (non-dry-run) batch passes**; delete `.docai_batch_state.json`; OS package installs; `.wslconfig`/`wsl.conf` changes; new public endpoints.

*Updated 2026-09-03.*