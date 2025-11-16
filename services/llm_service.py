import os
from typing import Dict, List, Optional, Any
import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import json
import re
import uuid

logger = logging.getLogger(__name__)

class QuizQuestion(BaseModel):
    id: str = Field(description="Unique question identifier")
    question: str = Field(description="The quiz question text")
    options: List[str] = Field(description="Four multiple choice options")
    answer: str = Field(description="The correct answer")
    difficulty: str = Field(description="Difficulty level: easy, medium, or hard")
    explanation: str = Field(description="Explanation of the correct answer")
    evidence_span: str = Field(description="Short quote or section title that supports the answer")
    section_reference: Optional[str] = Field(default=None, description="Which article section this relates to")

class QuizGeneration(BaseModel):
    questions: List[QuizQuestion] = Field(description="List of quiz questions")
    related_topics: List[str] = Field(description="Suggested related Wikipedia topics")
    key_entities: Dict[str, List[str]] = Field(description="Key entities found in the article")

class LLMService:
    """Service for generating quizzes using Large Language Models"""
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
        
        MODEL_CANDIDATES = [
            "models/gemini-2.5-flash", 
            "models/gemini-2.5-pro", 
            "models/gemini-flash-latest", 
            "models/gemini-pro-latest",
        ]
        
        self.llm = ChatGoogleGenerativeAI(
            model="models/gemini-flash-latest",
            google_api_key=self.api_key,
            temperature=0.3,
            max_output_tokens=1024, 
            top_p=0.8,
            top_k=40,  
        )
        
        self.parser = PydanticOutputParser(pydantic_object=QuizGeneration)
        
        self.quiz_prompt = PromptTemplate(
            template="""Generate {question_count} quiz questions from this article.
            Title: {title}
            Content: {content}
            Difficulty: {difficulty_distribution}
            Create questions with 4 options each, correct answer, difficulty level, brief explanation, evidence_span, and section_reference. Use only article content.
            {format_instructions}""",
            input_variables=["title", "content", "question_count", "difficulty_distribution"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
    def _invoke_llm(self, title: str, content: str, question_count: int, difficulty_distribution: Dict[str, int]) -> str:
        prompt_text = self.quiz_prompt.format(
            title=title,
            content=content,
            question_count=question_count,
            difficulty_distribution=str(difficulty_distribution)
        )
        response = self.llm.invoke(prompt_text)
        if isinstance(response, str):
            return response
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    pieces.append(item.get("text", ""))
                elif isinstance(item, str):
                    pieces.append(item)
            return "".join(pieces)
        return str(response)
    
    def generate_quiz(self, title: str, content: str, question_count: int = 8, 
                     difficulty_distribution: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """
        Generate a quiz from Wikipedia article content
        
        Args:
            title: Article title
            content: Article content text
            question_count: Number of questions to generate (5-10)
            difficulty_distribution: Dict with easy/medium/hard counts
            
        Returns:
            Dictionary containing quiz questions and metadata
        """
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("LLM generation timed out after 25 seconds")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(25)
        
        try:
            logger.info(f"Generating quiz for article: {title}")
            
            if not title or not content:
                raise ValueError("Title and content are required")
            
            if question_count < 5 or question_count > 10:
                raise ValueError("Question count must be between 5 and 10")
            
            if not difficulty_distribution:
                difficulty_distribution = {
                    "easy": max(2, question_count // 3),
                    "medium": max(2, question_count // 2),
                    "hard": max(1, question_count - (question_count // 3 + question_count // 2))
                }
            
            total_dist = sum(difficulty_distribution.values())
            if total_dist != question_count:
                remaining = question_count - total_dist
                difficulty_distribution["medium"] += remaining
            
            max_content_length = 8000
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
            
            max_retries = 3
            quiz_data = None
            
            for attempt in range(max_retries):
                try:
                    response_text = self._invoke_llm(
                        title=title,
                        content=content,
                        question_count=question_count,
                        difficulty_distribution=difficulty_distribution
                    )
                    try:
                        parsed_response = self.parser.parse(response_text)
                        quiz_data = parsed_response.dict()
                        break
                    except Exception as parse_error:
                        logger.warning(f"Parser failed on attempt {attempt + 1}, trying manual JSON extraction: {parse_error}")
                        quiz_data = self._extract_json_manually(response_text)
                        if quiz_data and len(quiz_data.get('questions', [])) > 0:
                            break
                except Exception as llm_error:
                    logger.warning(f"LLM generation failed on attempt {attempt + 1}: {llm_error}")
                    if attempt == max_retries - 1:
                        raise
                    
                    import time
                    time.sleep(2 ** attempt)
            
            if not quiz_data or len(quiz_data.get('questions', [])) == 0:
                logger.warning("LLM failed to generate questions, creating basic questions from content")
                quiz_data = self._generate_basic_questions(content, question_count, difficulty_distribution)

            for question in quiz_data.get("questions", []):
                if "id" not in question or not question["id"]:
                    question["id"] = str(uuid.uuid4())
                if "evidence_span" not in question or not question.get("evidence_span"):
                    question["evidence_span"] = question.get("section_reference") or "insufficient evidence in article"
            
            self._validate_quiz_data(quiz_data, question_count, content)
            
            logger.info(f"Successfully generated quiz with {len(quiz_data['questions'])} questions")
            return quiz_data
            
        except TimeoutError as te:
            logger.error(f"Quiz generation timed out: {str(te)}")
            return self._generate_basic_questions(content, question_count, difficulty_distribution)
            
        except Exception as e:
            logger.error(f"Error generating quiz: {str(e)}")
            raise Exception(f"Failed to generate quiz: {str(e)}")
        
        finally:
            signal.alarm(0)
    
    def _extract_json_manually(self, response: str) -> Dict[str, Any]:
        """Fallback method to extract JSON from LLM response"""
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    logger.warning("JSON parsing failed, attempting to fix common issues")
                    return self._fix_and_parse_json(json_str)
            else:
                logger.warning("No JSON found in response, creating basic structure")
                return {
                    "questions": [],
                    "related_topics": [],
                    "key_entities": {"people": [], "organizations": [], "locations": []}
                }
        except Exception as e:
            logger.error(f"Failed to parse JSON from response: {e}")
            logger.warning("Creating basic structure due to JSON parsing failure")
            return {
                "questions": [],
                "related_topics": [],
                "key_entities": {"people": [], "organizations": [], "locations": []}
            }
    
    def _fix_and_parse_json(self, json_str: str) -> Dict[str, Any]:
        """Attempt to fix common JSON parsing issues"""
        try:
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            
            if json_str.count('"') % 2 != 0:
                json_str += '"'
            
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to fix JSON: {e}")
            return {
                "questions": [],
                "related_topics": [],
                "key_entities": {"people": [], "organizations": [], "locations": []}
            }
    
    def _generate_basic_questions(self, content: str, question_count: int, difficulty_distribution: Dict[str, int]) -> Dict[str, Any]:
        """Generate basic questions from article content when LLM fails"""
        try:
            sentences = content.split('.')
            questions = []
            
            for i in range(min(question_count, len(sentences) - 1)):
                sentence = sentences[i].strip()
                if len(sentence) > 50:
                    words = sentence.split()
                    if len(words) > 5:
                        question_text = f"What does the article state about {words[0].lower()}?"
                        correct_answer = sentence
                        
                        distractors = []
                        for j in range(3):
                            other_idx = (i + j + 1) % len(sentences)
                            other_sentence = sentences[other_idx].strip()
                            if other_idx != i and len(other_sentence) > 30:
                                distractors.append(other_sentence)
                        
                        if len(distractors) >= 3:
                            options = [correct_answer] + distractors[:3]
                            
                            questions.append({
                                "id": str(uuid.uuid4()),
                                "question": question_text,
                                "options": options,
                                "answer": correct_answer,
                                "difficulty": "easy",
                                "explanation": f"This information is found directly in the article: '{sentence}'",
                                "evidence_span": sentence or "insufficient evidence in article",
                                "section_reference": f"Paragraph {i+1}"
                            })
            
            while len(questions) < question_count:
                questions.append({
                    "id": str(uuid.uuid4()),
                    "question": "What is the main topic of this article?",
                    "options": ["The main topic", "A secondary topic", "An unrelated topic", "A different subject"],
                    "answer": "The main topic",
                    "difficulty": "easy",
                    "explanation": "This question tests basic comprehension of the article content.",
                    "evidence_span": "insufficient evidence in article",
                    "section_reference": "General"
                })
            
            return {
                "questions": questions[:question_count],
                "related_topics": ["Technology", "Science", "Education"],
                "key_entities": {
                    "people": [],
                    "organizations": [],
                    "locations": []
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to generate basic questions: {e}")
            return {
                "questions": [],
                "related_topics": [],
                "key_entities": {"people": [], "organizations": [], "locations": []}
            }
    
    def _validate_question_content(self, question: Dict[str, Any], article_content: str) -> bool:
        """Verify question answer exists in article content"""
        try:
            answer = question["answer"].lower()
            explanation = question["explanation"].lower()
            content_lower = article_content.lower()
            
            answer_in_content = answer in content_lower or any(option.lower() in content_lower for option in question["options"])
            explanation_in_content = explanation in content_lower
            
            question_text = question["question"].lower()
            key_terms = [term for term in question_text.split() if len(term) > 3]
            terms_in_content = sum(1 for term in key_terms if term in content_lower)
            
            content_relevance = terms_in_content / len(key_terms) if key_terms else 0
            
            return answer_in_content and content_relevance >= 0.5
            
        except Exception as e:
            logger.warning(f"Content validation error for question: {e}")
            return False

    def _validate_quiz_data(self, quiz_data: Dict[str, Any], expected_question_count: int, article_content: str = "") -> None:
        """Validate the generated quiz data"""
        if not isinstance(quiz_data, dict):
            raise ValueError("Quiz data must be a dictionary")
        
        if "questions" not in quiz_data:
            raise ValueError("Quiz data must contain 'questions' field")
        
        questions = quiz_data["questions"]
        if not isinstance(questions, list):
            raise ValueError("Questions must be a list")
        
        if len(questions) != expected_question_count:
            logger.warning(f"Expected {expected_question_count} questions, got {len(questions)}")
        
        for i, question in enumerate(questions):
            if not isinstance(question, dict):
                raise ValueError(f"Question {i} must be a dictionary")
            
            required_fields = ["id", "question", "options", "answer", "difficulty", "explanation", "evidence_span"]
            for field in required_fields:
                if field not in question:
                    raise ValueError(f"Question {i} missing required field: {field}")
            
            options = question["options"]
            if not isinstance(options, list) or len(options) != 4:
                raise ValueError(f"Question {i} must have exactly 4 options")
            
            difficulty = question["difficulty"]
            if difficulty not in ["easy", "medium", "hard"]:
                raise ValueError(f"Question {i} has invalid difficulty: {difficulty}")
            
            answer = question["answer"]
            if answer not in options:
                raise ValueError(f"Question {i} answer must be one of the options")
            
            if article_content and not self._validate_question_content(question, article_content):
                logger.warning(f"Question {i} content validation failed - not based on article content")
        
        logger.info(f"Quiz validation passed: {len(questions)} questions validated")

llm_service = None

def get_llm_service() -> LLMService:
    """Get or create the global LLM service instance"""
    global llm_service
    if llm_service is None:
        llm_service = LLMService()
    return llm_service
