from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional, Dict, Any
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import uuid
import asyncio


from services.wikipedia_scraper import wikipedia_scraper
from services.llm_service import get_llm_service
from services.cache_service import get_cache_service
from services.quiz_repository import get_quiz_repository
import bleach
from urllib.parse import urlparse
import re


load_dotenv()


import structlog
import time


structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('quiz_api.log')
    ]
)

logger = structlog.get_logger(__name__)


import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            )
        ],
        traces_sample_rate=1.0, 
        profiles_sample_rate=1.0, 
        environment=os.getenv("ENVIRONMENT", "development"),
        release="ai-wiki-quiz-generator@1.0.0"
    )
    logger.info("Sentry error monitoring initialized")
else:
    logger.warning("Sentry DSN not configured - error monitoring disabled")


def sanitize_wikipedia_url(url: str) -> str:
    """Validate and sanitize Wikipedia URL with strict security checks"""
    try:
        parsed = urlparse(str(url))
        

        allowed_domains = [
            'en.wikipedia.org', 'wikipedia.org', 'www.wikipedia.org',
            'en.m.wikipedia.org', 'm.wikipedia.org'
        ]
        
        if parsed.netloc not in allowed_domains:
            raise ValueError(f"Invalid Wikipedia domain: {parsed.netloc}")
        

        if parsed.scheme != 'https':
            raise ValueError("URL must use HTTPS protocol")
        

        if not parsed.path or parsed.path == '/':
            raise ValueError("URL must contain a specific article path")
        

        safe_url = f"https://en.wikipedia.org{parsed.path}"
        

        if len(safe_url) > 500:
            raise ValueError("URL too long")
        

        if re.search(r'[<>\'"\s]', safe_url):
            raise ValueError("URL contains invalid characters")
        
        return safe_url
        
    except Exception as e:
        raise ValueError(f"Invalid Wikipedia URL: {str(e)}")

def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input to prevent XSS and injection attacks"""
    if not text:
        return ""
    

    if len(text) > max_length:
        text = text[:max_length]
    

    text = bleach.clean(
        text,
        tags=[], 
        attributes={}, 
        strip=True
    )
    

    text = re.sub(r'[<>\'"\x00-\x1f\x7f-\x9f]', '', text)
    
    return text.strip()

def get_client_identifier(request_headers: dict) -> str:
    """Get client identifier for rate limiting (IP + User-Agent hash)"""

    forwarded = request_headers.get('x-forwarded-for', '')
    real_ip = request_headers.get('x-real-ip', '')
    client_ip = forwarded.split(',')[0].strip() if forwarded else (real_ip or 'unknown')
    

    user_agent = request_headers.get('user-agent', 'unknown')
    

    import hashlib
    identifier = f"{client_ip}:{user_agent}"
    return hashlib.md5(identifier.encode()).hexdigest()

app = FastAPI(
    title="AI Wiki Quiz Generator API",
    description="API for generating quizzes from Wikipedia articles using AI",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateQuizRequest(BaseModel):
    url: HttpUrl
    question_count: Optional[int] = Field(default=8, ge=5, le=10)
    difficulty_distribution: Optional[Dict[str, int]] = None

class QuizQuestion(BaseModel):
    id: str
    question: str
    options: List[str]
    answer: str
    difficulty: str
    explanation: str
    evidence_span: Optional[str] = None
    section_reference: Optional[str] = None

class GenerateQuizResponse(BaseModel):
    id: str
    url: str
    title: str
    summary: str
    key_entities: Dict[str, List[str]]
    sections: List[str]
    quiz: List[QuizQuestion]
    related_topics: List[str]
    generated_at: str
    difficulty_distribution: Dict[str, int]

class QuizListResponse(BaseModel):
    quizzes: List[GenerateQuizResponse]
    total: int
    page: int
    limit: int

class SubmitQuizRequest(BaseModel):
    quiz_id: str
    answers: List[Dict[str, str]]
    completed_at: Optional[str] = None

class SubmitQuizResponse(BaseModel):
    quiz_id: str
    score: int
    correct_answers: int
    total_questions: int
    results: List[Dict[str, Any]]
    performance_feedback: str
    suggested_topics: List[str]


quizzes_db = {}
quiz_repository = get_quiz_repository()


def _get_quiz_payload(quiz_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve quiz payload from cache, memory, or database."""
    cache_service = get_cache_service()
    cached_quiz = cache_service.get_cached_quiz(quiz_id)
    if cached_quiz:
        return cached_quiz
    
    if quiz_id in quizzes_db:
        return quizzes_db[quiz_id]
    
    quiz_data = quiz_repository.get_quiz(quiz_id)
    if quiz_data:
        quizzes_db[quiz_id] = quiz_data
        cache_service.cache_quiz(quiz_id, quiz_data, ttl=3600)
    return quiz_data

@app.get("/")
async def root():
    return {"message": "AI Wiki Quiz Generator API", "version": "1.0.0"}

@app.post("/api/quizzes/generate", response_model=GenerateQuizResponse)
async def generate_quiz(request: GenerateQuizRequest, background_tasks: BackgroundTasks):
    """
    Generate a quiz from a Wikipedia article URL with caching and rate limiting
    """
    try:

        client_id = "default_client" 
        cache_service = get_cache_service()
        

        if not cache_service.increment_rate_limit(client_id, limit=10, window=3600):
            rate_limit_status = cache_service.get_rate_limit_status(client_id)
            logger.warning(f"Rate limit exceeded for client {client_id}")
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit exceeded. Try again in {rate_limit_status['resets_in']} seconds"
            )
        
        try:
            safe_url = sanitize_wikipedia_url(str(request.url))
            logger.info(f"Generating quiz for sanitized URL: {safe_url}")
        except ValueError as e:
            logger.error(f"Invalid Wikipedia URL: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid Wikipedia URL: {str(e)}")
        

        cached_content = cache_service.get_cached_wikipedia_content(safe_url)
        if cached_content:
            logger.info(f"Using cached Wikipedia content for {safe_url}")
            article_data = cached_content
        else:

            logger.info("Scraping Wikipedia content...")
            scrape_start = time.time()
            try:
                article_data = wikipedia_scraper.scrape_article(safe_url)
                scrape_time = time.time() - scrape_start
                logger.info(f"Successfully scraped article: {article_data['title']} (took {scrape_time:.2f}s)")
                
                cache_service.cache_wikipedia_content(safe_url, article_data, ttl=7200)
            except Exception as e:
                logger.error(f"Failed to scrape Wikipedia article: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to scrape Wikipedia article: {str(e)}")
        

        quiz_id = str(uuid.uuid4())
        

        logger.info("Generating quiz using LLM...")
        start_time = time.time()
        try:
            llm_service = get_llm_service()
            quiz_data = llm_service.generate_quiz(
                title=article_data["title"],
                content=article_data["content"],
                question_count=request.question_count,
                difficulty_distribution=request.difficulty_distribution
            )
            generation_time = time.time() - start_time
            logger.info(f"LLM generation completed in {generation_time:.2f} seconds")
            logger.info(f"Successfully generated {len(quiz_data['questions'])} questions")
        except Exception as e:
            logger.error(f"Failed to generate quiz with LLM: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")
        

        quiz_response = quiz_repository.save_quiz(
            quiz_id=quiz_id,
            url=safe_url,
            title=article_data["title"],
            summary=article_data["summary"],
            scraped_content=article_data["content"],
            key_entities=article_data["key_entities"],
            sections=article_data["sections"],
            quiz_questions=quiz_data["questions"],
            related_topics=quiz_data["related_topics"],
        )
        
        quizzes_db[quiz_id] = quiz_response
        cache_service.cache_quiz(quiz_id, quiz_response, ttl=3600) 
        
        logger.info(f"Quiz generated successfully: {quiz_id}")
        return GenerateQuizResponse(**quiz_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating quiz: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")

@app.get("/api/quizzes", response_model=QuizListResponse)
async def get_quizzes(
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    difficulty: Optional[str] = None,
    request_headers: dict = {}
):
    """
    Get quiz history with pagination, filtering, and caching
    """
    try:

        if search:
            search = sanitize_user_input(search, max_length=200)
        

        if difficulty and difficulty not in ['easy', 'medium', 'hard']:
            raise HTTPException(status_code=400, detail="Invalid difficulty level")
        

        user_id = get_client_identifier(request_headers)
        cache_service = get_cache_service()

        use_cache = not search and not difficulty and page == 1
        cached_payload = cache_service.get_cached_quiz_list(user_id) if use_cache else None
        
        if cached_payload:
            logger.info(f"Using cached quiz list for user {user_id}")
            quizzes = cached_payload.get("quizzes", [])
            total = cached_payload.get("total", len(quizzes))
        else:
            logger.info(f"Fetching quizzes from database: page={page}, limit={limit}, search={search}, difficulty={difficulty}")
            quizzes, total = quiz_repository.list_quizzes(page, limit, search, difficulty)
            if use_cache:
                cache_service.cache_quiz_list(
                    user_id,
                    {"quizzes": quizzes, "total": total},
                    ttl=300
                )
        
        return QuizListResponse(
            quizzes=[GenerateQuizResponse(**quiz) for quiz in quizzes],
            total=total,
            page=page,
            limit=limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quizzes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quizzes: {str(e)}")

@app.get("/api/quizzes/{quiz_id}", response_model=GenerateQuizResponse)
async def get_quiz(quiz_id: str):
    """
    Get specific quiz details with caching
    """
    try:
        logger.info(f"Fetching quiz: {quiz_id}")
        

        quiz_data = _get_quiz_payload(quiz_id)
        if not quiz_data:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        return GenerateQuizResponse(**quiz_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching quiz {quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quiz: {str(e)}")

@app.post("/api/quizzes/{quiz_id}/submit", response_model=SubmitQuizResponse)
async def submit_quiz(quiz_id: str, request: SubmitQuizRequest):
    """
    Submit quiz answers and get results
    """
    try:
        logger.info(f"Submitting quiz: {quiz_id}")
        
        quiz = _get_quiz_payload(quiz_id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        user_answers = request.answers
        

        correct_answers = 0
        total_questions = len(quiz["quiz"])
        results = []
        
        for question in quiz["quiz"]:
            question_id = question["id"]
            user_answer = next((a["selected_option"] for a in user_answers if a["question_id"] == question_id), None)
            is_correct = user_answer == question["answer"]
            
            if is_correct:
                correct_answers += 1
            
            results.append({
                "question_id": question_id,
                "user_answer": user_answer,
                "correct_answer": question["answer"],
                "is_correct": is_correct,
                "explanation": question["explanation"]
            })
        
        score = int((correct_answers / total_questions) * 100) if total_questions > 0 else 0
        

        if score >= 90:
            performance_feedback = "Excellent! You have mastered this topic."
        elif score >= 70:
            performance_feedback = "Good job! You have a solid understanding."
        elif score >= 50:
            performance_feedback = "Not bad! Keep studying to improve your knowledge."
        else:
            performance_feedback = "Keep practicing! Review the material and try again."
        
        return SubmitQuizResponse(
            quiz_id=quiz_id,
            score=score,
            correct_answers=correct_answers,
            total_questions=total_questions,
            results=results,
            performance_feedback=performance_feedback,
            suggested_topics=quiz["related_topics"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting quiz {quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit quiz: {str(e)}")


@app.get("/health")
async def health_check():
    """
    Health check endpoint for service monitoring
    """
    try:

        cache_service = get_cache_service()
        cache_stats = cache_service.get_cache_stats()
        

        llm_service = get_llm_service()
        llm_status = "healthy" if llm_service else "unhealthy"
        

        services_healthy = cache_stats.get("status") == "connected" and llm_status == "healthy"
        
        return {
            "status": "healthy" if services_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "cache": cache_stats,
                "llm": {"status": llm_status},
                "api": {"status": "healthy"}
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "version": "1.0.0"
        }

@app.get("/metrics")
async def get_metrics():
    """
    Performance metrics endpoint
    """
    try:
        cache_service = get_cache_service()
        cache_stats = cache_service.get_cache_stats()
        

        total_quizzes = quiz_repository.count_quizzes()
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cache": cache_stats.get("stats", {}),
            "api": {
                "total_quizzes_generated": total_quizzes,
                "active_cache_entries": cache_stats.get("stats", {}).get("total_keys", 0),
                "cache_hit_rate": cache_stats.get("stats", {}).get("hit_rate", "0%")
            }
        }
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to collect metrics: {str(e)}")

@app.get("/rate-limit-status")
async def get_rate_limit_status(request_headers: dict = {}):
    """
    Check current rate limit status for the client
    """
    try:
        client_id = get_client_identifier(request_headers)
        cache_service = get_cache_service()
        status = cache_service.get_rate_limit_status(client_id)
        
        return {
            "client_id": client_id,
            "rate_limit_status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Rate limit status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check rate limit: {str(e)}")

@app.get("/api/quizzes/{quiz_id}/related")
async def get_related_topics(quiz_id: str):
    """
    Get related topics for a quiz
    """
    try:
        logger.info(f"Fetching related topics for quiz: {quiz_id}")
        
        quiz = _get_quiz_payload(quiz_id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        return {"related_topics": quiz["related_topics"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching related topics for quiz {quiz_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch related topics: {str(e)}")

@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NOT_FOUND", "message": "Resource not found", "timestamp": datetime.utcnow().isoformat()}}
    )

@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error", "timestamp": datetime.utcnow().isoformat()}}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002, reload=True)
