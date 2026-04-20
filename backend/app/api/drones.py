from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..db.database import get_db
from ..models.drone import Drone
from ..schemas.drone import DroneResponse
from ..schemas.diagnostic import DiagnosticResultResponse
from ..services.diagnostic_service import run_diagnostic

router = APIRouter(prefix="/drones", tags=["drones"])


@router.get("", response_model=List[DroneResponse])
def list_drones(db: Session = Depends(get_db)):
    return db.query(Drone).order_by(Drone.id).all()


@router.get("/{drone_id}", response_model=DroneResponse)
def get_drone(drone_id: int, db: Session = Depends(get_db)):
    drone = db.query(Drone).filter(Drone.id == drone_id).first()
    if not drone:
        raise HTTPException(status_code=404, detail=f"Drone {drone_id} not found")
    return drone


@router.post("/{drone_id}/diagnostic", response_model=DiagnosticResultResponse)
async def trigger_diagnostic(drone_id: int, db: Session = Depends(get_db)):
    drone = db.query(Drone).filter(Drone.id == drone_id).first()
    if not drone:
        raise HTTPException(status_code=404, detail=f"Drone {drone_id} not found")
    try:
        result = await run_diagnostic(drone_id, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result
