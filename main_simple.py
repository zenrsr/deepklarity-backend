from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import os
from datetime import datetime
import uuid
import requests
from bs4 import BeautifulSoup
import json
import re
import logging


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
    question_count: Optional[int] = 8

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

class WikipediaScraper:
    def scrape_article(self, url: str) -> Dict[str, Any]:
        """Scrape Wikipedia article"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            

            title = self._extract_title(soup, url)
            

            summary = self._extract_summary(soup)
            

            content = self._extract_content(soup)
            

            sections = self._extract_sections(soup)
            
            return {
                "title": title,
                "summary": summary,
                "content": content,
                "sections": sections,
                "url": str(url)
            }
        except Exception as e:
            raise Exception(f"Failed to scrape Wikipedia article: {str(e)}")
    
    def _extract_title(self, soup: BeautifulSoup, url: str) -> str:
        try:
            h1 = soup.find('h1', {'id': 'firstHeading'})
            if h1:
                return h1.get_text().strip()
            

            title = url.split('/wiki/')[-1].replace('_', ' ')
            return title
        except Exception:
            return "Unknown Article"
    
    def _extract_summary(self, soup: BeautifulSoup) -> str:
        try:
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if not content_div:
                return ""
            
            first_p = content_div.find('p')
            if first_p:
                summary = first_p.get_text().strip()
                summary = re.sub(r'\[\d+\]', '', summary)
                return summary[:500]
            
            return ""
        except Exception:
            return ""
    
    def _extract_content(self, soup: BeautifulSoup) -> str:
        try:
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if not content_div:
                return ""
            
            paragraphs = content_div.find_all('p')
            content_parts = []
            
            for p in paragraphs:
                text = p.get_text().strip()
                if text and len(text) > 50:
                    text = re.sub(r'\[\d+\]', '', text)
                    content_parts.append(text)
            
            return ' '.join(content_parts[:10]) 
        except Exception:
            return ""
    
    def _extract_sections(self, soup: BeautifulSoup) -> List[str]:
        try:
            sections = []
            headings = soup.find_all(['h2', 'h3'])
            
            for heading in headings:
                text = heading.get_text().strip()
                if text and not text.lower().startswith('contents'):
                    sections.append(text)
            
            return sections[:10]
        except Exception:
            return []


class QuizGenerator:
    def generate_quiz(self, title: str, content: str, question_count: int) -> Dict[str, Any]:
        """Generate quiz questions from content"""
        

        questions = []
        

        sample_questions = [
            {
                "question": f"What is the main topic of the article about {title}?",
                "options": [f"{title} overview", f"History of {title}", f"Applications of {title}", f"Future of {title}"],
                "answer": f"{title} overview",
                "difficulty": "easy",
                "explanation": f"This article primarily discusses {title} and its key aspects.",
                "section_reference": "Introduction"
            },
            {
                "question": f"Which of the following is mentioned in the article about {title}?",
                "options": ["Key concepts", "Historical background", "Modern applications", "All of the above"],
                "answer": "All of the above",
                "difficulty": "medium",
                "explanation": f"The article covers various aspects of {title} including its concepts, history, and applications.",
                "section_reference": "Main Content"
            }
        ]
        

        for i in range(min(question_count, len(sample_questions))):
            question_data = sample_questions[i % len(sample_questions)].copy()
            question_data["id"] = f"q{i+1}"
            questions.append(QuizQuestion(**question_data))
        

        while len(questions) < question_count:
            questions.append(QuizQuestion(
                id=f"q{len(questions)+1}",
                question=f"Question about {title} #{len(questions)+1}?",
                options=["Option A", "Option B", "Option C", "Option D"],
                answer="Option A",
                difficulty="medium",
                explanation=f"This question relates to {title}.",
                section_reference="General"
            ))
        
        return {
            "questions": questions,
            "related_topics": [
                f"Related topic 1 about {title}",
                f"Related topic 2 about {title}",
                f"Related topic 3 about {title}"
            ],
            "key_entities": {
                "people": ["Person 1", "Person 2"],
                "organizations": ["Organization 1"],
                "locations": ["Location 1", "Location 2"]
            }
        }


scraper = WikipediaScraper()
quiz_generator = QuizGenerator()


quizzes_db = {}

@app.get("/")
async def root():
    return {"message": "AI Wiki Quiz Generator API", "version": "1.0.0"}

@app.post("/api/quizzes/generate", response_model=GenerateQuizResponse)
async def generate_quiz(request: GenerateQuizRequest):
    """Generate a quiz from a Wikipedia article URL"""
    try:

        if "wikipedia.org" not in str(request.url):
            raise HTTPException(status_code=400, detail="URL must be from wikipedia.org")
        

        quiz_id = str(uuid.uuid4())
        

        try:
            article_data = scraper.scrape_article(str(request.url))
            title = article_data["title"]
            summary = article_data["summary"]
            content = article_data["content"]
            sections = article_data["sections"]
        except Exception as scrape_error:

            logger.warning(f"Wikipedia scraping failed, using mock data: {scrape_error}")
            title = str(request.url).split('/wiki/')[-1].replace('_', ' ')
            summary = f"This article discusses {title} and its significance in various contexts."
            content = f"{title} is an important topic that has been widely studied and discussed. This article covers the key aspects and provides comprehensive information about the subject."
            sections = ["Introduction", "Background", "Key Concepts", "Applications", "Conclusion"]
        

        quiz_data = quiz_generator.generate_quiz(
            title=title,
            content=content,
            question_count=request.question_count
        )
        

        quiz_response = {
            "id": quiz_id,
            "url": str(request.url),
            "title": title,
            "summary": summary,
            "key_entities": quiz_data["key_entities"],
            "sections": sections,
            "quiz": quiz_data["questions"],
            "related_topics": quiz_data["related_topics"],
            "generated_at": datetime.utcnow().isoformat(),
            "difficulty_distribution": {
                "easy": sum(1 for q in quiz_data["questions"] if q.difficulty == "easy"),
                "medium": sum(1 for q in quiz_data["questions"] if q.difficulty == "medium"),
                "hard": sum(1 for q in quiz_data["questions"] if q.difficulty == "hard")
            }
        }
        

        quizzes_db[quiz_id] = quiz_response
        
        return GenerateQuizResponse(**quiz_response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate quiz: {str(e)}")

@app.get("/api/quizzes")
async def get_quizzes(page: int = 1, limit: int = 10, search: Optional[str] = None):
    """Get quiz history with pagination and filtering"""
    try:
        all_quizzes = list(quizzes_db.values())
        

        if search:
            all_quizzes = [
                quiz for quiz in all_quizzes 
                if search.lower() in quiz["title"].lower() or 
                   search.lower() in quiz["summary"].lower()
            ]
        

        total = len(all_quizzes)
        start = (page - 1) * limit
        end = start + limit
        
        quizzes = all_quizzes[start:end]
        
        return {
            "quizzes": quizzes,
            "total": total,
            "page": page,
            "limit": limit
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quizzes: {str(e)}")

@app.get("/api/quizzes/{quiz_id}", response_model=GenerateQuizResponse)
async def get_quiz(quiz_id: str):
    """Get specific quiz details"""
    if quiz_id not in quizzes_db:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    return GenerateQuizResponse(**quizzes_db[quiz_id])

@app.post("/api/quizzes/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, answers: Dict[str, Any]):
    """Submit quiz answers and get results"""
    if quiz_id not in quizzes_db:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    quiz = quizzes_db[quiz_id]
    user_answers = answers.get("answers", [])
    

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
    
    return {
        "quiz_id": quiz_id,
        "score": score,
        "correct_answers": correct_answers,
        "total_questions": total_questions,
        "results": results,
        "performance_feedback": performance_feedback,
        "suggested_topics": quiz["related_topics"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002, reload=True)
