"""User profile for the angler."""

from pydantic import BaseModel, Field

from src.models.jurisdiction import JurisdictionCode


class Location(BaseModel):
    name: str
    lat: float
    lng: float


class UserProfile(BaseModel):
    home_jurisdiction: JurisdictionCode
    frequented_jurisdictions: list[JurisdictionCode] = Field(default_factory=list)
    home_location: Location | None = None
    target_species: list[str] = Field(default_factory=list)
    gear: list[dict] = Field(default_factory=list)
    budget: float | None = None
    skill_level: str = "intermediate"
    fishing_style: str = ""
    preferences: str = ""

    @classmethod
    def default(cls) -> "UserProfile":
        """Toronto-based starter profile matching CLAUDE.md."""
        return cls(
            home_jurisdiction="CA-ON",
            home_location=Location(name="Toronto, ON", lat=43.6532, lng=-79.3832),
            target_species=[
                "smallmouth bass",
                "brook trout",
                "northern pike",
                "walleye",
            ],
            fishing_style="stream + small lakes",
            preferences=(
                "Top priority is exploration over catch optimization. "
                "Interested in all species — including microfishing targets "
                "(darters, dace, madtoms, shiners, chubs, lampreys)."
            ),
        )
