# ORF Cookbook — v4.0.0

Copy-paste recipes for common ORF workflows. Each recipe is self-contained; adjust
the endpoints, models, and tokens for your environment. See
[README.md](README.md) for the full reference.

> **Authorized use only.** Run audits exclusively against systems you own or are
> explicitly authorized to test.

**Contents**

- [0. First-time setup](#0-first-time-setup)
- [1. Chat with a model](#1-chat-with-a-model)
- [2. Probe a target before auditing](#2-probe-a-target-before-auditing)
- [3. Run an audit](#3-run-an-audit)
- [4. Tune the judge](#4-tune-the-judge)
- [5. Advanced payload techniques](#5-advanced-payload-techniques)
- [6. Indirect injection via file upload](#6-indirect-injection-via-file-upload)
- [7. Docker sandbox & VPN](#7-docker-sandbox--vpn)
- [8. Test memory & self-learning](#8-test-memory--self-learning)
- [9. Reports & the PQC vault](#9-reports--the-pqc-vault)
- [10. Offline work (no endpoint)](#10-offline-work-no-endpoint)
- [11. Troubleshooting](#11-troubleshooting)

---

## 0. First-time setup

Install dependencies and (optionally) pull local models:

```bash
pip install -r requirements.txt

# Optional local models for the attacker + judge
ollama pull dolphin-llama3     # attacker (payload generation)
ollama pull qwen2.5            # judge (strong instruction-follower)
```

Create your local config from the template and fill in real values:

```bash
cp PLACEHOLDER.env .env     # or edit PLACEHOLDER.env directly (both are git-ignored)
```

Sanity-check everything is wired without touching a target:

```bash
python main.py benchmark --use-seeds        # offline technique coverage
python main.py chat --provider ollama --model dolphin-llama3 -m "say hi"
```

---

## 1. Chat with a model

**Interactive REPL** (local Ollama):

```bash
python main.py chat --provider ollama --model dolphin-llama3
```

Inside the chat: `/help`, `/reset`, `/system <text>`, `/save transcript.json`,
`/tokens 2048`, `/temp 0.7`, `/exit`.

**OpenAI-compatible endpoint:**

```bash
python main.py chat --provider openai --base-url https://host/v1 \
  --model gpt-4o-mini --api-key "$KEY" --system "You are a terse expert."
```

**SSE chatbot** (the same target you audit; server keeps the session):

```bash
python main.py chat --provider sse --base-url https://your-chat-host.example \
  --target-cookie "$COOKIE"
```

**One-shot / scripting** (prints the reply and exits):

```bash
answer=$(python main.py chat --provider ollama --model dolphin-llama3 \
  -m "Summarize OWASP LLM01 in one sentence")
echo "$answer"
```

---

## 2. Probe a target before auditing

Confirm connectivity and auth first — cheaper than a failed run:

```bash
# SSE chatbot
python main.py probe --target-provider sse \
  --base-url https://your-chat-host.example \
  --target-cookie "$COOKIE"

# OpenAI-compatible
python main.py probe --target-provider openai \
  --base-url https://host/v1 --model gpt-4o-mini --target-api-key "$KEY"
```

Find the right file-upload attach mode for indirect injection:

```bash
python main.py probe --target-provider sse \
  --base-url https://your-chat-host.example \
  --indirect-mode file_upload --file-attach-mode session
```

---

## 3. Run an audit

**Standard run** — local Ollama attacker + judge against an SSE target:

```bash
python main.py run \
  --suite quick \
  --target-provider sse --base-url https://your-chat-host.example \
  --target-cookie "$COOKIE" \
  --attacker-provider ollama --attacker-base-url http://localhost:11434 \
  --model dolphin-llama3 \
  --judge-provider ollama --judge-model qwen2.5 \
  --judge-samples 3 --judge-temperature 0.3
```

**Pick the surface** with `--suite`:

```bash
python main.py run --suite llm      ...   # OWASP LLM Top 10 (8)
python main.py run --suite agentic  ...   # OWASP ASI T1–T15 (15)
python main.py run --suite all      ...   # everything (23)
```

**Audit an OpenAI-compatible target** instead of SSE:

```bash
python main.py run --suite quick \
  --target-provider openai --target-base-url https://host/v1 \
  --secondary-model gpt-4o-mini --target-api-key "$KEY" \
  --attacker-provider ollama --attacker-base-url http://localhost:11434 \
  --model dolphin-llama3
```

> Always set `--attacker-provider ollama` explicitly. Otherwise the attacker/judge
> inherit the default `sse` provider and have no local model to generate or judge.

**Use hosted named providers** (keys/models come from `PLACEHOLDER.env`):

```bash
# Mix providers per role — no base URLs to retype:
python main.py run --suite quick \
  --attacker-provider nvidia \
  --judge-provider google \
  --target-provider sse --base-url https://your-chat-host.example --target-cookie "$COOKIE"

# Or chat/probe against one directly:
python main.py chat  --provider groq
python main.py probe --provider openrouter --prompt "ping"
```

Named providers: `nvidia | google | groq | openrouter | siliconflow | cloudflare
| featherless | deepinfra | together | deepseek | mistral | fireworks |
perplexity | xai | cerebras | novita | hyperbolic | ollamacloud | custom`
(all OpenAI-compatible; `custom` needs `CUSTOM_BASE_URL`). Override a provider's
model with `--model` (attacker) / `--secondary-model` (target) / `--judge-model`.

---

## 4. Tune the judge

Verdicts come only from the judge model. Trade accuracy vs. speed:

```bash
# Strong judge (e.g. qwen2.5): single deterministic pass — accurate and fast
python main.py run ... --judge-model qwen2.5 --judge-samples 1 --judge-temperature 0

# Weak/small judge: self-consistency voting (majority of N)
python main.py run ... --judge-samples 5 --judge-temperature 0.3

# Disable few-shot exemplars (rarely needed)
python main.py run ... --judge-no-fewshot
```

Point the judge at a **different endpoint** from the attacker:

```bash
python main.py run ... \
  --judge-provider openai --judge-base-url https://host/v1 \
  --judge-model gpt-4o-mini --judge-api-key "$KEY"
```

---

## 5. Advanced payload techniques

List the technique catalog:

```bash
python main.py techniques
```

Preview how a payload gets composed (offline, no target):

```bash
python main.py compose --surface EXCESSIVE_AGENCY --compose auto
python main.py compose --compose manual \
  --injection-techniques base64,image_markdown_zero_click,cot_manipulation,memory_poisoning
```

Run an audit with composition enabled:

```bash
# Surface-aware auto composition
python main.py run ... --compose auto

# Manual technique stack + let the attacker query extracted target intel
python main.py run ... --compose manual \
  --injection-techniques base64,payload_splitting,crescendo \
  --agentic-intel
```

---

## 6. Indirect injection via file upload

Deliver the payload as an uploaded document, then attach it to a benign turn:

```bash
python main.py run --suite quick \
  --target-provider sse --base-url https://your-chat-host.example \
  --target-cookie "$COOKIE" \
  --indirect-mode file_upload \
  --target-file-upload-url https://your-chat-host.example/api/file/upload?type=chat \
  --file-attach-mode body_field --file-attach-field file_ids \
  --obfuscation all \
  --attacker-provider ollama --model dolphin-llama3
```

Tune the injected document's obfuscation corpus with `--obfuscation` (comma list
or `all`); `probe --indirect-mode file_upload` helps you find the attach mode a
given deployment accepts.

---

## 7. Docker sandbox & VPN

Check what ORF detects on this host:

```bash
python main.py settings
```

**Enable a VPN** — use an existing tunnel if present, else install WireGuard:

```bash
python main.py settings --vpn auto            # best-effort; degrade if absent
python main.py settings --vpn on              # required for `run`
python main.py settings --install-vpn         # print the OS install command
python main.py settings --install-vpn --yes   # actually install WireGuard
```

**Enable the Docker sandbox:**

```bash
python main.py settings --docker on
python main.py settings --install-docker --yes    # install Docker if missing

# Bring the sandbox up / down (dry-run without --yes)
python main.py settings --compose-up --yes                 # default: postgres-db
python main.py settings --compose-up --services all --yes  # whole stack
python main.py settings --compose-down --yes
```

**How modes affect a run:**

```bash
# docker=on / vpn=on are enforced: run hard-fails if unmet
python main.py run ...                 # exits early with guidance if a feature is missing
python main.py run ... --yes           # allow auto-install + `docker compose up`
python main.py run ... --no-settings   # skip the environment check entirely
```

`chat` applies the same modes but never blocks (best-effort). Settings persist to
`orf_settings.json`; `ORF_DOCKER_MODE` / `ORF_VPN_MODE` set the defaults.

**Providers via settings** — see active providers and persist a default without
editing the env:

```bash
python main.py settings                            # status shows attacker/judge/target + which keys are set
python main.py settings --attacker-provider groq   # persist (overrides PLACEHOLDER.env)
python main.py settings --judge-provider google
python main.py settings --attacker-provider clear  # revert to the env default
```

Precedence: per-run flag > persisted setting > `PLACEHOLDER.env` > default.

---

## 8. Test memory & self-learning

ORF remembers every test across runs and feeds prior outcomes back into payload
generation. It is **on by default** (`ORF_MEMORY_MODE=learn`).

```bash
# Default run already records + learns. Control it per run:
python main.py run ... --memory learn      # store + feed back (default)
python main.py run ... --memory record     # store only, no feedback
python main.py run ... --no-memory         # neither (equivalent to --memory off)
```

How the loop works: for each category, ORF injects a "reflection on prior
attempts" block into the attacker prompt — winning techniques to escalate and
failed ones to avoid — so successive runs get sharper instead of starting cold.

Inspect what it has learned:

```bash
python main.py memory                       # summary: totals + top categories
python main.py memory list --status VULNERABLE
python main.py memory list --category DIRECT_JAILBREAK_AND_EVASION --limit 20
python main.py memory show --id 42          # full record (payload + response)
python main.py memory stats                 # breach rate per category & technique
python main.py memory export --output memory_snapshot.json
```

Remove entries (you decide what is remembered):

```bash
python main.py memory remove --id 42
python main.py memory remove --category MODEL_DENIAL_OF_SERVICE
python main.py memory remove --status COMPLIANT      # forget the failures
python main.py memory remove --before 2026-01-01
python main.py memory remove --all --yes             # wipe everything
```

The store is `orf_memory.db` (SQLite) next to `main.py`; point it elsewhere with
`ORF_MEMORY_DB=/path/to/memory.db` (e.g. a separate memory per target).

---

## 9. Reports & the PQC vault

Reports land in `secure_vault/` as they are produced (JSON always; PDF + dossier
when `fpdf2` is available).

Every finding — **VULNERABLE and COMPLIANT alike** — records the `original_payload`
(raw attacker query pre-weaponization), the `full_payloads` actually dispatched,
and the target's `exploit_proof` response. Inspect them:

```bash
# JSON: every finding with original + complete payloads
python -c "import json;print(json.dumps(json.load(open('secure_vault/REPORT_<session>.json'))[0],indent=2))"

# Dossier (verbatim, full UTF-8): both breaches and defended attempts
cat secure_vault/PAYLOADS_<session>.md
```

The PDF (`VULN_REPORT_<session>.pdf`) has a *Confirmed breaches* section and a
*Defended attempts (compliant)* section — so a refused category still shows
exactly what was sent and how the target declined it.

Enable post-quantum encryption (Linux/Colab is easiest):

```bash
pip install liboqs-python pycryptodome

python main.py keygen \
  --pub /workspace/audit_authority.pub \
  --key /workspace/audit_authority.key

# With the keypair + native liboqs present, `run` writes SECURE_REPORT_*.pqc.json
```

Verify an encrypt/decrypt round-trip:

```bash
python main.py armor  --input report.json --pub audit_authority.pub --output report.pqc.json
python main.py unlock --input report.pqc.json --key audit_authority.key --output restored.json
```

File confirmed breaches as GitHub issues by setting `GITHUB_ACCESS_TOKEN` and
`GITHUB_TARGET_REPOSITORY` (env or `PLACEHOLDER.env`).

---

## 10. Offline work (no endpoint)

Everything below runs without a network target:

```bash
python main.py benchmark --use-seeds           # coverage over the local CSV corpus
python main.py benchmark --use-seeds --json    # machine-readable coverage report
python main.py techniques                       # list the technique catalog
python main.py compose --surface INDIRECT_PROMPT_INJECTION --compose auto
```

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `advanced technique modules unavailable` | Install the optional modules; `techniques`/`compose`/`benchmark` need `injection_techniques`, `technique_composer`, `superdata_bridge`. |
| Attacker/judge produce nothing | You left the provider as `sse`. Pass `--attacker-provider ollama --attacker-base-url http://localhost:11434`. |
| `Cannot connect to host localhost:11434` | Ollama isn't running / model not pulled. Start Ollama and `ollama pull <model>`. |
| SSE target returns empty replies | Check `--target-cookie` / `--target-api-key`; confirm with `probe` first. |
| `run` exits with a settings error | A `docker`/`vpn` mode is `on` but unmet. Pass `--yes`, set the mode to `auto`/`off`, or use `--no-settings`. |
| Docker "daemon is not running" | Start Docker Desktop / the engine, then retry `--compose-up --yes`. |
| PQC writes plaintext instead of `.pqc.json` | `liboqs-python` isn't installed or the keypair isn't at `/workspace/audit_authority.pub`. See recipe 8. Set `ORF_DISABLE_PQC=1` to skip PQC entirely. |
| Offensive banner is noisy | It is suppressed for `chat`, `settings`, `memory`, and any `--help`; it prints to stderr for the other modes. |
| Memory not accumulating | Check `python main.py memory` (DB path + totals). Runs with `--no-memory` / `ORF_MEMORY_MODE=off` don't record. |
| Want a clean-slate run | `python main.py run ... --no-memory`, or `python main.py memory remove --all --yes` first. |
