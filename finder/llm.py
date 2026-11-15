"""LLM interface for the agent: chat(messages, tools) -> (text, tool_calls).

tool_calls is a list of {"id", "name", "arguments"} where arguments is the raw JSON string from
the model (the agent parses it, so bad JSON is the agent's call to handle).
OpenAICompatBackend speaks the OpenAI /chat/completions format with `tools`, which covers Ollama
(/v1), Gemini, Groq, OpenAI, LM Studio and vLLM.

qwen3 thinking mode, checked against Ollama's /v1/chat/completions (qwen3:8b):
  - Thinking text does NOT appear as <think> tags in `content`; Ollama returns it in a separate
    `message.reasoning` field, and `content` holds only the answer. We ignore that field and also
    strip any <think>...</think> a server might leave in `content`.
  - A "/no_think" marker in the system prompt did NOT turn thinking off here (still thought, ~7 s
    for "Say hi").
  - `"reasoning_effort": "none"` in the request body DOES turn it off: 13.5 s -> 0.7 s for "Say hi", no
    `reasoning` field at all. So we send reasoning_effort="none" for qwen3 models by default
    (override with FINDER_LLM_REASONING_EFFORT; set it to "off" to send nothing, e.g. for providers
    that reject the parameter).
"""
import json
import os
import re

import requests

from finder.schemas import ChatResponse, DataError, ModelsResponse, validate

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen3:8b"
_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLMError(Exception):
    pass


def strip_think(text):
    text = _THINK.sub("", text or "")
    return text.split("</think>")[-1].strip()  # an unmatched closing tag: drop what precedes it


class OpenAICompatBackend:
    def __init__(self, base_url=None, model=None, api_key=None, timeout=45, reasoning_effort=None):
        self.base_url = (base_url or os.environ.get("FINDER_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("FINDER_LLM_MODEL") or DEFAULT_MODEL
        self.api_key = api_key if api_key is not None else os.environ.get("FINDER_LLM_API_KEY", "")
        self.timeout = timeout
        effort = reasoning_effort or os.environ.get("FINDER_LLM_REASONING_EFFORT") or \
            ("none" if self.model.lower().startswith("qwen3") else "off")
        self.reasoning_effort = None if effort == "off" else effort

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def preflight(self, timeout=3):
        """Raise LLMError unless the server answers GET /models within `timeout` s and lists the model."""
        try:
            r = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=timeout)
            r.raise_for_status()
            body = r.json()
            validate(ModelsResponse, body, "LLM /models response")
            ids = [m.get("id", "") for m in body.get("data", [])]
        except requests.RequestException as e:
            raise LLMError(f"LLM server not reachable at {self.base_url}: {type(e).__name__}") from e
        except (ValueError, AttributeError, TypeError, DataError) as e:  # DataError is a ValueError
            raise LLMError(f"unexpected /models response from {self.base_url}") from e
        m = self.model
        if not any(i == m or i == f"{m}:latest" or i.endswith("/" + m) for i in ids):
            raise LLMError(f"model {m!r} not available at {self.base_url}")

    def chat(self, messages, tools, timeout=None):
        body = {"model": self.model, "messages": messages, "tools": tools, "stream": False}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        try:
            r = requests.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
                              timeout=timeout or self.timeout)
        except requests.Timeout as e:
            raise LLMError(f"LLM call timed out after {timeout or self.timeout:g}s") from e
        except requests.RequestException as e:
            raise LLMError(f"LLM request failed: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:150]}")
        try:
            resp = r.json()
            validate(ChatResponse, resp, "LLM chat response")
            msg = resp["choices"][0]["message"]
            calls = []
            for i, c in enumerate(msg.get("tool_calls") or []):
                args = c["function"].get("arguments")
                if args is None:
                    args = "{}"
                elif not isinstance(args, str):  # some servers return an object, not a string
                    args = json.dumps(args)
                calls.append({"id": c.get("id") or f"call_{i}", "name": c["function"]["name"], "arguments": args})
            content = msg.get("content") or ""
            if not isinstance(content, str):
                raise TypeError("content")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise LLMError(f"malformed LLM response: {r.text[:150]}") from None
        return strip_think(content), calls
