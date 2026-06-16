from dataclasses import dataclass
from itertools import combinations

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
    transactions = [
        completed_problem_set_ids & active_problem_set_ids
        for completed_problem_set_ids in completed_by_user.values()
    ]
    transactions = [
        transaction
        for transaction in transactions
        if transaction
    ]
    support_counts = _calculate_frequent_itemset_support_counts(transactions)
    association_rules = _generate_association_rules(
        support_counts=support_counts,
        total_transaction_count=len(transactions),
    )
    recommendations_by_user = {}

    for user_id, completed_problem_set_ids in completed_by_user.items():
        recommendations = _recommend_for_user(
            completed_problem_set_ids=completed_problem_set_ids & active_problem_set_ids,
            active_problem_set_ids=active_problem_set_ids,
            association_rules=association_rules,
            recommendation_count=recommendation_count,
        )

        if len(recommendations) == recommendation_count:
            recommendations_by_user[user_id] = recommendations

    return recommendations_by_user


def _calculate_frequent_itemset_support_counts(
    transactions: list[set[int]],
) -> dict[frozenset[int], int]:
    support_counts = {}

    current_frequent_itemsets = _find_frequent_single_itemsets(transactions)
    support_counts.update(current_frequent_itemsets)

    itemset_size = 2
    while current_frequent_itemsets and itemset_size <= MAX_ITEMSET_SIZE:
        candidates = _generate_candidates(
            previous_frequent_itemsets=set(current_frequent_itemsets),
            itemset_size=itemset_size,
        )

        current_frequent_itemsets = _count_frequent_candidates(
            transactions=transactions,
            candidates=candidates,
        )
        support_counts.update(current_frequent_itemsets)
        itemset_size += 1

    return support_counts


def _find_frequent_single_itemsets(
    transactions: list[set[int]],
) -> dict[frozenset[int], int]:
    item_counts = {}

    for transaction in transactions:
        for problem_set_id in transaction:
            itemset = frozenset({problem_set_id})
            item_counts[itemset] = item_counts.get(itemset, 0) + 1

    return _filter_by_min_support_count(item_counts)


def _generate_candidates(
    previous_frequent_itemsets: set[frozenset[int]],
    itemset_size: int,
) -> set[frozenset[int]]:
    candidates = set()
    previous_items = sorted(previous_frequent_itemsets, key=lambda item: sorted(item))

    for left_index, left in enumerate(previous_items):
        for right in previous_items[left_index + 1:]:
            candidate = left | right

            if len(candidate) != itemset_size:
                continue

            if _all_subsets_frequent(candidate, previous_frequent_itemsets):
                candidates.add(candidate)

    return candidates


def _all_subsets_frequent(
    candidate: frozenset[int],
    previous_frequent_itemsets: set[frozenset[int]],
) -> bool:
    return all(
        frozenset(subset) in previous_frequent_itemsets
        for subset in combinations(candidate, len(candidate) - 1)
    )


def _count_frequent_candidates(
    transactions: list[set[int]],
    candidates: set[frozenset[int]],
) -> dict[frozenset[int], int]:
    candidate_counts = {}

    for transaction in transactions:
        for candidate in candidates:
            if candidate.issubset(transaction):
                candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1

    return _filter_by_min_support_count(candidate_counts)


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


def _recommend_for_user(
    completed_problem_set_ids: set[int],
    active_problem_set_ids: set[int],
    association_rules: list[AssociationRule],
    recommendation_count: int,
) -> list[ProblemSetRecommendation]:
    best_rule_by_problem_set = {}

    for rule in association_rules:
        if not rule.antecedent_problem_set_ids.issubset(completed_problem_set_ids):
            continue

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
