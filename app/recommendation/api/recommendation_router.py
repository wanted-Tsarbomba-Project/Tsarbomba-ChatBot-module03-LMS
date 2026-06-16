from fastapi import APIRouter

from app.recommendation.schema.recommendation import (
    RecommendationGenerateRequest,
    RecommendationGenerateResponse,
)
from app.recommendation.service.recommendation_service import (
    generate_problem_set_recommendations,
)

router = APIRouter(
    prefix="/internal/recommendations",
    tags=["recommendations"],
)


@router.post(
    "/problem-sets/generate",
    response_model=RecommendationGenerateResponse,
    response_model_by_alias=True,
)
def generate_recommendations(
    request: RecommendationGenerateRequest,
) -> RecommendationGenerateResponse:
    return generate_problem_set_recommendations(request.recommendation_count)
