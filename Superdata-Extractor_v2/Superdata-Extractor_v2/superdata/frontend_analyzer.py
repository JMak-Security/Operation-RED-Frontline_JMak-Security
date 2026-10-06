"""Analyze local frontend source files for data structures and API usage."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable, List, Optional, Set

from .models import (
    ApiEndpoint,
    ConfigObject,
    ExtractionBundle,
    FormField,
    LocalizedString,
    StateSchema,
    StaticAsset,
    UiComponent,
)

logger = logging.getLogger("superdata")

FRONTEND_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".vue", ".html", ".htm",
    ".json", ".css", ".scss", ".sass", ".less",
}
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".mp4", ".webm"}
LOCALE_FILE_HINTS = ("i18n", "locale", "locales", "translations", "lang")
CONFIG_FILE_HINTS = ("config", "settings", "env", "constants")

STATE_PATTERNS = [
    re.compile(r"useState\s*\(\s*(\{[\s\S]*?\}|[^)\n]+)\s*\)"),
    re.compile(r"useReducer\s*\(\s*[^,]+,\s*(\{[\s\S]*?\})\s*\)"),
    re.compile(r"create\s*\(\s*\(\s*set\s*\)\s*=>\s*\(\s*\{([\s\S]*?)\}\s*\)"),  # zustand-ish
    re.compile(r"initialState\s*[:=]\s*(\{[\s\S]*?\})"),
]

FORM_PATTERNS = [
    re.compile(r"""<input[^>]+name=['"]([^'"]+)['"][^>]*>""", re.I),
    re.compile(r"""<textarea[^>]+name=['"]([^'"]+)['"][^>]*>""", re.I),
    re.compile(r"""<select[^>]+name=['"]([^'"]+)['"][^>]*>""", re.I),
    re.compile(r"""register\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
]

COMPONENT_PATTERN = re.compile(
    r"(?:export\s+(?:default\s+)?(?:function|const)\s+|function\s+)([A-Z][A-Za-z0-9_]*)",
)


class FrontendAnalyzer:
    """Extract schemas, endpoints, state, and UI mappings from a codebase directory."""

    def __init__(self, root_dir: Path, *, max_files: int = 500):
        self.root_dir = root_dir.resolve()
        self.max_files = max_files

    def analyze(self) -> ExtractionBundle:
        bundle = ExtractionBundle(source_type="local_codebase", source_path=str(self.root_dir))

        if not self.root_dir.exists():
            bundle.warnings.append(f"Source directory not found: {self.root_dir}")
            return bundle

        files = self._collect_files()
        if not files:
            bundle.warnings.append(f"No frontend files found under {self.root_dir}")
            return bundle

        logger.info("Scanning %d frontend file(s) in %s", len(files), self.root_dir)

        for file_path in files:
            try:
                self._analyze_file(file_path, bundle)
            except Exception as exc:
                bundle.warnings.append(f"Failed to parse {file_path.name}: {exc}")
                logger.debug("Parse error in %s: %s", file_path, exc)

        self._deduplicate_bundle(bundle)
        return bundle

    def _collect_files(self) -> List[Path]:
        collected: List[Path] = []
        skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__", "extracted_output"}

        for path in self.root_dir.rglob("*"):
            if len(collected) >= self.max_files:
                break
            if any(part in skip_dirs for part in path.parts):
                continue
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in FRONTEND_EXTENSIONS or suffix in ASSET_EXTENSIONS:
                collected.append(path)
        return collected

    def _analyze_file(self, file_path: Path, bundle: ExtractionBundle) -> None:
        rel = str(file_path.relative_to(self.root_dir))
        suffix = file_path.suffix.lower()

        if suffix in ASSET_EXTENSIONS:
            bundle.static_assets.append(
                StaticAsset(path=rel, asset_type=suffix.lstrip("."), source="local_file")
            )
            return

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            bundle.warnings.append(f"Unreadable file {rel}: {exc}")
            return

        if suffix in {".js", ".jsx", ".ts", ".tsx", ".vue", ".html", ".htm"}:
            self._extract_api_endpoints(content, rel, bundle)
            self._extract_state_schemas(content, rel, bundle)
            self._extract_form_fields(content, rel, bundle)
            self._extract_ui_components(content, rel, bundle)

        if suffix == ".json":
            self._extract_json_config(content, rel, bundle)

        if any(h in rel.lower() for h in LOCALE_FILE_HINTS):
            self._extract_localized_strings(content, rel, bundle)

        if any(h in file_path.name.lower() for h in CONFIG_FILE_HINTS):
            if suffix == ".json":
                self._extract_json_config(content, rel, bundle, force=True)
            elif suffix in {".js", ".ts"}:
                self._extract_js_config(content, rel, bundle)

    def _extract_api_endpoints(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        simple_fetch = re.compile(r"""fetch\s*\(\s*[`'"]([^`'"]+)[`'"]""")
        fetch_with_method = re.compile(
            r"""fetch\s*\(\s*[`'"]([^`'"]+)[`'"]\s*,\s*\{[^}]*method\s*:\s*['"](\w+)['"]""",
            re.I | re.S,
        )
        axios_pattern = re.compile(
            r"""axios\.(get|post|put|patch|delete)\s*\(\s*[`'"]([^`'"]+)[`'"]""",
            re.I,
        )
        api_literal = re.compile(r"""['"]/(api|v\d)[^'"]*['"]""")

        for match in fetch_with_method.finditer(content):
            self._append_endpoint(bundle, match.group(2).upper(), match.group(1), rel, content, match.start())

        for match in simple_fetch.finditer(content):
            window = content[match.start(): match.end() + 80]
            if re.search(r"method\s*:\s*['\"]", window, re.I):
                continue
            self._append_endpoint(bundle, "GET", match.group(1), rel, content, match.start())

        for match in axios_pattern.finditer(content):
            self._append_endpoint(bundle, match.group(1).upper(), match.group(2), rel, content, match.start())

        for match in api_literal.finditer(content):
            path = match.group(0).strip("'\"")
            self._append_endpoint(bundle, "GET", path, rel, content, match.start())

    def _append_endpoint(
        self, bundle: ExtractionBundle, method: str, path: str, rel: str, content: str, char_offset: int
    ) -> None:
        if not path.startswith("/") and not path.startswith("http"):
            return
        line_hint = content[:char_offset].count("\n") + 1
        bundle.api_endpoints.append(
            ApiEndpoint(
                method=method,
                path=path,
                source_file=rel,
                line_hint=line_hint,
                client_library="fetch/axios",
            )
        )

    def _extract_state_schemas(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        for idx, pattern in enumerate(STATE_PATTERNS):
            for match in pattern.finditer(content):
                raw = match.group(1).strip()
                fields, initial = self._parse_object_literal(raw)
                state_type = ["useState", "useReducer", "zustand", "redux"][min(idx, 3)]
                bundle.state_schemas.append(
                    StateSchema(
                        name=f"{Path(rel).stem}_state_{idx}",
                        source_file=rel,
                        fields=fields,
                        initial_values=initial,
                        state_type=state_type,
                    )
                )

    def _extract_form_fields(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        for pattern in FORM_PATTERNS:
            for match in pattern.finditer(content):
                name = match.group(1)
                snippet = match.group(0).lower()
                field_type = "text"
                if "type=" in snippet:
                    type_match = re.search(r"type=['\"]([^'\"]+)['\"]", snippet)
                    if type_match:
                        field_type = type_match.group(1)
                elif "textarea" in snippet:
                    field_type = "textarea"
                elif "select" in snippet:
                    field_type = "select"

                bundle.form_fields.append(
                    FormField(
                        name=name,
                        field_type=field_type,
                        source_file=rel,
                        required="required" in snippet,
                    )
                )

    def _extract_ui_components(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        for match in COMPONENT_PATTERN.finditer(content):
            name = match.group(1)
            api_calls = re.findall(r"[`'](/api[^`'\"]+)[`'\"]", content)
            state_refs = re.findall(r"useState\s*\(\s*(\w+)", content)
            bundle.ui_components.append(
                UiComponent(
                    name=name,
                    source_file=rel,
                    data_dependencies=sorted(set(api_calls + state_refs)),
                    api_calls=sorted(set(api_calls)),
                    state_refs=sorted(set(state_refs)),
                )
            )

    def _extract_js_config(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        const_match = re.search(
            r"(?:export\s+)?const\s+(\w+)\s*=\s*(\{[\s\S]*?\})\s*;",
            content,
        )
        if not const_match:
            return
        name = const_match.group(1)
        raw_obj = const_match.group(2)
        fields = re.findall(r"(\w+)\s*:", raw_obj)
        bundle.config_objects.append(
            ConfigObject(
                name=name,
                source_file=rel,
                data={"inferred_keys": fields, "raw_preview": raw_obj[:500]},
            )
        )

    def _extract_json_config(self, content: str, rel: str, bundle: ExtractionBundle, force: bool = False) -> None:
        if not force and not any(h in rel.lower() for h in CONFIG_FILE_HINTS):
            return
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            if force:
                bundle.warnings.append(f"Unparseable config JSON: {rel}")
            return
        if isinstance(data, dict):
            bundle.config_objects.append(
                ConfigObject(name=Path(rel).stem, source_file=rel, data=data)
            )

    def _extract_localized_strings(self, content: str, rel: str, bundle: ExtractionBundle) -> None:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return

        def walk(obj, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, str):
                        bundle.localized_strings.append(
                            LocalizedString(key=key, value=v, source_file=rel)
                        )
                    else:
                        walk(v, key)

        walk(data)

    @staticmethod
    def _parse_object_literal(raw: str) -> tuple[List[str], dict]:
        fields: List[str] = []
        initial: dict = {}
        for key_match in re.finditer(r"(\w+)\s*:", raw):
            key = key_match.group(1)
            fields.append(key)
            initial[key] = None
        return fields, initial

    @staticmethod
    def _deduplicate_bundle(bundle: ExtractionBundle) -> None:
        seen_endpoints: Set[str] = set()
        unique_endpoints: List[ApiEndpoint] = []
        for ep in bundle.api_endpoints:
            key = f"{ep.method}:{ep.path}"
            if key not in seen_endpoints:
                seen_endpoints.add(key)
                unique_endpoints.append(ep)
        bundle.api_endpoints = unique_endpoints

        seen_fields: Set[str] = set()
        bundle.form_fields = [
            f for f in bundle.form_fields
            if f.name not in seen_fields and not seen_fields.add(f.name)
        ]

        seen_components: Set[str] = set()
        bundle.ui_components = [
            c for c in bundle.ui_components
            if c.name not in seen_components and not seen_components.add(c.name)
        ]
