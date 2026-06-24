import logging
from time import perf_counter

from app.monitoring.metrics import (
    RECOMMENDATION_GENERATION_STAGE_DURATION,
    RECOMMENDATION_GENERATION_STAGE_LAST_DURATION,
)
from app.recommendation.schema.recommendation import (
    ProblemSetRecommendationResponse,
    RecommendationGenerateResponse,
    UserProblemSetRecommendationResponse,
)
from app.recommendation.service.apriori import generate_apriori_recommendations
from app.recommendation.service.repository import (
    find_active_problem_set_ids,
    find_completed_problem_sets_by_user,
)

logger = logging.getLogger(__name__)
RECOMMENDATION_ALGORITHM = "ASSOCIATION_RULE_BRUTE_FORCE"


def generate_problem_set_recommendations(
    recommendation_count: int,
) -> RecommendationGenerateResponse:
    total_started_at = perf_counter()

    started_at = perf_counter()
    completed_by_user = find_completed_problem_sets_by_user()
    active_problem_set_ids = find_active_problem_set_ids()
    scale_users = str(len(completed_by_user))
    db_fetch_seconds = perf_counter() - started_at
    _record_stage_duration("db_fetch", scale_users, db_fetch_seconds)

    started_at = perf_counter()
    recommendations_by_user = generate_apriori_recommendations(
        completed_by_user=completed_by_user,
        active_problem_set_ids=active_problem_set_ids,
        recommendation_count=recommendation_count,
    )
    algorithm_seconds = perf_counter() - started_at
    _record_stage_duration("algorithm_total", scale_users, algorithm_seconds)

    started_at = perf_counter()
    recommendations = [
        UserProblemSetRecommendationResponse(
            user_id=user_id,
            problem_sets=[
                ProblemSetRecommendationResponse(
                    problem_set_id=recommendation.problem_set_id,
                    support=recommendation.support,
                    confidence=recommendation.confidence,
                    lift=recommendation.lift,
                    rank_no=recommendation.rank_no,
                    algorithm=RECOMMENDATION_ALGORITHM,
                )
                for recommendation in recommendations
            ],
        )
        for user_id, recommendations in recommendations_by_user.items()
    ]
    response_build_seconds = perf_counter() - started_at
    total_seconds = perf_counter() - total_started_at
    _record_stage_duration("response_build", scale_users, response_build_seconds)
    _record_stage_duration("total", scale_users, total_seconds)

    logger.info(
        "event=recommendation_python_generation_completed "
        "inputUsers=%s activeProblemSets=%s generatedUsers=%s "
        "dbFetchMs=%.3f algorithmMs=%.3f responseBuildMs=%.3f totalMs=%.3f",
        len(completed_by_user),
        len(active_problem_set_ids),
        len(recommendations_by_user),
        db_fetch_seconds * 1000,
        algorithm_seconds * 1000,
        response_build_seconds * 1000,
        total_seconds * 1000,
    )

    return RecommendationGenerateResponse(
        recommendations=recommendations,
    )


def _record_stage_duration(stage: str, scale_users: str, duration_seconds: float) -> None:
    labels = {"stage": stage, "scale_users": scale_users}
    RECOMMENDATION_GENERATION_STAGE_DURATION.labels(**labels).observe(duration_seconds)
    RECOMMENDATION_GENERATION_STAGE_LAST_DURATION.labels(**labels).set(duration_seconds)
