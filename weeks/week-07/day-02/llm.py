import os
import time
from typing import Any

import requests

RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
RETRY_DELAYS = (0, 2, 4, 6)


def complete(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("DOCKHOST_AI_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Не найден DOCKHOST_AI_KEY (или OPENAI_API_KEY) в окружении."
        )

    base_url = os.getenv("OPENAI_BASE_URL", "https://inference.dockhost.io/v1").rstrip(
        "/"
    )
    model = os.getenv("DOCKHOST_MODEL", "deepseek/deepseek-v3.2")
    url = f"{base_url}/chat/completions"

    last_error: Exception | None = None
    total_attempts = len(RETRY_DELAYS)

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                },
                timeout=45,
            )

            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(
                    f"HTTP {response.status_code}",
                    response=response,
                )

            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload["choices"][0]["message"]["content"].strip()
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt == total_attempts:
                break
            print(
                f"[retry] попытка {attempt}/{total_attempts} не удалась "
                f"(сеть/таймаут), жду {RETRY_DELAYS[attempt]}с..."
            )
        except requests.HTTPError as error:
            last_error = error
            status_code = error.response.status_code if error.response else "unknown"
            if status_code not in RETRYABLE_STATUS_CODES or attempt == total_attempts:
                break
            print(
                f"[retry] попытка {attempt}/{total_attempts} не удалась "
                f"(HTTP {status_code}), жду {RETRY_DELAYS[attempt]}с..."
            )
        except requests.RequestException as error:
            last_error = error
            break

    raise RuntimeError(f"LLM запрос не удался: {last_error}") from last_error
