"""User profile load/save (JSON-backed at data/user_profile.json)."""

from pathlib import Path

from src.models.profile import UserProfile

PROFILE_PATH = Path("data/user_profile.json")


def load_profile(path: Path | None = None) -> UserProfile:
    p = path or PROFILE_PATH
    if not p.exists():
        profile = UserProfile.default()
        save_profile(profile, path=p)
        return profile
    return UserProfile.model_validate_json(p.read_text())


def save_profile(profile: UserProfile, path: Path | None = None) -> None:
    p = path or PROFILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(profile.model_dump_json(indent=2))
