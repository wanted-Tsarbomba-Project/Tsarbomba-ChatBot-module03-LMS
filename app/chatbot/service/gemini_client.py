import logging
from functools import lru_cache
from typing import Iterator, Optional

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.chatbot.schema.chat import ChatRequest
from app.chatbot.service import sse

logger = logging.getLogger(__name__)

# 정답 노출 등 도메인 에러코드 (Spring ChatErrorCode와 공유)
AI_RESPONSE_FAILED = "CHT-003"
AI_RESPONSE_FAILED_MESSAGE = "AI 응답 생성에 실패했습니다."


@lru_cache()
def _get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


def _build_contents(request: ChatRequest) -> list[types.Content]:
    """conversation_history + 변하는 컨텍스트를 Gemini contents로 조립한다."""
    contents: list[types.Content] = []

    if request.conversation_history:
        for msg in request.conversation_history:
            role = "model" if msg.role == "ai" else "user"
            contents.append(
                types.Content(role=role, parts=[types.Part(text=msg.content)])
            )

    # 변하는 컨텍스트를 user_message prefix로 합침 (캐시 히트 유지)
    prefix_parts: list[str] = []

    if request.session_progress:
        prefix_parts.append(
            f"[Current problem: #{request.session_progress.current_problem_number}]"
        )

    if request.problems:
        submitted = [
            f"Problem #{i + 1} ({p.title}): {p.submitted_answer}"
            for i, p in enumerate(request.problems)
            if p.submitted_answer
        ]
        if submitted:
            prefix_parts.append("[Submitted answers]\n" + "\n".join(submitted))

    current_text = request.user_message
    if prefix_parts:
        current_text = "\n\n".join(prefix_parts) + "\n\n" + request.user_message

    contents.append(
        types.Content(role="user", parts=[types.Part(text=current_text)])
    )
    return contents


def _usage_payload(usage_metadata) -> dict:
    """Gemini usage_metadata → done 이벤트 페이로드."""
    if usage_metadata is None:
        return {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0}
    return {
        "promptTokens": usage_metadata.prompt_token_count or 0,
        "completionTokens": usage_metadata.candidates_token_count or 0,
        "totalTokens": usage_metadata.total_token_count or 0,
    }


def stream_gemini(
    request: ChatRequest, system_prompt: str, trace_id: Optional[str] = None
) -> Iterator[str]:
    """Gemini 스트림을 SSE 프레임 문자열로 흘린다.

    토큰마다 token_frame, 끝에 done_frame(사용량). 도중 예외는 error_frame으로 보내고 종료.
    trace_id는 BE(Spring)가 보낸 X-Trace-Id — 실패 로그에 박아 두 서비스 로그를 엮는다.
    """
    settings = get_settings()
    client = _get_client()
    contents = _build_contents(request)

    usage = None
    try:
        stream = client.models.generate_content_stream(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        for chunk in stream:
            if chunk.text:
                yield sse.token_frame(chunk.text)
            if getattr(chunk, "usage_metadata", None) is not None:
                usage = chunk.usage_metadata
        yield sse.done_frame(_usage_payload(usage))
    except Exception:
        logger.exception(
            "event=chatbot_gemini_failed code=%s trace_id=%s", AI_RESPONSE_FAILED, trace_id
        )
        yield sse.error_frame(AI_RESPONSE_FAILED, AI_RESPONSE_FAILED_MESSAGE)
