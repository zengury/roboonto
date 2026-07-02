"""Readiness — run a Profile against a loaded Ontology and grade the result.

Output is a structured ReadinessReport that the CLI / CI / build session
can serialize. Callers decide how strict to be:
  - default: alpha / beta / customer-ready grade (lenient)
  - --require=customer-ready: exit non-zero unless the grade matches
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..api.loader import OntologyLoader, ValidationIssue
from .profile import Profile, RuleResult, load_profile


GRADE_ORDER = ["fail", "alpha", "beta", "customer-ready"]


@dataclass
class ReadinessReport:
    robot_id: str
    profile_id: str
    profile_reference: str
    results: list[RuleResult]
    grade: str
    score: float                           # 0.0 - 100.0 (must + should weighted)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    # ── derived views ─────────────────────────────────────────────────
    def failures_by_severity(self, severity: str) -> list[RuleResult]:
        return [r for r in self.results if r.rule.severity == severity and not r.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "robot_id": self.robot_id,
            "profile": self.profile_id,
            "reference_robot": self.profile_reference,
            "grade": self.grade,
            "score": round(self.score, 1),
            "counts": self.counts,
            "results": [
                {
                    "id": r.rule.id,
                    "severity": r.rule.severity,
                    "passed": r.passed,
                    "observed": r.observed,
                    "expected": r.expected,
                    "detail": r.detail,
                    "hint": r.rule.hint if not r.passed else "",
                }
                for r in self.results
            ],
        }

    def to_text(self, *, color: bool = False) -> str:
        green = "\033[32m" if color else ""
        red = "\033[31m" if color else ""
        yellow = "\033[33m" if color else ""
        reset = "\033[0m" if color else ""
        ok = lambda b: f"{green}✓{reset}" if b else f"{red}✗{reset}"
        sev_color = {"must": red, "should": yellow, "may": ""}

        lines = [
            f"RoboOnto Readiness — {self.robot_id}",
            f"  Profile:   {self.profile_id} (reference: {self.profile_reference})",
            f"  Grade:     {self.grade}",
            f"  Score:     {self.score:.1f} / 100",
            f"  Counts:    must {self.counts['must']['passed']}/{self.counts['must']['total']}"
            f"  should {self.counts['should']['passed']}/{self.counts['should']['total']}"
            f"  may {self.counts['may']['passed']}/{self.counts['may']['total']}",
            "",
        ]
        for sev in ("must", "should", "may"):
            sev_results = [r for r in self.results if r.rule.severity == sev]
            if not sev_results:
                continue
            lines.append(f"── {sev_color.get(sev,'')}{sev.upper()}{reset} ──")
            for r in sev_results:
                tag = ok(r.passed)
                lines.append(f"  {tag} [{r.rule.id}] {r.rule.description}")
                if not r.passed:
                    lines.append(f"        observed={r.observed!r}  expected={r.expected!r}")
                    if r.detail:
                        lines.append(f"        {r.detail}")
                    if r.rule.hint:
                        lines.append(f"        hint: {r.rule.hint}")
            lines.append("")
        return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# Grade computation
# ────────────────────────────────────────────────────────────────────

def grade(results: list[RuleResult], *, beta_threshold_pct: float = 70.0) -> tuple[str, float]:
    """Compute (grade, score).

    Score: weighted percentage where must=2x, should=1x, may=0.5x.
    Grade ladder:
      fail            any must fails
      alpha           all must pass; <70% should
      beta            all must pass; ≥70% should; not 100% should
      customer-ready  all must pass; 100% should
    """
    must = [r for r in results if r.rule.severity == "must"]
    should = [r for r in results if r.rule.severity == "should"]
    may = [r for r in results if r.rule.severity == "may"]

    must_pass = sum(1 for r in must if r.passed)
    should_pass = sum(1 for r in should if r.passed)
    may_pass = sum(1 for r in may if r.passed)

    # Weighted score
    weights = (2.0 * len(must)) + len(should) + (0.5 * len(may))
    earned = (2.0 * must_pass) + should_pass + (0.5 * may_pass)
    score = (100.0 * earned / weights) if weights > 0 else 0.0

    if must and must_pass < len(must):
        return "fail", score
    if not should:
        return "customer-ready", score
    should_pct = 100.0 * should_pass / len(should)
    if should_pass == len(should):
        return "customer-ready", score
    if should_pct >= beta_threshold_pct:
        return "beta", score
    return "alpha", score


# ────────────────────────────────────────────────────────────────────
# Top-level entrypoint
# ────────────────────────────────────────────────────────────────────

class Readiness:
    """Run a profile against an ontology directory and produce a report."""

    def __init__(self, ontology_dir: str | Path, profile: Profile | str | Path = "customer_v1"):
        self.ontology_dir = Path(ontology_dir)
        if isinstance(profile, Profile):
            self.profile = profile
        else:
            self.profile = load_profile(profile)

    def run(self) -> ReadinessReport:
        loader = OntologyLoader(self.ontology_dir)
        ont = loader.load()
        issues = loader.validate()
        # Inject loader issues + capability_boundary into ontology meta so
        # checks can read them without re-parsing files.
        ont.robot_meta["_issues"] = issues
        ont.robot_meta["_capability_boundary"] = self._read_capability_boundary()

        results = self.profile.evaluate(ont)
        g, score = grade(results)

        counts = {}
        for sev in ("must", "should", "may"):
            sev_results = [r for r in results if r.rule.severity == sev]
            counts[sev] = {
                "total": len(sev_results),
                "passed": sum(1 for r in sev_results if r.passed),
            }

        return ReadinessReport(
            robot_id=ont.robot_id,
            profile_id=self.profile.id,
            profile_reference=self.profile.reference_robot,
            results=results,
            grade=g,
            score=score,
            counts=counts,
        )

    def _read_capability_boundary(self) -> dict:
        path = self.ontology_dir / "capability_boundary.yaml"
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}
