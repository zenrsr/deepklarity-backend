import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, or_, desc

from models import QuizRecord
from services.database_service import get_database_service

logger = logging.getLogger(__name__)


class QuizRepository:
    """Repository that manages quiz persistence in PostgreSQL."""

    def __init__(self):
        self.db_service = get_database_service()
        self.SessionLocal = sessionmaker(bind=self.db_service.get_engine(), expire_on_commit=False)

    def _serialize(self, record: QuizRecord) -> Dict[str, Any]:
        """Convert a QuizRecord into API-facing dict structure."""
        if not record:
            return {}

        try:
            quiz_questions = json.loads(record.quiz_json or "[]")
        except json.JSONDecodeError:
            quiz_questions = []

        generated_at = record.generated_at or datetime.utcnow()

        return {
            "id": record.id,
            "url": record.url,
            "title": record.title,
            "summary": record.summary,
            "key_entities": record.key_entities or {"people": [], "organizations": [], "locations": []},
            "sections": record.sections or [],
            "quiz": quiz_questions,
            "related_topics": record.related_topics or [],
            "generated_at": generated_at.isoformat(),
            "difficulty_distribution": {
                "easy": record.easy_count or 0,
                "medium": record.medium_count or 0,
                "hard": record.hard_count or 0,
            },
        }

    def save_quiz(
        self,
        quiz_id: str,
        url: str,
        title: str,
        summary: str,
        scraped_content: str,
        key_entities: Dict[str, Any],
        sections: List[str],
        quiz_questions: List[Dict[str, Any]],
        related_topics: List[str],
    ) -> Dict[str, Any]:
        session = self.SessionLocal()
        try:
            easy_count = sum(1 for q in quiz_questions if q.get("difficulty") == "easy")
            medium_count = sum(1 for q in quiz_questions if q.get("difficulty") == "medium")
            hard_count = sum(1 for q in quiz_questions if q.get("difficulty") == "hard")

            record = QuizRecord(
                id=quiz_id,
                url=url,
                title=title,
                summary=summary,
                scraped_content=scraped_content,
                key_entities=key_entities or {"people": [], "organizations": [], "locations": []},
                sections=sections or [],
                quiz_json=json.dumps(quiz_questions),
                related_topics=related_topics or [],
                easy_count=easy_count,
                medium_count=medium_count,
                hard_count=hard_count,
                generated_at=datetime.utcnow(),
            )

            session.merge(record)
            session.commit()
            logger.info(f"Persisted quiz {quiz_id} to database")
            return self._serialize(record)
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save quiz {quiz_id}: {e}")
            raise
        finally:
            session.close()

    def get_quiz(self, quiz_id: str) -> Optional[Dict[str, Any]]:
        session = self.SessionLocal()
        try:
            record = session.get(QuizRecord, quiz_id)
            if not record:
                return None
            return self._serialize(record)
        except Exception as e:
            logger.error(f"Failed to fetch quiz {quiz_id}: {e}")
            raise
        finally:
            session.close()

    def list_quizzes(
        self,
        page: int,
        limit: int,
        search: Optional[str] = None,
        difficulty: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        session = self.SessionLocal()
        try:
            query = session.query(QuizRecord)

            if search:
                pattern = f"%{search.lower()}%"
                query = query.filter(
                    or_(
                        func.lower(QuizRecord.title).like(pattern),
                        func.lower(QuizRecord.summary).like(pattern)
                    )
                )

            if difficulty == "easy":
                query = query.filter(QuizRecord.easy_count > 0)
            elif difficulty == "medium":
                query = query.filter(QuizRecord.medium_count > 0)
            elif difficulty == "hard":
                query = query.filter(QuizRecord.hard_count > 0)

            total = query.count()
            records = (
                query.order_by(desc(QuizRecord.generated_at))
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )

            return [self._serialize(record) for record in records], total
        except Exception as e:
            logger.error(f"Failed to list quizzes: {e}")
            raise
        finally:
            session.close()

    def count_quizzes(self) -> int:
        """Return the total number of quizzes stored."""
        session = self.SessionLocal()
        try:
            return session.query(func.count(QuizRecord.id)).scalar() or 0
        except Exception as e:
            logger.error(f"Failed to count quizzes: {e}")
            raise
        finally:
            session.close()


quiz_repository: Optional[QuizRepository] = None


def get_quiz_repository() -> QuizRepository:
    global quiz_repository
    if quiz_repository is None:
        quiz_repository = QuizRepository()
    return quiz_repository
