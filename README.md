# incident-agent

A local incident detection and root-cause-analysis (RCA) agent. It watches a log file, detects error spikes, looks up similar past incidents, and asks a local LLM for a structured RCA (summary, root causes, actions, open questions).

Built with **LangGraph** (workflow), **LangChain + Ollama** (local LLM), and **ChromaDB** (incident memory / RAG). Everything runs on your machine, so no API keys are needed.

> New to LangGraph/LangChain? Read [docs/LANGGRAPH_REHBERI.md](docs/LANGGRAPH_REHBERI.md) (Turkish), a walkthrough of this codebase's graph, nodes, state and RAG.

## Features
- Reads the last N lines of a log file: JSONL, syslog, or plain text
- Rule-based incident detection (ERROR/CRITICAL count vs. threshold) with MEDIUM/HIGH severity
- RAG: retrieves similar past incidents from ChromaDB and feeds them to the LLM
- LLM-based RCA with JSON-constrained output, schema validation, and rule-based fallbacks
- Deduplication so the same incident isn't reported twice in a row
- Three front-ends: CLI daemon, web dashboard (FastAPI), and desktop app (Qt)

## How it works

The pipeline is a LangGraph state graph ([graph.py](src/incident_agent/graph.py)). Nodes live in [nodes/](src/incident_agent/nodes/) and share the state defined in [state.py](src/incident_agent/state.py).

```
ingest → detect ─┬─ no incident ───────────────────────────────→ notify → END
                 └─ incident → rag_retrieve → rca → dedupe → notify → rag_store → END
```

| Node | File | What it does |
|---|---|---|
| `ingest` | [ingest_file.py](src/incident_agent/nodes/ingest_file.py) | Tail the last `WINDOW_LINES` lines; parse JSONL, syslog, or raw text |
| `detect` | [detect.py](src/incident_agent/nodes/detect.py) | Count ERROR/CRITICAL; `is_incident` if ≥ `ERROR_THRESHOLD`, `HIGH` if ≥ 3× |
| `rag_retrieve` | [rag_retrieve.py](src/incident_agent/nodes/rag_retrieve.py) | Fetch the 3 most similar past incidents from ChromaDB |
| `rca` | [rca_llm.py](src/incident_agent/nodes/rca_llm.py) | Ask the LLM for JSON RCA; validate with Pydantic; fall back to playbook actions if the LLM gives none |
| `dedupe` | [dedup.py](src/incident_agent/nodes/dedup.py) | Fingerprint severity + services + events; suppress repeats |
| `notify` | [notify_stdout.py](src/incident_agent/nodes/notify_stdout.py) | Print the report |
| `rag_store` | [rag_store.py](src/incident_agent/nodes/rag_store.py) | Save new incidents to ChromaDB and `data/incidents.jsonl` |

[app.py](src/incident_agent/app.py) runs the graph in a loop, re-running whenever the log file changes (polled every `POLL_INTERVAL_SECONDS`).

## Models

| Purpose | Default | Notes |
|---|---|---|
| RCA (chat) | `qwen3.5:9b` | ~6.6 GB, fits fully in a 12 GB GPU |
| RAG embeddings | `qwen3-embedding:0.6b` | ~0.6 GB, used only to vectorize incidents |

You can swap models with `OLLAMA_MODEL` in `.env`. Some options:
- `qwen3.5:4b`: faster, for GPUs with 6–8 GB VRAM
- `qwen3.8:27b`: newest Qwen, stronger reasoning, but 18 GB. It needs ~20 GB VRAM to run fully on GPU; otherwise it spills to CPU and each RCA takes minutes.
- `llama3.1`: older default. Set `OLLAMA_REASONING=` (empty) because it has no thinking mode.

Changing `OLLAMA_EMBED_MODEL` starts a fresh ChromaDB collection, because vectors from different embedding models are incompatible.

## Setup (Windows / PowerShell)

Prerequisites: Python 3.10+ and [Ollama](https://ollama.com/download).

```powershell
# 1. Virtual environment + dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install --no-deps -e .

# 2. Config
Copy-Item .env.example .env

# 3. Models (Ollama must be running — it starts automatically after install)
ollama pull qwen3.5:9b
ollama pull qwen3-embedding:0.6b

# 4. Sample logs
python scripts\generate_complex_logs.py
```

<details>
<summary>macOS / Linux</summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install --no-deps -e .
cp .env.example .env
ollama pull qwen3.5:9b
ollama pull qwen3-embedding:0.6b
python scripts/generate_complex_logs.py
```
</details>

`pip install -e .` makes `incident_agent` importable, so you don't need to set `PYTHONPATH=src`.

## Running

```powershell
# Agent daemon (watches LOG_PATH, Ctrl+C to stop)
python -m incident_agent.app

# Web dashboard: http://localhost:8080 (run in a second terminal)
python -m incident_agent.api

# Desktop app: pick a log file and analyze it interactively
python -m incident_agent.ui_qt.app_qt
```

### Docker

```bash
docker compose up -d
scripts/setup_models.sh            # pulls qwen3.5:9b + qwen3-embedding:0.6b into the ollama container
```

This starts the agent, the dashboard (port 8080), Ollama, and ChromaDB. For GPU acceleration, uncomment the `deploy` block under `ollama` in [docker-compose.yml](docker-compose.yml).

## Configuration

All settings are environment variables, read from `.env` (see [.env.example](.env.example)).

| Variable | Default | Description |
|---|---|---|
| `LOG_PATH` | `./data/sample.log.jsonl` | Log file to watch |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Chat model for RCA |
| `OLLAMA_EMBED_MODEL` | `qwen3-embedding:0.6b` | Embedding model for RAG |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_REASONING` | `false` | Thinking mode for qwen3.x (`true` = slower, deeper). Empty for models without thinking. |
| `OLLAMA_NUM_CTX` | `8192` | LLM context window (tokens) |
| `ERROR_THRESHOLD` | `5` | ERROR/CRITICAL count that triggers an incident (3× → HIGH) |
| `WINDOW_LINES` | `200` | How many recent lines to analyze |
| `POLL_INTERVAL_SECONDS` | `30` | Daemon polling interval |
| `CHROMA_HOST` / `CHROMA_PORT` | empty / `8000` | Remote ChromaDB; leave host empty for a local store |
| `CHROMA_DATA_DIR` | `./.chromadb` | Local ChromaDB directory |

## Sample data
- `scripts/generate_complex_logs.py` writes synthetic JSONL logs (including a payments outage) to `data/sample.log.jsonl`.
- `scripts/download_loghub.py` downloads real-world log datasets from [LogHub](https://github.com/logpai/loghub). Point `LOG_PATH` at one of them; syslog-format lines are parsed automatically.

## Extending
- **New step:** write a function `(state) -> state` in `nodes/`, then register it with `add_node` / `add_edge` in `graph.py`. If it needs new state fields, add them to `state.py`.
- **Different LLM provider:** replace `ChatOllama` in `rca_llm.py` with any LangChain chat model (`ChatOpenAI`, `ChatAnthropic`, …).

## Troubleshooting
- **`LLM error: ResponseError` / model not found:** run `ollama list` and make sure `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` are pulled.
- **`does not support thinking`:** the model has no thinking mode. Set `OLLAMA_REASONING=` (empty).
- **RCA is very slow:** the model doesn't fit in VRAM. Check with `ollama ps` (the `PROCESSOR` column should be `100% GPU`) and pick a smaller model.
- **`Log file not found`:** generate sample logs or fix `LOG_PATH`. Relative paths resolve from the project root.
- **"RAG disabled" warning:** ChromaDB or the embedding model is unavailable. The agent keeps working without history.

## License
See [LICENSE](LICENSE).
