"""DocAI full pipeline: OCR cascade, document parsing, entity extraction, cleaning, pretty output."""
import csv
import io
import json
import re
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# ---------------------------------------------------------------------------
# Engine availability probe
# ---------------------------------------------------------------------------

_AVAIL: dict[str, bool] = {}


def _try_import(name: str) -> bool:
    if name not in _AVAIL:
        try:
            __import__(name)
            _AVAIL[name] = True
        except Exception:
            _AVAIL[name] = False
    return _AVAIL[name]


# ---------------------------------------------------------------------------
# 1. IMAGE PREPROCESSING — every cleaning trick available
# ---------------------------------------------------------------------------

def preprocess_image(path: str | Path, variants: bool = True) -> list[Image.Image]:
    """Return [original, enhanced] or a full variant set for OCR confidence."""
    img = Image.open(path).convert("RGB")
    out = [img]
    if variants:
        # grayscale + contrast boost (helps most OCR)
        g = ImageOps.grayscale(img)
        g = ImageEnhance.Contrast(g).enhance(2.0)
        out.append(g)
        # upscaled 2x (helps small text)
        big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        big = ImageOps.grayscale(big)
        big = ImageEnhance.Sharpness(big).enhance(1.5)
        out.append(big)
        # binarized (threshold) for crisp text
        bw = ImageOps.grayscale(img).point(lambda p: 255 if p > 140 else 0)
        out.append(bw)
        # denoised
        d = ImageOps.grayscale(img).filter(ImageFilter.MedianFilter(3))
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# 2. OCR CASCADE — docling (structure) → paddleocr → easyocr → rapidocr → tesseract
# ---------------------------------------------------------------------------

_converter = None
_ocr_engines: dict[str, Any] = {}


def _docling():
    global _converter
    if _converter is None and _try_import("docling.document_converter"):
        from docling.document_converter import DocumentConverter
        _converter = DocumentConverter()
    return _converter


def _engine_paddle():
    if "paddle" not in _ocr_engines:
        if _try_import("paddleocr"):
            try:
                from paddleocr import PaddleOCR
                _ocr_engines["paddle"] = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            except Exception as e:
                print(f"paddleocr init failed: {e}")
                _ocr_engines["paddle"] = None
        else:
            _ocr_engines["paddle"] = None
    return _ocr_engines.get("paddle")


def _engine_easy():
    if "easy" not in _ocr_engines:
        if _try_import("easyocr"):
            try:
                import easyocr
                _ocr_engines["easy"] = easyocr.Reader(["en"], gpu=False, verbose=False)
            except Exception as e:
                print(f"easyocr init failed: {e}")
                _ocr_engines["easy"] = None
        else:
            _ocr_engines["easy"] = None
    return _ocr_engines.get("easy")


def _engine_rapid():
    if "rapid" not in _ocr_engines:
        if _try_import("rapidocr"):
            try:
                from rapidocr import RapidOCR
                _ocr_engines["rapid"] = RapidOCR()
            except Exception as e:
                print(f"rapidocr init failed: {e}")
                _ocr_engines["rapid"] = None
        else:
            _ocr_engines["rapid"] = None
    return _ocr_engines.get("rapid")


def _engine_tesseract():
    if "tess" not in _ocr_engines:
        if _try_import("pytesseract"):
            try:
                import pytesseract
                _ocr_engines["tess"] = pytesseract
            except Exception as e:
                print(f"tesseract init failed: {e}")
                _ocr_engines["tess"] = None
        else:
            _ocr_engines["tess"] = None
    return _ocr_engines.get("tess")


def ocr_image(path: str | Path) -> tuple[str, dict]:
    """OCR a single image through every available engine; return (best_text, engine_report)."""
    text = ""
    report: dict[str, Any] = {}
    variants = preprocess_image(path)
    engines = {
        "paddleocr": _engine_paddle(),
        "easyocr": _engine_easy(),
        "rapidocr": _engine_rapid(),
        "tesseract": _engine_tesseract(),
    }
    for name, eng in engines.items():
        if eng is None:
            report[name] = "unavailable"
            continue
        try:
            eng_text = ""
            for v in variants:
                img_bytes = io.BytesIO()
                v.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                try:
                    res = eng(img_bytes)
                except Exception:
                    # some engines prefer a path or numpy array
                    v2 = v.convert("RGB")
                    arr = np.array(v2)
                    res = eng(arr)
                if res is None:
                    continue
                # normalize per-engine output
                lines: list[str] = []
                if name == "paddleocr":
                    for page in res:
                        for item in page:
                            lines.append(item[1][0] if isinstance(item, (list, tuple)) and len(item) > 1 and item[1] else "")
                elif name == "easyocr":
                    for item in res:
                        lines.append(item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else "")
                elif name == "rapidocr":
                    if isinstance(res, tuple):
                        res, _ = res
                    for item in res or []:
                        lines.append(item[1] if len(item) > 1 else "")
                elif name == "tesseract":
                    lines = res.splitlines()
                piece = "\n".join(l for l in lines if l)
                if len(piece) > len(eng_text):
                    eng_text = piece
            report[name] = f"{len(eng_text)} chars"
            if len(eng_text) > len(text):
                text = eng_text
        except Exception as e:
            report[name] = f"error: {e}"
    return text, report


# ---------------------------------------------------------------------------
# 3. DOCUMENT PARSING — docling returns structure + tables + markdown
# ---------------------------------------------------------------------------

def parse_document(path: str | Path) -> dict[str, Any]:
    """Docling: PDF/image/docx/xlsx/html → structure + tables + md."""
    result: dict[str, Any] = {"markdown": "", "tables": [], "text": "", "error": None}
    conv = _docling()
    if conv is None:
        result["error"] = "docling unavailable"
        return result
    try:
        doc = conv.convert(str(path)).document
        result["markdown"] = doc.export_to_markdown()
        result["text"] = doc.export_to_text()
        tables = []
        for tbl in doc.tables:
            try:
                df = tbl.export_to_dataframe()
                tables.append(df.to_dict(orient="records"))
            except Exception:
                continue
        result["tables"] = tables
    except Exception as e:
        result["error"] = str(e)
    return result


# ---------------------------------------------------------------------------
# 4. ENTITY EXTRACTION — money, dates, phones, emails, invoice numbers
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"(?:US\$|USD|\$|PKR|Rs\.?)\s?([0-9][0-9,]*(?:\.[0-9]{2})?)", re.I)
_DATE_RE = re.compile(
    r"\b(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{2,4})\b"
    r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.I,
)
_PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_INVOICE_RE = re.compile(r"(?:invoice|inv|bill)\s*(?:no|#|number)?\.?\s*:?\s*([A-Za-z0-9\-/]{4,})", re.I)
_CNIC_RE = re.compile(r"\b\d{5}[\s\-]?\d{7}[\s\-]?\d\b")


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract structured fields from raw text via regex layers."""
    return {
        "amounts": list(dict.fromkeys(_MONEY_RE.findall(text))),
        "dates": list(dict.fromkeys(_DATE_RE.findall(text))),
        "phones": list(dict.fromkeys(_PHONE_RE.findall(text))),
        "emails": list(dict.fromkeys(_EMAIL_RE.findall(text))),
        "invoice_numbers": list(dict.fromkeys(_INVOICE_RE.findall(text))),
        "cnic_ids": list(dict.fromkeys(_CNIC_RE.findall(text))),
    }


# ---------------------------------------------------------------------------
# 5. CLASSIFICATION — taxonomy keywords
# ---------------------------------------------------------------------------

_TAXONOMY: dict[str, list[str]] = {
    "invoice": ["invoice", "total due", "amount payable", "bill to"],
    "bank_statement": ["account statement", "bank statement", "transaction"],
    "tax": ["tax return", "federal tax", "irs", "fbr"],
    "employment": ["employee", "salary slip", "offer letter", "payroll"],
    "immigration": ["passport", "visa", "immigration", "travel document"],
    "receipt": ["receipt", "payment received", "thank you for your"],
    "identity": ["national identity", "cnic", "driving license"],
    "order": ["order id", "order number", "delivery", "shipment"],
    "legal": ["court", "complaint", "affidavit", "legal notice"],
    "personal": ["profile", "personal information", "address:"],
}


def classify(text: str) -> dict[str, Any]:
    """Classify doc into taxonomy categories with confidence scores."""
    low = text.lower()
    scores: dict[str, int] = {}
    for cat, kws in _TAXONOMY.items():
        score = sum(1 for k in kws if k in low)
        if score:
            scores[cat] = score
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not top:
        return {"category": "uncategorized", "confidence": 0.0, "matches": {}}
    total = sum(v for _, v in top)
    return {
        "category": top[0][0],
        "confidence": round(top[0][1] / total, 2),
        "matches": dict(top[:3]),
    }


# ---------------------------------------------------------------------------
# 6. CLEANING — normalize whitespace, unicode, OCR garbage
# ---------------------------------------------------------------------------

_GARBAGE = re.compile(r"[^\S\n]+")


def clean_text(raw: str) -> str:
    """Remove OCR artifacts and normalize whitespace/encoding."""
    # normalize unicode dashes/quotes
    raw = raw.replace("\u2014", "-").replace("\u2013", "-")
    raw = raw.replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("\u2018", "'").replace("\u2019", "'")
    # drop nulls and control chars (keep newlines)
    raw = "".join(ch for ch in raw if ch >= " " or ch in "\n\t")
    # collapse runs of spaces but keep line breaks
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
    return "\n".join(l for l in lines if l)


# ---------------------------------------------------------------------------
# 7. PRETTY OUTPUT — structured report with rich metadata
# ---------------------------------------------------------------------------

def make_report(source: str, parse: dict, entities: dict, cls: dict,
                ocr_report: dict | None = None, engine: str = "") -> dict:
    """Assemble a clean, human-readable extraction report."""
    now = datetime.now().isoformat()
    return {
        "source": str(source),
        "processed_at": now,
        "engine": engine or ("docling" if not parse.get("error") else "ocr-cascade"),
        "document_type": cls.get("category", "uncategorized"),
        "classification_confidence": cls.get("confidence", 0),
        "entities": {k: v for k, v in entities.items() if v},
        "tables_found": len(parse.get("tables", [])),
        "chars_extracted": len(parse.get("text", "") or ""),
        "ocr_engine_report": ocr_report or {},
        "cleaned_text": clean_text(parse.get("text", "") or ""),
        "markdown": parse.get("markdown", "")[:20000],
    }


def run_full_pipeline(path: str | Path) -> dict:
    """Run every tool: preprocess → parse (docling) → OCR fallback → entities → classify."""
    p = Path(path)
    ext = p.suffix.lower()
    parse = parse_document(p)
    text = parse.get("text") or ""

    ocr_report: dict[str, Any] = {}
    # For images / when docling produced no text, run OCR cascade
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp") or not text.strip():
        ocr_text, ocr_report = ocr_image(p)
        if len(ocr_text) > len(text):
            text = ocr_text
            parse["text"] = text

    # fallback for structured files docling can't read
    if not text.strip():
        text = _read_fallback(p)
        parse["text"] = text

    entities = extract_entities(text)
    cls = classify(text)
    return make_report(str(p), parse, entities, cls, ocr_report)


def _read_fallback(p: Path) -> str:
    """Open xlsx/docx/csv/txt if docling missed them."""
    try:
        if p.suffix == ".xlsx":
            return "\n".join(
                df.to_string(index=False)
                for df in pd.read_excel(p, sheet_name=None).values()
            )
        if p.suffix == ".docx":
            import docx
            return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
        if p.suffix == ".csv":
            return open(p, encoding="utf-8", errors="ignore").read()
        if p.suffix == ".txt":
            return open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: pipeline.py <file>")
        sys.exit(1)
    report = run_full_pipeline(sys.argv[1])
    print(json.dumps(report, indent=2, default=str))
