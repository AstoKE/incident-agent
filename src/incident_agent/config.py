import os
from dotenv import load_dotenv

load_dotenv()

LOG_PATH = os.getenv("LOG_PATH", "./data/sample.log.jsonl")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ERROR_THRESHOLD = int(os.getenv("ERROR_THRESHOLD", "5"))
WINDOW_LINES = int(os.getenv("WINDOW_LINES", "200"))
DEDUP_WINDOW_SECONDS = int(os.getenv("DEDUP_WINDOW_SECONDS", "600"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

# ChromaDB — leave CHROMA_HOST empty to use a local persistent store
CHROMA_HOST = os.getenv("CHROMA_HOST", "")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_DATA_DIR = os.getenv("CHROMA_DATA_DIR", "./.chromadb")
