# Superdata Extractor — Full Guidebook

Complete step-by-step instructions to run Superdata Extractor perfectly on your local machine using **Ollama**.

---

## Table of Contents

1. [What This Tool Does](#1-what-this-tool-does)
2. [System Requirements](#2-system-requirements)
3. [First-Time Setup (Do This Once)](#3-first-time-setup-do-this-once)
4. [Ollama Setup (Required for Full AI Backend)](#4-ollama-setup-required-for-full-ai-backend)
5. [The One Command You Need](#5-the-one-command-you-need)
6. [Analyzing Your Own Frontend](#6-analyzing-your-own-frontend)
7. [Analyzing a Live URL](#7-analyzing-a-live-url)
8. [What Gets Created (Output Walkthrough)](#8-what-gets-created-output-walkthrough)
9. [Running the Generated Backend](#9-running-the-generated-backend)
10. [Pre-Flight Checklist (Run Before Every Session)](#10-pre-flight-checklist-run-before-every-session)
11. [All CLI Options Explained](#11-all-cli-options-explained)
12. [Troubleshooting](#12-troubleshooting)
13. [Tips for Best Results](#13-tips-for-best-results)

---

## 1. What This Tool Does

Superdata Extractor performs **three phases in a single command**:

| Phase | What happens |
|-------|----------------|
| **Extract** | Scans frontend source files (or a URL) for API calls, state models, forms, UI components, config, and i18n strings |
| **Organize** | Writes everything into `./extracted_output/` in a clean folder hierarchy |
| **Predict** | Sends the extracted data to **local Ollama** and generates a FastAPI backend reference in `./extracted_output/predicted_backend/` |

If Ollama is unavailable, phase 3 falls back to a deterministic template backend — the run still completes.

---

## 2. System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.10 or newer |
| **RAM** | 8 GB (16 GB recommended when running Ollama + extraction) |
| **Disk** | ~2 GB free (Python packages + Ollama model) |
| **Ollama** | Required for AI-generated backend (optional with `--dry-run`) |
| **Internet** | Required only for initial `pip install` and `ollama pull` |

Supported frontend file types for local analysis:
`.js`, `.jsx`, `.ts`, `.tsx`, `.vue`, `.html`, `.json`, `.css`, and common asset formats.

---

## 3. First-Time Setup (Do This Once)

Open **PowerShell** and run every step in order.

### Step 1 — Go to the project folder

```powershell
cd "C:\Users\user\Downloads\ORF_V4.0.0-Package\ORF_V4.0.0-Package\Superdata-Extractor"
```

### Step 2 — Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` at the start of your prompt.

### Step 3 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

This installs: `rich`, `python-dotenv`, `requests`, `beautifulsoup4`, `playwright`.

No Rust or `litellm` required — Ollama is called directly via its native HTTP API.

### Step 4 — (Optional) Install Playwright browser for URL mode

Only needed if you plan to analyze live URLs with JavaScript rendering:

```powershell
playwright install chromium
```

Skip this if you only analyze local code folders.

### Step 5 — Create your environment file

```powershell
copy .env.example .env
```

Default contents (no changes needed for standard local Ollama):

```env
OLLAMA_API_BASE=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

---

## 4. Ollama Setup (Required for Full AI Backend)

### Step 1 — Install Ollama

Download and install from: https://ollama.com/

Ollama runs as a background service after installation.

### Step 2 — Pull the default model

```powershell
ollama pull llama3.2:3b
```

This downloads ~2 GB. Wait until it finishes.

### Step 3 — Verify Ollama is running

```powershell
curl http://localhost:11434/api/tags
```

**Expected:** JSON listing installed models (includes `llama3.2:3b`).

**If it fails:** Open the Ollama app from the Start menu, then retry.

### Step 4 — (Optional) Use a different model

```powershell
ollama pull qwen2.5:1.5b
```

Then either edit `.env`:

```env
OLLAMA_MODEL=qwen2.5:1.5b
```

Or pass it on the command line:

```powershell
python superdata_extractor.py --model qwen2.5:1.5b
```

---

## 5. The One Command You Need

With your virtual environment activated and Ollama running:

```powershell
cd "C:\Users\user\Downloads\ORF_V4.0.0-Package\ORF_V4.0.0-Package\Superdata-Extractor"
.\.venv\Scripts\Activate.ps1
python superdata_extractor.py
```

### What you should see

1. **Banner** — "Superdata Extractor"
2. **`[OK] Ollama reachable at http://localhost:11434`**
3. **Extraction Summary table** — counts for endpoints, state, forms, components
4. **`[OK] Created api_endpoints/`** (and other folders)
5. **`Generating predictive backend via Ollama...`**
6. **`[OK] Generated main.py`** (and other backend files)
7. **`Superdata extraction complete.`**

### Total runtime

- Sample frontend: ~30 seconds (template fallback) to ~3 minutes (Ollama generation)
- Large codebases: 1–5 minutes depending on file count and model speed

---

## 6. Analyzing Your Own Frontend

Point `--source` at your project root (the folder containing `src/`, `app/`, or similar):

```powershell
python superdata_extractor.py --source "C:\path\to\your\frontend"
```

### What gets scanned

- All `.js`, `.jsx`, `.ts`, `.tsx`, `.vue`, `.html`, `.json` files
- Skips: `node_modules`, `.git`, `dist`, `build`, `.next`, `coverage`

### Custom output location

```powershell
python superdata_extractor.py --source "C:\my-app" --output "C:\my-app\superdata_out"
```

### Example: React / Next.js app

```powershell
python superdata_extractor.py --source "C:\projects\my-dashboard\src"
```

---

## 7. Analyzing a Live URL

For publicly reachable pages:

```powershell
# HTTP only (fast, no browser install needed)
python superdata_extractor.py --url https://example.com --no-playwright

# With Playwright (renders JavaScript — requires: playwright install chromium)
python superdata_extractor.py --url https://example.com
```

URL mode extracts: HTML forms, inline scripts, linked assets, embedded JSON config blocks.

---

## 8. What Gets Created (Output Walkthrough)

After a successful run, open `./extracted_output/`:

```
extracted_output/
├── manifest.json                  # Run metadata and artifact counts
├── extraction_summary.json        # High-level stats and warnings
│
├── api_endpoints/
│   └── endpoints.json             # All discovered API routes + methods
│
├── state_schemas/
│   ├── state_models.json          # useState / useReducer / store shapes
│   ├── form_fields.json           # Input fields and types
│   └── config_objects.json        # App config constants
│
├── ui_components/
│   └── component_map.json         # Components → data dependencies
│
├── static_assets/
│   ├── asset_manifest.json        # Images, fonts, scripts
│   ├── localized_strings.json     # i18n / locale strings
│   └── copied/                    # Local assets copied from codebase
│
└── predicted_backend/               # Generated FastAPI reference
    ├── main.py                      # App entry point
    ├── models.py                    # SQLAlchemy database models
    ├── schemas.py                   # Pydantic request/response schemas
    ├── routes.py                    # Route handlers (mock controllers)
    ├── requirements.txt             # Backend dependencies
    └── ARCHITECTURE.md              # Business rules and data flow notes
```

### Key files to review first

1. `api_endpoints/endpoints.json` — verify discovered routes match your app
2. `extraction_summary.json` — check `warnings` for parse failures
3. `predicted_backend/ARCHITECTURE.md` — read the AI's backend design rationale
4. `predicted_backend/routes.py` — inspect generated mock API handlers

---

## 9. Running the Generated Backend

After extraction completes:

```powershell
cd extracted_output\predicted_backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Then open in your browser:

| URL | Purpose |
|-----|---------|
| http://localhost:8000/health | Health check |
| http://localhost:8000/docs | Interactive Swagger UI |
| http://localhost:8000/api/... | Mock API routes inferred from your frontend |

Press `Ctrl+C` to stop the server.

---

## 10. Pre-Flight Checklist (Run Before Every Session)

Use this checklist for a perfect run every time:

```
[ ] Virtual environment activated     →  (.venv) visible in prompt
[ ] In correct directory              →  Superdata-Extractor/
[ ] Ollama app is running             →  curl http://localhost:11434/api/tags returns JSON
[ ] Model is pulled                   →  llama3.2:3b appears in tags response
[ ] Dependencies installed            →  pip show rich requests returns versions
[ ] (URL mode only) Playwright ready  →  playwright install chromium
```

Quick all-in-one verification script:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
pip show rich requests | Select-String Version
curl http://localhost:11434/api/tags
python superdata_extractor.py
```

---

## 11. All CLI Options Explained

```powershell
python superdata_extractor.py [OPTIONS]
```

| Option | Default | When to use |
|--------|---------|-------------|
| *(no flags)* | Analyzes `sample_frontend/` | Quick test / demo run |
| `--source PATH` | `sample_frontend/` | Analyze your own codebase |
| `--url URL` | — | Analyze a live webpage |
| `--output PATH` | `extracted_output/` | Custom output directory |
| `--api-url URL` | `http://localhost:11434` | Ollama on a different host/port |
| `--model NAME` | `llama3.2:3b` | Use a different Ollama model |
| `--dry-run` | off | Skip Ollama; template backend only |
| `--skip-backend` | off | Extract data only; no backend generation |
| `--no-playwright` | off | URL mode without headless browser |
| `--verbose` | off | Show debug logs for troubleshooting |

---

## 12. Troubleshooting

### Ollama not reachable

```
Warning: Ollama unreachable at http://localhost:11434
```

**Fix:**
1. Launch the Ollama application
2. Run `curl http://localhost:11434/api/tags`
3. Re-run `python superdata_extractor.py`

### Model not found

```
LLM prediction failed: model not found
```

**Fix:**
```powershell
ollama pull llama3.2:3b
```

### Backend is template-only (not AI-generated)

Check `extracted_output/extraction_summary.json` → `warnings`. Common causes:
- Ollama was down during the run
- Model returned invalid JSON (small models sometimes struggle)
- You used `--dry-run`

**Fix:** Ensure Ollama is running and retry without `--dry-run`. Try a larger model if JSON parsing keeps failing.

### `pip install` or `Activate.ps1` fails

```powershell
python -m pip install --upgrade pip
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### No frontend files found

```
No frontend files found under ...
```

**Fix:** Point `--source` at the directory that actually contains `.js`/`.tsx` files, not the repo root if code lives in `src/`.

### Playwright errors in URL mode

```powershell
pip install playwright
playwright install chromium
```

Or use HTTP-only mode:

```powershell
python superdata_extractor.py --url https://example.com --no-playwright
```

### Console encoding errors on Windows

```powershell
$env:PYTHONIOENCODING = "utf-8"
python superdata_extractor.py
```

---

## 13. Tips for Best Results

1. **Start with the sample** — Run `python superdata_extractor.py` with no flags first to confirm your environment works.

2. **Point `--source` at source code, not build output** — Analyze `src/` rather than `dist/` or `.next/`.

3. **Use a capable Ollama model for backend generation** — `llama3.2:3b` works; larger models (`llama3.1:8b`, `qwen2.5:7b`) produce richer backend code.

4. **Review warnings** — Always check `extraction_summary.json` for files that failed to parse.

5. **Re-run after frontend changes** — Delete or rename `extracted_output/` before re-running to avoid mixing old and new artifacts:
   ```powershell
   Remove-Item -Recurse -Force extracted_output
   python superdata_extractor.py --source .\my-app
   ```

6. **The generated backend is a reference, not production code** — Use it as architectural scaffolding; add auth, validation, and real database connections before deploying.

---

## Quick Reference Card

```powershell
# ── FIRST TIME ONLY ──────────────────────────────────────────
cd Superdata-Extractor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
ollama pull llama3.2:3b

# ── EVERY RUN ────────────────────────────────────────────────
.\.venv\Scripts\Activate.ps1
python superdata_extractor.py

# ── YOUR OWN APP ─────────────────────────────────────────────
python superdata_extractor.py --source "C:\path\to\frontend"

# ── OFFLINE / NO OLLAMA ──────────────────────────────────────
python superdata_extractor.py --dry-run

# ── RUN GENERATED API ────────────────────────────────────────
cd extracted_output\predicted_backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# → http://localhost:8000/docs
```

---

*Superdata Extractor v1.0 — local Ollama edition*
