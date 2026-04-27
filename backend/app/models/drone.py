from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from ..db.database import Base


class Drone(Base):
    __tablename__ = "drones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    raspberry_pi_id = Column(String, nullable=False)
    # URL the backend uses to reach this drone's Pi agent
    agent_url = Column(String, nullable=False)
    facility_name = Column(String, nullable=False)
    # OFFLINE | IDLE | DIAGNOSTIC | READY | CHARGING | MAINTENANCE | ERROR
    status = Column(String, default="OFFLINE", nullable=False)
    battery_percent = Column(Float, default=0.0)
    rotor_ok = Column(Boolean, default=False)
    sensors_ok = Column(Boolean, default=False)
    communication_ok = Column(Boolean, default=False)
    max_payload_kg = Column(Float, default=5.0)
    last_check_at = Column(DateTime, nullable=True)
    last_error_message = Column(String, nullable=True)
