from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from datetime import datetime, timezone
from ..db.database import Base


class DiagnosticResult(Base):
    __tablename__ = "diagnostic_results"

    id = Column(Integer, primary_key=True, index=True)
    drone_id = Column(Integer, ForeignKey("drones.id"), nullable=False)
    battery_percent = Column(Float, nullable=False)
    rotor_ok = Column(Boolean, nullable=False)
    sensors_ok = Column(Boolean, nullable=False)
    communication_ok = Column(Boolean, nullable=False)
    computed_status = Column(String, nullable=False)
    message = Column(String, nullable=False)
    checked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
