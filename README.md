# Operation Red-Frontline (ORF) — v4.0.0

An automated red-team harness for **LLM and agentic AI** targets, with an
interactive **chatbot** and a built-in **environment manager** (Docker sandbox +
VPN). ORF generates adversarial payloads with a local attacker model, delivers
them to a target chatbot/agent, and decides **VULNERABLE vs COMPLIANT** for every
attack category using a **local LLM-as-judge**. Findings are written to JSON, a
branded PDF, a verbatim payload dossier, and (optionally) a post-quantum-encrypted
vault.

It maps findings to **OWASP LLM Top 10**, the **OWASP Agentic Security Initiative
(ASI T1–T15)**, and MITRE ATLAS techniques.

> **Authorized use only.** This is an offensive-security testing tool. Run it
> exclusively against systems you own or are explicitly authorized to test.

---

## Table of contents

- [What ORF does](#what-orf-does)
- [The three model roles](#the-three-model-roles)
- [Install](#install)
- [Quick start](#quick-start)
- [Threat suites](#threat-suites)
- [Interactive chat](#interactive-chat)
- [Settings: Docker & VPN](#settings-docker--vpn)
- [Test memory & self-learning](#test-memory--self-learning)
- [Configuration](#configuration)
- [CLI reference](#cli-reference)
- [The LLM judge](#the-llm-judge)
- [Reports & the PQC vault](#reports--the-pqc-vault)
- [One-cell Colab runner](#one-cell-colab-runner)
- [Project layout](#project-layout)

---

## What ORF does

For each attack category in the active suite, one audit runs this loop:

1. **White-box intel** — statically scans `input_src/target_agent/` (system
   prompt, backend tools, frontend routes) to ground payload generation.
2. **Generate** — the **attacker** model produces a raw adversarial payload.
3. **Compose / deliver** — the payload is wrapped in natural delivery framing (or
   composed with multi-technique encodings, or uploaded as a document for
   indirect injection).
4. **Send** — it is delivered to the **target** (SSE chatbot, OpenAI-compatible
   endpoint, or Ollama model).
5. **Judge** — the **judge** model reads the target's response and returns a
   verdict (`VULNERABILITY_CONFIRMED` / `COMPLIANT`) with confidence and a reason.
6. **Report** — confirmed breaches are written incrementally to `secure_vault/`
   and (optionally) filed as GitHub issues.

Categories run concurrently; only the network round-trips to the models are
rate-limited. Verdicts are decided **purely by the judge model** — there is no
regex/keyword scoring in the decision path.

Beyond the audit, ORF ships two operator conveniences:

- **`chat`** — a normal conversational front-end on the same provider stack, for
  open questions. See [Interactive chat](#interactive-chat).
- **`settings`** — enable a hardened **Docker sandbox** and/or a **VPN tunnel**
  around your runs, with install helpers. See [Settings](#settings-docker--vpn).

---

## The three model roles

ORF separates three independent model roles, each with its own provider/endpoint:

| Role | Purpose | Default | Providers |
|------|---------|---------|-----------|
| **Attacker** | Generates adversarial payloads | Ollama `dolphin-llama3` @ `localhost:11434` | `ollama`, `openai`, `sse` |
| **Target** | System under test | `sse` @ `https://your-chat-host.example` | `sse`, `openai`, `ollama` |
| **Judge** | Decides VULNERABLE/COMPLIANT | *follows the attacker* | `ollama`, `openai`, `sse` |

```
attacker (local)  --generates-->  payload
        |                            |
        |                     compose / upload
        v                            v
   target (SSE / OpenAI / Ollama)  <-- delivered
        |
    response
        v
   judge (local)  --verdict-->  VULNERABLE / COMPLIANT  -->  secure_vault/
```

The `deterministic_assertions` module is still used for payload delivery framing
and canary-token minting — not for the verdict.

### Named providers (OpenAI-compatible)

Besides the base `openai` / `ollama` / `sse` providers, ORF ships **named
providers** that resolve to an OpenAI-compatible endpoint + key + default model
straight from `PLACEHOLDER.env` (template: `.env.example`): **`nvidia`**,
**`google`**, **`groq`**, **`openrouter`**, **`siliconflow`**, **`cloudflare`**,
**`featherless`**, **`deepinfra`**, **`together`**, **`deepseek`**, **`mistral`**,
**`fireworks`**, **`perplexity`**, **`xai`**, **`cerebras`**, **`novita`**,
**`hyperbolic`**, **`ollamacloud`**, and the generic **`custom`** escape hatch
(any OpenAI-compatible host — set `CUSTOM_BASE_URL`). Set each one's
`NAME_API_KEY` / `NAME_MODEL` / `NAME_BASE_URL` (already scaffolded in the env
file), then select it per role — no need to retype base URLs. Any URL containing
`/v1` is used verbatim, so no new transport code is ever needed:

```bash
python main.py chat --provider groq
python main.py run --suite quick \
  --attacker-provider nvidia \
  --judge-provider google \
  --target-provider sse --base-url https://your-chat-host.example
```

Override the model per run with `--model` (attacker), `--secondary-model`
(target), or `--judge-model`. If a provider rejects `repetition_penalty` /
`temperature`, blank `OPENAI_REPETITION_PENALTY=` / `OPENAI_TEMPERATURE=` to omit
them.

**Defaults without flags.** Set `ATTACKER_PROVIDER` and `JUDGE_PROVIDER` in
`PLACEHOLDER.env` to a named provider and a bare `run` uses them — no per-role
flags needed:

```env
ATTACKER_PROVIDER=groq      # generates payloads
JUDGE_PROVIDER=google       # decides VULNERABLE / COMPLIANT
```

```bash
python main.py run --suite quick --base-url https://your-chat-host.example
# → attacker=Groq, judge=Google, target=SSE, automatically
```

> **Attacker caveat:** hosted providers run **safety-tuned** models that may
> **refuse** to generate adversarial payloads. For a real audit prefer an
> uncensored attacker — `ATTACKER_PROVIDER=ollama` (local `dolphin-llama3`) or
> `--attacker-provider ollama`. The judge, by contrast, benefits from a strong
> hosted model like Google Gemini.

---

## Install

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
```

Core runtime deps: `aiohttp`, `requests`, `pydantic`, `python-dotenv`,
`datasets`, `sqlalchemy`, `fpdf2`.

**Optional components** (all self-guarding — the tool degrades gracefully if
missing):

- **Local models** — an [Ollama](https://ollama.com) server for the attacker/judge:
  ```bash
  ollama pull dolphin-llama3     # attacker (payload generation)
  ollama pull qwen2.5            # recommended judge (strong instruction-follower)
  ```
- **Advanced techniques** — `injection_techniques`, `technique_composer`,
  `superdata_bridge` (enables `--compose`, `techniques`, `compose`, `benchmark`).
- **Report bundle** — `report_generator` + `fpdf2` for the PDF/dossier.
- **PQC vault** — `pycryptodome` (AES) + `liboqs-python` (native ML-KEM). See
  [Reports & the PQC vault](#reports--the-pqc-vault).
- **Docker / VPN** — managed by `python main.py settings` (see below); nothing is
  installed until you ask for it.

---

## Quick start

**1. Offline self-test (no endpoint needed)** — build every technique over the
seed corpus in `data/`:

```bash
python main.py benchmark --use-seeds
```

**2. Chat with a model** — sanity-check your provider before an audit:

```bash
python main.py chat --provider ollama --model dolphin-llama3
```

**3. Smoke-test a target** endpoint:

```bash
python main.py probe --target-provider sse --base-url https://your-chat-host.example
```

**4. Live audit** — local Ollama attacker + judge against an SSE target:

```bash
python main.py run \
  --suite quick \
  --target-provider sse --base-url https://your-chat-host.example \
  --attacker-provider ollama --attacker-base-url http://localhost:11434 \
  --model dolphin-llama3 \
  --judge-provider ollama --judge-model qwen2.5 \
  --judge-samples 3 --judge-temperature 0.3
```

> **Note:** the attacker and judge default to `ATTACKER_PROVIDER` /
> `JUDGE_PROVIDER` from `PLACEHOLDER.env` (a per-role `--attacker-provider` /
> `--judge-provider` flag overrides them). Make sure the attacker resolves to a
> real generator — a named provider, or `ollama` for local `dolphin-llama3` — not
> `sse`, which has no model to generate payloads.

---

## Threat suites

Pick the surface with `--suite` (or the `ORF_SUITE` env var):

| Suite | Categories | Contents |
|-------|-----------|----------|
| **`quick`** *(default)* | 8 | A fast, representative subset spanning **both** surfaces below |
| `llm` | 8 | OWASP **LLM Top 10** (prompt injection, jailbreak, system-prompt leakage, sensitive-data disclosure, insecure output, excessive agency, insecure code gen, model DoS) |
| `agentic` | 15 | OWASP **ASI T1–T15** (memory poisoning, tool misuse, privilege compromise, goal manipulation, identity spoofing, RCE, multi-agent attacks, human manipulation, …) |
| `all` | 23 | `llm` + `agentic` |

`quick` runs full mutations on a curated subset (4 LLM + 4 agentic) — the fastest
way to touch both surfaces.

---

## Interactive chat

Besides the automated audit, ORF ships a plain **chatbot** for open questions. It
reuses the same three-provider stack, keeps a rolling conversation history, and
works either interactively or as a one-shot.

```bash
# Local Ollama (endpoint defaults to http://localhost:11434)
python main.py chat --provider ollama --model dolphin-llama3

# OpenAI-compatible endpoint
python main.py chat --provider openai --base-url https://host/v1 \
  --model gpt-4o-mini --api-key "$KEY"

# SSE chatbot (the same target you audit; the server keeps session state)
python main.py chat --provider sse --base-url https://your-chat-host.example \
  --target-cookie "$COOKIE"

# One-shot (prints the reply and exits — good for scripts/pipes)
python main.py chat --provider ollama --model dolphin-llama3 -m "Explain SSE in one line"
```

**Flags:** `--system "<prompt>"` sets the assistant's system prompt,
`--max-tokens N` caps each reply (Ollama/OpenAI), `--temperature T` controls
sampling. Connection flags (`--base-url`, `--model`, `--api-key`,
`--target-cookie`, …) are shared with `run`/`probe`.

**In-session commands:**

| Command | Effect |
|---------|--------|
| `/help` | List commands |
| `/exit`, `/quit`, `/q` | Leave the chat |
| `/reset` | Clear the conversation (keeps the system prompt) |
| `/system <text>` | Replace the system prompt and reset the conversation |
| `/history` | Print the conversation so far |
| `/save <path>` | Save the transcript to a JSON file |
| `/tokens <n>` | Change the max response tokens |
| `/temp <value>` | Change the sampling temperature |

---

## Settings: Docker & VPN

ORF can wrap a run in a hardened **Docker sandbox** and/or a **VPN tunnel**. Each
is a toggle with three modes, managed by `settings` and persisted to
`orf_settings.json` (git-ignored; env vars `ORF_DOCKER_MODE` / `ORF_VPN_MODE`
supply the defaults):

| Mode | Meaning |
|------|---------|
| `off` | Disabled — ORF ignores the feature (default). |
| `auto` | Detect and use it if present; degrade gracefully and continue if not. |
| `on` | Required — `run` refuses to start until the feature is satisfied. |

**VPN** follows *use what you have, else install WireGuard*: `auto`/`on` first
look for an existing VPN (an active WireGuard/OpenVPN/tun tunnel or the installed
tooling) and only fall back to **WireGuard** when none is found.

**Docker `on`** additionally brings up the sandbox from `docker-compose.yml`
(behind `--yes`). By default it starts only the supporting DB service
(`postgres-db`), not `redfront-engine` — which would re-run the whole audit
inside the container. Override the service list with `ORF_DOCKER_COMPOSE_SERVICES`
or `--services`.

```bash
# Show current settings + live detection (Docker daemon, compose, VPN tunnels)
python main.py settings

# Turn features on/off/auto (persists to orf_settings.json)
python main.py settings --docker auto
python main.py settings --vpn on

# Install (prints the exact OS command by default; --yes actually runs it)
python main.py settings --install-docker
python main.py settings --install-vpn --yes

# Bring the Docker sandbox up / down (dry-run without --yes)
python main.py settings --compose-up --yes                 # default: postgres-db
python main.py settings --compose-up --services all --yes  # whole stack
python main.py settings --compose-down --yes

# Preview the enable/detect logic that `run` will perform
python main.py settings --apply
```

At startup, `run` and `chat` apply the saved modes: `run` **hard-fails** if an
`on` feature is unmet (pass `--yes` to auto-install / bring up the sandbox, or
`--no-settings` to skip the check); `chat` treats them as best-effort and never
blocks. Installing system software needs admin rights and is never auto-run
without `--yes`.

`settings` (with no action flags) also reports the **active model providers**
(attacker / judge / target, and which named-provider keys are present), and can
**persist a provider default** that overrides `PLACEHOLDER.env`:

```bash
python main.py settings                          # status incl. providers + key presence
python main.py settings --attacker-provider groq # persist attacker default
python main.py settings --judge-provider google  # persist judge default
python main.py settings --attacker-provider clear # revert to the env default
```

Precedence: a per-run `--attacker-provider`/`--judge-provider` flag > the value
persisted here > `PLACEHOLDER.env` > built-in default.

---

## Test memory & self-learning

Every audit result (one category test) is stored in a persistent SQLite memory
(`orf_memory.db`; override with `ORF_MEMORY_DB`) that survives across runs. On the
next run, ORF reads that memory and folds a compact **"reflection on prior
attempts"** block into the attacker's payload-generation prompt for each category
— which techniques already scored **VULNERABLE** (reuse and escalate) and which
came back **COMPLIANT** (don't just repeat them). This is a closed self-learning
loop: the tool stops re-trying dead ends and builds on what worked. The judge is
unaffected — feedback only steers payload generation.

Modes (flag `--memory` on `run`, or `ORF_MEMORY_MODE`):

| Mode | Meaning |
|------|---------|
| `learn` | Store each test **and** feed prior results back into generation (default). |
| `record` | Store each test, but don't use it as feedback. |
| `off` | Don't store or use memory (`--no-memory` is an alias). |

Recording and feedback are wrapped so memory can never crash a run.

**Inspect and remove** stored tests with the `memory` subcommand:

```bash
python main.py memory                       # status: DB path, totals, top categories
python main.py memory list                  # recent tests (filter: --category/--status/--target/--before/--limit)
python main.py memory show --id 12          # full record incl. payload + response
python main.py memory stats                 # breach rate per category and per technique
python main.py memory export --output m.json

# Removal (you stay in control of what's remembered)
python main.py memory remove --id 12
python main.py memory remove --category DIRECT_JAILBREAK_AND_EVASION
python main.py memory remove --status COMPLIANT
python main.py memory remove --before 2026-01-01
python main.py memory remove --all --yes    # wipe everything (--yes required)
```

Disable it for a single run with `python main.py run ... --no-memory`.

---

## Configuration

Settings come from CLI flags, environment variables, or a **`PLACEHOLDER.env`**
file in the project root (loaded automatically). CLI flags win over env vars.

```env
# --- Attacker (local Ollama that generates payloads) ---
ATTACKER_PROVIDER=ollama
ATTACKER_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=dolphin-llama3

# --- Target (system under test) ---
TARGET_PROVIDER=sse
TARGET_BASE_URL=https://your-chat-host.example
TARGET_API_KEY=            # optional Bearer token
TARGET_COOKIE=             # optional Cookie header

# --- Judge (local model that decides the verdict) ---
JUDGE_PROVIDER=ollama      # default: follows the attacker
JUDGE_MODEL=qwen2.5        # default: the attacker model
JUDGE_BASE_URL=http://localhost:11434
JUDGE_SAMPLES=3            # self-consistency votes (1 = single pass)
JUDGE_TEMPERATURE=0.3      # per-sample temperature (>0 needed if SAMPLES>1)
JUDGE_FEWSHOT=true         # few-shot exemplars in the judge prompt

# --- Suite / behavior ---
ORF_SUITE=quick            # quick | llm | agentic | all
ORF_COMPOSE_MODE=off       # off | auto | manual  (multi-technique composition)

# --- Environment (Docker / VPN) ---
ORF_DOCKER_MODE=off        # off | on | auto
ORF_VPN_MODE=off           # off | on | auto
# ORF_DOCKER_COMPOSE_SERVICES=postgres-db   # services brought up by docker=on

# --- Optional GitHub issue sync ---
GITHUB_ACCESS_TOKEN=
GITHUB_TARGET_REPOSITORY=your-org/your-repo

# --- Misc ---
DATABASE_URL=sqlite:///:memory:
# Native liboqs auto-build is skipped when no C toolchain (git+cmake) and no
# prebuilt liboqs are present; set to 1 to force-disable PQC.
ORF_DISABLE_PQC=
```

---

## CLI reference

```
python main.py <subcommand> [flags]
```

| Subcommand | Purpose |
|------------|---------|
| `run` | Run the full red-team pipeline against the configured target |
| `chat` | Interactive chatbot for open questions (Ollama / OpenAI-compatible / SSE) |
| `settings` | View/change Docker & VPN enablement (auto/on/off), install them, control the sandbox |
| `memory` | Inspect / remove the persistent test memory that powers self-learning |
| `probe` | Connectivity smoke-test (SSE / OpenAI-compatible / file-upload) |
| `techniques` | List the technique catalog (encoding / structural / framing / multi-turn) |
| `compose` | Dry-run the composer on a sample payload (offline preview) |
| `benchmark` | Offline coverage benchmark of every technique + combos |
| `keygen` | Generate a PQC keypair |
| `armor` | Encrypt a JSON report with the PQC public key |
| `unlock` | Decrypt a PQC package with the private key |

**Key `run` / `probe` / `chat` flags:**

| Flag | Meaning |
|------|---------|
| `--suite {quick,llm,agentic,all}` | Threat suite (default `quick`) |
| `--provider {openai,ollama,sse}` | Default provider when role providers are unset |
| `--attacker-provider / --target-provider` | Per-role provider override |
| `--model` / `--secondary-model` | Attacker model / target logical name |
| `--attacker-base-url` / `--target-base-url` / `--base-url` | Endpoints |
| `--target-api-key` / `--target-cookie` | Target auth |
| `--judge-provider / --judge-model / --judge-base-url / --judge-api-key` | Judge endpoint |
| `--judge-samples N` / `--judge-temperature T` / `--judge-no-fewshot` | Judge quality controls |
| `--indirect-mode {direct,file_upload}` | Indirect prompt injection via file upload |
| `--file-attach-mode {body_field,session,query_ref}` / `--obfuscation` | Upload delivery / obfuscation corpus |
| `--compose {off,auto,manual}` / `--injection-techniques` | Multi-technique composition |
| `--agentic-intel` | Let the attacker query the Superdata bridge mid-generation |
| `--temperature` / `--repetition-penalty` | OpenAI-compatible sampling controls |
| `--no-settings` / `--yes` | Skip the Docker/VPN check / allow auto-install (`run`, `chat`) |
| `--memory {off,record,learn}` / `--no-memory` | `run`: test-memory mode for this run |
| `--system` / `-m,--message` / `--max-tokens` | `chat`: system prompt / one-shot / reply cap |

Run `python main.py <subcommand> --help` for the full list.

---

## The LLM judge

Every verdict is produced by the judge model — no keyword matching. Because the
judge can run **locally (no API tokens)**, ORF spends compute rather than money to
raise accuracy on weak local models:

- **Few-shot exemplars** (`JUDGE_FEWSHOT`, default on) — labeled VULNERABLE/COMPLIANT
  examples anchor the decision boundary (including negation, e.g. *"I will not
  grant admin"* → COMPLIANT) and the strict-JSON output format.
- **Self-consistency voting** (`JUDGE_SAMPLES`, default 3) — the judge is sampled
  N times at `JUDGE_TEMPERATURE` and the **majority wins**; a tie resolves to
  COMPLIANT. `vote_ratio` reports the real tally (e.g. `2/3`).

**Choosing a judge model:** a more capable model gives better *accuracy*, not just
more verbose output. Prefer a strong instruction-tuned model (e.g. `qwen2.5`) over
the uncensored attacker model.

- **Strong judge:** `--judge-samples 1 --judge-temperature 0` (accurate *and* fast).
- **Weak/small judge:** keep `--judge-samples 3 --judge-temperature 0.3`.

---

## Reports & the PQC vault

As categories finish, findings are written incrementally to `secure_vault/`:

- **JSON** report of all findings (verdict, confidence, OWASP/MITRE mapping,
  per-turn trace) — including, for **every** finding, both the
  `original_payload` (the raw attacker query before weaponization) and
  `full_payloads` (the exact payload[s] dispatched to the target), plus the
  target's response in `exploit_proof`.
- **PDF** assessment + a verbatim **payload dossier** (when `report_generator` +
  `fpdf2` are available). Both cover **every** category, not just breaches: the
  PDF has a *Confirmed breaches* section and a *Defended attempts (compliant)*
  section, and the dossier reproduces the original + complete payloads verbatim
  for both. This means a COMPLIANT category still records exactly what was sent
  and how the target refused it — useful for regression and tuning.
- Optional **GitHub issues** for each confirmed breach (set `GITHUB_ACCESS_TOKEN`
  + `GITHUB_TARGET_REPOSITORY`).

### Post-quantum encryption (optional)

The vault can hybrid-encrypt reports with **ML-KEM-768 (Kyber) + AES-GCM**. This is
**dormant unless two conditions are met**:

1. Native **liboqs** is installed (`pip install liboqs-python` — needs a C
   toolchain: CMake + compiler; easiest on Linux/Colab, and it auto-builds the
   native library on first import). If absent, the tool safely writes **plaintext**
   reports instead. To keep startup fast the auto-build is **skipped entirely**
   when no prebuilt liboqs is found and `cmake`/`git` are not on `PATH` (so an
   offline host never hangs or aborts at import); force it off anywhere with
   `ORF_DISABLE_PQC=1`.
2. A keypair exists at **`/workspace/audit_authority.pub`** — the exact path the
   pipeline checks. Generate it explicitly:
   ```bash
   python main.py keygen --pub /workspace/audit_authority.pub \
                         --key /workspace/audit_authority.key
   ```

With both in place, `run` writes `SECURE_REPORT_*.pqc.json`. Verify a full
round-trip any time:

```bash
python main.py armor  --input report.json --pub audit_authority.pub --output report.pqc.json
python main.py unlock --input report.pqc.json --key audit_authority.key --output restored.json
```

> Set `ORF_DISABLE_PQC=1` to skip the native liboqs import entirely (avoids the
> auto-build attempt in offline/CI environments).

---

## One-cell Colab runner

`colab/ORF_OneCell_Runner.ipynb` runs the whole thing from a **single cell**:
provide a project `.zip` (Drive path / upload), and it unzips, installs, optionally
activates PQC, and executes — streaming logs and listing report artifacts.

Top-of-cell toggles:

- `MODE` — `"benchmark"` (offline, default) or `"run"` (live audit).
- `SETUP_PQC` — **Colab/Linux only**: builds native liboqs, generates the keypair,
  and runs a verified self-test that prints `✅ PQC ACTIVE`. Safe no-op elsewhere.
- `SUITE`, target URL/cookie, attacker model, and the judge settings.

---

## Project layout

```
main.py                     # CLI + pipeline orchestration + role dispatch + judge + chat
orf_settings.py             # Docker/VPN enablement (auto/on/off), install helpers, compose control
orf_memory.py               # persistent test memory + self-learning feedback for payload generation
deterministic_assertions.py # payload delivery framing, canary tokens, (legacy detectors)
injection_techniques.py     # technique primitives (encoding/structural/framing/multi-turn)
technique_composer.py       # multi-technique composition + catalog
obfuscation.py              # obfuscated document variants for file-upload injection
superdata_bridge.py         # agentic white-box intel (Superdata Extractor bridge)
report_generator.py         # branded PDF + verbatim payload dossier
docker-compose.yml          # hardened sandbox: postgres-db + redfront-engine
Dockerfile                  # zero-trust Python runtime image
requirements.txt
vvs_test.py                 # VVS adversarial test harness (smoke / k+ / attack-a..d / boundary)
report-template.py          # standalone branded PDF sample generator
data/                       # seed CSV corpora (local; not committed)
input_src/target_agent/     # white-box target surface (local; not committed)
secure_vault/               # generated reports (JSON / PDF / dossier / .pqc.json)
colab/ORF_OneCell_Runner.ipynb
COOKBOOK.md                 # task-oriented recipes
VERIFICATION_v4.0.0.md      # verification report (offline self-test evidence)
```

See **[COOKBOOK.md](COOKBOOK.md)** for copy-paste recipes covering the common
workflows end to end.
