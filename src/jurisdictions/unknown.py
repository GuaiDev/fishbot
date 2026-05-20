"""Fallback jurisdiction for codes not in the registry."""

from dataclasses import dataclass

from src.jurisdictions.base import Jurisdiction


@dataclass(kw_only=True)
class UnknownJurisdiction(Jurisdiction):
    name: str = "Unknown jurisdiction"
    country: str = ""
    has_detailed_data: bool = False

    def regulatory_context(self) -> str:
        return (
            f"## Unknown jurisdiction ({self.code})\n\n"
            f"I don't recognize the jurisdiction code `{self.code}`. I have no "
            f"populated regulatory or species data for this region. Please verify "
            f"all rules with the appropriate fish & wildlife agency before fishing."
        )
