# FastAPI SSE 스트리밍 전환 — 기술 문서

> 대상 커밋: `e07db3c 챗봇 스트리밍 도입`
> 작성일: 2026-06-15
> 관련: Spring `chatbot` 도메인 ADR-0005(스트리밍 응답 표준), `docs/handoff_fastapi_connect.md`

## 1. 한 줄 요약

Gemini 응답을 **다 만든 뒤 JSON 한방(`ChatResponse`)** 으로 주던 `/chat` 엔드포인트를, **생성되는 즉시 토큰 단위로 흘려보내는 SSE(`text/event-stream`)** 로 전환했다.

```
이전:  POST /chat → (Gemini 완성 대기) → JSON 한방
이후:  POST /chat → data:{"t":..} · data:{"t":..} · ... · event:done   (토큰 스트림)
```

## 2. 왜 바꿨나

- 학습자가 질문하면 답이 **완성될 때까지 빈 화면**을 봐야 했다. 답이 길거나 Gemini가 느리면 멈춘 것처럼 느껴진다.
- 토큰이 나오는 즉시 흘려보내면 **첫 글자를 거의 즉시** 보여줄 수 있고, 타이핑되듯 실시간으로 따라가게 된다.
- Spring·브라우저까지 3-hop 전 구간을 SSE로 통일한다(이 레포는 그중 FastAPI 구간).

## 3. 파일별 변경 내용 (무엇을·왜)

### 3.1 `app/api/chat_router.py` — 엔드포인트 응답 타입 교체

| 항목 | 이전 | 이후 | 이유 |
|------|------|------|------|
| 응답 | `JSONResponse` / `response_model=ChatResponse` | `StreamingResponse(media_type="text/event-stream")` | 토큰을 끝까지 모으지 않고 제너레이터로 즉시 흘리려면 스트리밍 응답이어야 한다 |
| 호출 | `call_gemini(...)` (한방) | `stream_gemini(...)` (제너레이터) | 아래 3.3 참조 |
| 헤더 | 없음 | `Cache-Control: no-cache`, `X-Accel-Buffering: no` | 프록시(nginx 등)가 SSE를 **버퍼링**하면 토큰이 한꺼번에 도착해 스트리밍이 무의미해진다. `X-Accel-Buffering: no`로 버퍼링을 끈다 |

요청 스키마(`ChatRequest`)와 입력 계약은 **그대로**다. 바뀐 건 응답 형식뿐.

### 3.2 `app/schema/chat.py` — 응답 스키마(`ChatResponse`) 제거

- `ChatResponse` 모델 전체 삭제. 더 이상 JSON 바디로 응답하지 않으므로 불필요.
- 그 안에 있던 `is_answer_detected`, `retry_count` 필드도 함께 제거.
  - **이유**: 둘 다 "미구현 상태로 자리만 차지하던" 죽은 필드였다(정답 노출 감지·재시도 기능은 이번 범위에서 제외). 계약을 오염시키지 않도록 제거했다.
- 토큰 사용량은 이제 응답 모델 필드가 아니라 **`done` 이벤트 페이로드**로 전달한다(3.4).

### 3.3 `app/service/gemini_client.py` — 비스트림 호출 → 스트림 제너레이터

- `generate_content` (전체 응답 1회) → **`generate_content_stream`** (토큰 청크 반복)으로 교체.
- 함수 분리:
  - `_build_contents()` — `conversation_history` + 변하는 컨텍스트를 Gemini `contents`로 조립(기존 로직 그대로 추출). 순수 함수라 단독 테스트 가능.
  - `stream_gemini()` — 스트림을 돌며 **토큰마다 `sse.token_frame`** 을 `yield`, 끝에 **`sse.done_frame(사용량)`**, 도중 예외는 **`sse.error_frame`** 후 종료.
  - `_usage_payload()` — Gemini `usage_metadata` → `{"promptTokens","completionTokens","totalTokens"}` 변환. 메타가 없으면 0으로 채운다.
- **에러 처리**: 스트림 도중 어떤 예외든 잡아서 `error_frame(CHT-003, ...)`로 한 프레임 보내고 종료한다. HTTP 상태는 이미 `200 + text/event-stream`으로 커밋된 뒤라 상태코드로 에러를 알릴 수 없기 때문 — 에러도 **스트림 안의 이벤트**로 전달한다.
- 에러코드 `CHT-003`은 Spring `ChatErrorCode.AI_RESPONSE_FAILED`와 **공유**한다(같은 코드/메시지 문자열).

### 3.4 `app/service/sse.py` — SSE 프레임 직렬화기 (신규)

SSE 프레임 문자열을 만드는 **순수 함수 모음**. Gemini/네트워크 의존이 없어 격리 테스트가 쉽다.

```python
token_frame("def foo():\n  return 1")
#  → 'data: {"t": "def foo():\\n  return 1"}\n\n'   (event 이름 없음)

done_frame({"promptTokens": 12, "completionTokens": 80, "totalTokens": 92})
#  → 'event: done\ndata: {"promptTokens": 12, ...}\n\n'

error_frame("CHT-003", "AI 응답 생성에 실패했습니다.")
#  → 'event: error\ndata: {"code": "CHT-003", "message": "..."}\n\n'
```

**핵심 설계 — 토큰 본문을 JSON으로 감싼다(`{"t": ...}`).**
SSE는 **빈 줄(`\n\n`)이 한 이벤트의 끝**이고, 줄 단위로 파싱한다. Gemini 토큰에는 코드블록 줄바꿈(`\n`)이 그대로 들어오는데, 이걸 생텍스트로 `data:`에 넣으면 줄바꿈이 프레임을 둘로 쪼개 **파싱이 깨진다**. `json.dumps`로 감싸면 줄바꿈이 `\n`(이스케이프된 두 글자)로 바뀌어 한 줄로 유지된다. `ensure_ascii=False`로 한글은 그대로 둔다.

### 3.5 `requirements.txt` — 개발 의존성 추가

- `pytest`, `httpx` 추가(테스트용). 런타임 의존성 변화 없음.

## 4. SSE 응답 계약 (Spring·프론트가 이 규격에 맞춤)

```
(event 없음)   data: {"t":"def foo():\n  return 1"}                  # 본문 토큰, N회
event: done    data: {"promptTokens":12,"completionTokens":80,"totalTokens":92}
event: error   data: {"code":"CHT-003","message":"AI 응답 생성에 실패했습니다."}
```

- **토큰**: `event` 이름 없음. `data`는 `{"t": "<조각>"}`.
- **done**: 정상 종료 1회. 토큰 사용량 메타. (성공 신호)
- **error**: 스트림 도중 실패 시 1회 후 종료. (`done` 대신 옴)
- `room` 이벤트(첫 메시지의 새 방 ID)는 **Spring이 붙이는 것**으로, FastAPI는 보내지 않는다.

> ⚠️ FastAPI는 정상 경로에서 항상 HTTP `200`을 반환한다. Gemini 실패도 `200` 바디 안의 `event: error`로 전달된다 — Spring은 HTTP 상태가 아니라 **이벤트 타입**으로 성공/실패를 구분해야 한다.

## 5. 테스트 (격리)

DB·Gemini·네트워크 없이 순수 입출력만 검증한다.

- `tests/test_sse.py` — 프레임 직렬화기. 특히 **줄바꿈·따옴표·중괄호가 든 토큰**이 프레임을 깨지 않는지(JSON 인코딩 핵심 케이스)와, 프레임이 `\n\n`로 끝나는 무결성 검증.
- `tests/test_stream_gemini.py` — 가짜 Gemini 청크 스트림을 넣어 토큰 프레임들 + `done`(사용량) 순서로 나오는지 검증.

실행:

```bash
pytest -q
```

## 6. 단독 동작 확인 (curl)

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_message":"파이썬 리스트 컴프리헨션 알려줘"}'
```

`-N`(`--no-buffer`)로 토큰이 실시간으로 한 줄씩 찍히는지 확인한다. `data: {"t":...}`가 흐르다 마지막에 `event: done`이 오면 정상.

## 7. 미적용/주의

- `X-Accel-Buffering: no`는 **응답 헤더만** 제공한다. 실제 nginx 등 리버스 프록시의 `proxy_buffering off`는 인프라 측 설정 책임.
- 사용량 메타는 `done` 이벤트로 **전달만** 한다. 과금/대시보드 집계는 범위 밖.
- 정답 감지(`is_answer_detected`)·재시도(`retry_count`)는 이번에 **제거만** 했고 재구현하지 않았다.
