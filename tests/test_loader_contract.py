"""Contract tests for roboonto.api.loader public API.

These pin the externally-visible shape so downstream consumers
(roboonto-mcp, agent_runtime, customer integrations) don't break silently.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from roboonto.api.loader import (
    Ontology,
    OntologyLoader,
    ValidationIssue,
    load_and_report,
)


# ── public surface ───────────────────────────────────────────────────

def test_loader_public_methods_exist():
    for name in ("load", "validate", "summary"):
        assert hasattr(OntologyLoader, name), f"OntologyLoader.{name} missing"


def test_ontology_dataclass_shape():
    fields = {f for f in vars(Ontology(robot_id="x"))}
    assert {
        "robot_id",
        "robot_meta",
        "objects_by_id",
        "objects_by_type",
        "actions_by_id",
        "links",
        "links_by_source",
        "links_by_type",
    }.issubset(fields)


def test_ontology_count_returns_known_keys():
    o = Ontology(robot_id="x")
    c = o.count()
    assert {"objects", "actions", "links", "object_types"}.issubset(c.keys())


def test_validation_issue_str_includes_severity():
    iss = ValidationIssue(severity="error", category="cat", message="msg")
    s = str(iss)
    assert "ERROR" in s and "cat" in s and "msg" in s


# ── X2 baseline ──────────────────────────────────────────────────────

def test_x2_loads_and_validates_clean(x2_ontology):
    c = x2_ontology.count()
    assert c["objects"] >= 100
    assert c["actions"] >= 10
    assert c["links"] >= 50


def test_x2_validate_no_errors(x2_dir):
    loader = OntologyLoader(x2_dir)
    loader.load()
    issues = loader.validate()
    assert all(i.severity != "error" for i in issues), \
        [str(i) for i in issues if i.severity == "error"]


def test_x2_summary_runs(x2_dir):
    loader = OntologyLoader(x2_dir)
    loader.load()
    loader.validate()
    summary = loader.summary()
    assert "agibot_x2" in summary
    assert "objects" in summary


# ── error paths ──────────────────────────────────────────────────────

def test_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        OntologyLoader(Path("/no/such/path/abcd1234")).load()


def test_load_and_report_helper(x2_dir):
    ont, issues = load_and_report(x2_dir)
    assert ont.robot_id == "agibot_x2"
    assert isinstance(issues, list)


# ── public signature stability ──────────────────────────────────────

def test_loader_init_signature():
    sig = inspect.signature(OntologyLoader.__init__)
    assert "ontology_dir" in sig.parameters


# ── duplicate id detection ──────────────────────────────────────────

def test_duplicate_id_detected(tmp_path):
    """Loader must flag duplicate object ids as errors."""
    (tmp_path / "ontology.yaml").write_text(
        "robot:\n  id: x\nincludes:\n  - shard.yaml\n", encoding="utf-8"
    )
    (tmp_path / "shard.yaml").write_text(
        "objects:\n"
        "- {type: Mode, id: dup, properties: {mode_value: A}}\n"
        "- {type: Mode, id: dup, properties: {mode_value: B}}\n",
        encoding="utf-8",
    )
    loader = OntologyLoader(tmp_path)
    loader.load()
    loader.validate()
    cats = {i.category for i in loader.issues}
    assert "duplicate_id" in cats
