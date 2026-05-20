"""Registry of jurisdictions known to the bot.

`get_jurisdiction(code)` returns a populated Jurisdiction if the code is known,
otherwise an `UnknownJurisdiction(code)` so the bot still works gracefully —
just with a "limited data" disclaimer in its system prompt.
"""

from src.jurisdictions.base import Jurisdiction
from src.jurisdictions.ontario import OntarioJurisdiction
from src.jurisdictions.stubs import STUB_JURISDICTIONS
from src.jurisdictions.unknown import UnknownJurisdiction

JURISDICTIONS: dict[str, Jurisdiction] = {
    "CA-ON": OntarioJurisdiction(),
    **{j.code: j for j in STUB_JURISDICTIONS},
}


def get_jurisdiction(code: str) -> Jurisdiction:
    if code in JURISDICTIONS:
        return JURISDICTIONS[code]
    return UnknownJurisdiction(code=code)
