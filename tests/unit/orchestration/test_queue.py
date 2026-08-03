from __future__ import annotations

from experiments.orchestration.queue import ExperimentStage, expand_stage

FAMILIES = ("patchcore", "efficient_ad", "dinomaly")
CATEGORIES = (
    "can",
    "fabric",
    "fruit_jelly",
    "rice",
    "sheet_metal",
    "vial",
    "wallplugs",
    "walnuts",
)


def family_configs() -> dict[str, dict[str, object]]:
    return {
        family: {
            "family": family,
            "batch_size": 4,
            "oom_fallback_batch_size": 1,
        }
        for family in FAMILIES
    }


def test_screening_expands_three_families_eight_categories_and_seed_42() -> None:
    stage = ExperimentStage(
        name="screening",
        family_configs=family_configs(),
        dataset_manifest_sha256="a" * 64,
    )

    queue = expand_stage(stage)

    assert len(queue) == 24
    assert {item.seed for item in queue} == {42}
    assert [(item.category, item.model_family, item.seed) for item in queue] == sorted(
        (item.category, item.model_family, item.seed) for item in queue
    )
    assert {item.category for item in queue} == set(CATEGORIES)
    assert {item.model_family for item in queue} == set(FAMILIES)


def test_replication_expands_only_frozen_contenders_and_new_seeds() -> None:
    contenders = {
        category: ("dinomaly", "patchcore") if index % 2 else ("efficient_ad", "dinomaly")
        for index, category in enumerate(CATEGORIES)
    }
    stage = ExperimentStage(
        name="replication",
        family_configs=family_configs(),
        dataset_manifest_sha256="a" * 64,
        contenders=contenders,
    )

    queue = expand_stage(stage)

    assert len(queue) == 32
    assert {item.seed for item in queue} == {17, 2026}
    assert all(item.model_family in contenders[item.category] for item in queue)
    assert [(item.category, item.model_family, item.seed) for item in queue] == sorted(
        (item.category, item.model_family, item.seed) for item in queue
    )


def test_queue_identity_changes_when_config_changes() -> None:
    first_stage = ExperimentStage(
        name="screening",
        family_configs=family_configs(),
        dataset_manifest_sha256="a" * 64,
    )
    changed_configs = family_configs()
    changed_configs["patchcore"]["batch_size"] = 2
    second_stage = ExperimentStage(
        name="screening",
        family_configs=changed_configs,
        dataset_manifest_sha256="a" * 64,
    )

    first = next(item for item in expand_stage(first_stage) if item.model_family == "patchcore")
    second = next(item for item in expand_stage(second_stage) if item.model_family == "patchcore")

    assert first.identity != second.identity
