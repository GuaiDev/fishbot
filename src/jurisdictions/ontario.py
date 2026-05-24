"""Ontario — the first fully-modeled jurisdiction in the bot."""

from dataclasses import dataclass

from src.jurisdictions.base import Jurisdiction


@dataclass(kw_only=True)
class OntarioJurisdiction(Jurisdiction):
    code: str = "CA-ON"
    name: str = "Ontario"
    country: str = "CA"
    has_detailed_data: bool = True

    def regulatory_context(self) -> str:
        return (
            "## Ontario (CA-ON)\n\n"
            "Ontario fishing is regulated by the Ontario Ministry of Natural Resources "
            "and Forestry (MNRF).\n\n"
            "- Anglers aged 18-64 need an Outdoors Card plus a valid fishing licence.\n"
            "- Regulations are zone-based: Ontario is split into 20 Fisheries Management "
            "Zones (FMZs). Seasons, limits, and slot sizes vary by zone and by water body.\n"
            "- The annual Recreational Fishing Regulations Summary published by MNRF is "
            "the authoritative reference. Specific water bodies can be checked on Fish ON-Line.\n"
            "- Border waters with the US (Lake Erie, Huron, Ontario, St. Lawrence River, "
            "Lake of the Woods, Rainy Lake) have binational considerations — possession may "
            "depend on which side of the line a fish was caught on.\n"
            "- Indigenous/First Nations waters and reserves are governed separately. If a "
            "question concerns those waters, flag it and direct the user to the relevant "
            "First Nation's authority.\n\n"
            "Use the get_regulations tool to look up actual zone text from the MNRF "
            "Recreational Fishing Regulations Summary (parsed from the official PDF). "
            "Always remind the user to verify current-year specifics with MNRF before "
            "relying on any specific limit, season, or slot size."
        )
