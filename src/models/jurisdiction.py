"""ISO 3166-2 jurisdiction code type (e.g., "CA-ON", "US-MI")."""

from typing import Annotated

from pydantic import StringConstraints

JurisdictionCode = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z]{2}-[A-Z0-9]{1,3}$"),
]
