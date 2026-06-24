from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.chatbot.api.chat_router import router
from app.monitoring.api.monitoring_router import router as monitoring_router
from app.recommendation.api.recommendation_router import router as recommendation_router

app = FastAPI(
    title="tsarbomba ChatBot API",
    description="데이터 분석 튜터링 AI 챗봇 서버",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(recommendation_router)
app.include_router(monitoring_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
