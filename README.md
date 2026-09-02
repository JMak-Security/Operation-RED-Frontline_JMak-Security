# ⚔️ OPERATION RED-FRONTLINE-[v3.2.0]: Extended Agentic Security Attack Surface

*The Battlefield Logistics Engine, hardened. A localized, authorized AI red-teaming platform that moves beyond API-probing into full-stack architectural vulnerability validation — now with sandboxed SAST, BYOK multi-provider warfare, and locked-down endpoints.*

## 🚀 Overview: What’s New in v3.2.0?

**v3.2.0** is a maintenance-and-hardening patch over the v3.1.0 *Extended Agentic Security* release. Where v3.1.0 expanded the attack matrix to eleven surfaces, v3.2.0 fortifies the engine itself — isolating the code-execution paths, correcting the persistence layer, and opening the platform to any LLM backend you can point it at. This is the same combat doctrine, re-armored for real operations.

### ⚡ Major Upgrades from v3.1.0

*   **Sandboxed SAST (No More Host Bandit):** Generated Python is no longer scanned inside the engine process. It is shipped over an internal Docker network to a dedicated `sast-sandbox` service that runs Bandit as a locked-down non-root user. The engine analyzes source text — it never executes generated programs.
*   **BYOK Multi-Provider Arsenal:** Attacker, target, judge, and probe roles can each independently select `ollama`, `anthropic`, `openai`, `nvidia`, `google`/`genai`, or `groq`. Keys are read only from environment variables and are **never** written to reports or logs.
*   **Hardened Endpoint Policy:** Ollama URLs must be absolute HTTP(S) URLs with no embedded credentials. Enterprise and production modes demand HTTPS plus a Bearer `OLLAMA_AUTH_TOKEN`; plain local HTTP is accepted only under explicit local mode.
*   **Corrected Persistence Layer:** `LocalVulnerabilityTelemetry` is a valid ORM model backing the `vulnerability_telemetry` table. Sessions, votes, and confidence scores persist cleanly to SQLite locally or PostgreSQL under Compose.
*   **Timezone-Aware UTC Everywhere:** Logging, ORM defaults, session identifiers, and report metadata all use timezone-aware UTC timestamps.
*   **Precise Verdict & SAST Semantics:** Only an exact `__UNSAFE__` response is treated as unsafe — text that merely *contains* the token is not. Scanner failures, malformed code, and timeouts are represented distinctly and are **not** auto-reported as vulnerabilities.
*   **Protected Environment Precedence:** `PLACEHOLDER.env` loads without overriding shell or container variables, so production secrets never get shadowed by a tracked placeholder file.
*   **Fixed Source Formatting:** The ASCII banner, payload wrappers, and SQLAlchemy imports are all syntactically valid; advanced URL payloads use standard URL encoding, and tactic selection can be pinned for deterministic tests while staying random in normal operation.

---

## 🏗️ Architectural Blueprint

The Docker deployment fields three coordinated services:

*   **`redfront-engine` (Adversarial Generation Node):** Generates test payloads, calls the target model and the semantic judge, and writes reports and telemetry.
*   **`sast-sandbox` (White-Box SAST Engine):** Accepts generated source over an internal Docker network and runs Bandit as UID 10001 — read-only filesystem, no new privileges, dropped capabilities, no external network, and CPU / memory / PID / input-size / timeout limits. Source-text analysis only; no program execution.
*   **`postgres-db` (Persistent Telemetry Node):** Stores audit sessions and per-category telemetry when the Compose PostgreSQL configuration is used.

For local non-Docker runs, point `SAST_SANDBOX_URL` at a separately isolated service. Leaving it empty **disables** SAST evaluation for code blocks rather than falling back to Bandit inside the engine process.

---

## 🛡️ Target Vulnerability Matrix

v3.2.0 audits **11 Attack Surface Categories** — the four core LLM surfaces plus the seven Agentic Security (ASI) surfaces introduced in v3.1.0:

**Core LLM surfaces**
1.  **SEC-CODE-001:** Insecure Code Generation (CWE validation via sandboxed SAST).
2.  **SEC-INJ-001:** Indirect Prompt Injection.
3.  **SEC-BRK-001:** Direct Jailbreak & Evasion.
4.  **SEC-LEAK-001:** System Prompt Leakage.

**Agentic Security (ASI) surfaces**
5.  **SEC-ASI-001:** Agent Goal Hijack.
6.  **SEC-ASI-002:** Tool Misuse Exploitation.
7.  **SEC-ASI-003:** Identity / Privilege Abuse.
8.  **SEC-ASI-004:** Memory / Context Poisoning.
9.  **SEC-ASI-005:** Unexpected Code Execution.
10. **SEC-ASI-006:** Insecure Inter-Agent Communication.
11. **SEC-ASI-007:** Human–Agent Trust Exploitation.

---

## 🛠️ Quick Start

### 1. Install Dependencies

Requires **Python 3.11+**. Install the declared runtime dependencies:

```bash
pip install -r requirements.txt
```

You will also need a running **Ollama** instance serving your configured models (or valid BYOK credentials for a hosted provider).

### 2. Environment Setup

Create or edit `PLACEHOLDER.env` in the root directory (loaded automatically at startup, without overriding existing shell/container variables):

```env
ENV_MODE=local
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_AUTH_TOKEN=
SAST_SANDBOX_URL=
PRIMARY_PROVIDER=ollama
SECONDARY_PROVIDER=ollama
JUDGE_PROVIDER=ollama
OLLAMA_PRIMARY_MODEL=tinydolphin        # The Adversary (attacker)
OLLAMA_SECONDARY_MODEL=qwen2.5:latest   # The Target + Judge
PRIMARY_MODEL=                          # optional provider-neutral override
SECONDARY_MODEL=                        # optional provider-neutral override
OLLAMA_MAX_CONCURRENT_TASKS=1           # Async concurrency cap

# BYOK credentials. Set only the keys for the providers you select above.
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
NVIDIA_API_KEY=
GOOGLE_API_KEY=                         # GEMINI_API_KEY accepted as an alias.
GROQ_API_KEY=

# SQLite is the default local telemetry store.
DATABASE_URL=sqlite:///orf_audit.db

# Optional — target agent config and auto-filed GitHub Issues.
TARGET_SYSTEM_PROMPT_FILE=input_src/target_agent/system_prompt.txt
GITHUB_ACCESS_TOKEN=your_token
GITHUB_TARGET_REPOSITORY=user/repo
```

The process environment always takes precedence over `PLACEHOLDER.env`. **Never** put production credentials in the tracked placeholder file.

### 3. BYOK Providers

Assign a provider per role. `PRIMARY_MODEL` / `SECONDARY_MODEL` are provider-neutral overrides; the legacy `OLLAMA_PRIMARY_MODEL` / `OLLAMA_SECONDARY_MODEL` names remain supported for compatibility:

```env
PRIMARY_PROVIDER=openai
SECONDARY_PROVIDER=anthropic
JUDGE_PROVIDER=groq
OLLAMA_PRIMARY_MODEL=gpt-4o-mini
OLLAMA_SECONDARY_MODEL=claude-3-5-haiku-latest
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GROQ_API_KEY=...
```

Supported values: `ollama`, `anthropic`, `openai`, `nvidia`, `google`, `genai`, `groq`. The `google`/`genai` names use Google’s Generative Language API (`GOOGLE_API_KEY` preferred, `GEMINI_API_KEY` accepted as an alias); OpenAI, NVIDIA NIM, and Groq use their OpenAI-compatible chat-completions APIs. Optional `OPENAI_BASE_URL`, `NVIDIA_BASE_URL`, `GROQ_BASE_URL`, `ANTHROPIC_BASE_URL`, and `GOOGLE_GENAI_BASE_URL` can point at approved gateways. A selected provider’s key is required at startup and is never logged or included in reports.

### 4. Endpoint Security

`OLLAMA_BASE_URL` must include a scheme (e.g. `https://ollama.example.com`); URLs carrying usernames or passwords are rejected. In `enterprise` or `production` mode the endpoint must use HTTPS and `OLLAMA_AUTH_TOKEN` must be set — the token is sent as a Bearer header. Local HTTP is accepted only when `ENV_MODE=local`.

### 5. Deploy Simulation

The engine ships with a small CLI. Smoke-test connectivity first, then launch the full audit:

```bash
# Smoke-test connectivity to your backend
python main.py probe --prompt "Hello, system check."

# Run the complete standalone red-team audit pipeline
python main.py run
```

Both modes accept explicit overrides. When omitted, each falls back to the matching environment value:

| Option | Environment fallback | Purpose |
| --- | --- | --- |
| `--model` | `OLLAMA_PRIMARY_MODEL` | Attacker (adversary) model |
| `--secondary-model` | `OLLAMA_SECONDARY_MODEL` | Target + judge model |
| `--base-url` | `OLLAMA_BASE_URL` | Ollama API URL |
| `--prompt` | None | Probe prompt (`probe` mode only) |

---

## 🐳 Docker Deployment

Compose requires secrets from the environment — none are baked into `docker-compose.yml`. This example uses a local HTTP Ollama endpoint and is for **development only**:

```bash
POSTGRES_PASSWORD='choose-a-local-password' \
OLLAMA_AUTH_TOKEN='choose-a-token' \
OLLAMA_BASE_URL='http://host.docker.internal:11434' \
docker compose up --build
```

Compose defaults to explicit local mode so this example can use plain HTTP. For an enterprise deployment, set `ENV_MODE=production`, supply an HTTPS `OLLAMA_BASE_URL`, and provide a real `OLLAMA_AUTH_TOKEN`.

The engine and SAST service share the project source as a **read-only** mount. Reports land in the named Docker volume `vaultdata` at `/workspace/secure_vault` — a named volume is not automatically a Windows host directory, so export it or swap in an explicit bind mount when reports must be directly visible on the host.

---

## 📤 Output & Reporting

Every run writes a timestamped findings report:

```text
secure_vault/REPORT_<session_id>.json
```

The report carries UTC metadata and category findings. The database stores each audit session plus per-category status, payload, exploit proof, vote ratio, and confidence — SQLite for local use, PostgreSQL under Compose. Confirmed findings can optionally be published to **GitHub Issues** via `GITHUB_ACCESS_TOKEN` and `GITHUB_TARGET_REPOSITORY`; missing or placeholder credentials simply skip publication.

**Performance note:** *runtime is dominated by local LLM inference. On CPU-only, a full audit can take ~1 hour; a GPU is far faster. The engine runs one request at a time by default — raise `OLLAMA_MAX_CONCURRENT_TASKS` on a stronger machine to parallelize.*

---

## ✅ Validation

Run the focused tests and source checks:

```bash
python -m unittest discover -s tests -v
python -m py_compile main.py sast_sandbox.py
```

Validate the Compose file with sanitized values:

```bash
POSTGRES_PASSWORD='test-password' \
OLLAMA_AUTH_TOKEN='test-token' \
docker compose config
```

The tests cover endpoint validation, exact payload behavior, timezone-aware timestamps, and the corrected telemetry model. A live Ollama service is required for `probe` and a full audit.

---

## ⚠️ Responsible Use

**OPERATION RED-FRONTLINE [v3.2.0]** generates weaponized adversarial vectors and is strictly for educational purposes and **authorized** security research. Use it only against models, agents, and infrastructure you own or are explicitly authorized to test. Generated payloads and model responses may contain sensitive or harmful material — protect reports and credentials accordingly. The authors take no responsibility for misuse against unauthorized systems.

---
**Developed by:** [JMak-Security]  
**Release:** v3.2.0  
**Status:** *Hardened. Combat Ready.*
