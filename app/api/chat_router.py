from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schema.chat import ChatRequest, ChatResponse
from app.service.prompt_builder import build_system_prompt
from app.service.gemini_client import call_gemini
from app.core.config import get_settings

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """
    Spring Backend로부터 ChatRequest를 받아 Gemini 응답을 반환한다.

    Flow:
    1. 모드 분기 (문제풀이 / 자유질문)
    2. 시스템 프롬프트 조립 (Jinja2)
    3. Gemini API 호출
    4. ChatResponse 반환
    """
    settings = get_settings()
    system_prompt = build_system_prompt(request, settings.default_max_length)
    response = call_gemini(request, system_prompt)
    return response
