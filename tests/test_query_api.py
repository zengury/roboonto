"""Contract tests for roboonto.api.query public API.

Tests run against both the X2 reference and the minimal_valid fixture so
the API holds for differently-shaped ontologies.
"""
from __future__ import annotations

from roboonto.api.query import Query, action_for_llm


# ── basic existence ──────────────────────────────────────────────────

def test_objects_of_type_returns_list(x2_ontology):
    q = Query(x2_ontology)
    modes = q.objects_of_type("Mode")
    assert isinstance(modes, list)
    assert all(o.get("type") == "Mode" for o in modes)


def test_get_resolves_object_or_action(x2_ontology):
    q = Query(x2_ontology)
    assert q.exists("agibot_x2.hw.compute.pc1")
    obj = q.get("agibot_x2.hw.compute.pc1")
    assert obj is not None
    assert obj["type"] == "ComputeUnit"


def test_get_returns_none_for_missing(x2_ontology):
    q = Query(x2_ontology)
    assert q.get("not_a_real_id") is None
    assert q.exists("not_a_real_id") is False


# ── filter by properties ─────────────────────────────────────────────

def test_where_filters_by_properties(x2_ontology):
    q = Query(x2_ontology)
    development_units = q.where("ComputeUnit", role="development")
    motion_units = q.where("ComputeUnit", role="motion_control")
    assert development_units, "X2 should declare a development unit"
    assert motion_units, "X2 should declare a motion control unit"
    assert development_units != motion_units


# ── action queries ───────────────────────────────────────────────────

def test_all_actions_nonempty(x2_ontology):
    q = Query(x2_ontology)
    actions = q.all_actions()
    assert len(actions) >= 10
    assert all("type_id" in a for a in actions)


def test_actions_by_safety_class(x2_ontology):
    q = Query(x2_ontology)
    motion = q.actions_by_safety_class("MOTION")
    assert motion, "X2 has at least one MOTION action"
    info = q.actions_by_safety_class("INFO")
    assert info, "X2 has at least one INFO action"


# ── status / events ──────────────────────────────────────────────────

def test_status_bits_filter_by_severity(x2_ontology):
    q = Query(x2_ontology)
    errs = q.status_bits_by_severity("error")
    assert all((b.get("properties") or {}).get("severity") == "error" for b in errs)


def test_status_bits_on_field(x2_ontology):
    q = Query(x2_ontology)
    pmu = q.status_bits_on_field("pmu_bool_status")
    assert len(pmu) >= 5


# ── action_for_llm helper ────────────────────────────────────────────

def test_action_for_llm_compaction(x2_ontology):
    q = Query(x2_ontology)
    actions = q.all_actions()
    spec = action_for_llm(actions[0])
    assert {"id", "description", "invoker", "parameters",
            "preconditions", "affects", "safety_class"}.issubset(spec.keys())


# ── minimal fixture ──────────────────────────────────────────────────

def test_minimal_fixture_query_works(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    assert q.exists("minibot.hw.compute.main")
    assert q.objects_of_type("Mode")
    assert q.all_actions()


def test_minimal_fixture_action_lookup(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    assert q.get("set_velocity") is not None
    assert q.get("get_mode") is not None


# ── capability / service semantics ───────────────────────────────────

def test_minimal_fixture_lists_capabilities(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    caps = q.list_capabilities()
    assert [c["id"] for c in caps] == ["minibot.cap.velocity_control"]


def test_find_capabilities_by_kind_and_exposure(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    caps = q.find_capabilities(
        capability_kind="actuation",
        exposed_via="set_velocity",
    )
    assert [c["id"] for c in caps] == ["minibot.cap.velocity_control"]


def test_capability_context_resolves_provider_parameters_and_interfaces(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    cap_id = "minibot.cap.velocity_control"
    providers = q.capability_providers(cap_id)
    parameters = q.capability_parameters(cap_id)
    interfaces = q.capability_interfaces(cap_id)
    assert [p["id"] for p in providers] == ["minibot.sw.motion.controller"]
    assert [p["id"] for p in parameters] == ["minibot.cap.param.velocity_control.linear_x"]
    assert {i.get("id") or i.get("type_id") for i in interfaces} == {
        "set_velocity",
        "minibot.if.topic.cmd_vel",
    }


def test_explain_service_fit_uses_requirement_links(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    fit = q.explain_service_fit("minibot.req.drive_base")
    assert fit["required_capabilities"] == ["actuation"]
    assert len(fit["matches"]) == 1
    assert fit["matches"][0]["capability"]["id"] == "minibot.cap.velocity_control"
    assert "linked_by_satisfies_requirement" in fit["matches"][0]["reasons"]


def test_capability_summary_is_agent_ready(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    summary = q.capability_summary("minibot.cap.velocity_control")
    assert summary is not None
    assert summary["kind"] == "actuation"
    assert [a["id"] for a in summary["actions"]] == ["set_velocity"]
    assert summary["interfaces"][0]["name"] == "/minibot/cmd_vel"


def test_agent_affordance_menu_groups_actions_by_capability(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    menu = q.agent_affordance_menu()
    assert [item["id"] for item in menu] == ["minibot.cap.velocity_control"]
    assert menu[0]["providers"][0]["id"] == "minibot.sw.motion.controller"


def test_standard_mappings_available(minimal_valid_ontology):
    q = Query(minimal_valid_ontology)
    standards = q.standard_mappings()["standards"]
    assert {s["id"] for s in standards} >= {"ieee_1872_2_aur", "roso"}
