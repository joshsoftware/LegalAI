"""Combines all validation checks into one weighted confidence number."""

from collections import defaultdict

from cross_document_validation.services import validation_config as cfg
from cross_document_validation.services.dto import ScoreResult, ValidationResult


def compute_score(validation_results: list[ValidationResult]) -> ScoreResult:
    scores_by_type: dict[str, list[float]] = defaultdict(list)
    for result in validation_results:
        scores_by_type[result.check_type.value].append(result.score)

    mean_by_type = {
        check_type: sum(scores) / len(scores) for check_type, scores in scores_by_type.items()
    }

    observed_weight_total = sum(
        weight for check_type, weight in cfg.VALIDATION_WEIGHTS.items() if check_type in mean_by_type
    )

    if observed_weight_total == 0:
        return ScoreResult(overall_score=0.0, component_scores={})

    overall_score = (
        sum(
            cfg.VALIDATION_WEIGHTS[check_type] * mean_by_type[check_type]
            for check_type in mean_by_type
            if check_type in cfg.VALIDATION_WEIGHTS
        )
        / observed_weight_total
    )

    return ScoreResult(overall_score=overall_score, component_scores=mean_by_type)
