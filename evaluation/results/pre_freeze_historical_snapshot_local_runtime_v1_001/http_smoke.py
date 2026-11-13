"""One HTTP/SSE check against rebuilt API; preserve only public final output."""

import json
import sys
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from local_runtime import OUT, inspect
from runtime_trace import QUESTIONS


def main():
    path = OUT / (sys.argv[1] if len(sys.argv) > 1 else "http_sse_smoke.json")
    if path.exists():
        raise FileExistsError("Never overwrite a prior smoke")
    env = dict(
        item.split("=", 1) for item in inspect("ufpi-tcc-local-agent_service-1")["Config"]["Env"]
    )
    headers = {"Authorization": "Bearer " + env["AUTH_SECRET"]} if env.get("AUTH_SECRET") else {}
    thread = str(uuid4())
    row = dict(
        timestamp=datetime.now(UTC).isoformat(),
        endpoint="http://127.0.0.1:8080/chatbot_ufpi_integrated_v1/stream",
        case="TEMP-GRAD-002",
        thread_id=thread,
        question=QUESTIONS["TEMP-GRAD-002"],
        events=[],
        messages=[],
    )
    try:
        with httpx.stream(
            "POST",
            row["endpoint"],
            headers=headers,
            json=dict(
                message=row["question"],
                thread_id=thread,
                user_id="snapshot-local-http-smoke",
                stream_tokens=True,
            ),
            timeout=180,
        ) as response:
            row["http_status"] = response.status_code
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    row["events"].append("DONE")
                    continue
                event = json.loads(raw)
                row["events"].append(event["type"])
                if event["type"] == "message":
                    row["messages"].append(event["content"])
        assert row["events"] == ["message", "DONE"], row["events"]
        result = row["messages"][0]["normative_result"]
        row["terminal"], row["core_status"] = result["status"], result["core_status"]
        assert result["status"] == "ANSWER" and result["core_status"] in {"accepted", "regenerated"}
        row["verification"] = "PASS: public final-only HTTP/SSE answer, no clarification/fallback"
    finally:
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            dict(events=row["events"], terminal=row["terminal"], core_status=row["core_status"])
        )
    )


if __name__ == "__main__":
    main()
