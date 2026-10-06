# 🔴 Operation Red-Frontline (ORF) — v4.0.0

> An automated red-team harness for **LLM and agentic AI** targets — generate,
> deliver, and judge adversarial payloads end to end, with LLM-as-judge verdicts
> and post-quantum-encrypted evidence.

---

## 🎯 Audit engine
- **Three-role model architecture** — independently configurable **attacker**,
  **target**, and **judge** (each with its own provider / endpoint / model).
- **Judge-only verdicts** — `VULNERABILITY_CONFIRMED` / `COMPLIANT` decided purely
  by a local LLM judge with confidence + reason (no regex/keyword scoring).
- **Full audit loop** — white-box intel → generate → compose/deliver → send →
  judge → report, run per attack category.
- **Concurrent categories** — rate-limits only real network round-trips; local
  work (whitebox scan, composition, evaluation) runs fully in parallel.

## 🧬 Payload weaponization
- **Technique composition** — encoding / structural / framing / multi-turn
  primitives, with **`auto`** (surface-aware) or **`manual`** selection.
- **Indirect prompt injection** — document **file-upload** delivery with an
  obfuscation corpus.
- **Agentic intel** — the attacker model can query the Superdata bridge
  mid-generation via the `NEED_INTEL` protocol.

## 🌐 Transport & targets
- **Targets** — generic **SSE chatbot**, **OpenAI-compatible `/v1`**, and
  **native Ollama**.
- **19 OpenAI-compatible providers** — NVIDIA, Google, Groq, OpenRouter,
  SiliconFlow, Cloudflare, Featherless, DeepInfra, Together, DeepSeek, Mistral,
  Fireworks, Perplexity, xAI, Cerebras, Novita, Hyperbolic, Ollama Cloud, and a
  generic **custom** escape hatch.
- **Role-scoped endpoints** — per-role base URL / key / model overrides, plus
  default providers via `ATTACKER_PROVIDER` / `JUDGE_PROVIDER`.

## 🧠 Self-learning & intel
- **Persistent test memory** — `off` / `record` / `learn`, feeding prior findings
  back into payload generation.
- **Superdata Extractor** — pre-run white-box intel from a frontend codebase or a
  live URL.

## 🛡️ Evidence & hardening
- **Branded PDF + verbatim payload dossier** — covers *confirmed breaches* **and**
  *defended attempts*, reproducing original + full payloads for both.
- **JSON findings** mapped to **OWASP LLM Top 10**, **OWASP ASI T1–T15**, and
  **MITRE ATLAS**.
- **Post-quantum vault** — optional **ML-KEM-768 (Kyber) + AES-GCM** hybrid
  encryption of reports.
- **Hardened Docker sandbox** — zero-trust read-only runtime + isolated Postgres
  (optional VPN tunnel).

## 🧪 Verification & tooling
- **VVS adversarial harness** (`vvs_test.py`) — smoke / k+ / attack-a…d / boundary
  suites.
- **Offline benchmark** — **27/27** techniques and **6/6** combos, with
  deterministic seeds (0 failures).
- **Operator conveniences** — interactive **chat**, target **probe** (smoke test),
  and **settings** (Docker / VPN) enablement.
- **One-cell Colab runner** — zip → unzip → install → [PQC] → execute.

---

> **Authorized use only.** This is an offensive-security testing tool. Run it
> exclusively against systems you own or are explicitly authorized to test.
