import logging
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.chatbot.schema.chat import ChatRequest
from app.chatbot.service.prompt_builder import build_system_prompt
from app.chatbot.service.gemini_client import stream_gemini
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat")
def chat(
    request: ChatRequest,
    x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
) -> StreamingResponse:
    """
    Spring Backend로부터 ChatRequest를 받아 Gemini 응답을 SSE로 스트리밍한다.

    Flow:
    1. 모드 분기 (문제풀이 / 자유질문)
    2. 시스템 프롬프트 조립 (Jinja2)
    3. Gemini 스트림 호출 → 토큰을 SSE 프레임으로 흘림 (event 없는 data=토큰, done, error)

    Spring이 보낸 X-Trace-Id를 받아 로그에 박는다 → BE와 같은 traceId로 두 서비스 로그가 엮인다.
    유저 입력 원문은 로깅하지 않는다(개인정보) — 길이만 남긴다.
    """
    settings = get_settings()
    history_len = len(request.conversation_history or [])
    logger.info(
        "event=chatbot_chat_started history_len=%s user_message_length=%s trace_id=%s",
        history_len, len(request.user_message or ""), x_trace_id,
    )
    system_prompt = build_system_prompt(request, settings.default_max_length)

    return StreamingResponse(
        stream_gemini(request, system_prompt, x_trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
