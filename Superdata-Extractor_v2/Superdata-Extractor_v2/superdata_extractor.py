#!/usr/bin/env python3
"""
Superdata Extractor (Colab / Linux)
===================================
Analyze a local frontend codebase or target URL, then generate a predictive
FastAPI backend blueprint via local Ollama (uncensored model by default).

    python3 superdata_extractor.py
    python3 superdata_extractor.py --source ./my-app
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from superdata.backend_predictor import BackendPredictor
from superdata.frontend_analyzer import FrontendAnalyzer
from superdata.logger import console, create_progress, print_banner, print_extraction_summary, setup_logging
from superdata.llm_client import (
    DEFAULT_OLLAMA_BASE,
    DEFAULT_OLLAMA_MODEL,
    check_llm_reachable,
    detect_provider,
    resolve_api_key,
)
from superdata.storage import OutputOrganizer
from superdata.target_agent_pack import TargetAgentPackBuilder
from superdata.url_scraper import UrlScraper

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = BASE_DIR / "sample_frontend"


def _running_on_colab() -> bool:
    return Path("/content").exists() or "COLAB_RELEASE_TAG" in os.environ or "google.colab" in sys.modules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Superdata Extractor — Colab/Linux Ollama backend blueprint generator",
    )
    source_group = parser.add_mutually_exclusive_group(required=False)
    source_group.add_argument(
        "--source",
        type=Path,
        default=None,
        help=f"Local frontend directory (default: {DEFAULT_SOURCE.name}/)",
    )
    source_group.add_argument(
        "--url",
        type=str,
        help="Target URL to analyze (HTTP fetch; Playwright off by default on Colab)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("extracted_output"),
        help="Output root directory (default: ./extracted_output/)",
    )
    parser.add_argument(
        "--api-url",
        "--endpoint",
        "--base-url",
        "--endpoint-base-url",
        dest="api_url",
        default=None,
        help="LLM API base URL (Ollama or OpenAI-compatible /v1). Env: OLLAMA_API_BASE / ENDPOINT_BASE_URL",
    )
    parser.add_argument(
        "--api-key",
        "--key",
        dest="api_key",
        default=None,
        help="API key for commercial providers. Env: OPENAI_API_KEY / LLM_API_KEY",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai"],
        default=os.getenv("LLM_PROVIDER") or None,
        help="Force provider: ollama | openai",
    )
    parser.add_argument(
        "--model",
        "--model-id",
        dest="model",
        default=None,
        help=f"Model / deployment id (default: {DEFAULT_OLLAMA_MODEL}). Env: OLLAMA_MODEL / MODEL_ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM; generate template backend from extracted data only",
    )
    parser.add_argument(
        "--no-playwright",
        action="store_true",
        help="Disable Playwright for URL mode (HTTP + BeautifulSoup only)",
    )
    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Force Playwright for URL mode (requires: playwright install chromium)",
    )
    parser.add_argument(
        "--skip-backend",
        action="store_true",
        help="Only extract frontend data; skip backend prediction",
    )
    parser.add_argument(
        "--no-target-agent",
        action="store_true",
        help="Skip building the input_src/target_agent white-box intel pack for red-team automation",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    load_dotenv(BASE_DIR / ".env")
    setup_logging(args.verbose)
    print_banner()

    args.api_url = (
        args.api_url
        or os.getenv("OLLAMA_API_BASE")
        or os.getenv("ENDPOINT_BASE_URL")
        or os.getenv("TARGET_API_URL")
        or DEFAULT_OLLAMA_BASE
    ).rstrip("/")
    args.model = (
        args.model
        or os.getenv("OLLAMA_MODEL")
        or os.getenv("MODEL_ID")
        or DEFAULT_OLLAMA_MODEL
    )
    if not args.api_key:
        args.api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("TARGET_API_KEY")
            or None
        )

    if not args.url and args.source is None:
        args.source = DEFAULT_SOURCE

    use_playwright = bool(args.use_playwright) and not args.no_playwright
    if _running_on_colab() and not args.use_playwright:
        use_playwright = False

    if not args.dry_run and not args.skip_backend:
        api_key = resolve_api_key(args.api_key)
        provider = detect_provider(args.api_url, args.provider, api_key)
        ok, msg = check_llm_reachable(args.api_url, provider=provider, api_key=api_key)
        if ok:
            console.print(f"[success][OK][/success] {msg}")
        else:
            console.print(f"[warning]Warning:[/warning] {msg}")
            console.print("[dim]Will fall back to template backend if LLM is still unavailable.[/dim]")
            console.print("[dim]Hint: bash ../setup_colab.sh  OR  set OPENAI_API_KEY for commercial APIs[/dim]")

    console.print(f"[dim]Model: {args.model} | Output: {args.output}[/dim]")

    bundle = None
    source_root = None

    with create_progress() as progress:
        if args.url:
            task = progress.add_task("[step]Scraping target URL...", total=1)
            scraper = UrlScraper(args.url, use_playwright=use_playwright)
            bundle = scraper.analyze()
            progress.update(task, advance=1)
        else:
            task = progress.add_task("[step]Analyzing local frontend codebase...", total=1)
            source_root = args.source.resolve()
            analyzer = FrontendAnalyzer(source_root)
            bundle = analyzer.analyze()
            progress.update(task, advance=1)

    print_extraction_summary(bundle.to_summary_dict())

    organizer = OutputOrganizer(args.output.resolve(), source_root=source_root)
    organizer.write_bundle(bundle)

    pack_dir = None
    if not args.no_target_agent:
        with create_progress() as progress:
            task = progress.add_task("[step]Building target_agent white-box intel pack...", total=1)
            pack_builder = TargetAgentPackBuilder(
                model=args.model,
                api_base_url=args.api_url,
                dry_run=args.dry_run,
                provider=args.provider,
                api_key=args.api_key,
            )
            pack_files = pack_builder.build(bundle)
            pack_dir = organizer.write_target_agent_pack(pack_files)
            progress.update(task, advance=1)

    if not args.skip_backend:
        with create_progress() as progress:
            task = progress.add_task("[step]Generating backend (LLM plan + FastAPI template)...", total=1)
            predictor = BackendPredictor(
                model=args.model,
                api_base_url=args.api_url,
                dry_run=args.dry_run,
                provider=args.provider,
                api_key=args.api_key,
            )
            backend_files = predictor.predict(bundle)
            organizer.write_predicted_backend(backend_files)
            progress.update(task, advance=1)

    console.print("\n[success]Superdata extraction complete.[/success]")
    console.print(f"[dim]Output root: {args.output.resolve()}[/dim]")
    if pack_dir is not None:
        console.print(f"[dim]Target-agent intel pack: {pack_dir}[/dim]")
        console.print(
            "[dim]Feed the red-team automation: copy this folder to "
            "<automation>/input_src/target_agent/[/dim]"
        )
    console.print(
        "[dim]Run backend: cd extracted_output/predicted_backend && "
        "pip install -r requirements.txt && uvicorn main:app --reload --host 0.0.0.0 --port 8000[/dim]"
    )
    return 0


def main() -> None:
    args = parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        console.print("\n[warning]Interrupted by user.[/warning]")
        sys.exit(130)
    except Exception as exc:
        logging.getLogger("superdata").exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
