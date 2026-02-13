import os
from dotenv import load_dotenv

load_dotenv()

LOG_PATH = os.getenv("LOG_PATH", "./data/sample.log.jsonl")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
ERROR_THRESHOLD = int(os.getenv("ERROR_THRESHOLD", "5"))
WINDOW_LINES = int(os.getenv("WINDOW_LINES", "200"))
DEDUP_WINDOW_SECONDS = int(os.getenv("DEDUP_WINDOW_SECONDS", "600")) #10 min