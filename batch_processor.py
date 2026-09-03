"""Batch document processor — walk corpus, OCR via Railway, store, auto-rename & organize.

For every file under the source root:
  1. Upload to Railway pipeline (POST /documents) → get doc_type + extracted fields
  2. Store result in Postgres (Railway handles it; we record locally too)
  3. Auto-rename file by its detected type + key field (e.g. "Tax_Invoice_YS-2026-0042.pdf")
  4. Move/copy it into the correct taxonomy folder (matching 2206.md categories)

Idempotent: skips files already recorded in the local state cache.
"""
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

API = os.environ.get("DOCAI_API", "https://docai-production-424b.up.railway.app")

# 2206.md taxonomy → source folder mapping (order matters: matched first wins)
CATEGORY_FOLDERS = {
    "00. _QUARANTINE": ["uncategorized", "unknown", "misc", "metadata"],
    "1. Identity_and_Civil_Registry": ["identity"],
    "2. Taxation_and_FBR": ["tax"],
    "3. Financial_and_Banking": ["bank_statement", "receipt"],
    "4. Legal_and_Compliance": ["legal"],
    "5. Corporate_and_SECP": ["corporate", "secp", "registration", "company"],
    "6. Immigration_and_Travel": ["immigration"],
    "7. Education_and_Professional": ["education", "degree", "certificate", "employment"],
    "8. ECommerce_and_Marketing": ["invoice", "order", "receipt"],
    "9. Design_and_Creative_Assets": ["design", "creative", "mockup"],
    "10. Medical_and_Health": ["medical", "health", "prescription", "lab"],
    "11. Personal_Profile_and_Security": ["personal", "security"],
}

# Invert for folder lookup: doc_type -> canonical folder
_TYPE_TO_FOLDER: dict[str, str] = {}
for folder, types in CATEGORY_FOLDERS.items():
    for t in types:
        _TYPE_TO_FOLDER[t] = folder

# Existing folder name → likely doc_type priors (order matters)
_FOLDER_PRIORS: list[tuple[str, str]] = [
    ("Identity_and_Civil_Registry", "identity"),
    ("Taxation_and_FBR", "tax"),
    ("Financial_and_Banking", "bank_statement"),
    ("Legal_and_Compliance", "legal"),
    ("Corporate_and_SECP", "corporate"),
    ("Immigration_and_Travel", "immigration"),
    ("Education_and_Professional", "education"),
    ("ECommerce_and_Marketing", "invoice"),
    ("Design_and_Creative_Assets", "design"),
    ("Medical_and_Health", "medical"),
    ("Personal_Profile_and_Security", "personal"),
    ("_QUARANTINE", "metadata"),
]


def folder_prior(rel_path: str) -> str:
    """Use the existing taxonomy folder as a classification prior."""
    for token, doc_type in _FOLDER_PRIORS:
        if token in rel_path:
            return doc_type
    return ""

# Rename templates: category → (type_slug, key_field, suffix). Falls back to fileno.
RENAME_RULES: dict[str, tuple[str, str]] = {
    "tax": ("Tax", "registration"),        # 3410422179127 → Tax_3410422179127.pdf
    "identity": ("ID", "cnic"),            # → ID_3410422179127.pdf
    "invoice": ("Invoice", "invoice_number"),
    "order": ("Order", "order_number"),
    "bank_statement": ("Statement", "account_number"),
    "receipt": ("Receipt", "amount"),
    "legal": ("Legal", "invoice_number"),
    "metadata": ("Meta", ""),
    "uncategorized": ("Doc", ""),
}

STATE_FILE = ".docai_batch_state.json"


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", s).strip("_")
    return s[:80] or "doc"


def safe_ascii(s: str) -> str:
    """Strip non-ASCII so filenames stay Windows/WSL-safe."""
    return re.sub(r"[^\x20-\x7E]", "", s).strip()


def pick_key(entity: dict, key: str) -> str:
    """Choose the best field value from extracted entities."""
    vals = entity.get(key) or entity.get(key + "s") or entity.get("names") or []
    for v in vals:
        v = str(v)
        if len(v) >= 4 and any(c.isalnum() for c in v):
            return safe_ascii(v)
    return ""


def rename_for(doc_type: str, entities: dict, name: str) -> str:
    """Build a content-driven new filename. Falls back to original base."""
    low = (doc_type or "").lower()
    prefix, key = RENAME_RULES.get(low, ("Doc", None))
    val = pick_key(entities, key) if key else ""
    base = Path(name).stem
    if val:
        new = f"{prefix}_{val}"
    else:
        new = f"{prefix}_{base}"
    return safe_ascii(new) + Path(name).suffix.lower()


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {"processed": {}}


def save_state(state: dict):
    json.dump(state, open(STATE_FILE, "w"), indent=2)


def main(src: str, dest_root: str, dry_run: bool = False, limit: int = 0):
    src = Path(src)
    dest_root = Path(dest_root)
    if not src.is_dir():
        print(f"SOURCE NOT FOUND: {src}")
        sys.exit(1)
    dest_root.mkdir(parents=True, exist_ok=True)
    # Ensure category folders exist at dest
    for folder in CATEGORY_FOLDERS:
        (dest_root / folder).mkdir(parents=True, exist_ok=True)

    state = load_state()
    files = sorted(src.rglob("*"))
    docs = [f for f in files if f.is_file() and f.suffix.lower() in
            (".pdf", ".docx", ".txt", ".csv", ".xlsx", ".png", ".jpg", ".jpeg", ".tiff", ".webp", ".md", ".json")]
    if limit:
        docs = docs[:limit]
    total = len(docs)
    print(f"[batch] {total} documents under {src}")

    # REPORT — collect issues for a final rollup
    issues: list[str] = []
    lock_print = __import__("threading").Lock()

    def process_one(client: httpx.Client, f: Path, idx: int) -> None:
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        with __import__("threading").Lock():
            if digest in state["processed"]:
                print(f"[{idx}/{total}] SKIP (already) {f.name}")
                return
        try:
            rel = f.relative_to(src)
            with f.open("rb") as fh:
                r = client.post(f"{API}/documents", files={"file": (f.name, fh, "application/octet-stream")})
            if r.status_code != 201:
                issues.append(f"HTTP {r.status_code}: {f.name} — {r.text[:80]}")
                print(f"[{idx}/{total}] HTTP {r.status_code} {f.name}: {r.text[:80]}")
                return
            data = r.json()

            # Async flow: upload returns status=queued → poll until done/failed
            if data.get("status") in ("queued", "processing"):
                doc_id = data["id"]
                deadline = time.time() + 900  # 15 min per doc
                while time.time() < deadline:
                    time.sleep(5)
                    g = client.get(f"{API}/documents/{doc_id}")
                    if g.status_code != 200:
                        continue
                    gd = g.json()
                    if gd.get("status") in ("done", "failed"):
                        data = gd
                        break
                if data.get("status") in ("queued", "processing"):
                    issues.append(f"POLL-TIMEOUT: {f.name} — {doc_id}")
                    print(f"[{idx}/{total}] POLL-TIMEOUT {f.name}")
                    return

            if data.get("status") == "failed":
                issues.append(f"PIPELINE-FAILED: {f.name}")
                print(f"[{idx}/{total}] FAILED {f.name}")
                return

            doc_type = data.get("doc_type", "uncategorized")
            entities = data.get("entities") or {}
            confidence = data.get("classification_confidence", 0)

            # --- FOLDER-AWARE CLASSIFICATION CORRECTION ---
            prior = folder_prior(str(rel))
            if prior and confidence < 0.70:
                doc_type = prior
                confidence = max(confidence, 0.70)
            elif confidence < 0.50 and doc_type != "metadata":
                doc_type = "uncategorized"

            new_name = rename_for(doc_type, entities, f.name)
            folder = _TYPE_TO_FOLDER.get(doc_type, "00. _QUARANTINE")

            with __import__("threading").Lock():
                state["processed"][digest] = {
                    "doc_id": data.get("id"),
                    "source": str(rel),
                    "doc_type": doc_type,
                    "confidence": confidence,
                    "new_name": new_name,
                    "folder": folder,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
                if confidence < 0.50:
                    issues.append(f"LOW-CONF {confidence:.2f}: {f.name} -> {doc_type}")
                if "uncategorized" in (doc_type or ""):
                    issues.append(f"UNCATEGORIZED: {f.name}")

            if not dry_run:
                target = dest_root / folder / new_name
                counter = 1
                while target.exists():
                    target = dest_root / folder / f"{Path(new_name).stem}_{counter}{Path(new_name).suffix}"
                    counter += 1
                if f.parent.resolve() != target.parent.resolve():
                    shutil.copy2(f, target)
            with lock_print:
                print(f"[{idx}/{total}] {doc_type} -> {folder}/{new_name} ({confidence})")
        except Exception as e:
            issues.append(f"ERROR: {f.name} — {e}")
            print(f"[{idx}/{total}] ERROR {f.name}: {e}")

    WORKERS = int(os.environ.get("BATCH_WORKERS", "6"))
    with httpx.Client(timeout=600.0) as client:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(process_one, client, f, idx) for idx, f in enumerate(docs, 1)]
            for fut in as_completed(futures):
                fut.result()

        save_state(state)
    print(f"[batch] DONE — processed {len(state['processed'])} unique docs in this run")
    print(f"[batch] ISSUES ({len(issues)}):")
    for i in issues:
        print("   -", i)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else r"/mnt/c/Users/ateeb/OneDrive/Documents/Documents"
    dest = sys.argv[2] if len(sys.argv) > 2 else r"/mnt/c/Users/ateeb/OneDrive/Documents/Documents_organized"
    dry = "--dry-run" in sys.argv
    limit = 0
    for a in sys.argv:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    main(src, dest, dry_run=dry, limit=limit)