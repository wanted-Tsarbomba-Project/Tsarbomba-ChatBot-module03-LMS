from typing import Optional
from pydantic import BaseModel


class ProblemSetInfo(BaseModel):
    problem_set_id: int
    title: str
    description: str


class ProblemInfo(BaseModel):
    title: str
    content: str
    problem_type: str  # "CODE" or "TEXT"
    answer: Optional[str] = None
    explanation: str
    submitted_answer: Optional[str] = None


class SessionProgress(BaseModel):
    current_problem_number: int


class DatasetInfo(BaseModel):
    meta_data: str  # JSON string ex) "[\"id\", \"value\"]"


class ConversationMessage(BaseModel):
    role: str  # "user" or "ai"
    content: str


class ChatRequest(BaseModel):
    user_message: str
    problem_set: Optional[ProblemSetInfo] = None
    problems: Optional[list[ProblemInfo]] = None
    session_progress: Optional[SessionProgress] = None
    dataset: Optional[DatasetInfo] = None
    conversation_history: Optional[list[ConversationMessage]] = None


class ChatResponse(BaseModel):
    answer: str
    is_answer_detected: bool = False
    retry_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
