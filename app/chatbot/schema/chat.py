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
    explanation: Optional[str] = None  # 해설 없는 문제 존재 가능 (Spring 이 null 로 보냄)
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
