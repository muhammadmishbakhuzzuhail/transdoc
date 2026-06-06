"""transdoc CLI.

  transdoc translate input.pdf --to docx --lang id
  transdoc translate scan.png --lang en --engine tesseract
  transdoc convert in.pdf --to docx              # reconstruct, no translation
  transdoc diagnose input.pdf                    # profile only
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from .config import Config, Engine, Fidelity, Mode, OCREngine, OutputFormat, Register
from .pipeline import run

app = typer.Typer(add_completion=False, help="Document Intelligence & Translation Agent")
console = Console()


def _cfg(target, source, fmt, engine, ocr, fidelity, domain, localize, register, pages):
    return Config(
        source_lang=source,
        target_lang=target,
        output_format=OutputFormat(fmt),
        engine=Engine(engine),
        ocr_engine=OCREngine(ocr),
        fidelity=Fidelity(fidelity),
        domain=domain,
        localize=localize,
        register=Register(register),
        pages=pages,
    )


@app.command()
def translate(
    input: str = typer.Argument(..., help="Input document"),
    lang: str = typer.Option(..., "--lang", "-l", help="TARGET language (ISO 639)"),
    source: str = typer.Option("auto", "--source", "-s", help="Source language"),
    to: str = typer.Option("markdown", "--to", "-t", help="markdown|docx|pdf|plain-text|same-as-source"),
    engine: str = typer.Option("echo", "--engine", "-e",
                               help="echo|madlad|opusmt|argos|nllb|openrouter|anthropic "
                                    "(commercial-safe offline: madlad/opusmt/argos)"),
    ocr: str = typer.Option("auto", "--ocr", help="auto|tesseract|surya"),
    fidelity: str = typer.Option("auto", "--fidelity", "-f", help="auto|flow|layout"),
    domain: str = typer.Option("auto", "--domain", "-d"),
    localize: bool = typer.Option(False, "--localize"),
    register: str = typer.Option("auto", "--register", "-r"),
    pages: str = typer.Option(None, "--pages", "-p", help='e.g. "3-7,10"'),
    out: str = typer.Option(None, "--out", "-o", help="Output path"),
):
    """Run the full pipeline: extract -> diagnose -> translate -> regenerate + report."""
    cfg = _cfg(lang, source, to, engine, ocr, fidelity, domain, localize, register, pages)
    _execute(input, cfg, out)


@app.command()
def convert(
    input: str = typer.Argument(...),
    to: str = typer.Option("docx", "--to", "-t"),
    ocr: str = typer.Option("auto", "--ocr"),
    fidelity: str = typer.Option("auto", "--fidelity", "-f"),
    out: str = typer.Option(None, "--out", "-o"),
):
    """Reconstruct / convert format only (OCR repair, no translation)."""
    cfg = _cfg("source", "auto", to, "echo", ocr, fidelity, "auto", False, "auto", None)
    cfg.mode = Mode.RECONSTRUCT
    _execute(input, cfg, out)


@app.command()
def serve(host: str = typer.Option("127.0.0.1", "--host"),
          port: int = typer.Option(8000, "--port")):
    """Launch the web UI + REST API (upload -> translate -> download)."""
    import uvicorn

    console.print(f"[bold cyan]transdoc[/] web UI → http://{host}:{port}")
    uvicorn.run("transdoc.api.app:app", host=host, port=port, reload=False)


@app.command()
def diagnose(input: str = typer.Argument(...), source: str = typer.Option("auto", "-s")):
    """Print a document profile only (Phase 1)."""
    cfg = _cfg(None, source, "markdown", "echo", "auto", "auto", "auto", False, "auto", None)
    cfg.mode = Mode.DIAGNOSE
    res = run(input, cfg)
    console.print(res.report_text)


def _execute(input: str, cfg: Config, out: str | None):
    console.print(f"[bold cyan]transdoc[/] {Path(input).name} "
                  f"→ {cfg.target_lang} ({cfg.output_format.value}, engine={cfg.engine.value})")
    res = run(input, cfg, out)
    if res.output_path:
        console.print(f"[green]✓ output:[/] {res.output_path}")
    if res.report_path:
        console.print(f"[green]✓ report:[/] {res.report_path}")
    console.print(f"  blocks={len(res.doc.blocks)} flagged={len(res.doc.flagged_blocks())} "
                  f"pages={res.doc.page_count}")


if __name__ == "__main__":
    app()
