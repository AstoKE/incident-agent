import logging
import os
import signal
import time

from .graph import build_graph
from .config import LOG_PATH, WINDOW_LINES, POLL_INTERVAL_SECONDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

_running = True


def _handle_signal(sig, _frame):
    global _running
    logger.info("Received signal %s — shutting down gracefully", sig)
    _running = False


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    graph = build_graph()
    last_file_size = -1
    last_incident_fingerprint: str | None = None

    logger.info(
        "Incident agent started | log=%s | poll_interval=%ss | window=%s lines",
        LOG_PATH,
        POLL_INTERVAL_SECONDS,
        WINDOW_LINES,
    )

    while _running:
        try:
            current_size = os.path.getsize(LOG_PATH) if os.path.exists(LOG_PATH) else 0

            if current_size != last_file_size:
                last_file_size = current_size
                logger.debug("Log file changed (%d bytes) — running pipeline", current_size)

                state = {
                    "log_path": LOG_PATH,
                    "window_lines": WINDOW_LINES,
                    "last_incident_fingerprint": last_incident_fingerprint,
                }

                result = graph.invoke(state)

                # Persist fingerprint so the next iteration knows what was already notified
                if result.get("incident_fingerprint"):
                    last_incident_fingerprint = result["incident_fingerprint"]
            else:
                logger.debug("No new log content, sleeping %ss", POLL_INTERVAL_SECONDS)

        except FileNotFoundError:
            logger.warning("Log file not found: %s — will retry", LOG_PATH)
        except Exception:
            logger.exception("Pipeline error (will retry next poll)")

        if _running:
            time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Incident agent stopped")


if __name__ == "__main__":
    main()
