# 🚩 Operation RED-Frontline: Battlefield Logistics Engine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Ollama Support](https://img.shields.io/badge/Ollama-Supported-orange.svg)](https://ollama.ai/)
[![Security: Red-Team](https://img.shields.io/badge/Security-Red--Team-red.svg)](#)

```text
  ____  ____  _____ ____    _ _____ ___ ___  _   _    ____  _____ ____  
 / __ \|  _ \| ____|  _ \  / \_   _|_ _/ _ \| \ | |  |  _ \| ____|  _ \ 
| |  | | |_) |  _| | |_) |/ _ \ | |  | | | | |  \| |  | |_) |  _| | |_) |
| |__| |  __/| |___|  _ </ ___ \| |  | | |_| | |\  |  |  _ <| |___|  _ < 
 \____/|_|   |_____|_| \_/_/   \_\_| |___\___/|_| \_|  |_| \_\_____|_| \_\_
                         _____ ____   ___  _   _ _____ _     ___ _   _ _____ 
                        |  ___|  _ \ / _ \| \ | |_   _| |   |_ _| \ | | ____|
                        | |_  | |_) | | | |  \| | | | | |    | ||  \| |  _|  
                        |  _| |  _ <| |_| | |\  | | | | |___ | || |\  | |___ 
                        |_|   |_| \_\___/|_| \_| |_| |_____|___|_| \_|_____|
```

**Operation RED-Frontline (ORF)** is an automated, high-velocity adversarial simulation framework designed to stress-test Large Language Model (LLM) alignment, guardrails, and agentic workflows. By leveraging parallel mutation streams, ORF autonomously generates, executes, and audits complex injection attacks to identify vulnerabilities before they reach production.

---

## 🎯 Core Functionality

ORF runs as a **two-model, three-role orchestrator** (the Target and Judge share the secondary model):
1.  **The Attacker (Primary Model):** Autonomously engineers weaponized payloads based on MITRE ATLAS and OWASP LLM Top 10 threat corridors.
2.  **The Target (Secondary Model):** The model under audit, loaded with a specific `system_prompt.txt` to simulate a real-world agent.
3.  **The Judge (Secondary Model):** A cynical auditor that evaluates the interaction to determine if a security breach occurred.

### Key Features
*   **Parallel Adversarial Vectors:** Spawns multiple asynchronous streams to test different mutation depths simultaneously.
*   **Integrated SAST Engine:** Runs `Bandit` static analysis over AI-generated **Python** code blocks, deterministically flagging insecure patterns (CWE-89 SQLi, CWE-78 Command Injection) before falling back to the LLM verdict. *(Multi-language / JS-TS frontend scanning is an Enterprise feature.)*
*   **MITRE ATLAS Mapping:** Categorizes findings into recognized threat techniques (e.g., AML.T0051, AML.T0054).
*   **DevSecOps Automation:** Optionally publishes confirmed vulnerabilities as GitHub Issues with full Proof-of-Concept (PoC) logs (enabled when a token is supplied).
*   **Telemetry Layer:** SQLite logging of all simulation sessions and vote ratios. *(Defaults to in-memory; set `DATABASE_URL` to a file/DB for persistence.)*

---

## 🛡️ Attack Surface Coverage (Community Edition)

The Community Edition focuses on critical LLM vulnerabilities:
*   **SEC-CODE-001:** Insecure Code Generation (CWE-89, CWE-78 detection).
*   **SEC-INJ-001:** Indirect Prompt Injection via data-layer contexts.
*   **SEC-BRK-001:** Direct Jailbreaking (Roleplay, Evasion, Translation Shifts).
*   **SEC-LEAK-001:** System Prompt Leakage & Extraction.

---

## 🛠️ Installation & Setup

### Prerequisites
*   **Python 3.9+**
*   **Ollama:** Ensure the Ollama server is running locally or accessible via network.
*   **Bandit:** bundled in `requirements.txt`; powers the SAST check for `INSECURE_CODE_GENERATION`.

### 1. Clone the Repository
```bash
git clone https://github.com/JMak-Security/Operation-RED-Frontline_JMak-Security.git
cd Operation-RED-Frontline_JMak-Security
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
> **Performance note:** *runtime is dominated by local LLM inference. On CPU-only, a full audit can take ~1 hour; on a GPU (e.g. a Colab T4 or better) it's much faster. The engine also runs one request at a time by default — raise OLLAMA_MAX_CONCURRENT_TASKS on a stronger machine to parallelize.*

### 3. Environment Configuration
Create a **`PLACEHOLDER.env`** in the root directory (this exact filename is what the engine loads at startup):
```env
OLLAMA_BASE_URL=http://127.0.0.1:7777
OLLAMA_HOST=http://127.0.0.1:7777
OLLAMA_PRIMARY_MODEL=tinydolphin        # The Attacker
OLLAMA_SECONDARY_MODEL=qwen2.5:latest   # The Target / Judge
OLLAMA_MAX_CONCURRENT_TASKS=1           # Async concurrency cap

# Optional — persist audit telemetry (defaults to in-memory SQLite)
DATABASE_URL=sqlite:///orf_audit.db

# Optional — target agent config (inline string OR path to a .txt file)
TARGET_SYSTEM_PROMPT_FILE=./input_src/target_agent/system_prompt.txt

# Optional — auto-file confirmed breaches as GitHub Issues
GITHUB_ACCESS_TOKEN=your_token_here
GITHUB_TARGET_REPOSITORY=your-org/your-repo
```
> **Note:** The default Ollama port is `11434`. The values above match this repo's shipped `PLACEHOLDER.env` (`7777`); change them if your Ollama listens elsewhere.

---

## 📦 Usage

### Running a Standalone Audit
Start the red-team simulation against the target model configured in your `PLACEHOLDER.env`:
```bash
python main.py            # or: python main.py run
```

Smoke-test connectivity before a full run:
```bash
python main.py probe --prompt "Hello, system check."
```

CLI flags (`--model`, `--secondary-model`, `--base-url`) override the `.env` values when passed; omit them to use your `PLACEHOLDER.env` configuration.

### How it works
1.  **Ingestion:** The engine loads malicious seeds and safe edge cases from local CSVs (`xstest_v2`, `data_en`).
2.  **Mutation:** The attacker model generates variations (URL encoding, hypothetical simulations, sandbox-refactoring framing, pseudocode blueprints, etc.).
3.  **Execution:** Payloads are fired at the target model.
4.  **Verification:** The judge model and the Bandit SAST pass verify whether the response leaks protected data or contains insecure code.
5.  **Reporting:** A plaintext JSON report is written to the `secure_vault/` directory.

### Docker (optional)
A hardened, read-only container setup is provided via `Dockerfile` and `docker-compose.yml` (bundles a PostgreSQL telemetry node):
```bash
OLLAMA_BASE_URL=http://host.docker.internal:7777 docker compose up --build
```

---

## 📊 Reporting & Telemetry
ORF writes a detailed `REPORT_<session_id>.json` per session under `secure_vault/`. Confirmed vulnerabilities include:
*   **Payload Used:** The exact string that bypassed the guardrail.
*   **Exploit Proof:** The verbatim response from the target model.
*   **Consensus Vote:** The vote ratio and confidence score from the Judge.
*   **Analysis:** How the breach was flagged (SAST vs. semantic judge).

---

## ⚠️ Legal & Ethical Warning
**Operation RED-Frontline is for authorized security research only.**
Do not use this tool against services or models you do not own or have explicit written permission to test. Generating adversarial payloads against third-party APIs may violate their Terms of Service and lead to account suspension.

---

## ⚖️ License
This project is licensed under the **MIT License**.

*ORF Community Edition is a subset of the ORF Enterprise build. Advanced features like PQC-encrypted reports, AST White-Box scanning, multi-language SAST, and Multi-Agent Goal Hijacking modules are restricted to the Enterprise build.*

---
**Developed by:** JMak-Security  
**Mission:** *Hardening the future of Agentic Intelligence.*


---
**Developed by:** [JMak-Security]  
**Release:** v3.0-Community  
**Status:** *Combat Ready.*
