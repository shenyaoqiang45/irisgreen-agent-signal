"""A vision-language model as a Grounder, over any OpenAI-compatible chat API.

Works with Qwen (DashScope compatible mode), Kimi, OpenAI and local servers
that speak /chat/completions. Uses only the standard library.
"""

from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request


class VlmError(RuntimeError):
    pass


def _ask(url: str, api_key: str, model: str, prompt: str, jpeg: bytes, timeout: float) -> str:
    body = {
        "model": model,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    request = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        return payload["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise VlmError(f"VLM request failed: HTTP {exc.code} {exc.read()[:200]!r}") from exc
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
        raise VlmError(f"VLM request failed: {exc}") from exc


def openai_compatible_grounder(base_url: str, api_key: str, model: str, timeout: float = 60.0):
    """Build a Grounder: (jpeg bytes, prompt) -> the model's reply text."""

    async def grounder(jpeg: bytes, prompt: str) -> str:
        return await asyncio.to_thread(_ask, base_url, api_key, model, prompt, jpeg, timeout)

    return grounder
