from sqlalchemy import Column, Integer, String, Float
from database.base import Base  # Corrected import path


class Outlet(Base):
    __tablename__ = "outlets"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    address = Column(String)
    operating_hours = Column(String)
    waze_link = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
