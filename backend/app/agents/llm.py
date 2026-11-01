"""LLM 호출 한 곳. 테스트에서는 set_backend()로 가짜 함수로 바꾼다.

실제 호출은 OpenAI 호환 API를 쓰며 환경변수로 설정한다.
  LLM_API_KEY (필수), LLM_BASE_URL (기본 https://api.openai.com/v1), LLM_MODEL (기본 gpt-4o-mini)
주의: 프롬프트에 담긴 입력(I/O 목록, 조건)이 외부 서비스로 전송된다.
"""
import json
import os
import urllib.request
from typing import Callable

Backend = Callable[[str, dict], dict]
_backend: Backend | None = None


class LlmUnavailable(RuntimeError):
    pass


def set_backend(fn: Backend | None) -> None:
    global _backend
    _backend = fn


def call_llm(prompt: str, schema: dict) -> dict:
    """프롬프트를 보내고 schema(JSON Schema)에 맞는 JSON(dict)을 돌려준다."""
    if _backend:
        return _backend(prompt, schema)
    return _http_call(prompt, schema)


def _http_call(prompt: str, schema: dict) -> dict:
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise LlmUnavailable("LLM_API_KEY가 설정되지 않았어요. 서버 환경변수에 API 키를 넣어 주세요.")
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "반드시 다음 JSON Schema에 맞는 JSON만 출력하세요.\n" + json.dumps(schema, ensure_ascii=False)},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            return json.loads(json.loads(res.read())["choices"][0]["message"]["content"])
    except (OSError, KeyError, ValueError) as e:
        raise LlmUnavailable(f"LLM 호출에 실패했어요: {e}") from e
