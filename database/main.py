from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base  # Corrected import path
from database.crud import create_outlet
from scraper.scraper import scrape_subway_outlets

# Initialize database
engine = create_engine("sqlite:///database/subway.db")
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Run scraper
db = SessionLocal()
scrape_subway_outlets(db)
db.close()
