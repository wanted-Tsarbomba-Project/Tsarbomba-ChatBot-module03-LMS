# Handoff: Spring ↔ FastAPI 어댑터 연결

## 현재 상태

| 항목 | 상태 |
|------|------|
| Python FastAPI 서버 | ✅ 구현 완료 (`C:\Project\tsarbombaChatBot`) |
| Spring `FastApiChatClient` | ✅ 구현 완료 — 아직 비활성화 상태 |
| Spring `ChatContextBuilder` | ✅ 구현 완료 |
| Spring `ChatContextAdapter` | ✅ 구현 완료 |
| Spring `WebClientConfig` | ✅ 구현 완료 |
| **현재 활성 클라이언트** | ❌ `MockAiChatClient` (mock 프로파일) |

**문제 한 줄 요약**: `application.yml`의 `spring.profiles.active: local, mock` 에서 `mock`이 활성화되어 있어 `FastApiChatClient` 대신 `MockAiChatClient`가 동작 중.

---

## 연결에 필요한 작업

### 작업 1 (필수): mock 프로파일 제거

**파일**: `src/main/resources/application.yml`

```yaml
# 현재 (FastAPI 안 쓰는 상태)
spring:
  profiles:
    active: local, mock

# 변경 후 (FastAPI 연결)
spring:
  profiles:
    active: local
```

이 한 줄 변경으로:
- `MockAiChatClient` (`@Profile("mock")`) → 비활성화
- `FastApiChatClient` (`@Profile("!mock")`) → 활성화

> ⚠️ **주의**: `mock` 제거 후에는 Python 서버가 반드시 실행 중이어야 Spring 서버가 정상 작동.
> Python 서버 없이 Spring만 띄우면 메시지 전송 시 WebClient 연결 에러 발생.

---

## 데이터 흐름 전체 경로 (연결 후)

```
POST /api/v1/chat/{roomId}/messages
  │
  ▼
ChatMessageController
  │ SendMessageCommand
  ▼
ChatMessageCommandService.send()
  │ 1. ChatRoom 조회 + 소유권 확인
  │ 2. 유저 메시지 DB 저장
  │
  ▼
ChatContextBuilder.build()
  │ ChatContextAdapter 경유:
  │   ├── findProblemSet(problemSetId)   → SpringDataProblemSetRepository
  │   ├── findProblems(problemSetId, userId) → SpringDataProblemRepository
  │   │                                     + SpringDataSubmissionRepository (submitted_answer)
  │   ├── findSessionProgress(problemId) → SpringDataProblemRepository
  │   └── findDataset(problemSetId)      → SpringDataProblemDatasetRepository
  │ + ChatMessageRepository.findRecentByRoomId() → 최근 20개 대화 이력
  │
  ▼
ChatContext (application VO)
  │
  ▼
FastApiChatClient.call(context)
  │ ChatContext → FastApiChatRequest 변환
  │ WebClient POST http://localhost:8000/chat
  │
  ▼  (Python 서버)
prompt_builder.build_system_prompt()
  │ problem_set 존재 → system_problem.j2
  │ problem_set 없음 → system_free.j2
  │
  ▼
gemini_client.call_gemini()
  │ Gemini 3.5 Flash API 호출
  │
  ▼  (Python 서버 응답)
FastApiChatResponse { answer, is_answer_detected, retry_count, ... }
  │
  ▼
FastApiChatClient.toClientResponse()
  │ FastApiChatResponse → AiChatClientResponse
  │
  ▼
ChatMessageCommandService
  │ 3. AI 메시지 DB 저장 (aiResponse.answer())
  │ 4. ChatRoom timestamp 업데이트
  │
  ▼
AiChatResult(answer)
  │
  ▼
AiChatResponse { answer }
```

---

## 핵심 매핑 검증 (Spring ↔ Python)

Spring `FastApiChatClient.toRequest()`가 만드는 JSON과 Python `ChatRequest` Pydantic 모델이 일치하는지 확인.

| Spring `FastApiChatRequest` 필드 | Python `ChatRequest` 필드 | 일치 여부 |
|----------------------------------|--------------------------|----------|
| `user_message` | `user_message` | ✅ |
| `problem_set.problem_set_id` | `problem_set.problem_set_id` | ✅ |
| `problem_set.title` | `problem_set.title` | ✅ |
| `problem_set.description` | `problem_set.description` | ✅ |
| `problems[].title` | `problems[].title` | ✅ |
| `problems[].content` | `problems[].content` | ✅ |
| `problems[].problem_type` | `problems[].problem_type` | ✅ |
| `problems[].answer` | `problems[].answer` | ✅ |
| `problems[].explanation` | `problems[].explanation` | ✅ |
| `problems[].submitted_answer` | `problems[].submitted_answer` | ✅ |
| `session_progress.current_problem_number` | `session_progress.current_problem_number` | ✅ |
| `dataset.meta_data` | `dataset.meta_data` | ✅ |
| `conversation_history[].role` | `conversation_history[].role` | ✅ |
| `conversation_history[].content` | `conversation_history[].content` | ✅ |

Python 응답 → Spring 역직렬화:

| Python `ChatResponse` 필드 | Spring `FastApiChatResponse` 필드 | 일치 여부 |
|---------------------------|----------------------------------|----------|
| `answer` | `answer` | ✅ |
| `is_answer_detected` | `is_answer_detected` | ✅ ⚠️ `answer_detected` 아님 |
| `retry_count` | `retry_count` | ✅ |
| `prompt_tokens` | `prompt_tokens` | ✅ |
| `completion_tokens` | `completion_tokens` | ✅ |
| `total_tokens` | `total_tokens` | ✅ |

> 현재 Python이 `is_answer_detected: false`, 토큰 필드 `0` 고정 반환. Spring이 받아도 현재 로직에서 사용 안 함 (`AiChatResult`는 `answer`만).

---

## 실행 순서

### 1. Python 서버 먼저 실행

```bash
cd C:\Project\tsarbombaChatBot
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

정상 기동 확인:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

헬스체크:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 2. Spring 서버 실행 (mock 제거 후)

```bash
./gradlew bootRun
```

또는 IntelliJ에서 `local` 프로파일로 실행.

### 3. 연동 테스트

Swagger UI: `http://localhost:8080/swagger-ui.html`

`POST /api/v1/chat/{roomId}/messages` 호출:
```json
{
  "userMessage": "DataFrame의 행과 열 개수를 확인하려면 어떻게 해야 하나요?"
}
```

정상 응답 예시:
```json
{
  "code": "CHT-003",
  "message": "메시지가 전송되었습니다.",
  "data": {
    "answer": "`head()`는 데이터를 미리보는 메서드예요. 행과 열의 '개수'를 튜플로 반환하는 속성이 따로 있어요. DataFrame의 '모양'을 나타내는 속성이 무엇일지 찾아보세요."
  }
}
```

---

## 에러 시나리오 및 대응

| 에러 | 원인 | 대응 |
|------|------|------|
| `WebClientRequestException: Connection refused` | Python 서버 미실행 | `uvicorn app.main:app --port 8000` 실행 |
| `WebClientResponseException: 422 Unprocessable Entity` | Spring이 보내는 JSON이 Python Pydantic 모델과 불일치 | `FastApiChatRequest` 필드명 재확인 |
| `WebClientResponseException: 500 Internal Server Error` | Python 서버 내부 에러 (템플릿 오류, Gemini 호출 실패 등) | Python 서버 로그 확인 |
| Gemini API key 에러 | `.env`의 `GEMINI_API_KEY` 누락 또는 만료 | `.env` 파일 확인 |
| `NoUniqueBeanDefinitionException` | `FastApiChatClient`와 `MockAiChatClient` 동시 활성화 | `application.yml`에서 `mock` 프로파일 제거 확인 |

---

## 테스트 전략

### 단위 테스트 — MockWebServer 활용

Spring 쪽 `FastApiChatClient` 단위 테스트는 실제 Python 서버 없이 `MockWebServer`로 검증.

```java
// MockWebServer로 Python 서버 흉내
MockWebServer mockWebServer = new MockWebServer();
mockWebServer.enqueue(new MockResponse()
    .setBody("{\"answer\":\"힌트입니다.\",\"is_answer_detected\":false,\"retry_count\":0,\"prompt_tokens\":0,\"completion_tokens\":0,\"total_tokens\":0}")
    .addHeader("Content-Type", "application/json"));

// WebClient를 MockWebServer URL로 교체
WebClient webClient = WebClient.builder()
    .baseUrl(mockWebServer.url("/").toString())
    .build();
```

### 통합 테스트 — 실제 연동

Python 서버를 `localhost:8000`으로 띄운 상태에서 Spring `bootRun` 후 Swagger로 E2E 검증.

---

## 관련 파일 경로

### Spring 측
| 파일 | 역할 |
|------|------|
| `src/main/resources/application.yml` | **`mock` 제거 대상** |
| `chatbot/infrastructure/client/FastApiChatClient.java` | WebClient POST /chat |
| `chatbot/infrastructure/client/FastApiChatRequest.java` | 요청 DTO |
| `chatbot/infrastructure/client/FastApiChatResponse.java` | 응답 DTO |
| `chatbot/infrastructure/client/WebClientConfig.java` | WebClient 빈 (baseUrl: fastapi.url) |
| `chatbot/infrastructure/client/FastApiProperties.java` | `fastapi.url` 프로퍼티 |
| `chatbot/infrastructure/client/MockAiChatClient.java` | mock 프로파일용 — 연결 후 건드리지 말 것 |
| `chatbot/infrastructure/adapter/ChatContextAdapter.java` | DB에서 문제/데이터셋/제출 조회 |
| `chatbot/application/service/ChatContextBuilder.java` | ChatContext 조립 |

### Python 측
| 파일 | 역할 |
|------|------|
| `C:\Project\tsarbombaChatBot\app\api\chat_router.py` | POST /chat 엔드포인트 |
| `C:\Project\tsarbombaChatBot\app\service\prompt_builder.py` | 시스템 프롬프트 조립 |
| `C:\Project\tsarbombaChatBot\app\service\gemini_client.py` | Gemini API 호출 |
| `C:\Project\tsarbombaChatBot\app\schema\chat.py` | Pydantic 모델 |
| `C:\Project\tsarbombaChatBot\.env` | API 키 (GEMINI_API_KEY) |
| `C:\Project\tsarbombaChatBot\templates\` | Jinja2 프롬프트 템플릿 |

---

## 관측 — traceId 상관(correlation) [BE ↔ FastAPI]

Spring이 `/chat` 호출 시 **`X-Trace-Id` 헤더**로 상관 ID를 전파한다(`FastApiChatClient`). FastAPI는 이를 받아 로그에 박아 두 서비스 로그를 같은 traceId로 엮는다.

- `chat_router.chat()` — `x_trace_id: Optional[str] = Header(alias="X-Trace-Id")` 수신 → `stream_gemini`로 전달. 유저 입력 원문은 로깅 안 함(`user_message_length`만).
- `gemini_client.stream_gemini(request, system_prompt, trace_id)` — 실패 시 `event=chatbot_gemini_failed code=.. trace_id=..`.
- 로그 수집: `deploy/promtail-config.yml`이 컨테이너 로그를 **BE와 동일한 ③ Loki**로 push → Grafana에서 `{job=~".+"} |= "<traceId>"` 로 BE+FastAPI 로그가 한 화면에 뜬다(값으로 매칭 → BE `traceId=`·FastAPI `trace_id=` 둘 다 잡힘).
- ⚠️ traceId가 없으면(헤더 미수신) `trace_id=None`으로 찍힌다 — BE 단독 추적은 가능.

## 다음 세션이 할 것

1. `src/main/resources/application.yml` — `spring.profiles.active: local, mock` → `local` 변경
2. Python 서버 기동 (`uvicorn app.main:app --port 8000`)
3. Spring 서버 기동 (`./gradlew bootRun`)
4. Swagger로 `POST /api/v1/chat/{roomId}/messages` E2E 테스트
5. (선택) `FastApiChatClient` MockWebServer 단위 테스트 작성
