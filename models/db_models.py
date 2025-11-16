from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class QuizRecord(Base):

    __tablename__ = "quizzes"

    id = Column(String(64), primary_key=True)
    url = Column(String(500), nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    scraped_content = Column(Text, nullable=False)
    key_entities = Column(JSON, nullable=False)
    sections = Column(JSON, nullable=False)
    quiz_json = Column(Text, nullable=False)
    related_topics = Column(JSON, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    easy_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    hard_count = Column(Integer, nullable=False, default=0)
