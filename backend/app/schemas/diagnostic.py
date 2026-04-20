from pydantic import BaseModel, ConfigDict
from datetime import datetime


class DiagnosticResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    drone_id: int
    battery_percent: float
    rotor_ok: bool
    sensors_ok: bool
    communication_ok: bool
    computed_status: str
    message: str
    checked_at: datetime
