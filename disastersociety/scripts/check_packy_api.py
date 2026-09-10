"""One authenticated, minimal model request. Not a simulation or model evaluation.

An unauthenticated GET /models can be blocked while chat completions work.
Read the credential from PACKY_API_KEY or a hidden terminal prompt; never save it.
"""
from __future__ import annotations

import getpass
import json
import os
import urllib.error
import urllib.request


def probe(key: str, opener=urllib.request.urlopen) -> dict:
    if not key.strip():
        raise ValueError("A nonempty API key is required")
    payload = {"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "Reply with OK."}],
               "temperature": 0, "max_tokens": 64, "thinking": {"type": "disabled"}}
    request = urllib.request.Request("https://www.packyapi.com/v1/chat/completions",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        response = opener(request, timeout=45)
    except urllib.error.HTTPError as error:
        response = error
    except Exception as error:
        return {"ok": False, "request": "authenticated_chat_completion",
                "error_type": type(error).__name__,
                "detail": str(error).replace(key, "[REDACTED]")[:300]}
    with response:
        body = response.read(65536).decode("utf-8", errors="replace").replace(key, "[REDACTED]")
        result = {"ok": False, "request": "authenticated_chat_completion",
                  "http_status": response.status, "server": response.headers.get("Server")}
        if response.status == 403 and "cloudflare" in body.lower():
            return {**result, "classification": "cloudflare_block", "cf_ray": response.headers.get("CF-RAY")}
        try:
            data = json.loads(body)
        except ValueError:
            return {**result, "classification": "non_json_response"}
        result.update({k: data[k] for k in ("model", "usage", "error") if k in data})
        result["ok"] = response.status == 200 and bool(data.get("choices"))
        return result


def main():
    key = os.environ.get("PACKY_API_KEY") or getpass.getpass("Packy API key (hidden): ")
    result = probe(key.strip())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
