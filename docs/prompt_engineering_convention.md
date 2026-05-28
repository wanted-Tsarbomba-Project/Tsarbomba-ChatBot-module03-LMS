# 프롬프트 / 컨텍스트 엔지니어링 + 튜터링 컨벤션

> FastAPI Python 서버의 시스템 프롬프트 설계 원칙.
> 프로젝트 구조는 `docs/ChatBot/fastapi_project_convention.md` 참조.

---

## 1. 핵심 원칙

이 서버는 **데이터 분석 학습용 AI 튜터**입니다.

- **절대 정답을 직접 알려주지 않는다**
- 유저의 사고 과정을 유도한다
- 제공된 컨텍스트(문제, 데이터셋, 제출 답안) 기반으로만 말한다
- 모르면 모른다고 한다 (Hallucination 방지)

---

## 2. 시스템 프롬프트 아키텍쳐

### 2.1 섹션 배치 순서

LLM의 Self-Attention 특성을 활용한 배치. **앞(primacy)**과 **끝(recency)**에 가장 중요한 규칙 배치.

```
[system_instruction]

┌─────────────────────────────────────────────┐
│ 1. ROLE + FORBIDDEN RULES        ← primacy │
│    가장 중요한 제약이 최상단               │
├─────────────────────────────────────────────┤
│ 2. ANSWER (정답)                            │
│    금지 규칙 바로 뒤에 붙여서              │
│    "금지" ↔ "정답" attention 연결 강화     │
├─────────────────────────────────────────────┤
│ 3. PROBLEM CONTEXT                          │
│    문제 세트, 문제 목록, 데이터셋 정보     │
│    CODE/TEXT 분기 가이드                    │
├─────────────────────────────────────────────┤
│ 4. HALLUCINATION DEFENSE                    │
│    grounding 규칙                           │
├─────────────────────────────────────────────┤
│ 5. RESPONSE FORMAT               ← recency │
│    길이, 톤, 언어, 구조 규칙              │
│    출력에 직접 영향 → 마지막 위치          │
└─────────────────────────────────────────────┘
```

### 2.2 배치 근거 (Self-Attention + Positional Encoding)

| 위치 | 효과 | 배치하는 것 |
|------|------|------------|
| **최상단 (primacy)** | 모든 후속 토큰이 이 내용을 강하게 참조 | 역할 정의 + 절대 금지 규칙 |
| **금지 규칙 직후** | "금지" 토큰과 "정답" 토큰의 attention score 극대화 | 정답 데이터 |
| **중간** | attention이 상대적으로 약함 | 컨텍스트 데이터 (참조용) |
| **최하단 (recency)** | 디코더가 응답 생성 직전에 마지막으로 참조 | 응답 포맷 규칙 |

---

## 3. 템플릿 파일 구조

### 3.1 파일 구성

```
templates/
├── system_base.j2           # 공통 규칙 (모든 모드 공유)
├── system_problem.j2        # 문제풀이 모드 전용
├── system_free.j2           # 자유질문 모드 전용
└── ko/                      # 한국어 참조본 (실제 사용 안 함)
    ├── system_base.j2
    ├── system_problem.j2
    └── system_free.j2
```

### 3.2 include 관계

```
system_problem.j2
  └── {% include 'system_base.j2' %}   ← 공통 규칙 삽입
      + 문제풀이 전용 블록 (정답, 문제 정보, CODE/TEXT 분기)

system_free.j2
  └── {% include 'system_base.j2' %}   ← 공통 규칙 삽입
      + 자유질문 전용 블록 (일반 어시스턴트 역할)
```

### 3.3 모드 분기 조건

```python
if request.problem_set is not None:
    # 문제풀이 모드 → system_problem.j2
else:
    # 자유질문 모드 → system_free.j2
```

---

## 4. 프롬프트 언어 정책

### 4.1 토큰 효율

한국어는 영어 대비 동일 의미에 **2배 이상 토큰**을 소모합니다.

시스템 프롬프트의 규칙/구조 부분은 **매 요청마다 반복되는 고정 비용**이므로, 영어로 작성하여 토큰을 절약합니다.

| 구분 | 언어 | 이유 |
|------|------|------|
| 시스템 프롬프트 (규칙, 구조) | **영어** | 토큰 절약 + implicit caching 히트율 향상 |
| DB에서 오는 데이터 (문제, 정답 등) | **한국어 그대로** | DB 원본값 유지 |
| AI 응답 | **한국어** | 프롬프트에 "Respond in Korean" 지시 |

### 4.2 한국어 참조본 관리 규칙

- `templates/ko/` 디렉토리에 동일 구조의 한국어 번역본 유지
- **실제 Gemini 호출에 사용하지 않음** — 팀원이 프롬프트 의도를 이해하기 위한 참조용
- 영어 템플릿 수정 시 **반드시 한국어 참조본도 동기화**
- PR 리뷰 시 영어/한국어 불일치 체크

---

## 5. 컨텍스트 엔지니어링

### 5.1 `system_instruction` vs `contents` 분리 원칙

**Implicit Caching 효율 극대화**가 목표. `system_instruction`이 요청 간 동일하면 Gemini가 자동 캐시 → 입력 토큰 비용 90% 할인.

**규칙: 같은 채팅방 내에서 변하지 않는 데이터 → `system_instruction`, 변하는 데이터 → `contents`**

| 데이터 | 변동 여부 | 위치 |
|--------|----------|------|
| 역할 + 금지 규칙 + 포맷 규칙 | 불변 | `system_instruction` |
| problem_set 정보 | 불변 | `system_instruction` |
| 전체 problems[] + answer | 불변 | `system_instruction` |
| dataset.meta_data | 불변 | `system_instruction` |
| CODE/TEXT 가이드 규칙 | 불변 | `system_instruction` |
| session_progress | 변동 (문제 전환 시) | `contents` (user_message prefix) |
| conversation_history | 변동 (매 요청) | `contents` (멀티턴 매핑) |
| user_message | 변동 (매 요청) | `contents` |

### 5.2 conversation_history 처리

Gemini의 네이티브 멀티턴 구조를 활용합니다. 시스템 프롬프트에 텍스트로 넣지 않습니다.

```python
# payload role → Gemini role 매핑
# "user" → "user"
# "ai"   → "model"

contents = []
for msg in conversation_history:
    role = "model" if msg.role == "ai" else "user"
    contents.append({"role": role, "parts": [{"text": msg.content}]})
```

**이유**: Gemini가 멀티턴을 네이티브로 지원하므로 role 구분이 정확합니다. 시스템 프롬프트에 텍스트로 넣으면 컨텍스트 윈도우 낭비 + role 구분 약화.

### 5.3 session_progress 처리

`user_message`에 prefix로 합칩니다.

```python
current_text = user_message
if session_progress:
    current_text = f"[Current problem: #{session_progress.current_problem_number}]\n\n{user_message}"
contents.append({"role": "user", "parts": [{"text": current_text}]})
```

**이유**: session_progress는 문제 전환 시 변하므로 `system_instruction`에 넣으면 캐시가 깨집니다. `user_message`에 합치면 단순하고 더미 응답도 불필요합니다.

### 5.4 dataset.meta_data 파싱

DB에서 JSON string으로 옵니다. 파싱하여 리스트로 변환 후 템플릿에 전달합니다.

```python
import json

# 입력: "[\"id\", \"name\", \"age\", \"score\"]"
# 출력: ["id", "name", "age", "score"]
columns = json.loads(dataset.meta_data)
```

템플릿에서 줄바꿈 리스트로 렌더링:

```jinja2
[Dataset Columns]
{% for col in columns %}
- {{ col }}
{% endfor %}
```

**이유**: JSON 배열 형태보다 줄바꿈 리스트가 AI의 attention이 각 컬럼에 고르게 분산됩니다. JSON string은 하나의 덩어리로 처리되어 개별 컬럼 인식이 약해집니다.

---

## 6. 튜터링 규칙

### 6.1 절대 금지 사항

| 금지 항목 | 설명 |
|----------|------|
| **정답 직접 노출** | answer 필드의 내용을 그대로 말하거나 유사하게 표현 금지 |
| **추임새 / 칭찬** | "잘했어요!", "좋은 질문이에요!" 등 금지. 힌트와 유도만 |
| **데이터 분석 외 주제** | 데이터 분석과 무관한 질문은 거절 |
| **없는 정보 생성** | 제공된 컨텍스트에 없는 컬럼, 함수 등을 지어내지 않음 |
| **이전 힌트 반복** | conversation_history에서 이미 제공한 힌트를 그대로 반복하지 않음 |

### 6.2 CODE 타입 문제 — 정답 의도 vs 제출 의도 비교

CODE 문제에서 `submitted_answer`가 존재할 때, AI는 **코드를 실행할 수 없습니다**. 대신 **의도 비교**로 피드백합니다.

```
분석 과정:
1. 정답 코드(answer)의 의도를 파악 (예: "행/열 개수 확인")
2. 제출 코드(submitted_answer)의 의도를 파악 (예: "데이터 미리보기")
3. 두 의도의 차이(gap)를 식별
4. gap을 좁히는 방향으로 유도 (정답 자체를 말하지 않고)
```

**프롬프트 규칙 (영어):**
```
When submitted_answer exists for a CODE problem:
- Understand the intent of the correct answer (without revealing it).
- Understand the intent of the submitted code.
- Identify the gap between the two intents.
- Guide the user toward closing that gap without revealing the answer code.
```

**예시:**
- 정답: `df.shape` (행/열 개수)
- 제출: `df.head()` (데이터 미리보기)
- AI 응답: "데이터를 확인하려는 접근은 좋아요. 그런데 이 문제에서 원하는 건 '개수'예요. 개수를 알 수 있는 다른 속성을 찾아보세요."

### 6.3 TEXT 타입 문제 — 핵심 키워드 기반 유도

TEXT 문제에서 `submitted_answer`가 존재할 때, **정답의 핵심 개념(키워드)**을 기준으로 피드백합니다.

```
분석 과정:
1. 정답(answer)에서 핵심 개념/키워드를 추출
2. 제출 답안(submitted_answer)이 어떤 개념을 포함하고 어떤 게 누락인지 판별
3. 누락된 개념 방향으로 질문을 던져서 사고 유도
4. 정답에 없는 개념은 도입하지 않음
```

**프롬프트 규칙 (영어):**
```
For TEXT problems:
- Identify key concepts in the correct answer.
- Check which concepts the user's response covers and which are missing.
- Ask questions that lead toward the missing concepts.
- Do not introduce concepts not present in the correct answer.
```

**예시:**
- 정답: "정규화는 0~1 범위로 스케일링, 표준화는 평균 0 표준편차 1로 변환"
- 제출: "정규화는 데이터를 작게 만드는 것"
- AI 응답: "'작게 만든다'는 방향은 맞아요. 그런데 정확히 어떤 범위로 만드는지, 그리고 표준화와는 어떤 기준값이 다른지 생각해보세요."

### 6.4 submitted_answer 없을 때

유저가 아직 시도하지 않은 상태. **문제 접근 방향을 유도**합니다.

- CODE: 어떤 종류의 함수/메서드를 찾아볼지 방향 제시
- TEXT: 핵심 키워드나 비교 관점을 던져서 사고 시작점 제공

### 6.5 데이터셋 활용

`dataset.meta_data`의 컬럼 정보를 두 가지 용도로 활용:

**1. Grounding (환각 방지)**
- AI가 실제 존재하는 컬럼만 언급하도록 제한
- 없는 컬럼을 지어내는 것 방지

**2. 힌트 재료**
- "이 데이터셋에는 이런 컬럼들이 있어요. 문제에서 요구하는 '성과 점수'와 관련된 컬럼이 어떤 건지 살펴보세요"
- AI가 데이터셋의 의미를 파악하고, 문제 풀이에 필요한 컬럼을 유도

---

## 7. 응답 포맷

### 7.1 길이 제한

| 설정 | 기본값 | 비고 |
|------|--------|------|
| `DEFAULT_MAX_LENGTH` | 200자 | 환경변수로 변경 가능 |
| 확장 범위 | 300~500자 | 추후 분기 가능하게 변수화 |

프롬프트에서:
```
Keep your response within {{ max_length }} characters.
```

### 7.2 톤

- 한국어 응답
- 존댓말 사용
- 튜터 톤 (학습 유도형)
- **추임새 / 칭찬 절대 금지** — "잘했어요", "좋은 접근이에요" 등 사용하지 않음
- 오직 힌트와 유도 질문만

### 7.3 구조화된 포맷

매 응답이 일관된 구조를 가지도록 강제합니다. **(구체적 구조는 추후 결정)**

설계 방향:
- 힌트 + 유도 질문 조합
- 유저가 "다음에 뭘 해야 하는지" 알 수 있는 구조
- 매번 동일한 패턴으로 응답하여 예측 가능성 확보

### 7.4 반복 방어

```
- Do not repeat hints you already gave in the conversation history.
- If the user asks the same question again, try a different approach or angle.
- Never start consecutive responses with the same phrase.
```

---

## 8. 실패 모드 방어

### 8.1 Hallucination (환각)

**프롬프트 규칙:**
```
- Only reference columns that exist in the provided dataset metadata.
- If you are unsure about a function or method, say "I'm not certain" instead of guessing.
- Do not fabricate information not present in the provided context.
```

**위험 시나리오 및 방어:**

| 시나리오 | 방어 |
|----------|------|
| 없는 pandas 함수를 가르침 | "확실하지 않으면 모른다고 말해라" 규칙 |
| 문제 내용을 왜곡해서 설명 | 문제 원문을 `system_instruction`에 포함하여 참조 강제 |
| 데이터셋 컬럼을 지어냄 | grounding 규칙 — 제공된 컬럼만 언급 |

### 8.2 정답 노출 (튜터링 원칙 위반)

**방어 계층:**

1. **프롬프트 최상단에 금지 규칙** — primacy 효과로 강하게 인식
2. **금지 규칙 + 정답을 붙여놓기** — "이것을 말하지 마"의 대상이 attention으로 명확히 연결
3. **`is_answer_detected` 검증** — (추후 구현) AI 응답에 정답이 포함됐는지 자체 검증

### 8.3 반복/장황 (Verbose Repetition)

**방어:**
- 답변 길이 제한 (환경변수 `DEFAULT_MAX_LENGTH`)
- 이전 힌트 반복 금지 규칙
- 같은 질문에 다른 접근 규칙
- 추임새/판박이 응답 금지

### 8.4 포맷 붕괴 (Format Collapse)

**방어:**
- 구조화된 응답 포맷 강제 (섹션 5의 recency 위치에 배치)
- Jinja2 템플릿으로 프롬프트 구조 고정 — 매번 동일한 규칙 전달 보장

---

## 9. 자유질문 모드 상세

### 9.1 역할

- 일반 어시스턴트 (문제풀이 튜터가 아님)
- 데이터 분석 관련 질문에 답변
- 정답 금지 규칙은 유지 (습관적으로라도 직접 답을 주지 않는 톤)
- 데이터 분석 외 질문은 거절

### 9.2 향후 확장: RAG

- 자유질문 모드에 RAG를 붙여서 자사 보유 자료 기반 답변 예정
- 현재는 Gemini 자체 지식으로 답변
- RAG 도입 시 `system_free.j2`에 검색 결과 주입 블록 추가 예정

### 9.3 `system_instruction` 내용

자유질문 모드에서는 문제/정답/데이터셋이 없으므로 `system_instruction`이 단순합니다:

```
{% include 'system_base.j2' %}  ← 공통 규칙 (톤, 언어, 길이, 거절)

[Role]
You are a general data analysis assistant.
Answer questions about data analysis concepts, tools, and methods.
Do not provide direct answers — guide the user's thinking process.
```

---

## 10. 프롬프트 수정 가이드

### 10.1 수정 프로세스

```
1. 영어 템플릿 (templates/*.j2) 수정
2. 한국어 참조본 (templates/ko/*.j2) 동기화
3. 로컬 테스트 (동일 payload로 응답 품질 확인)
4. PR 제출 — 리뷰어는 영어/한국어 일치 여부 확인
```

### 10.2 Jinja2 문법 요약

```jinja2
{{ variable }}                          # 변수 출력
{% if condition %}...{% endif %}        # 조건문
{% for item in list %}...{% endfor %}   # 반복문
{% include 'other_template.j2' %}      # 다른 템플릿 삽입
{# 이것은 주석입니다 #}                  # 주석 (렌더링 안 됨)
```

### 10.3 새 변수 추가 시

1. `prompt_builder.py`의 `render()` 호출에 변수 추가
2. 해당 `.j2` 템플릿에서 `{{ new_variable }}` 사용
3. `ko/` 참조본에도 반영

### 10.4 주의사항

- 프롬프트 문자열을 Python 코드에 하드코딩하지 않을 것
- 모든 프롬프트 텍스트는 `.j2` 파일에만 존재
- `system_instruction`의 텍스트가 변하면 implicit caching이 깨짐 — 고정 부분을 함부로 수정하지 않을 것
- 동적 데이터(문제 내용 등)는 Jinja2 변수로 주입 — 이건 캐시에 영향 없음 (변수가 같은 값이면 동일 텍스트)

---

## 11. 관련 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| FastAPI 프로젝트 컨벤션 | `docs/ChatBot/fastapi_project_convention.md` | 프로젝트 구조, payload, 실행 방법 |
| Spring ChatBot 컨벤션 | `docs/ChatBot/convention.md` | Spring 측 클린아키텍쳐 규칙 |
| Payload 스펙 | `docs/ChatBot/handoff.md` | FastApiChatRequest/Response 상세 |
| 글로벌 컨벤션 | `docs/CONVENTION.md` | 에러코드, API 응답 등 |
