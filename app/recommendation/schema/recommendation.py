from pydantic import BaseModel, ConfigDict, Field


class RecommendationGenerateRequest(BaseModel):
    recommendation_count: int = Field(default=3, gt=0, alias="recommendationCount")

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class ProblemSetRecommendationResponse(BaseModel):
    problem_set_id: int = Field(alias="problemSetId")
    support: float
    confidence: float
    lift: float
    rank_no: int = Field(alias="rankNo")
    algorithm: str = "ASSOCIATION_RULE_BRUTE_FORCE"

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class UserProblemSetRecommendationResponse(BaseModel):
    user_id: int = Field(alias="userId")
    problem_sets: list[ProblemSetRecommendationResponse] = Field(alias="problemSets")

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)


class RecommendationGenerateResponse(BaseModel):
    recommendations: list[UserProblemSetRecommendationResponse]
