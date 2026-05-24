"""Pydantic model for PWQMN water quality field readings."""

from datetime import date

from pydantic import BaseModel, field_validator


class WaterQualityReading(BaseModel):
    record_id: str                      # str(Field_ID) from PWQMN field data
    station_id: str                     # Collection_Site (10-digit PWQMN code)
    station_name: str | None = None
    lat: float | None = None
    lng: float | None = None
    jurisdiction: str = "CA-ON"
    sampled_at: date
    do_mgl: float | None = None         # Dissolved_Oxygen_mgl
    ph: float | None = None             # Field_PH
    temp_c: float | None = None         # Water_Temperature_C
    conductivity_us_cm: float | None = None  # Specific_Conductance_uS_cm_1
    turbidity_fnu: float | None = None  # Turb_FNU

    @field_validator("ph")
    @classmethod
    def ph_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 14):
            raise ValueError(f"pH out of range 0-14: {v}")
        return v

    @field_validator("do_mgl")
    @classmethod
    def do_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError(f"DO cannot be negative: {v}")
        return v

    @field_validator("temp_c")
    @classmethod
    def temp_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (-5 <= v <= 40):
            raise ValueError(f"Temperature out of range -5 to 40°C: {v}")
        return v
