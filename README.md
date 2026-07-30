# 🚩 Operation RED-Frontline: Battlefield Logistics Engine v3.0

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

## 🚀 Core Functionality

ORF operates as a **dual-model orchestrator**:
1.  **The Attacker (Primary Model):** Autonomously engineers weaponized payloads based on MITRE ATLAS and OWASP LLM Top 10 threat corridors.
2.  **The Target (Secondary Model):** The model under audit, loaded with a specific `system_prompt.txt` to simulate a real-world agent.
3.  **The Judge (Consensus Node):** A cynical auditor model that evaluates the interaction to determine if a security breach occurred.

### Key Features
*   **Parallel Adversarial Vectors:** Spawns multiple asynchronous streams to test different mutation depths simultaneously.
*   **Integrated SAST Engine:** Uses `Bandit` to perform Static Analysis Security Testing on AI-generated code blocks to detect SQLi, XSS, and RCE.
*   **MITRE ATLAS Mapping:** Categorizes findings into recognized threat techniques (e.g., AML.T0051, AML.T0054).
*   **DevSecOps Automation:** Automatically publishes confirmed vulnerabilities as GitHub Issues with full Proof-of-Concept (PoC) logs.
*   **Telemetry Layer:** Persistent SQLite logging for auditing all simulation sessions and vote ratios.

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
*   **Bandit:** `pip install bandit` (required for code scanning).

### 1. Clone the Repository
```bash
git clone https://github.com/JMak-Security/Operation-RED-Frontline_JMak-Security.git
cd Operation-RED-Frontline_JMak-Security
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=llama3.2:latest   # The Attacker
OLLAMA_SECONDARY_MODEL=qwen2.5:latest  # The Target / Judge
GITHUB_ACCESS_TOKEN=your_token_here
GITHUB_TARGET_REPOSITORY=your-org/your-repo
TARGET_SYSTEM_PROMPT_FILE=./input_src/target_agent/system_prompt.txt
```

---

## 🚦 Usage

### Running a Standalone Audit
To start the red-team simulation against the target model configured in your `.env`:
```bash
python main.py
```

### How it works:
1.  **Ingestion:** The engine loads malicious seeds and safe edge cases from local CSVs (`xstest_v2`, `data_en`).
2.  **Mutation:** The attacker model generates variations (Base64 encoding, Hypothetical Simulations, etc.).
3.  **Execution:** Payloads are fired at the target model.
4.  **Verification:** The judge model and the SAST engine verify if the response contains sensitive data or insecure code.
5.  **Reporting:** A plaintext JSON report is generated in the `secure_vault/` directory.

---

## 📊 Reporting & Telemetry
ORF generates a detailed audit log for every session. Confirmed vulnerabilities include:
*   **Payload Used:** The exact string that bypassed the guardrail.
*   **Exploit Proof:** The verbatim response from the target model.
*   **Consensus Vote:** The confidence score from the Judge model.
*   **SAST Details:** Specific CWE patterns found in generated code.

---

## ⚠️ Legal & Ethical Warning
**Operation RED-Frontline is for authorized security research only.** 
Do not use this tool against services or models you do not own or have explicit written permission to test. Generating adversarial payloads against third-party APIs may violate their Terms of Service and lead to account suspension.

---

## ⚖️ License
This project is licensed under the **MIT License**.

*ORF Community Edition is a subset of the ORF Enterprise build. Advanced features like PQC-encrypted reports, AST White-Box scanning, and Multi-Agent Goal Hijacking modules are restricted to the Enterprise build.*

---
**Developed by:** JMak-Security  
**Mission:** *Hardening the future of Agentic Intelligence.*
