"""Shared fixtures for roboonto tests."""
from pathlib import Path

import pytest

from roboonto.api.loader import OntologyLoader

ROOT = Path(__file__).resolve().parent.parent          # roboonto/ package root
X2_DIR = ROOT / "robots" / "agibot_x2"
TEMPLATE_DIR = ROOT / "robots" / "_template"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
MINIMAL_VALID_DIR = FIXTURES_DIR / "minimal_valid"


@pytest.fixture(scope="session")
def x2_dir() -> Path:
    return X2_DIR


@pytest.fixture(scope="session")
def template_dir() -> Path:
    return TEMPLATE_DIR


@pytest.fixture(scope="session")
def minimal_valid_dir() -> Path:
    return MINIMAL_VALID_DIR


@pytest.fixture(scope="session")
def x2_ontology(x2_dir):
    loader = OntologyLoader(x2_dir)
    ont = loader.load()
    issues = loader.validate()
    errors = [i for i in issues if i.severity == "error"]
    assert not errors, f"X2 ontology has loader errors: {errors}"
    return ont


@pytest.fixture(scope="session")
def minimal_valid_ontology(minimal_valid_dir):
    loader = OntologyLoader(minimal_valid_dir)
    ont = loader.load()
    issues = loader.validate()
    errors = [i for i in issues if i.severity == "error"]
    assert not errors, f"minimal fixture has loader errors: {errors}"
    return ont
