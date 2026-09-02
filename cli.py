"""ai-cli — terminal document AI. Docling primary extraction; VLM layer arrives with the Railway boundary."""
from pathlib import Path

import typer
from docling.document_converter import DocumentConverter

app = typer.Typer(help="Terminal document AI: ocr documents via Docling.")

_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        _converter = DocumentConverter()
    return _converter


@app.command()
def ocr(
    path: Path = typer.Argument(..., exists=True, readable=True, help="PDF, image, or document file"),
    out: Path = typer.Option(None, "--out", "-o", help="Write markdown to file instead of stdout"),
):
    """Extract text from a document or image as markdown (local, small files only)."""
    result = _get_converter().convert(str(path))
    md = result.document.export_to_markdown()
    if out is not None:
        out.write_text(md, encoding="utf-8")
        typer.echo(f"saved: {out}")
    else:
        typer.echo(md)


@app.command()
def vision(path: Path, prompt: str = typer.Argument("Describe this image.")):
    """VLM layer — wired to a hosted API in the Railway phase."""
    typer.echo(f"[vision] {path} — '{prompt}' (VLM provider lands with the Railway boundary)")


@app.command()
def chat():
    """Terminal chat — wired to a model provider in the Railway phase."""
    typer.echo("[chat] provider wiring lands with the Railway boundary")


if __name__ == "__main__":
    app()
