"""Frozen migration/test defaults only. Runtime rules come from master records."""
import json
from pathlib import Path


def seed_documents():
    path = Path(__file__).parent / 'data' / 'failure_classification_review_defaults.json'
    return json.loads(path.read_text())


INITIAL_CLASSIFICATIONS = tuple(row['classification_name'] for row in seed_documents())


def seed_legacy_aliases():
    return {alias: row['classification_name'] for row in seed_documents()
            for alias in row.get('legacy_aliases', '').splitlines() if alias}


def seed_configuration():
    from engineering.controllers.failure_classification import configuration_from_documents
    return configuration_from_documents(seed_documents())
