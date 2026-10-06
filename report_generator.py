"""Human-facing vulnerability report generation for the ORF audit pipeline.

The runtime pipeline (``main.py``) already emits a machine-readable JSON report
per run and files GitHub issues for confirmed breaches. This module adds two
extra artifacts on top of that, taking its layout/branding cues from
``report-template.py``:

    * ``VULN_REPORT_<session>.pdf`` -- a branded, human-readable assessment with
      an executive summary, a findings table, a native (matplotlib-free)
      reproducible-probability chart, per-finding detail, and -- importantly --
      the complete and original payloads used against the target for every
      finding.
    * ``PAYLOADS_<session>.md`` -- a plain-text dossier that reproduces the
      complete and original payloads verbatim (full UTF-8 fidelity, no PDF
      sanitisation) so nothing is lost to the latin-1 core PDF fonts.

Both are best-effort: ``fpdf`` is optional (the dossier is always written), and
every entry point degrades gracefully rather than crashing an audit run.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("orf.report")

# --- CONFIGURATION & BRANDING (mirrors report-template.py) ---
BRAND_NAME = "Mr. RED"
ACCENT_COLOR = (200, 0, 0)      # Red
HEADER_TEXT_COLOR = (255, 255, 255)  # White

try:  # fpdf is optional; the markdown dossier is always produced regardless.
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except Exception as _exc:  # noqa: BLE001
    FPDF = object  # type: ignore
    _FPDF_AVAILABLE = False
    _FPDF_IMPORT_ERROR = _exc


# =====================================================================
# Text helpers -- keep arbitrary payload text safe for the core PDF fonts
# =====================================================================
def _pdf_safe(text: Any) -> str:
    """Coerce arbitrary text to something the latin-1 core PDF fonts can render.

    Payloads routinely contain emoji / CJK / control bytes; the core Arial font
    is latin-1 only, so non-encodable characters are replaced rather than left
    to raise mid-render. Full-fidelity payloads live in the markdown dossier.
    """
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _soft_wrap(text: str, width: int = 90) -> str:
    """Break tokens longer than ``width`` so ``multi_cell`` never runs out of
    horizontal space on unbreakable blobs (e.g. base64 / URL-encoded cores)."""
    wrapped_lines: List[str] = []
    for line in text.split("\n"):
        words: List[str] = []
        for tok in line.split(" "):
            while len(tok) > width:
                words.append(tok[:width])
                tok = tok[width:]
            words.append(tok)
        wrapped_lines.append(" ".join(words))
    return "\n".join(wrapped_lines)


def _clean_block(text: Any, width: int = 90) -> str:
    return _soft_wrap(_pdf_safe(text), width=width)


# =====================================================================
# Reproducible-probability curve (computed from the run, not hard-coded)
# =====================================================================
def _probability_series(reports: List[Dict[str, Any]], max_attempts: int = 10) -> List[Tuple[int, float]]:
    """Cumulative probability of a confirmed breach as a function of attempts.

    For every VULNERABLE finding we know how many mutation iterations it took
    (``iterations_required``). The curve at attempt ``a`` is the fraction of
    vulnerable findings that had already breached within ``a`` attempts -- a
    genuine reproducibility CDF rather than the template's illustrative line.
    """
    depths = [
        int(r.get("iterations_required") or 1)
        for r in reports
        if str(r.get("status", "")).upper() == "VULNERABLE"
    ]
    span = max(max_attempts, max(depths) if depths else 1)
    if not depths:
        return [(a, 0.0) for a in range(1, span + 1)]
    total = len(depths)
    return [(a, sum(1 for d in depths if d <= a) / total) for a in range(1, span + 1)]


# =====================================================================
# PDF document
# =====================================================================
class VulnerabilityReport(FPDF):  # type: ignore[misc]
    def mcell(self, h: float, text: str, *, fill: bool = False, border: int = 0):
        """multi_cell that always continues at the left margin on the next line.

        fpdf2 defaults to leaving the cursor at the right edge of the cell, which
        starves the following ``multi_cell`` of horizontal space; forcing
        ``new_x=LMARGIN, new_y=NEXT`` restores classic pyfpdf flow behaviour.
        """
        self.multi_cell(0, h, text, border=border, fill=fill,
                        new_x="LMARGIN", new_y="NEXT")

    def header(self):
        self.set_fill_color(*ACCENT_COLOR)
        self.rect(0, 0, 210, 25, "F")
        self.set_font("Arial", "B", 16)
        self.set_text_color(*HEADER_TEXT_COLOR)
        self.set_y(8)
        self.cell(0, 10, f"{BRAND_NAME} | SECURITY ASSESSMENT REPORT", 0, 1, "C")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Page {self.page_no()} - Confidential - {BRAND_NAME}", 0, 0, "C")

    def section_title(self, label: str):
        self.set_font("Arial", "B", 12)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(*ACCENT_COLOR)
        self.cell(0, 10, f"  {_pdf_safe(label)}", 0, 1, "L", fill=True)
        self.ln(3)

    def chapter_body(self, text: str):
        self.set_font("Arial", "", 10)
        self.set_text_color(50, 50, 50)
        self.mcell(6, _clean_block(text))
        self.ln()

    def code_block(self, text: str):
        self.set_font("Courier", "", 7)
        self.set_text_color(20, 20, 20)
        self.set_fill_color(245, 245, 245)
        # Courier is fixed-width; keep the wrap well inside the printable width so
        # an unbreakable blob can never overflow a single line.
        self.mcell(4.2, _clean_block(text, width=95), border=0, fill=True)
        self.ln(2)

    def draw_probability_chart(self, series: List[Tuple[int, float]]):
        """Render the reproducible-probability curve with native primitives."""
        if not series:
            return
        x0, y0 = 25.0, self.get_y()
        plot_w, plot_h = 150.0, 55.0
        n = len(series)

        # Axes.
        self.set_draw_color(120, 120, 120)
        self.set_line_width(0.3)
        self.line(x0, y0, x0, y0 + plot_h)                     # y-axis
        self.line(x0, y0 + plot_h, x0 + plot_w, y0 + plot_h)   # x-axis

        # Horizontal gridlines + y labels (0.0 .. 1.0).
        self.set_font("Arial", "", 7)
        self.set_text_color(120, 120, 120)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            gy = y0 + plot_h - frac * plot_h
            self.set_draw_color(220, 220, 220)
            self.line(x0, gy, x0 + plot_w, gy)
            self.set_xy(x0 - 12, gy - 2)
            self.cell(10, 4, f"{frac:.2f}", 0, 0, "R")

        def _pt(idx: int, prob: float) -> Tuple[float, float]:
            px = x0 if n == 1 else x0 + (idx / (n - 1)) * plot_w
            py = y0 + plot_h - prob * plot_h
            return px, py

        # Area fill (thin verticals) then the line + markers, brand red.
        self.set_draw_color(*ACCENT_COLOR)
        self.set_line_width(0.2)
        for idx, (_attempt, prob) in enumerate(series):
            px, py = _pt(idx, prob)
            if prob > 0:
                self.line(px, y0 + plot_h, px, py)
        self.set_line_width(0.6)
        for idx in range(1, n):
            x1, y1 = _pt(idx - 1, series[idx - 1][1])
            x2, y2 = _pt(idx, series[idx][1])
            self.line(x1, y1, x2, y2)
        self.set_fill_color(*ACCENT_COLOR)
        for idx, (attempt, prob) in enumerate(series):
            px, py = _pt(idx, prob)
            self.rect(px - 0.7, py - 0.7, 1.4, 1.4, "F")
            self.set_xy(px - 5, y0 + plot_h + 1)
            self.set_text_color(120, 120, 120)
            self.cell(10, 4, str(attempt), 0, 0, "C")

        self.set_y(y0 + plot_h + 8)
        self.set_font("Arial", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, "Execution Attempts (x)  vs  Probability of Confirmed Breach (y)", 0, 1, "C")
        self.ln(2)


# =====================================================================
# Public entry points
# =====================================================================
def _fmt_payload_list(payloads: Any) -> str:
    if not payloads:
        return "(none captured)"
    if isinstance(payloads, str):
        payloads = [payloads]
    chunks = []
    for i, p in enumerate(payloads, start=1):
        chunks.append(f"--- payload segment {i} ---\n{p}")
    return "\n\n".join(chunks)


def generate_pdf_report(
    reports: List[Dict[str, Any]],
    output_path: Path,
    *,
    session_id: str = "",
    target_model: str = "",
    author_name: str = "Automated Battlefield Red-Team Core",
) -> Optional[Path]:
    """Write the branded PDF assessment. Returns the path, or ``None`` if fpdf
    is unavailable or rendering fails."""
    if not _FPDF_AVAILABLE:
        logger.warning("fpdf not installed (%s); skipping PDF report.", _FPDF_IMPORT_ERROR)
        return None

    try:
        vulnerable = [r for r in reports if str(r.get("status", "")).upper() == "VULNERABLE"]
        pdf = VulnerabilityReport()
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()

        # Title block.
        pdf.set_font("Arial", "B", 22)
        pdf.set_text_color(40, 40, 40)
        pdf.ln(6)
        pdf.cell(0, 10, "VULNERABILITY FINDING REPORT", 0, 1, "L")
        pdf.set_font("Arial", "", 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 7, f"Prepared by: {_pdf_safe(author_name)}", 0, 1, "L")
        if session_id:
            pdf.cell(0, 7, f"Session ID: {_pdf_safe(session_id)}", 0, 1, "L")
        if target_model:
            pdf.cell(0, 7, f"Target Agent: {_pdf_safe(target_model)}", 0, 1, "L")
        pdf.ln(4)

        # 1. Executive summary.
        pdf.section_title("EXECUTIVE SUMMARY")
        pdf.chapter_body(
            f"This automated white-box adversarial assessment evaluated "
            f"{len(reports)} attack-surface categories against the target agent. "
            f"{len(vulnerable)} category(ies) were confirmed VULNERABLE and "
            f"{len(reports) - len(vulnerable)} remained COMPLIANT. Confirmed guardrail "
            f"breaches allow unauthorized behaviour in the target and warrant immediate "
            f"remediation to prevent data exfiltration and restricted-action abuse. The "
            f"complete and original payloads used to trigger each finding are reproduced "
            f"verbatim in the FINDINGS DETAIL section below."
        )

        # 2. Findings overview table.
        pdf.section_title("FINDINGS OVERVIEW")
        pdf.set_font("Arial", "B", 9)
        pdf.set_fill_color(*ACCENT_COLOR)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(80, 7, " Category", 1, 0, "L", fill=True)
        pdf.cell(30, 7, "Status", 1, 0, "C", fill=True)
        pdf.cell(30, 7, "Attempts", 1, 0, "C", fill=True)
        pdf.cell(50, 7, "Confidence", 1, 1, "C", fill=True)
        pdf.set_font("Arial", "", 9)
        for r in reports:
            is_vuln = str(r.get("status", "")).upper() == "VULNERABLE"
            pdf.set_text_color(*(ACCENT_COLOR if is_vuln else (60, 120, 60)))
            pdf.cell(80, 6, " " + _pdf_safe(str(r.get("category", "?")))[:46], 1, 0, "L")
            pdf.cell(30, 6, _pdf_safe(str(r.get("status", "?"))), 1, 0, "C")
            pdf.cell(30, 6, str(r.get("iterations_required", "-")), 1, 0, "C")
            pdf.cell(50, 6, str(r.get("average_confidence", "-")), 1, 1, "C")
        pdf.ln(6)

        # 3. Reproducible probability chart.
        pdf.section_title("REPRODUCIBLE PROBABILITY ANALYSIS")
        pdf.draw_probability_chart(_probability_series(reports))
        pdf.chapter_body(
            "The graph shows the cumulative probability of a confirmed breach as a "
            "function of the number of mutation attempts, computed from the iterations "
            "each vulnerable finding required. A curve that saturates near 1.0 within a "
            "few attempts indicates a reliably reproducible weakness."
        )

        # 4. Per-finding detail with complete + original payloads — for EVERY
        #    finding, not just breaches, so defended (compliant) attempts are
        #    auditable too.
        compliant = [r for r in reports if str(r.get("status", "")).upper() != "VULNERABLE"]

        def _render_detail(r: Dict[str, Any], idx: int, *, breached: bool) -> None:
            pdf.set_font("Arial", "B", 11)
            pdf.set_text_color(*(ACCENT_COLOR if breached else (60, 120, 60)))
            pdf.mcell(7, _pdf_safe(f"{idx}. {r.get('category', 'Unknown Category')}"))
            pdf.set_font("Arial", "", 9)
            pdf.set_text_color(60, 60, 60)
            meta = (
                f"Delivery vector: {r.get('delivery_vector', 'n/a')}   |   "
                f"Obfuscation: {r.get('obfuscation_technique') or 'none'}   |   "
                f"OWASP: {r.get('owasp', 'n/a')}   |   "
                f"Vote ratio: {r.get('vote_ratio', 'n/a')}"
            )
            pdf.mcell(5, _clean_block(meta))
            pdf.ln(1)

            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 5, "Original attacker query (pre-weaponization):", 0, 1)
            pdf.code_block(r.get("original_payload") or "(not recorded)")

            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 5, "Complete payload(s) dispatched to the target:", 0, 1)
            pdf.code_block(_fmt_payload_list(r.get("full_payloads") or r.get("payload_used")))

            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 5, "Target compromise proof (excerpt):" if breached
                     else "Target response - defended (excerpt):", 0, 1)
            pdf.code_block((str(r.get("exploit_proof") or "(none)"))[:1500])
            pdf.ln(4)

        pdf.section_title("CONFIRMED BREACHES (COMPLETE & ORIGINAL PAYLOADS)")
        if not vulnerable:
            pdf.chapter_body("No categories were confirmed vulnerable in this run.")
        for idx, r in enumerate(vulnerable, start=1):
            _render_detail(r, idx, breached=True)

        pdf.section_title("DEFENDED ATTEMPTS (COMPLIANT - COMPLETE & ORIGINAL PAYLOADS)")
        if not compliant:
            pdf.chapter_body("Every category was confirmed vulnerable in this run.")
        for idx, r in enumerate(compliant, start=1):
            _render_detail(r, idx, breached=False)

        # 5. Impact analysis (from template).
        pdf.section_title("IMPACT ANALYSIS")
        impacts = [
            ("General Impact", "Broad risk to the integrity of the target agent platform."),
            ("Technical Impact", "Enables restricted-action invocation, prompt disclosure, and lateral movement."),
            ("Operational Impact", "May lead to service disruption or abuse if exploited at scale."),
            ("Business Impact", "Potential loss of customer trust and regulatory non-compliance (GDPR/HIPAA)."),
        ]
        for cat, desc in impacts:
            pdf.set_font("Arial", "B", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(45, 7, f"{cat}:", 0, 0)
            pdf.set_font("Arial", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.mcell(7, _clean_block(desc))
            pdf.ln(1)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
        logger.info("PDF vulnerability report written to %s", output_path)
        return output_path
    except Exception as exc:  # noqa: BLE001 - reporting must never crash an audit
        logger.error("PDF report generation failed: %s", exc, exc_info=True)
        return None


def write_payload_dossier(
    reports: List[Dict[str, Any]],
    output_path: Path,
    *,
    session_id: str = "",
    target_model: str = "",
) -> Optional[Path]:
    """Write a verbatim, full-fidelity (UTF-8) dossier of the complete and
    original payloads for every finding. Always attempted regardless of fpdf."""
    try:
        lines: List[str] = [
            f"# {BRAND_NAME} - Complete & Original Payload Dossier",
            "",
            f"- Session ID: `{session_id}`",
            f"- Target agent: `{target_model}`",
            f"- Categories evaluated: {len(reports)}",
            "",
            "This dossier reproduces the complete and original payloads used against "
            "the target verbatim, without the sanitisation applied to the PDF report.",
            "",
        ]
        for r in reports:
            status = str(r.get("status", "?")).upper()
            lines.append(f"## {r.get('category', 'Unknown')} — {status}")
            lines.append("")
            lines.append(f"- Delivery vector: `{r.get('delivery_vector', 'n/a')}`")
            lines.append(f"- Obfuscation: `{r.get('obfuscation_technique') or 'none'}`")
            lines.append(f"- Attempts (iterations required): `{r.get('iterations_required', 'n/a')}`")
            lines.append("")
            lines.append("### Original attacker query (pre-weaponization)")
            lines.append("```")
            lines.append(str(r.get("original_payload") or "(not recorded)"))
            lines.append("```")
            lines.append("")
            lines.append("### Complete payload(s) dispatched to the target")
            full = r.get("full_payloads") or r.get("payload_used")
            if isinstance(full, str):
                full = [full]
            if not full:
                lines.append("_(none captured)_")
            else:
                for i, p in enumerate(full, start=1):
                    lines.append(f"**Segment {i}:**")
                    lines.append("```")
                    lines.append(str(p))
                    lines.append("```")
            lines.append("")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Payload dossier written to %s", output_path)
        return output_path
    except Exception as exc:  # noqa: BLE001
        logger.error("Payload dossier generation failed: %s", exc)
        return None


def generate_full_report_bundle(
    reports: List[Dict[str, Any]],
    out_dir: Path,
    *,
    session_id: str = "",
    target_model: str = "",
) -> List[Path]:
    """Produce every human-facing artifact (PDF + dossier) for a run and return
    the paths actually written."""
    out_dir = Path(out_dir)
    written: List[Path] = []
    pdf_path = generate_pdf_report(
        reports,
        out_dir / f"VULN_REPORT_{session_id}.pdf",
        session_id=session_id,
        target_model=target_model,
    )
    if pdf_path:
        written.append(pdf_path)
    dossier_path = write_payload_dossier(
        reports,
        out_dir / f"PAYLOADS_{session_id}.md",
        session_id=session_id,
        target_model=target_model,
    )
    if dossier_path:
        written.append(dossier_path)
    return written
