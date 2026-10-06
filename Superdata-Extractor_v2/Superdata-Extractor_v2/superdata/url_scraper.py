"""Scrape a target URL using BeautifulSoup with optional Playwright rendering."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from .models import (
    ApiEndpoint,
    ConfigObject,
    ExtractionBundle,
    FormField,
    StaticAsset,
    UiComponent,
)

logger = logging.getLogger("superdata")


class UrlScraper:
    """Legal local headless analysis of a publicly reachable URL."""

    def __init__(self, url: str, *, timeout_ms: int = 30000, use_playwright: bool = True):
        self.url = url
        self.timeout_ms = timeout_ms
        self.use_playwright = use_playwright

    def analyze(self) -> ExtractionBundle:
        bundle = ExtractionBundle(source_type="url", source_path=self.url)

        html, final_url, warnings = self._fetch_html()
        bundle.warnings.extend(warnings)

        if not html:
            bundle.warnings.append("No HTML content retrieved from URL.")
            return bundle

        self._parse_html(html, final_url or self.url, bundle)
        return bundle

    def _fetch_html(self) -> tuple[Optional[str], Optional[str], list[str]]:
        warnings: list[str] = []

        if self.use_playwright:
            html, final_url, pw_warnings = self._fetch_with_playwright()
            warnings.extend(pw_warnings)
            if html:
                return html, final_url, warnings
            warnings.append("Playwright unavailable or failed; falling back to HTTP fetch.")

        return self._fetch_with_requests()

    def _fetch_with_playwright(self) -> tuple[Optional[str], Optional[str], list[str]]:
        warnings: list[str] = []
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            warnings.append("Playwright not installed. pip install playwright && playwright install chromium")
            return None, None, warnings

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, wait_until="networkidle", timeout=self.timeout_ms)
                html = page.content()
                final_url = page.url
                browser.close()
                return html, final_url, warnings
        except Exception as exc:
            warnings.append(f"Playwright session error: {exc}")
            return None, None, warnings

    def _fetch_with_requests(self) -> tuple[Optional[str], Optional[str], list[str]]:
        warnings: list[str] = []
        try:
            import requests
            from bs4 import BeautifulSoup  # noqa: F401 — validate import
        except ImportError:
            warnings.append("requests and beautifulsoup4 required for HTTP fallback.")
            return None, None, warnings

        try:
            import requests

            resp = requests.get(
                self.url,
                timeout=self.timeout_ms / 1000,
                headers={"User-Agent": "SuperdataExtractor/1.0 (local dev utility)"},
            )
            resp.raise_for_status()
            return resp.text, resp.url, warnings
        except Exception as exc:
            warnings.append(f"HTTP fetch error: {exc}")
            return None, None, warnings

    def _parse_html(self, html: str, base_url: str, bundle: ExtractionBundle) -> None:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            bundle.warnings.append("beautifulsoup4 not installed; HTML parsing skipped.")
            return

        soup = BeautifulSoup(html, "html.parser")

        for form in soup.find_all("form"):
            action = form.get("action") or base_url
            method = (form.get("method") or "GET").upper()
            full_path = urljoin(base_url, action)
            bundle.api_endpoints.append(
                ApiEndpoint(method=method, path=full_path, source_file=base_url, client_library="html_form")
            )
            for inp in form.find_all(["input", "textarea", "select"]):
                name = inp.get("name")
                if not name:
                    continue
                bundle.form_fields.append(
                    FormField(
                        name=name,
                        field_type=inp.get("type", inp.name),
                        source_file=base_url,
                        required=inp.has_attr("required"),
                        label=inp.get("placeholder") or inp.get("aria-label"),
                    )
                )

        for script in soup.find_all("script"):
            src = script.get("src")
            if src:
                bundle.static_assets.append(
                    StaticAsset(
                        path=urljoin(base_url, src),
                        asset_type="script",
                        source=base_url,
                    )
                )
            inline = script.string or ""
            for match in re.finditer(r"""fetch\s*\(\s*[`'"]([^`'"]+)[`'"]""", inline):
                bundle.api_endpoints.append(
                    ApiEndpoint(
                        method="GET",
                        path=urljoin(base_url, match.group(1)),
                        source_file=base_url,
                        client_library="inline_script",
                    )
                )

        for tag in soup.find_all(["link", "img", "source"]):
            attr = "href" if tag.name == "link" else "src"
            asset_url = tag.get(attr)
            if not asset_url:
                continue
            ext = Path(urlparse(asset_url).path).suffix.lstrip(".") or tag.name
            bundle.static_assets.append(
                StaticAsset(path=urljoin(base_url, asset_url), asset_type=ext, source=base_url)
            )

        root = soup.find(id="root") or soup.find(id="__next") or soup.body
        if root:
            bundle.ui_components.append(
                UiComponent(
                    name="PageRoot",
                    source_file=base_url,
                    data_dependencies=[f"forms:{len(soup.find_all('form'))}", f"scripts:{len(soup.find_all('script'))}"],
                )
            )

        for script in soup.find_all("script", type="application/json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    bundle.config_objects.append(
                        ConfigObject(
                            name="__NEXT_DATA__" if "props" in data else "embedded_json",
                            source_file=base_url,
                            data=data if len(json.dumps(data)) < 50000 else {"truncated": True, "keys": list(data.keys())},
                        )
                    )
            except json.JSONDecodeError:
                bundle.warnings.append("Unparseable embedded JSON script block.")
