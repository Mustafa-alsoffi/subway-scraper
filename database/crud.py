from sqlalchemy.orm import Session
from database.models import Outlet  # Corrected import path


def create_outlet(db: Session, name: str, address: str, hours: str, waze_link: str):
    outlet = Outlet(
        name=name,
        address=address,
        operating_hours=hours,
        waze_link=waze_link
    )
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    return outlet
