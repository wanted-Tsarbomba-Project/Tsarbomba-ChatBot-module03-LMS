from functools import lru_cache

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.schema.chat import ChatRequest, ChatResponse


@lru_cache()
def _get_client() -> genai.Client:
    return genai.Client(api_key=get_settings().gemini_api_key)


def call_gemini(request: ChatRequest, system_prompt: str) -> ChatResponse:
    settings = get_settings()
    client = _get_client()

    # conversation_history → Gemini contents 멀티턴 매핑
    contents: list[types.Content] = []

    if request.conversation_history:
        for msg in request.conversation_history:
            role = "model" if msg.role == "ai" else "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=msg.content)],
                )
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
        types.Content(
            role="user",
            parts=[types.Part(text=current_text)],
        )
    )

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
        ),
    )

    answer = response.text or ""

    return ChatResponse(
        answer=answer,
        is_answer_detected=False,  # 미구현 — 추후 활성화
        retry_count=0,             # 미구현
        prompt_tokens=0,           # 미구현
        completion_tokens=0,       # 미구현
        total_tokens=0,            # 미구현
    )
