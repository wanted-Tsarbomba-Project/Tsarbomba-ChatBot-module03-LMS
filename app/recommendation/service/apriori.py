from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

from app.monitoring.metrics import (
    RECOMMENDATION_GENERATION_SCALE,
    RECOMMENDATION_GENERATION_STAGE_DURATION,
    RECOMMENDATION_GENERATION_STAGE_LAST_DURATION,
)

MIN_SUPPORT_COUNT = 2
MAX_ITEMSET_SIZE = 4


@dataclass
class ProblemSetRecommendation:
    problem_set_id: int
    support: float
    confidence: float
    lift: float
    rank_no: int


@dataclass
class AssociationRule:
    antecedent_problem_set_ids: frozenset[int]
    target_problem_set_id: int
    support: float
    confidence: float
    lift: float


def generate_apriori_recommendations(
    completed_by_user: dict[int, set[int]],
    active_problem_set_ids: set[int],
    recommendation_count: int,
) -> dict[int, list[ProblemSetRecommendation]]:
    scale_users = str(len(completed_by_user))
    started_at = perf_counter()
    transactions = [
        completed_problem_set_ids & active_problem_set_ids
        for completed_problem_set_ids in completed_by_user.values()
    ]
    transactions = [
        transaction
        for transaction in transactions
        if transaction
    ]
    _record_stage_duration("transaction_build", scale_users, perf_counter() - started_at)

    started_at = perf_counter()
    support_counts = _calculate_frequent_itemset_support_counts(transactions)
    _record_stage_duration("frequent_itemset", scale_users, perf_counter() - started_at)

    started_at = perf_counter()
    association_rules = _generate_association_rules(
        support_counts=support_counts,
        total_transaction_count=len(transactions),
    )
    _record_stage_duration("rule_generation", scale_users, perf_counter() - started_at)

    started_at = perf_counter()
    recommendations_by_user = {}
    rules_by_antecedent = _index_rules_by_antecedent(association_rules)

    for user_id, completed_problem_set_ids in completed_by_user.items():
        recommendations = _recommend_for_user(
            completed_problem_set_ids=completed_problem_set_ids & active_problem_set_ids,
            active_problem_set_ids=active_problem_set_ids,
            rules_by_antecedent=rules_by_antecedent,
            recommendation_count=recommendation_count,
        )

        # 응답에 포함되는 사용자는 프론트 계약상 항상 요청 개수만큼 추천을 가진다.
        if len(recommendations) == recommendation_count:
            recommendations_by_user[user_id] = recommendations

    _record_stage_duration("user_pick", scale_users, perf_counter() - started_at)
    _record_scale_values(
        input_users=len(completed_by_user),
        transactions=len(transactions),
        active_problem_sets=len(active_problem_set_ids),
        frequent_itemsets=len(support_counts),
        association_rules=len(association_rules),
        generated_users=len(recommendations_by_user),
        generated_recommendations=sum(
            len(recommendations)
            for recommendations in recommendations_by_user.values()
        ),
    )

    return recommendations_by_user


def _record_stage_duration(stage: str, scale_users: str, duration_seconds: float) -> None:
    labels = {"stage": stage, "scale_users": scale_users}
    RECOMMENDATION_GENERATION_STAGE_DURATION.labels(**labels).observe(duration_seconds)
    RECOMMENDATION_GENERATION_STAGE_LAST_DURATION.labels(**labels).set(duration_seconds)


def _record_scale_values(
    input_users: int,
    transactions: int,
    active_problem_sets: int,
    frequent_itemsets: int,
    association_rules: int,
    generated_users: int,
    generated_recommendations: int,
) -> None:
    values = {
        "input_users": input_users,
        "transactions": transactions,
        "active_problem_sets": active_problem_sets,
        "frequent_itemsets": frequent_itemsets,
        "association_rules": association_rules,
        "generated_users": generated_users,
        "generated_recommendations": generated_recommendations,
    }

    for metric_type, value in values.items():
        RECOMMENDATION_GENERATION_SCALE.labels(type=metric_type).set(value)


def _calculate_frequent_itemset_support_counts(
    transactions: list[set[int]],
) -> dict[frozenset[int], int]:
    item_counts = {}

    for transaction in transactions:
        sorted_transaction = sorted(transaction)
        max_size = min(len(sorted_transaction), MAX_ITEMSET_SIZE)

        for itemset_size in range(1, max_size + 1):
            for itemset in combinations(sorted_transaction, itemset_size):
                frozen_itemset = frozenset(itemset)
                item_counts[frozen_itemset] = item_counts.get(frozen_itemset, 0) + 1

    return _filter_by_min_support_count(item_counts)


def _filter_by_min_support_count(
    item_counts: dict[frozenset[int], int],
) -> dict[frozenset[int], int]:
    return {
        itemset: count
        for itemset, count in item_counts.items()
        if count >= MIN_SUPPORT_COUNT
    }


def _generate_association_rules(
    support_counts: dict[frozenset[int], int],
    total_transaction_count: int,
) -> list[AssociationRule]:
    if total_transaction_count == 0:
        return []

    rules = []

    for itemset, itemset_count in support_counts.items():
        if len(itemset) < 2:
            continue

        for target_problem_set_id in itemset:
            antecedent = frozenset(itemset - {target_problem_set_id})
            antecedent_count = support_counts.get(antecedent)
            target_count = support_counts.get(frozenset({target_problem_set_id}))

            if not antecedent_count or not target_count:
                continue

            support = itemset_count / total_transaction_count
            confidence = itemset_count / antecedent_count
            target_support = target_count / total_transaction_count
            lift = confidence / target_support if target_support > 0 else 0.0

            rules.append(
                AssociationRule(
                    antecedent_problem_set_ids=antecedent,
                    target_problem_set_id=target_problem_set_id,
                    support=round(support, 6),
                    confidence=round(confidence, 6),
                    lift=round(lift, 6),
                )
            )

    return rules


def _index_rules_by_antecedent(
    association_rules: list[AssociationRule],
) -> dict[frozenset[int], list[AssociationRule]]:
    rules_by_antecedent = defaultdict(list)

    for rule in association_rules:
        rules_by_antecedent[rule.antecedent_problem_set_ids].append(rule)

    return dict(rules_by_antecedent)


def _recommend_for_user(
    completed_problem_set_ids: set[int],
    active_problem_set_ids: set[int],
    rules_by_antecedent: dict[frozenset[int], list[AssociationRule]],
    recommendation_count: int,
) -> list[ProblemSetRecommendation]:
    best_rule_by_problem_set = {}

    sorted_completed_problem_set_ids = sorted(completed_problem_set_ids)
    max_antecedent_size = min(
        len(sorted_completed_problem_set_ids),
        MAX_ITEMSET_SIZE - 1,
    )

    for antecedent_size in range(1, max_antecedent_size + 1):
        for antecedent in combinations(sorted_completed_problem_set_ids, antecedent_size):
            matched_rules = rules_by_antecedent.get(frozenset(antecedent), [])

            for rule in matched_rules:
                if rule.target_problem_set_id in completed_problem_set_ids:
                    continue

                if rule.target_problem_set_id not in active_problem_set_ids:
                    continue

                current_best = best_rule_by_problem_set.get(rule.target_problem_set_id)

                if current_best is None or _is_better_rule(rule, current_best):
                    best_rule_by_problem_set[rule.target_problem_set_id] = rule

    sorted_rules = sorted(
        best_rule_by_problem_set.values(),
        key=lambda item: (
            item.lift,
            item.confidence,
            item.support,
            len(item.antecedent_problem_set_ids),
        ),
        reverse=True,
    )

    return [
        ProblemSetRecommendation(
            problem_set_id=rule.target_problem_set_id,
            support=rule.support,
            confidence=rule.confidence,
            lift=rule.lift,
            rank_no=index + 1,
        )
        for index, rule in enumerate(sorted_rules[:recommendation_count])
    ]


def _is_better_rule(
    candidate: AssociationRule,
    current_best: AssociationRule,
) -> bool:
    return (
        candidate.lift,
        candidate.confidence,
        candidate.support,
        len(candidate.antecedent_problem_set_ids),
    ) > (
        current_best.lift,
        current_best.confidence,
        current_best.support,
        len(current_best.antecedent_problem_set_ids),
    )
