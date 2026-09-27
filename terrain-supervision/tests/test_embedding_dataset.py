"""Preparation tests for the future embedding evaluation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.embedding_dataset import DEVELOPMENT, VALIDATION, summary, validate_splits


def test_embedding_splits_are_valid_and_disjoint():
    validate_splits()
    assert {example.unfavorable for example in DEVELOPMENT} == {False, True}
    assert {example.unfavorable for example in VALIDATION} == {False, True}
    assert {example.id for example in DEVELOPMENT}.isdisjoint(
        {example.id for example in VALIDATION})


def test_embedding_dataset_summary_is_stable():
    dataset = summary()
    assert dataset["development_total"] == 49
    assert dataset["validation_total"] == 24
    assert dataset["development_attacks"] == 22
    assert dataset["validation_attacks"] == 12
