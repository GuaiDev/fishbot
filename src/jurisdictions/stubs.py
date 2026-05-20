"""Named-stub jurisdictions — name + country known, no detailed adapters yet.

Listed in the priority order from docs/planning/fishing_ai_multi_jurisdiction.md
Section 5: build out adapters in this order as the user actually fishes those regions.
"""

from src.jurisdictions.base import Jurisdiction

STUB_JURISDICTIONS: list[Jurisdiction] = [
    Jurisdiction(code="US-MI", name="Michigan", country="US"),
    Jurisdiction(code="US-NY", name="New York", country="US"),
    Jurisdiction(code="CA-QC", name="Quebec", country="CA"),
    Jurisdiction(code="US-MN", name="Minnesota", country="US"),
    Jurisdiction(code="US-WI", name="Wisconsin", country="US"),
    Jurisdiction(code="CA-BC", name="British Columbia", country="CA"),
]
