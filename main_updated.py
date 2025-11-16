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


load_dotenv()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Wiki Quiz Generator API",
    description="API for generating quizzes from Wikipedia articles using AI",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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

@app.get("/")
async def root():
    return {"message": "AI Wiki Quiz Generator API", "version": "1.0.0"}

@app.post("/api/quizzes/generate", response_model=GenerateQuizResponse)
async def generate_quiz(request: GenerateQuizRequest, background_tasks: BackgroundTasks):
    """
    Generate a quiz from a Wikipedia article URL
    """
    try:
        logger.info(f"Generating quiz for URL: {request.url}")
        

        if "wikipedia.org" not in str(request.url):
            raise HTTPException(status_code=400, detail="URL must be from wikipedia.org")
        

        quiz_id = str(uuid.uuid4())
        

        logger.info("Scraping Wikipedia content...")
        try:
            article_data = wikipedia_scraper.scrape_article(str(request.url))
            logger.info(f"Successfully scraped article: {article_data['title']}")
        except Exception as e:
            logger.error(f"Failed to scrape Wikipedia article: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to scrape Wikipedia article: {str(e)}")
        

        logger.info("Generating quiz using LLM...")
        try:
            llm_service = get_llm_service()
            quiz_data = llm_service.generate_quiz(
                title=article_data["title"],
                content=article_data["content"],
                question_count=request.question_count,
                difficulty_distribution=request.difficulty_distribution
            )
            logger.info(f"Successfully generated {len(quiz_data['questions'])} questions")
        except Exception as e:
            logger.error(f"Failed to generate quiz with LLM: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")
        

        quiz_response = {
            "id": quiz_id,
            "url": str(request.url),
            "title": article_data["title"],
            "summary": article_data["summary"],
            "key_entities": article_data["key_entities"],
            "sections": article_data["sections"],
            "quiz": quiz_data["questions"],
            "related_topics": quiz_data["related_topics"],
            "generated_at": datetime.utcnow().isoformat(),
            "difficulty_distribution": {
                "easy": sum(1 for q in quiz_data["questions"] if q["difficulty"] == "easy"),
                "medium": sum(1 for q in quiz_data["questions"] if q["difficulty"] == "medium"),
                "hard": sum(1 for q in quiz_data["questions"] if q["difficulty"] == "hard")
            }
        }
        

        quizzes_db[quiz_id] = quiz_response
        
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
    difficulty: Optional[str] = None
):
    """
    Get quiz history with pagination and filtering
    """
    try:
        logger.info(f"Fetching quizzes: page={page}, limit={limit}, search={search}, difficulty={difficulty}")
        

        all_quizzes = list(quizzes_db.values())
        

        if search:
            all_quizzes = [
                quiz for quiz in all_quizzes 
                if search.lower() in quiz["title"].lower() or 
                   search.lower() in quiz["summary"].lower()
            ]
        

        if difficulty:
            all_quizzes = [
                quiz for quiz in all_quizzes
                if quiz["difficulty_distribution"].get(difficulty, 0) > 0
            ]
        

        total = len(all_quizzes)
        start = (page - 1) * limit
        end = start + limit
        

        quizzes = all_quizzes[start:end]
        
        return QuizListResponse(
            quizzes=[GenerateQuizResponse(**quiz) for quiz in quizzes],
            total=total,
            page=page,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error fetching quizzes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch quizzes: {str(e)}")

@app.get("/api/quizzes/{quiz_id}", response_model=GenerateQuizResponse)
async def get_quiz(quiz_id: str):
    """
    Get specific quiz details
    """
    try:
        logger.info(f"Fetching quiz: {quiz_id}")
        
        if quiz_id not in quizzes_db:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        return GenerateQuizResponse(**quizzes_db[quiz_id])
        
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
        
        if quiz_id not in quizzes_db:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        quiz = quizzes_db[quiz_id]
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

@app.get("/api/quizzes/{quiz_id}/related")
async def get_related_topics(quiz_id: str):
    """
    Get related topics for a quiz
    """
    try:
        logger.info(f"Fetching related topics for quiz: {quiz_id}")
        
        if quiz_id not in quizzes_db:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        return {"related_topics": quizzes_db[quiz_id]["related_topics"]}
        
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
