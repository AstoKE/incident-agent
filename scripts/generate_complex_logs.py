import json
import random
import traceback
from datetime import datetime, timedelta

SERVICES = ["auth", "payments", "orders", "inventory", "gateway"]
LEVELS = ["INFO", "WARN", "ERROR"]
EVENTS = {
    "INFO": [
        "startup",
        "health_check",
        "request_ok",
        "cache_hit",
        "db_query_ok"
    ],
    "WARN": [
        "slow_query",
        "retrying_request",
        "rate_limit_near",
        "cache_miss"
    ],
    "ERROR": [
        "redis_timeout",
        "db_connection_refused",
        "null_pointer_exception",
        "payment_gateway_down",
        "context_deadline_exceeded",
        "authentication_failed"
    ]
}

def random_stacktrace():
    return traceback.format_exc().splitlines()[-3:]

now = datetime.utcnow()
logs = []

for i in range(12000):
    ts = now - timedelta(seconds=(12000 - i))
    service = random.choice(SERVICES)

    # normal traffic
    level = random.choices(LEVELS, weights=[0.7, 0.2, 0.1])[0]
    event = random.choice(EVENTS[level])

    log = {
        "ts": ts.isoformat() + "Z",
        "service": service,
        "level": level,
        "event": event,
        "message": f"{event} occurred in {service}",
        "trace_id": f"trace-{random.randint(1000,9999)}",
        "latency_ms": random.randint(5, 300)
    }

    # inject incidents (auth + redis meltdown)
    if i > 9000 and service == "auth":
        log["level"] = "ERROR"
        log["event"] = "redis_client_not_open"
        log["message"] = "Redis client not initialized before publish"
        log["latency_ms"] = random.randint(800, 3000)

    # payments outage
    if 7000 < i < 8200 and service == "payments":
        log["level"] = "ERROR"
        log["event"] = "payment_gateway_down"
        log["message"] = "Upstream payment provider unreachable"
        log["latency_ms"] = random.randint(1500, 5000)

    # occasional stack trace
    if log["level"] == "ERROR" and random.random() < 0.15:
        log["stacktrace"] = [
            "Exception: Something went wrong",
            "  at service.py:42",
            "  at handler.py:88"
        ]

    logs.append(json.dumps(log))

with open("data/sample.log.jsonl", "w", encoding="utf-8") as f:
    f.write("\n".join(logs))

print("✅ Generated 12,000 complex log lines at data/sample.log.jsonl")
