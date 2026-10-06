"""Shared data models for extracted frontend intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ApiEndpoint:
    method: str
    path: str
    source_file: str
    line_hint: Optional[int] = None
    request_body_hint: Optional[str] = None
    response_hint: Optional[str] = None
    client_library: Optional[str] = None


@dataclass
class StateSchema:
    name: str
    source_file: str
    fields: List[str] = field(default_factory=list)
    initial_values: Dict[str, Any] = field(default_factory=dict)
    state_type: str = "unknown"


@dataclass
class FormField:
    name: str
    field_type: str
    source_file: str
    label: Optional[str] = None
    required: bool = False
    validation_hint: Optional[str] = None


@dataclass
class UiComponent:
    name: str
    source_file: str
    data_dependencies: List[str] = field(default_factory=list)
    api_calls: List[str] = field(default_factory=list)
    state_refs: List[str] = field(default_factory=list)


@dataclass
class StaticAsset:
    path: str
    asset_type: str
    source: str
    copied_to: Optional[str] = None


@dataclass
class ConfigObject:
    name: str
    source_file: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalizedString:
    key: str
    value: str
    locale: Optional[str] = None
    source_file: str = ""


@dataclass
class ExtractionBundle:
    source_type: str
    source_path: str
    api_endpoints: List[ApiEndpoint] = field(default_factory=list)
    state_schemas: List[StateSchema] = field(default_factory=list)
    form_fields: List[FormField] = field(default_factory=list)
    ui_components: List[UiComponent] = field(default_factory=list)
    static_assets: List[StaticAsset] = field(default_factory=list)
    config_objects: List[ConfigObject] = field(default_factory=list)
    localized_strings: List[LocalizedString] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_path": self.source_path,
            "counts": {
                "api_endpoints": len(self.api_endpoints),
                "state_schemas": len(self.state_schemas),
                "form_fields": len(self.form_fields),
                "ui_components": len(self.ui_components),
                "static_assets": len(self.static_assets),
                "config_objects": len(self.config_objects),
                "localized_strings": len(self.localized_strings),
            },
            "warnings": self.warnings,
        }
