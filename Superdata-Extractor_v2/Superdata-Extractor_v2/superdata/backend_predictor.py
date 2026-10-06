"""LLM-powered backend architecture prediction and reference code generation."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from .models import ExtractionBundle

logger = logging.getLogger("superdata")

ARCHITECT_PROMPT = """You are a Principal Backend Architect analyzing a frontend application.

Based on the frontend extraction data, output ONLY a JSON object (no markdown, no code files).
Use this exact schema:

{
  "architecture_summary": "2-4 sentences describing the backend design",
  "business_rules": ["rule 1", "rule 2", "rule 3"],
  "database_entities": [
    {
      "name": "Budget",
      "fields": [
        {"name": "id", "type": "int"},
        {"name": "department", "type": "str"},
        {"name": "amount", "type": "float"}
      ]
    }
  ],
  "api_routes": [
    {"method": "GET", "path": "/api/budgets", "purpose": "List all budgets"}
  ]
}

Rules:
- Map every discovered API endpoint into api_routes
- Infer database entities from state schemas and form fields
- Use simple field types: int, str, float, bool, datetime
- Entity names must be valid PascalCase (e.g. Budget, FormSubmission)
- Output valid JSON only
"""


class BackendPredictor:
    """Generate predictive backend reference code from extracted frontend data."""

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        api_base_url: Optional[str] = None,
        dry_run: bool = False,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        from .llm_client import (
            configure_llm,
            normalize_model,
            detect_provider,
            resolve_api_key,
            DEFAULT_OLLAMA_MODEL,
        )

        self.api_base_url = configure_llm(api_base_url)
        raw_model = model or os.getenv("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        self.model = normalize_model(raw_model)
        self.api_key = resolve_api_key(api_key)
        self.provider = detect_provider(self.api_base_url, provider, self.api_key)
        self.dry_run = dry_run

    def predict(self, bundle: ExtractionBundle) -> Dict[str, str]:
        context = self._build_context(bundle)

        if self.dry_run:
            logger.warning("Dry-run mode - using template backend generator.")
            return self._generate_template_backend(bundle)

        ok, msg = self._check_llm()
        if not ok:
            logger.warning("%s — falling back to template backend.", msg)
            bundle.warnings.append(msg)
            return self._generate_template_backend(bundle)

        try:
            plan = self._fetch_architecture_plan(context)
            return self._build_backend_from_plan(bundle, plan)
        except Exception as exc:
            logger.error("LLM prediction failed: %s — falling back to template.", exc)
            bundle.warnings.append(f"LLM prediction failed: {exc}")
            return self._generate_template_backend(bundle)

    def _check_llm(self) -> tuple[bool, str]:
        from .llm_client import check_llm_reachable

        return check_llm_reachable(
            self.api_base_url, provider=self.provider, api_key=self.api_key
        )

    def _build_context(self, bundle: ExtractionBundle) -> str:
        payload = {
            "source": {"type": bundle.source_type, "path": bundle.source_path},
            "api_endpoints": [asdict(ep) for ep in bundle.api_endpoints],
            "state_schemas": [asdict(s) for s in bundle.state_schemas],
            "form_fields": [asdict(f) for f in bundle.form_fields],
            "ui_components": [asdict(c) for c in bundle.ui_components],
            "config_objects": [asdict(c) for c in bundle.config_objects],
            "localized_strings_sample": [asdict(s) for s in bundle.localized_strings[:20]],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _ollama_chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = True,
        num_predict: int = 1024,
    ) -> str:
        from .llm_client import chat_completion_sync

        return chat_completion_sync(
            api_base=self.api_base_url,
            model=self.model,
            messages=messages,
            provider=self.provider,
            api_key=self.api_key,
            temperature=0.1,
            max_tokens=num_predict,
            json_mode=json_mode,
            timeout=600.0,
        )

    def _fetch_architecture_plan(self, context: str) -> dict:
        """Ask LLM for a small JSON architecture plan (no embedded code)."""
        messages = [
            {"role": "system", "content": ARCHITECT_PROMPT},
            {"role": "user", "content": f"Frontend extraction data:\n\n{context}"},
        ]
        raw = self._ollama_chat(messages, json_mode=True)
        plan = self._parse_llm_json(raw)
        if not plan.get("architecture_summary") and not plan.get("database_entities"):
            raise ValueError("LLM plan missing architecture_summary and database_entities.")
        logger.info(
            "LLM plan received: %d entities, %d routes, %d rules",
            len(plan.get("database_entities") or []),
            len(plan.get("api_routes") or []),
            len(plan.get("business_rules") or []),
        )
        return plan

    def _build_backend_from_plan(self, bundle: ExtractionBundle, plan: dict) -> Dict[str, str]:
        """Render FastAPI files from LLM architecture plan + template engine."""
        entities = self._normalize_entities(plan.get("database_entities") or [])
        if not entities:
            entities = self._infer_entities(bundle)

        routes = self._normalize_routes(plan.get("api_routes") or [], bundle)

        files = {
            "main.py": self._render_main(),
            "models.py": self._render_models(entities),
            "schemas.py": self._render_schemas(entities, bundle),
            "routes.py": self._render_routes(routes, entities),
            "requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0\nsqlalchemy>=2.0.0\npydantic>=2.6.0\n",
            "ARCHITECTURE.md": self._build_architecture_md(plan, routes),
        }
        return files

    @staticmethod
    def _normalize_entities(raw_entities: list) -> list[dict]:
        entities: list[dict] = []
        for ent in raw_entities:
            if not isinstance(ent, dict):
                continue
            name = re.sub(r"[^A-Za-z0-9_]", "", str(ent.get("name", "Entity")))
            if not name or not name[0].isalpha():
                name = "Entity" + name
            fields = []
            for field in ent.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                fname = re.sub(r"[^A-Za-z0-9_]", "", str(field.get("name", "field")))
                if fname == "id":
                    continue
                ftype = str(field.get("type", "str")).lower()
                if ftype not in ("int", "str", "float", "bool", "datetime"):
                    ftype = "str"
                fields.append({"name": fname, "type": ftype})
            if not any(f["name"] == "id" for f in fields):
                fields.insert(0, {"name": "id", "type": "int"})
            entities.append({"name": name[:64], "fields": fields})
        return entities

    @staticmethod
    def _normalize_routes(raw_routes: list, bundle: ExtractionBundle) -> list[dict]:
        routes: list[dict] = []
        seen: set[str] = set()
        for route in raw_routes:
            if not isinstance(route, dict):
                continue
            method = str(route.get("method", "GET")).upper()
            path = str(route.get("path", ""))
            if not path:
                continue
            key = f"{method}:{path}"
            if key in seen:
                continue
            seen.add(key)
            routes.append({
                "method": method,
                "path": path,
                "source": route.get("purpose", "ollama_inferred"),
            })
        if routes:
            return routes
        return BackendPredictor._infer_routes(bundle)

    @staticmethod
    def _parse_llm_json(raw: str) -> dict:
        cleaned = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Grab outermost JSON object
        brace_match = re.search(r"\{[\s\S]*\}", cleaned)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fix common trailing-comma issues
        fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(fixed)

    @staticmethod
    def _build_architecture_md(parsed: dict, routes: Optional[list] = None) -> str:
        lines = [
            "# Predicted Backend Architecture",
            "",
            parsed.get("architecture_summary", "Architecture inferred from frontend extraction."),
            "",
            "## Business Rules",
        ]
        for rule in parsed.get("business_rules") or []:
            lines.append(f"- {rule}")

        lines.extend(["", "## Database Entities"])
        for entity in parsed.get("database_entities") or []:
            lines.append(f"### {entity.get('name', 'Entity')}")
            for field in entity.get("fields") or []:
                lines.append(f"- `{field.get('name')}`: {field.get('type')}")

        lines.extend(["", "## API Routes"])
        route_list = routes or parsed.get("api_routes") or []
        for route in route_list:
            if isinstance(route, dict):
                purpose = route.get("purpose") or route.get("source") or ""
                suffix = f" — {purpose}" if purpose else ""
                lines.append(f"- `{route.get('method', 'GET')} {route.get('path', '/')}`{suffix}")

        lines.extend([
            "",
            "## Generated By",
            "Superdata Extractor + local Ollama (architecture plan merged with FastAPI template)",
        ])
        return "\n".join(lines)

    def _generate_template_backend(self, bundle: ExtractionBundle) -> Dict[str, str]:
        """Deterministic fallback when LLM is unavailable."""
        entities = self._infer_entities(bundle)
        routes = self._infer_routes(bundle)

        models_py = self._render_models(entities)
        schemas_py = self._render_schemas(entities, bundle)
        routes_py = self._render_routes(routes, entities)
        main_py = self._render_main()

        architecture = [
            "# Predicted Backend Architecture (Template)",
            "",
            f"Generated from **{bundle.source_type}**: `{bundle.source_path}`",
            "",
            "## Inferred Entities",
        ]
        for ent in entities:
            architecture.append(f"- **{ent['name']}**: {', '.join(f['name'] for f in ent['fields'])}")
        architecture.extend(["", "## Inferred Routes"])
        for route in routes:
            architecture.append(f"- `{route['method']} {route['path']}`")

        return {
            "main.py": main_py,
            "models.py": models_py,
            "schemas.py": schemas_py,
            "routes.py": routes_py,
            "requirements.txt": "fastapi>=0.110.0\nuvicorn>=0.28.0\nsqlalchemy>=2.0.0\npydantic>=2.6.0\n",
            "ARCHITECTURE.md": "\n".join(architecture),
        }

    @staticmethod
    def _infer_entities(bundle: ExtractionBundle) -> list[dict]:
        entities: list[dict] = []

        if bundle.state_schemas:
            for schema in bundle.state_schemas[:5]:
                fields = [{"name": f, "type": "str"} for f in schema.fields] or [{"name": "id", "type": "int"}]
                entities.append({"name": schema.name.replace("_state_", " ").title().replace(" ", ""), "fields": fields})

        if bundle.form_fields:
            fields = [{"name": f.name, "type": "str"} for f in bundle.form_fields]
            entities.append({"name": "FormSubmission", "fields": fields})

        if not entities:
            entities.append({
                "name": "Resource",
                "fields": [
                    {"name": "id", "type": "int"},
                    {"name": "name", "type": "str"},
                    {"name": "created_at", "type": "datetime"},
                ],
            })
        return entities

    @staticmethod
    def _infer_routes(bundle: ExtractionBundle) -> list[dict]:
        if bundle.api_endpoints:
            return [
                {"method": ep.method, "path": ep.path, "source": ep.source_file}
                for ep in bundle.api_endpoints
            ]
        return [{"method": "GET", "path": "/api/resources", "source": "inferred"}]

    @staticmethod
    def _render_models(entities: list[dict]) -> str:
        blocks = [
            "from datetime import datetime",
            "from sqlalchemy import Integer, String, DateTime",
            "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column",
            "",
            "",
            "class Base(DeclarativeBase):",
            "    pass",
            "",
        ]
        for ent in entities:
            name = ent["name"]
            blocks.append(f"class {name}(Base):")
            blocks.append('    __tablename__ = "' + name.lower() + '"')
            blocks.append("")
            blocks.append("    id: Mapped[int] = mapped_column(Integer, primary_key=True)")
            for field in ent["fields"]:
                if field["name"] == "id":
                    continue
                ftype = field.get("type", "str")
                if ftype == "float":
                    col_type, py_type = "String(64)", "str"
                elif ftype == "bool":
                    col_type, py_type = "String(8)", "str"
                elif ftype == "int":
                    col_type, py_type = "Integer", "int"
                elif ftype == "datetime":
                    col_type, py_type = "DateTime", "datetime"
                else:
                    col_type, py_type = "String(255)", "str"
                blocks.append(f"    {field['name']}: Mapped[{py_type}] = mapped_column({col_type})")
            blocks.append("")
        return "\n".join(blocks)

    @staticmethod
    def _render_schemas(entities: list[dict], bundle: ExtractionBundle) -> str:
        lines = ["from pydantic import BaseModel", "from datetime import datetime", "from typing import Optional", ""]
        for ent in entities:
            name = ent["name"]
            lines.append(f"class {name}Create(BaseModel):")
            for field in ent["fields"]:
                if field["name"] == "id":
                    continue
                lines.append(f"    {field['name']}: Optional[str] = None")
            lines.append("")
            lines.append(f"class {name}Read(BaseModel):")
            lines.append("    id: int")
            for field in ent["fields"]:
                if field["name"] == "id":
                    continue
                lines.append(f"    {field['name']}: Optional[str] = None")
            lines.append("")
            lines.append("    model_config = {'from_attributes': True}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_routes(routes: list[dict], entities: list[dict]) -> str:
        ent = entities[0]["name"]
        lines = [
            "from fastapi import APIRouter",
            f"from schemas import {ent}Read",
            "",
            "router = APIRouter(prefix='/api')",
            "",
            "MOCK_DATA = [",
            f"    {{'id': 1, 'name': 'Sample {ent}'}},",
            "]",
            "",
        ]
        seen = set()
        for route in routes:
            path = route["path"]
            if path.startswith("http"):
                from urllib.parse import urlparse
                path = urlparse(path).path or "/api/unknown"
            path = path.replace("${", "{").replace("}", "}")
            if path.startswith("/api"):
                path = path[4:] or "/"
            method = route["method"].lower()
            key = f"{method}:{path}"
            if key in seen:
                continue
            seen.add(key)

            safe_segment = path.strip("/").replace("/", "_").replace("-", "_").replace("{", "").replace("}", "") or "root"
            func_name = f"{method}_{safe_segment}"
            lines.extend([
                f"@router.{method}('{path}')",
                f"def {func_name}():",
                f'    """Mock handler inferred from frontend: {route.get("source", "")}"""',
                f"    return {{'data': MOCK_DATA, 'message': 'Mock response for {method.upper()} {path}'}}",
                "",
            ])
        return "\n".join(lines)

    @staticmethod
    def _render_main() -> str:
        return '''"""Predicted FastAPI backend — generated by Superdata Extractor."""

from fastapi import FastAPI
from routes import router

app = FastAPI(title="Predicted Backend API", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
'''
