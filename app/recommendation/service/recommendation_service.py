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


def generate_problem_set_recommendations(
    recommendation_count: int,
) -> RecommendationGenerateResponse:
    completed_by_user = find_completed_problem_sets_by_user()
    active_problem_set_ids = find_active_problem_set_ids()

    recommendations_by_user = generate_apriori_recommendations(
        completed_by_user=completed_by_user,
        active_problem_set_ids=active_problem_set_ids,
        recommendation_count=recommendation_count,
    )

    return RecommendationGenerateResponse(
        recommendations=[
            UserProblemSetRecommendationResponse(
                user_id=user_id,
                problem_sets=[
                    ProblemSetRecommendationResponse(
                        problem_set_id=recommendation.problem_set_id,
                        support=recommendation.support,
                        confidence=recommendation.confidence,
                        lift=recommendation.lift,
                        rank_no=recommendation.rank_no,
                        algorithm="APRIORI",
                    )
                    for recommendation in recommendations
                ],
            )
            for user_id, recommendations in recommendations_by_user.items()
        ],
    )
