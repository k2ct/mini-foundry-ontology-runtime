"""
DeepSeek LLM client — httpx-based implementation of the LLMClient interface.

Calls the DeepSeek Chat Completions API (OpenAI-compatible endpoint).
Handles network errors, timeouts, and HTTP errors with controlled exceptions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.agent.base import LLMClient
from app.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
)

logger = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────

class DeepSeekAPIError(Exception):
    """Raised when the DeepSeek API returns an error or is unreachable."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class DeepSeekTimeoutError(DeepSeekAPIError):
    """Raised when the DeepSeek API request times out."""


class DeepSeekConnectionError(DeepSeekAPIError):
    """Raised when the DeepSeek API cannot be reached."""


# ── Client ───────────────────────────────────────────────────────────────────

class DeepSeekLLMClient(LLMClient):
    """Calls the DeepSeek Chat Completions API over HTTP.

    Parameters
    ----------
    timeout : float
        HTTP request timeout in seconds.  Default 30.0.
    max_retries : int
        Number of retries on transient (5xx / network) errors.  Default 1.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries

        if not DEEPSEEK_API_KEY:
            logger.warning(
                "DEEPSEEK_API_KEY is not set. DeepSeekLLMClient will raise "
                "DeepSeekAPIError on every call."
            )

    # ── LLMClient interface ───────────────────────────────────────────────

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Call the DeepSeek Chat Completions API and return the assistant's reply.

        Parameters
        ----------
        system_prompt : str
            The system-level instruction.
        user_prompt : str
            The user message / analysis request.

        Returns
        -------
        str
            The assistant's raw text response.

        Raises
        ------
        DeepSeekAPIError
            If the API key is missing, the API returns an error, or after
            exhausting retries.
        DeepSeekTimeoutError
            If the request times out.
        DeepSeekConnectionError
            If the server cannot be reached.
        """
        if not DEEPSEEK_API_KEY:
            raise DeepSeekAPIError(
                "DEEPSEEK_API_KEY is not configured. "
                "Set it in your .env file or environment variables."
            )

        url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 1024,
            "stream": False,
        }

        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._do_request(url, headers, payload)
            except httpx.TimeoutException as exc:
                last_error = DeepSeekTimeoutError(
                    f"DeepSeek API request timed out after {self._timeout}s"
                )
                logger.warning(
                    "DeepSeek API attempt %d/%d timed out: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )
            except httpx.ConnectError as exc:
                last_error = DeepSeekConnectionError(
                    f"Cannot connect to DeepSeek API at {url}: {exc}"
                )
                logger.warning(
                    "DeepSeek API attempt %d/%d connection failed: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )
            except httpx.HTTPStatusError as exc:
                # Do NOT retry on 4xx (client errors — bad key, bad request)
                if 400 <= exc.response.status_code < 500:
                    raise DeepSeekAPIError(
                        f"DeepSeek API returned HTTP {exc.response.status_code}: "
                        f"{exc.response.text[:500]}",
                        status_code=exc.response.status_code,
                    )
                last_error = DeepSeekAPIError(
                    f"DeepSeek API returned HTTP {exc.response.status_code}",
                    status_code=exc.response.status_code,
                )
                logger.warning(
                    "DeepSeek API attempt %d/%d returned %d: %s",
                    attempt + 1, self._max_retries + 1,
                    exc.response.status_code, exc,
                )
            except httpx.RequestError as exc:
                last_error = DeepSeekConnectionError(
                    f"DeepSeek API request failed: {exc}"
                )
                logger.warning(
                    "DeepSeek API attempt %d/%d request error: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )

            # Backoff before retry
            if attempt < self._max_retries:
                time.sleep(1.0 * (attempt + 1))

        # Exhausted retries — raise the last error
        assert last_error is not None
        raise last_error

    # ── internal ──────────────────────────────────────────────────────────

    def _do_request(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict,
    ) -> str:
        """Execute a single HTTP request and extract the assistant's message content."""
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        data = response.json()

        # Validate OpenAI-compatible response shape
        choices = data.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise DeepSeekAPIError(
                f"Unexpected API response: no 'choices' array. "
                f"Response keys: {list(data.keys())}"
            )

        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise DeepSeekAPIError(
                f"Empty content in API response. "
                f"Finish reason: {choices[0].get('finish_reason', 'unknown')}"
            )

        return content.strip()
