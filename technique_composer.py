"""
Multi-technique composition engine for ORF.

Merges techniques from three registries into ONE reasoned payload:

    core encoding      obfuscation.py            (base64, homoglyph, unicode_tag, ...)
    structural         injection_techniques.py   (url_fragmentation, image_markdown, ...)
    framing            injection_techniques.py   (many_shot, cot, multilingual, ...)
    multi-turn         injection_techniques.py   (logic/context/memory poisoning, ...)
    delivery carrier   obfuscation.py            (uploaded-document wrapper)

The composer applies a *layer order* and a *compatibility model* so combinations
are logical rather than a random pile of encoders. Key rules:

  - At most one core encoding, one structural technique, one multi-turn technique.
  - Self-encoding structural techniques (they Base64URL the core themselves) are not
    also character-obfuscated — the composer drops the redundant encoding and notes it.
  - When an encoding IS applied, its decode hint is carried inward so the model has a
    plausible reason to decode before acting.
  - A multi-turn technique is dominant: the fully-composed single-turn string becomes
    the payload of its trigger turn, so encoding+framing still ride along.

`auto_compose()` picks a surface-appropriate, guaranteed-compatible combo (optionally
informed by white-box intel from the Superdata Extractor).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from obfuscation import (
    ALL_TECHNIQUES as CORE_ENCODINGS,
    build_obfuscated_variants,
    decode_hint,
    wrap_in_carrier_document,
)
from injection_techniques import (
    FRAMING_TECHNIQUES,
    INJECTION_TECHNIQUES,
    MULTI_TURN_TECHNIQUES,
    STRUCTURAL_TECHNIQUES,
    TechniqueContext,
    Turn,
    apply_single_turn,
    build_turns,
)

# Structural techniques that Base64URL-encode the core themselves; adding a
# separate character encoding on top would corrupt reassembly semantics.
SELF_ENCODING_STRUCTURAL = frozenset({"url_fragmentation", "image_markdown_zero_click"})

# Inner -> outer application order for stacked framing techniques.
_FRAMING_ORDER = ["payload_splitting", "multilingual_injection", "cot_manipulation", "many_shot"]


@dataclass
class ComposedPayload:
    label: str
    turns: List[Turn]
    obfuscation: Optional[str] = None
    structural: Optional[str] = None
    framing: List[str] = field(default_factory=list)
    multi_turn: Optional[str] = None
    carrier: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def is_multi_turn(self) -> bool:
        return len(self.turns) > 1

    @property
    def final_payload(self) -> str:
        """The trigger/only turn's user content (what the evaluator ultimately scores)."""
        return self.turns[-1].user if self.turns else ""

    def preview(self) -> str:
        lines = [f"[compose] {self.label}"]
        if self.notes:
            lines.append("  notes: " + "; ".join(self.notes))
        for i, t in enumerate(self.turns):
            tag = t.label or f"turn{i}"
            lines.append(f"  --- turn {i + 1} ({tag}) ---")
            lines.append("  " + t.user.replace("\n", "\n  "))
        return "\n".join(lines)


def _validate(name: str, value: Optional[str], pool) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("", "none") and name == "obfuscation":
        return "none"
    if value in pool:
        return value
    return None


def compose(
    core: str,
    *,
    obfuscation: Optional[str] = None,
    structural: Optional[str] = None,
    framing: Optional[List[str]] = None,
    multi_turn: Optional[str] = None,
    carrier: bool = False,
    ctx: Optional[TechniqueContext] = None,
) -> ComposedPayload:
    """Merge the selected techniques into one reasoned :class:`ComposedPayload`."""
    core = (core or "").strip()
    ctx = ctx or TechniqueContext()
    notes: List[str] = []

    obfuscation = _validate("obfuscation", obfuscation, CORE_ENCODINGS)
    structural = _validate("structural", structural, STRUCTURAL_TECHNIQUES)
    multi_turn = _validate("multi_turn", multi_turn, MULTI_TURN_TECHNIQUES)
    framing = [f for f in (framing or []) if f in FRAMING_TECHNIQUES]

    # -- 1. resolve core encoding + decode hint -----------------------------
    encoded_core = core
    hint: Optional[str] = None
    if obfuscation and obfuscation != "none":
        if structural in SELF_ENCODING_STRUCTURAL:
            notes.append(
                f"dropped obfuscation '{obfuscation}': structural '{structural}' "
                "already encodes the core"
            )
            obfuscation = None
        else:
            variants = build_obfuscated_variants(core, [obfuscation])
            if variants:
                _, encoded_core = variants[0]
                hint = decode_hint(obfuscation)

    # -- 2. structural layer ------------------------------------------------
    if structural in SELF_ENCODING_STRUCTURAL:
        core_text = apply_single_turn(structural, core, ctx)  # builder encodes the raw core
    elif structural:
        inner = f"{hint}\n{encoded_core}" if hint else core
        core_text = apply_single_turn(structural, inner, ctx)
    else:
        core_text = f"{hint}\n{encoded_core}" if hint else encoded_core

    # -- 3. framing layer (inner -> outer) ----------------------------------
    applied_framing: List[str] = []
    ordered = sorted(framing, key=lambda f: _FRAMING_ORDER.index(f) if f in _FRAMING_ORDER else 99)
    text = core_text
    for f in ordered:
        text = apply_single_turn(f, text, ctx)
        applied_framing.append(f)
    if len(applied_framing) > 2:
        notes.append(f"{len(applied_framing)} framing layers stacked (noisy)")

    # -- 4. multi-turn (dominant) ------------------------------------------
    if multi_turn:
        turns = build_turns(multi_turn, text, ctx)
        if carrier:
            notes.append("carrier ignored for multi-turn composition")
            carrier = False
    else:
        turns = [Turn(user=text, label="single")]

    # -- 5. delivery carrier (single-turn only) -----------------------------
    if carrier and turns:
        label_for_hint = obfuscation or "none"
        turns[-1] = Turn(
            user=wrap_in_carrier_document(turns[-1].user, label_for_hint),
            role_context=turns[-1].role_context,
            label=(turns[-1].label or "single") + "+carrier",
        )

    parts = [p for p in (obfuscation if obfuscation != "none" else None, structural, *applied_framing, multi_turn) if p]
    if carrier:
        parts.append("carrier")
    label = "+".join(parts) if parts else "raw"

    return ComposedPayload(
        label=label,
        turns=turns,
        obfuscation=obfuscation if obfuscation != "none" else None,
        structural=structural,
        framing=applied_framing,
        multi_turn=multi_turn,
        carrier=carrier,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Surface-aware automatic composition
# ---------------------------------------------------------------------------
# Preferred structural technique per surface (exfil-shaped surfaces favour the
# zero-click image / URL fragmentation vectors).
_SURFACE_STRUCTURAL = {
    "SENSITIVE_DATA_DISCLOSURE": ["image_markdown_zero_click", "url_fragmentation"],
    "INSECURE_OUTPUT_HANDLING": ["image_markdown_zero_click", "multimodal_image_injection"],
    "INDIRECT_PROMPT_INJECTION": ["multimodal_image_injection", "url_fragmentation", "image_markdown_zero_click"],
    "SYSTEM_PROMPT_LEAKAGE": ["multimodal_image_injection", "url_fragmentation"],
}
_SURFACE_MULTI_TURN = {
    "EXCESSIVE_AGENCY": ["multi_turn_logic_injection", "memory_poisoning"],
    "INDIRECT_PROMPT_INJECTION": ["multi_turn_context_poisoning", "memory_poisoning"],
    "DIRECT_JAILBREAK_AND_EVASION": ["crescendo", "multi_turn_logic_injection"],
    "SYSTEM_PROMPT_LEAKAGE": ["crescendo"],
}
_SAFE_ENCODINGS = ["none", "base64", "homoglyph", "zero_width_insert", "rot13", "unicode_tag"]


def auto_compose(
    core: str,
    surface: str,
    *,
    ctx: Optional[TechniqueContext] = None,
    rng: Optional[random.Random] = None,
    allow_multi_turn: bool = True,
    max_framing: int = 1,
) -> ComposedPayload:
    """Pick a surface-appropriate, guaranteed-compatible multi-technique combo."""
    rng = rng or random.Random()
    ctx = ctx or TechniqueContext(surface=surface, rng=rng)

    structural = None
    if surface in _SURFACE_STRUCTURAL and rng.random() < 0.7:
        structural = rng.choice(_SURFACE_STRUCTURAL[surface])
    elif rng.random() < 0.4:
        structural = rng.choice(STRUCTURAL_TECHNIQUES)

    # Compatibility: skip a separate encoding when structural self-encodes.
    if structural in SELF_ENCODING_STRUCTURAL:
        obfuscation = "none"
    else:
        obfuscation = rng.choice(_SAFE_ENCODINGS)

    framing: List[str] = []
    if max_framing > 0 and rng.random() < 0.75:
        pool = list(FRAMING_TECHNIQUES)
        rng.shuffle(pool)
        framing = pool[:rng.randint(1, max_framing)]

    multi_turn = None
    if allow_multi_turn and rng.random() < 0.5:
        pool = _SURFACE_MULTI_TURN.get(surface) or MULTI_TURN_TECHNIQUES
        multi_turn = rng.choice(pool)

    return compose(
        core,
        obfuscation=obfuscation,
        structural=structural,
        framing=framing,
        multi_turn=multi_turn,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# CLI / benchmark helpers
# ---------------------------------------------------------------------------
def resolve_injection_spec(spec: Optional[str]) -> Dict[str, object]:
    """Parse a comma-separated technique spec into categorized selections.

    Unknown tokens are ignored; the first of each single-valued layer wins.
    Returns {obfuscation, structural, framing[list], multi_turn}.
    """
    out: Dict[str, object] = {"obfuscation": None, "structural": None, "framing": [], "multi_turn": None}
    if not spec:
        return out
    for tok in (t.strip().lower() for t in spec.split(",")):
        if not tok:
            continue
        if tok in CORE_ENCODINGS and out["obfuscation"] is None:
            out["obfuscation"] = tok
        elif tok in STRUCTURAL_TECHNIQUES and out["structural"] is None:
            out["structural"] = tok
        elif tok in FRAMING_TECHNIQUES:
            out["framing"].append(tok)  # type: ignore[union-attr]
        elif tok in MULTI_TURN_TECHNIQUES and out["multi_turn"] is None:
            out["multi_turn"] = tok
    return out


def catalog() -> Dict[str, List[str]]:
    return {
        "core_encoding": list(CORE_ENCODINGS),
        "structural": list(STRUCTURAL_TECHNIQUES),
        "framing": list(FRAMING_TECHNIQUES),
        "multi_turn": list(MULTI_TURN_TECHNIQUES),
    }


def describe_catalog() -> str:
    lines = ["ORF technique catalog", "=" * 60]
    lines.append("\n[core encoding]  (obfuscation.py — pick <=1)")
    lines.append("  " + ", ".join(CORE_ENCODINGS))
    for layer in ("structural", "framing", "multi_turn"):
        pool = STRUCTURAL_TECHNIQUES if layer == "structural" else (
            FRAMING_TECHNIQUES if layer == "framing" else MULTI_TURN_TECHNIQUES
        )
        lines.append(f"\n[{layer}]")
        for tid in pool:
            spec = INJECTION_TECHNIQUES[tid]
            lines.append(f"  {tid:<28} {spec.description}")
    return "\n".join(lines)
