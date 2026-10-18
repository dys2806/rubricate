"""LLM judges: the models that read a rubric and a response and return scores."""

from __future__ import annotations  # modern type hints on Python 3.10

import json  # judges reply with JSON text
import os  # read API keys from environment variables
import time  # wait between retries
from typing import Any, Protocol  # Protocol: "anything with these methods is a judge"

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"  # free tier allows ~500 requests/day
GEMINI_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")  # env vars the Gemini SDK recognizes


class JudgeError(RuntimeError):  # any failure talking to a judge, with a readable message
    pass


class Judge(Protocol):  # the interface every provider implements
    name: str  # e.g. "gemini:gemini-3.8-flash", recorded with every result

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Send instructions + prompt, get back a dict matching `schema`."""
        ...


class GeminiJudge:  # Google Gemini via the official google-genai SDK
    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,  # which Gemini model to use
        api_key: str | None = None,  # explicit key; otherwise read from the environment
        max_retries: int = 5,  # how many times to retry rate-limit and server errors
    ) -> None:
        try:  # the SDK is an optional extra, so validate/lint work without it
            from google import genai  # official Gemini client
            from google.genai import types  # request config classes
        except ImportError as exc:  # not installed
            raise JudgeError(
                "Gemini support isn't installed. Run: pip install 'rubricate[gemini]'"
            ) from exc
        key = api_key or next((os.environ[v] for v in GEMINI_KEY_VARS if os.environ.get(v)), None)
        if not key:  # no key anywhere: explain how to get one, never guess
            raise JudgeError(
                "No Gemini API key found. Create a free key at https://aistudio.google.com/apikey "
                "and set it with: export GEMINI_API_KEY=your-key"
            )
        self._types = types  # keep for building each request
        self._client = genai.Client(api_key=key)  # one client, reused for every call
        self.model = model  # remembered for results and error messages
        self.name = f"gemini:{model}"  # provider-qualified name for result records
        self.max_retries = max_retries  # retry budget per call

    def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        from google.genai import errors  # SDK error types, imported lazily with the SDK

        config = self._types.GenerateContentConfig(
            system_instruction=system,  # the judging instructions
            response_mime_type="application/json",  # ask for JSON, not prose
            response_json_schema=schema,  # and JSON in exactly this shape
            temperature=0.0,  # as repeatable as the model allows
        )
        delay = 2.0  # seconds before the first retry; doubles each time
        for attempt in range(self.max_retries + 1):  # first try plus retries
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
                text = response.text or ""  # the model's JSON reply as a string
                try:
                    return json.loads(text)  # parse it
                except json.JSONDecodeError as exc:  # model returned something that isn't JSON
                    raise JudgeError(f"{self.name} returned invalid JSON: {text[:200]!r}") from exc
            except errors.APIError as exc:  # HTTP-level failure from Google
                if "API_KEY_INVALID" in str(exc):  # wrong or revoked key: say so plainly
                    raise JudgeError(
                        "Gemini rejected the API key. Check GEMINI_API_KEY, or create a new key "
                        "at https://aistudio.google.com/apikey"
                    ) from exc
                retryable = exc.code == 429 or (exc.code or 0) >= 500  # rate limit or server error
                if not retryable or attempt == self.max_retries:  # give up
                    hint = (  # the free tier's most common failure, explained
                        " (rate limit: the free tier allows only a few requests per minute)"
                        if exc.code == 429
                        else ""
                    )
                    raise JudgeError(f"{self.name} request failed: {exc}{hint}") from exc
                time.sleep(delay)  # back off before retrying
                delay *= 2  # exponential backoff: 2s, 4s, 8s, ...
        raise JudgeError(
            f"{self.name}: retries exhausted"
        )  # not reached; keeps type checkers happy


def make_judge(spec: str) -> Judge:  # build a judge from a "provider:model" string
    provider, _, model = spec.partition(":")  # "gemini:gemini-3.8-flash" -> ("gemini", model)
    if provider == "gemini":  # the only provider in this release
        return GeminiJudge(model or DEFAULT_GEMINI_MODEL)  # bare "gemini" uses the default
    raise JudgeError(f"unknown judge provider {provider!r}; supported: gemini")
