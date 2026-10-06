# Superdata Extractor — Colab / Linux Commands

See the root [`README.md`](../README.md) for Ollama/Colab setup.  
See [`COMMERCIAL_LLM_GUIDEBOOK.md`](../COMMERCIAL_LLM_GUIDEBOOK.md) for commercial LLM setup.

## Quick start (local Ollama)

```bash
bash ../setup_colab.sh
cd Superdata-Extractor
python3 superdata_extractor.py
```

Default local model: **`dolphin-llama3:8b`**.

## Commercial LLM

```bash
export LLM_PROVIDER=openai
export OLLAMA_API_BASE=https://api.openai.com/v1
export OLLAMA_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-...

python3 superdata_extractor.py \
  --provider openai \
  --api-url https://api.openai.com/v1 \
  --api-key "$OPENAI_API_KEY" \
  --model gpt-4o-mini
```

```bash
# Custom frontend
python3 superdata_extractor.py --source /path/to/src --provider openai \
  --api-url https://api.openai.com/v1 --api-key "$OPENAI_API_KEY" --model gpt-4o-mini

# Template only
python3 superdata_extractor.py --dry-run

# URL (HTTP only — Playwright off by default on Colab)
python3 superdata_extractor.py --url https://example.com --no-playwright
```

## Env

```env
# Local
OLLAMA_API_BASE=http://127.0.0.1:11434
OLLAMA_MODEL=dolphin-llama3:8b

# Commercial
LLM_PROVIDER=openai
OLLAMA_API_BASE=https://api.openai.com/v1
OLLAMA_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```
