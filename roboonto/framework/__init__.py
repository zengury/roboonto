"""roboonto.framework — completeness profile + readiness grading.

Turns the implicit "what a customer-ready ontology looks like" knowledge
that lives in the X2 reference into machine-checkable rules.

Three rule severities:
  - must:   without it, the ontology cannot be released as a customer build.
  - should: expected for a customer-ready build; missing → demoted to beta.
  - may:    nice to have; only affects the maturity score, not the grade.

Three grades:
  - alpha:           all `must` rules pass.
  - beta:            alpha + ≥70% of `should` rules pass.
  - customer-ready:  beta + 100% of `should` rules pass.
"""

from .profile import Profile, Rule, RuleResult, load_profile
from .readiness import Readiness, ReadinessReport, grade

__all__ = [
    "Profile",
    "Rule",
    "RuleResult",
    "load_profile",
    "Readiness",
    "ReadinessReport",
    "grade",
]
