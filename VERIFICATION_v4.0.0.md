# ORF v4.0.0 — Verification Report

Evidence that **Operation Red-Frontline v4.0.0** runs and behaves as documented.

| | |
|---|---|
| **Build** | Operation Red-Frontline (ORF) **v4.0.0** |
| **Date** | 2026-10-06 |
| **Host** | Windows 11 (win32), Python **3.11.9** |
| **Result** | ✅ **PASS** — 0 failures |

---

## 1. Offline self-test — `python main.py benchmark --use-seeds --json`

Exit code `0`, machine-readable coverage report:

| Metric | Result |
|---|---|
| Techniques built | **27 / 27** |
| Combinatorial payloads (combo matrix) | **6 / 6** |
| Auto-compose surfaces | **8 / 8** |
| Failures | **0** |

Technique breakdown by layer (all `ok: true`):

| Layer | Techniques |
|---|---|
| `core_encoding` | 16 |
| `structural` | 3 |
| `framing` | 4 |
| `multi_turn` | 4 |
| **Total** | **27** |

The JSON payload exposes the keys `surface`, `cores`, `layers`, `failures`,
`combos`, `auto_compose`, and `summary` — the same report is reproducible with:

```bash
python main.py benchmark --use-seeds          # human-readable
python main.py benchmark --use-seeds --json   # machine-readable
```

## 2. Static integrity checks

| Check | Result |
|---|---|
| `python -m py_compile main.py` | ✅ pass |
| `colab/*.ipynb` parse as valid JSON | ✅ pass (3/3) |
| Version tokens across README / COOKBOOK / notebooks / GUIDEBOOK | ✅ all **v4.0.0** |

## 3. Prior end-to-end audit artifact (local, not shipped)

A completed live audit run is present in `secure_vault/` (git-ignored, so it is
**not** part of the release):

- `VULN_REPORT_audit_1791213653.pdf` — branded PDF report
- `REPORT_audit_1791213653.json` — structured findings (fields: `category`,
  `status`, `delivery_vector`, `obfuscation_technique`, `payload_used`,
  `full_payloads`, `exploit_proof`, `vote_ratio`, `average_confidence`,
  `owasp`, `analysis`, `turn_trace`)
- `PAYLOADS_audit_1791213653.md` — verbatim payload dossier

This confirms the report pipeline (finding → brand PDF + dossier + JSON) executes
end to end.

---

## Not verified in this environment (documented limitations)

| Item | Status |
|---|---|
| Docker image build / run | ⚠️ Not exercised (Docker daemon was not available); `docker-compose.yml` and `Dockerfile` are present and statically reviewed. |
| Native post-quantum key exchange | ⚠️ Verified against the **stub** path only — the native `liboqs` shared library is absent on this host. |
| Live target audits | ⚠️ Require a target endpoint and provider API keys (not part of this verification). |
| `vvs_test.py` attack suites | ⚠️ Require the VVS boundary service to be running. |

> These are environment constraints, not code defects. Each degrades or behaves
> as documented in `README.md` and `COOKBOOK.md`.
