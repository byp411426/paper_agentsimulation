"""Check the actual API request shape and credential-safe diagnostics offline."""
import io
import json
import urllib.error

from scripts.check_packy_api import probe


class Response(io.BytesIO):
    status = 200
    headers = {"Server": "cloudflare"}


def test_probe_uses_authenticated_chat_post_and_does_not_expose_key():
    key = "fixture-credential-do-not-persist"

    def transport(request, timeout):
        assert request.full_url.endswith("/v1/chat/completions")
        assert request.method == "POST" and request.get_header("Authorization") == "Bearer " + key
        assert json.loads(request.data)["model"] == "deepseek-v4-flash"
        assert timeout == 45
        return Response(json.dumps({"model": "deepseek-v4-flash", "choices": [{}],
                                    "usage": {"total_tokens": 10}}).encode())

    result = probe(key, transport)
    assert result["ok"] and key not in json.dumps(result)


def test_cloudflare_block_is_distinct_from_authentication_error():
    def transport(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden",
            {"Server": "cloudflare", "CF-RAY": "fixture-ray"}, io.BytesIO(b"Cloudflare: Sorry, you have been blocked"))

    result = probe("fixture-key", transport)
    assert not result["ok"] and result["classification"] == "cloudflare_block"


def test_transport_exception_redacts_credential():
    def transport(request, timeout):
        raise OSError("failed while using fixture-key")

    result = probe("fixture-key", transport)
    assert not result["ok"] and "fixture-key" not in json.dumps(result)
