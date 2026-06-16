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
    to: str = typer.Option("markdown", "--to", "-t",
                           help="markdown|docx|pdf|plain-text|pptx|xlsx|epub|srt|vtt|same-as-source"),
    engine: str = typer.Option("google", "--engine", "-e",
                               help="google|fallback|mymemory|libretranslate|madlad|opusmt|argos|"
                                    "nllb|openrouter|anthropic|echo "
                                    "(default: google = benchmark winner; nllb for offline/private; "
                                    "fallback = google->mymemory->libretranslate if you want backstops)"),
    ocr: str = typer.Option("auto", "--ocr", help="auto|tesseract|paddle|surya"),
    fidelity: str = typer.Option("auto", "--fidelity", "-f", help="auto|flow|layout"),
    domain: str = typer.Option("auto", "--domain", "-d"),
    localize: bool = typer.Option(False, "--localize"),
    register: str = typer.Option("auto", "--register", "-r"),
    pages: str = typer.Option(None, "--pages", "-p", help='e.g. "3-7,10"'),
    bilingual: bool = typer.Option(False, "--bilingual", "-b", help="source + translation"),
    quality: bool = typer.Option(False, "--quality", "-q", help="QE: score+flag weak segments"),
    escalate: bool = typer.Option(False, "--escalate",
                                  help="hybrid QE-gate: re-translate QA-weak segments with the "
                                       "local doc-context LLM (Ollama)"),
    verify: bool = typer.Option(False, "--verify", help="re-extract output, diff structure vs source"),
    ocr_figures: bool = typer.Option(False, "--ocr-figures",
                                     help="OCR text inside large embedded images (scan-in-page)"),
    glossary: str = typer.Option(None, "--glossary", "-g",
                                 help='JSON file of {source term: target term} to enforce'),
    layout: str = typer.Option("off", "--layout",
                               help="auto|off|paddle — PP-DocLayout region detection: crop "
                                    "figures/math/charts verbatim. auto = use it when paddle "
                                    "is reachable, else fall back to heuristics ([paddleocr])"),
    out: str = typer.Option(None, "--out", "-o", help="Output path"),
):
    """Run the full pipeline: extract -> diagnose -> translate -> regenerate + report."""
    cfg = _cfg(lang, source, to, engine, ocr, fidelity, domain, localize, register, pages)
    cfg.bilingual = bilingual
    cfg.quality_check = quality
    cfg.escalate = escalate
    cfg.verify = verify
    cfg.ocr_figures = ocr_figures
    cfg.layout = layout
    if glossary:
        from .translate.protect import load_glossary
        cfg.glossary = load_glossary(glossary)
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
def ocr(input: str = typer.Argument(..., help="Scanned PDF"),
        source: str = typer.Option("auto", "--source", "-s"),
        ocr_engine: str = typer.Option("auto", "--ocr"),
        out: str = typer.Option(None, "--out", "-o")):
    """Make a scanned PDF searchable (add an invisible OCR text layer, no translation)."""
    from .ingest.detect import detect
    from .extract import extract as extract_ir
    from .diagnose import diagnose
    from .regenerate.pdf_out import render_searchable

    cfg = _cfg(None, source, "pdf", "echo", ocr_engine, "auto", "auto", False, "auto", None)
    det = detect(input)
    doc = extract_ir(det, cfg)
    diagnose(doc, det, cfg)
    outp = out or str(Path(input).with_suffix("")) + ".searchable.pdf"
    render_searchable(doc, cfg, outp)
    console.print(f"[green]✓ searchable PDF:[/] {outp}")


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


glossary_app = typer.Typer(add_completion=False, help="Manage the persistent glossary "
                           "(term → target rendering, scoped per language pair + domain).")
app.add_typer(glossary_app, name="glossary")


@glossary_app.command("add")
def glossary_add(
    term: str = typer.Argument(..., help="Source term"),
    rendering: str = typer.Argument(..., help="Target rendering (emitted verbatim)"),
    source: str = typer.Option(..., "--source", "-s", help="Source language (ISO 639)"),
    target: str = typer.Option(..., "--target", "-t", help="Target language (ISO 639)"),
    domain: str = typer.Option("", "--domain", "-d", help="Domain scope ('' = global)"),
    lock: bool = typer.Option(False, "--lock", help="Lock: highest precedence, immune to -g/auto"),
):
    """Add or update a glossary entry."""
    from .store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is None:
        console.print("[red]glossary store unavailable[/] (TRANSDOC_TM_DISABLE set?)")
        raise typer.Exit(1)
    gs.add(term, rendering, source, target, domain=domain, locked=lock)
    console.print(f"[green]✓ added[/] {term} → {rendering} ({source}→{target}"
                  f"{', ' + domain if domain else ''}{', locked' if lock else ''})")


@glossary_app.command("list")
def glossary_list(
    source: str = typer.Option(None, "--source", "-s"),
    target: str = typer.Option(None, "--target", "-t"),
    domain: str = typer.Option(None, "--domain", "-d"),
):
    """List glossary entries."""
    from .store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is None:
        console.print("[red]glossary store unavailable[/]")
        raise typer.Exit(1)
    rows = gs.list(source, target, domain)
    if not rows:
        console.print("[yellow]no entries[/]")
        return
    for e in rows:
        lock = " [bold red]🔒[/]" if e["locked"] else ""
        dom = f" [{e['domain']}]" if e["domain"] else ""
        console.print(f"{e['src_lang']}→{e['tgt_lang']}{dom}: [cyan]{e['term']}[/] → "
                      f"{e['rendering']} ({e['origin']}){lock}")


@glossary_app.command("rm")
def glossary_rm(
    term: str = typer.Argument(...),
    source: str = typer.Option(..., "--source", "-s"),
    target: str = typer.Option(..., "--target", "-t"),
    domain: str = typer.Option("", "--domain", "-d"),
):
    """Remove a glossary entry."""
    from .store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is None:
        console.print("[red]glossary store unavailable[/]")
        raise typer.Exit(1)
    n = gs.remove(term, source, target, domain=domain)
    console.print(f"[green]✓ removed {n} entr{'y' if n == 1 else 'ies'}[/]" if n
                  else "[yellow]no match[/]")


@glossary_app.command("export")
def glossary_export(
    file: str = typer.Argument(..., help="Output .json or .tsv"),
    source: str = typer.Option(None, "--source", "-s"),
    target: str = typer.Option(None, "--target", "-t"),
):
    """Export glossary entries to JSON or TSV."""
    from .store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is None:
        console.print("[red]glossary store unavailable[/]")
        raise typer.Exit(1)
    n = gs.export(file, source, target)
    console.print(f"[green]✓ exported {n} entries[/] → {file}")


@glossary_app.command("import")
def glossary_import(file: str = typer.Argument(..., help="Input .json or .tsv")):
    """Import glossary entries from JSON or TSV (upserts)."""
    from .store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is None:
        console.print("[red]glossary store unavailable[/]")
        raise typer.Exit(1)
    n = gs.import_(file)
    console.print(f"[green]✓ imported {n} entries[/] from {file}")


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
