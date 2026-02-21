# incident-agent

Lightweight incident detection and RCA agent that reads recent logs, detects error spikes, deduplicates incidents, and (optionally) runs an LLM-powered RCA step.

## Features
- Windowed log ingestion from a JSONL log file
- Simple rule-based incident detection (error threshold)
- Deduplication of repeated incidents by fingerprint
- Optional RCA step using an LLM (via Ollama) to produce summary, root causes and actions

## Prerequisites
- Python 3.10+
- Git (optional)
- An LLM runtime if you want automated RCA (the code uses Ollama via `langchain_ollama`)

## Setup
1. Create a virtual environment and activate it (recommended):

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional) Create a `.env` file in the repository root to override defaults. See `Configuration` below for keys you can set.

## Configuration
Configuration is read from environment variables (via `python-dotenv`). Useful variables:

- `LOG_PATH` — path to the log file (default: `./data/sample.log.jsonl`)
- `OLLAMA_MODEL` — Ollama model name for RCA (default: `llama3.1`)
- `ERROR_THRESHOLD` — number of errors in the window to mark an incident (default: `5`)
- `WINDOW_LINES` — how many recent lines to read from the log file (default: `200`)
- `DEDUP_WINDOW_SECONDS` — deduplication window in seconds (default: `600`)

Example `.env`:

```text
LOG_PATH=./data/sample.log.jsonl
ERROR_THRESHOLD=10
WINDOW_LINES=300
OLLAMA_MODEL=llama3.1
```

## Running the agent

You can run the agent directly. From the repository root use either:

```bash
# Option A: run module with src on PYTHONPATH
PYTHONPATH=src python -m incident_agent.app


```

The agent will read the last `WINDOW_LINES` from the configured `LOG_PATH`, run detection, optionally call the LLM for RCA, and print results to stdout.

## Generating or downloading sample logs
- To generate sample logs for local testing, run:

```bash
python scripts/generate_complex_logs.py
```

- To download example datasets (if supported), check `scripts/download_loghub.py`.

## How the agent works (high-level)

The agent implements a small state graph built in `src/incident_agent/graph.py`. The graph nodes (functions) are in `src/incident_agent/nodes/` and run in sequence:

- `ingest` (`nodes/ingest_file.py`): read the last N log lines and parse JSONL entries
- `detect` (`nodes/detect.py`): count ERROR/CRITICAL entries, compute affected services, top events, and set `is_incident` and `severity`
- `dedupe` (`nodes/dedup.py`): generate a fingerprint for the incident and avoid duplicate notifications
- Conditional route: if the incident is new and `should_notify` is true the graph goes to `rca`, otherwise it goes straight to `notify`
- `rca` (`nodes/rca_llm.py`): optional LLM-based RCA step. Uses Ollama via `langchain_ollama` to request structured JSON with `summary`, `root_causes`, `actions`, `questions`.
- `notify` (`nodes/notify_stdout.py`): prints a human-readable notification summary to stdout

The graph entry point and orchestration live in `src/incident_agent/app.py` and the agent state shape is defined in `src/incident_agent/state.py`.

## Extending the agent
- Add new processing steps by creating a function in `src/incident_agent/nodes/` and adding a node/edge in `src/incident_agent/graph.py`.
- Swap or customize the RCA step by replacing `nodes/rca_llm.py` or adding additional handlers to `graph.py`.

## Troubleshooting
- If you see JSON parsing errors from logs, ensure your `LOG_PATH` file contains valid JSONL or plain text lines (the ingest node tolerates non-JSON lines).
- If RCA fails, check that Ollama is running and the `OLLAMA_MODEL` is available; the code falls back to a heuristic parser when the LLM output is not structured JSON.

## Quick commands

```bash
# generate sample logs
python scripts/generate_complex_logs.py

# run the agent
PYTHONPATH=src python -m incident_agent.app

# run with a custom log
LOG_PATH=/path/to/log.jsonl PYTHONPATH=src python -m incident_agent.app
```

## License
This project includes a `LICENSE` file in the repository root.

---
If you'd like, I can also add a simple systemd unit or a small looped runner script to run this agent continuously. Want that next?
