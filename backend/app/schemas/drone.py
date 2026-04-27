from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class DroneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    raspberry_pi_id: str
    facility_name: str
    status: str
    battery_percent: float
    rotor_ok: bool
    sensors_ok: bool
    communication_ok: bool
    max_payload_kg: float
    last_check_at: Optional[datetime]
    last_error_message: Optional[str]
