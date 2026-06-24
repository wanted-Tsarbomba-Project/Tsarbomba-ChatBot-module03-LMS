from prometheus_client import Gauge, Histogram

RECOMMENDATION_GENERATION_STAGE_DURATION = Histogram(
    "recommendation_python_generation_stage_duration_seconds",
    "Python recommendation generation duration by stage.",
    ["stage", "scale_users"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)

RECOMMENDATION_GENERATION_STAGE_LAST_DURATION = Gauge(
    "recommendation_python_generation_stage_last_duration_seconds",
    "Last Python recommendation generation duration by stage.",
    ["stage", "scale_users"],
)

RECOMMENDATION_GENERATION_SCALE = Gauge(
    "recommendation_python_generation_scale",
    "Last Python recommendation generation scale values.",
    ["type"],
)
