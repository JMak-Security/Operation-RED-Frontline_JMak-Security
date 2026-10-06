"""Organize extracted frontend intelligence into a structured output hierarchy."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .logger import log_folder_created
from .models import ExtractionBundle, StaticAsset

logger = logging.getLogger("superdata")

OUTPUT_SUBDIRS = (
    "api_endpoints",
    "state_schemas",
    "static_assets",
    "ui_components",
    "predicted_backend",
)

# Frontend source extensions copied into the target_agent pack so a downstream
# white-box scanner (fetch/axios/route detection) sees the real client code.
FRONTEND_COPY_EXTS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".html", ".htm", ".json"}
SKIP_COPY_DIRS = {"node_modules", ".git", "dist", "build", ".next", "coverage", "__pycache__"}
MAX_FRONTEND_COPIES = 200


class OutputOrganizer:
    """Write extraction results to ./extracted_output/ folder hierarchy."""

    def __init__(self, output_root: Path, source_root: Optional[Path] = None):
        self.output_root = output_root.resolve()
        self.source_root = source_root.resolve() if source_root else None

    def initialize(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        for sub in OUTPUT_SUBDIRS:
            path = self.output_root / sub
            path.mkdir(parents=True, exist_ok=True)
            log_folder_created(str(path), label=f"Created {sub}/")

    def write_bundle(self, bundle: ExtractionBundle) -> Path:
        self.initialize()

        self._write_json(
            self.output_root / "api_endpoints" / "endpoints.json",
            [asdict(ep) for ep in bundle.api_endpoints],
        )
        self._write_json(
            self.output_root / "state_schemas" / "state_models.json",
            [asdict(s) for s in bundle.state_schemas],
        )
        self._write_json(
            self.output_root / "ui_components" / "component_map.json",
            [asdict(c) for c in bundle.ui_components],
        )
        self._write_json(
            self.output_root / "state_schemas" / "form_fields.json",
            [asdict(f) for f in bundle.form_fields],
        )
        self._write_json(
            self.output_root / "state_schemas" / "config_objects.json",
            [asdict(c) for c in bundle.config_objects],
        )
        self._write_json(
            self.output_root / "static_assets" / "localized_strings.json",
            [asdict(s) for s in bundle.localized_strings],
        )
        self._write_json(
            self.output_root / "static_assets" / "asset_manifest.json",
            [asdict(a) for a in bundle.static_assets],
        )

        self._copy_local_assets(bundle.static_assets)
        self._write_json(self.output_root / "extraction_summary.json", bundle.to_summary_dict())

        manifest_path = self._write_json(
            self.output_root / "manifest.json",
            {
                "source_type": bundle.source_type,
                "source_path": bundle.source_path,
                "output_directories": OUTPUT_SUBDIRS,
                "artifact_counts": bundle.to_summary_dict()["counts"],
            },
        )
        logger.info("Extraction artifacts written to %s", self.output_root)
        return manifest_path

    def _copy_local_assets(self, assets: list[StaticAsset]) -> None:
        if not self.source_root:
            return

        dest_root = self.output_root / "static_assets" / "copied"
        dest_root.mkdir(parents=True, exist_ok=True)

        for asset in assets:
            if asset.source != "local_file":
                continue
            src = self.source_root / asset.path
            if not src.exists() or not src.is_file():
                continue
            try:
                dest = self._unique_path(dest_root / Path(asset.path).name)
                shutil.copy2(src, dest)
                asset.copied_to = str(dest.relative_to(self.output_root))
            except OSError as exc:
                logger.warning("Could not copy asset %s: %s", asset.path, exc)

    @staticmethod
    def _unique_path(path: Path) -> Path:
        """Return a non-clobbering path for ``path``.

        If nothing exists at ``path`` it is returned unchanged; otherwise a
        numeric suffix is appended to the stem (before the extension) until a
        free name is found -- e.g. ``system_prompt.txt`` -> ``system_prompt-2.txt``,
        ``tools/backend_tools.py`` -> ``tools/backend_tools-2.py``. Re-running the
        extractor into an existing output directory therefore versions artifacts
        side by side instead of silently overwriting the previous run.
        """
        if not path.exists():
            return path
        parent, stem, suffix = path.parent, path.stem, path.suffix
        counter = 2
        while True:
            candidate = parent / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _write_json(path: Path, data: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path = OutputOrganizer._unique_path(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def write_target_agent_pack(
        self, files: dict[str, str], *, copy_frontend: bool = True
    ) -> Path:
        """Write the target_agent white-box intel pack under ``target_agent/``.

        ``files`` maps relative paths -> text content (system_prompt.txt,
        tools/backend_tools.py, frontend/routes.js, ...). When a local source
        root is known, real frontend source files are also copied into
        ``target_agent/frontend/`` so a downstream white-box scanner harvests
        the live client code, not just the reconstructed route map.
        """
        pack_dir = self.output_root / "target_agent"
        pack_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in files.items():
            target = pack_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target = self._unique_path(target)
            target.write_text(content, encoding="utf-8")
            log_folder_created(str(target), label=f"Intel {rel_path}")

        if copy_frontend and self.source_root:
            self._copy_frontend_sources(pack_dir / "frontend")

        logger.info("Target-agent intel pack written to %s", pack_dir)
        return pack_dir

    def _copy_frontend_sources(self, dest_root: Path) -> None:
        if not self.source_root or not self.source_root.exists():
            return

        dest_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in self.source_root.rglob("*"):
            if copied >= MAX_FRONTEND_COPIES:
                logger.warning(
                    "Frontend copy capped at %d files; some sources omitted from pack.",
                    MAX_FRONTEND_COPIES,
                )
                break
            if not src.is_file() or src.suffix.lower() not in FRONTEND_COPY_EXTS:
                continue
            if any(part in SKIP_COPY_DIRS for part in src.parts):
                continue
            try:
                rel = src.relative_to(self.source_root)
            except ValueError:
                rel = Path(src.name)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
                copied += 1
            except OSError as exc:
                logger.warning("Could not copy frontend source %s: %s", src, exc)
        logger.info("Copied %d frontend source file(s) into %s", copied, dest_root)

    def write_predicted_backend(self, files: dict[str, str]) -> None:
        backend_dir = self.output_root / "predicted_backend"
        backend_dir.mkdir(parents=True, exist_ok=True)

        for rel_path, content in files.items():
            target = backend_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target = self._unique_path(target)
            target.write_text(content, encoding="utf-8")
            log_folder_created(str(target), label=f"Generated {rel_path}")

        logger.info("Predicted backend written to %s", backend_dir)
