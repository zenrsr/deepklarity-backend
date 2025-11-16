# LangChain Prompt Templates Documentation

This document contains the LangChain prompt templates designed for the AI Wiki Quiz Generator project. These templates are used to generate intelligent quiz questions from Wikipedia article content using Large Language Models.

## Overview

The prompt templates are designed to work with Google Gemini API and LangChain to create educational quiz questions that test comprehension of Wikipedia articles. Each template includes specific instructions for generating questions with varying difficulty levels, multiple choice options, explanations, and contextual references.

## Core Prompt Template

### Quiz Generation Prompt

```python
QUIZ_GENERATION_PROMPT = """
You are an expert educational content creator tasked with generating a comprehensive quiz from a Wikipedia article.

**Article Information:**
- Title: {article_title}
- Summary: {article_summary}
- Key Sections: {article_sections}
- Main Content: {article_content}

**Quiz Requirements:**
Generate exactly {question_count} multiple-choice questions based on this article. Each question must:

1. **Question Quality**: Test understanding, not just memorization
2. **Difficulty Distribution**: Follow this exact distribution:
   - Easy: {easy_count} questions (basic facts, definitions, main ideas)
   - Medium: {medium_count} questions (concepts, relationships, applications)
   - Hard: {hard_count} questions (analysis, synthesis, critical thinking)

3. **Question Structure**: Each question must include:
   - A clear, concise question stem
   - Exactly 4 multiple-choice options (A, B, C, D)
   - One correct answer
   - A detailed explanation of why the answer is correct
   - Reference to the relevant section of the article
   - Appropriate difficulty level

4. **Option Design**:
   - All options should be plausible and related to the topic
   - Avoid obviously wrong answers
   - Include common misconceptions as distractors when appropriate
   - Make sure the correct answer is definitively correct based on the article

5. **Content Coverage**: Questions should cover:
   - Key concepts and definitions
   - Important facts and figures
   - Historical context and significance
   - Relationships between concepts
   - Real-world applications and implications

**Output Format** (JSON):
```json
{{
  "questions": [
    {{
      "id": "q1",
      "question": "What is the primary purpose of [concept]?",
      "options": [
        "Option A",
        "Option B", 
        "Option C",
        "Option D"
      ],
      "answer": "Correct Option",
      "difficulty": "easy|medium|hard",
      "explanation": "Detailed explanation of why this is correct, referencing the article content.",
      "section_reference": "Name of the relevant section"
    }}
  ],
  "related_topics": [
    "Suggested related topic 1",
    "Suggested related topic 2",
    "Suggested related topic 3"
  ],
  "key_entities": {{
    "people": ["Important person 1", "Important person 2"],
    "organizations": ["Relevant organization 1"],
    "locations": ["Key location 1", "Key location 2"]
  }}
}}
```

**Important Guidelines:**
- Ensure factual accuracy based on the provided article content
- Make questions educational and thought-provoking
- Avoid questions that can be answered without reading the article
- Include a mix of factual, conceptual, and analytical questions
- Reference specific sections when appropriate
- Make explanations educational and comprehensive

Generate the quiz now:
"""
```

## Specialized Prompt Templates

### Easy Question Template

```python
EASY_QUESTION_PROMPT = """
Create an EASY difficulty question about: {topic}

**Characteristics of Easy Questions:**
- Test basic facts, definitions, or main ideas
- Should be answerable by someone who read the article once
- Focus on "what," "who," "when," or "where" questions
- Avoid complex analysis or synthesis

**Article Context:** {context}

**Question Requirements:**
- Simple, clear language
- One correct answer that is explicitly stated in the article
- Three plausible but incorrect distractors
- Brief explanation that reinforces the key fact

**Example Format:**
{{
  "question": "What is the definition of [term]?",
  "options": ["Definition A", "Definition B", "Definition C", "Definition D"],
  "answer": "Correct Definition",
  "explanation": "According to the article, [term] is defined as..."
}}
"""
```

### Medium Question Template

```python
MEDIUM_QUESTION_PROMPT = """
Create a MEDIUM difficulty question about: {topic}

**Characteristics of Medium Questions:**
- Test understanding of concepts and relationships
- Require comprehension of how ideas connect
- Focus on "how," "why," or "compare" questions
- Require synthesis of information from multiple parts of the article

**Article Context:** {context}

**Question Requirements:**
- Clear question that tests conceptual understanding
- One correct answer that requires understanding relationships
- Three distractors that test common misconceptions
- Detailed explanation that clarifies the concept

**Example Format:**
{{
  "question": "How does [concept A] relate to [concept B]?",
  "options": ["Relationship 1", "Relationship 2", "Relationship 3", "Relationship 4"],
  "answer": "Correct Relationship",
  "explanation": "The article explains that [concept A] and [concept B] are related through..."
}}
"""
```

### Hard Question Template

```python
HARD_QUESTION_PROMPT = """
Create a HARD difficulty question about: {topic}

**Characteristics of Hard Questions:**
- Test analytical thinking and critical evaluation
- Require synthesis of information and drawing conclusions
- Focus on "analyze," "evaluate," or "predict" questions
- May require applying knowledge to new situations

**Article Context:** {context}

**Question Requirements:**
- Complex question that requires deep understanding
- One correct answer that requires analysis and synthesis
- Three sophisticated distractors that test different levels of understanding
- Comprehensive explanation that walks through the reasoning

**Example Format:**
{{
  "question": "Based on the information in the article, what would be the most likely outcome if [scenario]?",
  "options": ["Outcome A", "Outcome B", "Outcome C", "Outcome D"],
  "answer": "Most Likely Outcome",
  "explanation": "To answer this question, we need to consider several factors from the article..."
}}
"""
```

## Implementation Notes

### LangChain Configuration

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List, Dict

class QuizQuestion(BaseModel):
    id: str = Field(description="Unique question identifier")
    question: str = Field(description="The question text")
    options: List[str] = Field(description="Four multiple choice options")
    answer: str = Field(description="The correct answer")
    difficulty: str = Field(description="Question difficulty: easy, medium, or hard")
    explanation: str = Field(description="Detailed explanation of the correct answer")
    section_reference: str = Field(description="Reference to relevant article section")

class QuizGeneration(BaseModel):
    questions: List[QuizQuestion] = Field(description="List of quiz questions")
    related_topics: List[str] = Field(description="Suggested related topics for further study")
    key_entities: Dict[str, List[str]] = Field(description="Important people, organizations, and locations")

# Initialize the parser
parser = PydanticOutputParser(pydantic_object=QuizGeneration)

# Create the LLM chain
llm = ChatGoogleGenerativeAI(
    model="gemini-pro",
    temperature=0.7,
    google_api_key=os.getenv("GEMINI_API_KEY")
)

quiz_chain = LLMChain(
    llm=llm,
    prompt=PromptTemplate(
        template=QUIZ_GENERATION_PROMPT,
        input_variables=["article_title", "article_summary", "article_sections", "article_content", "question_count", "easy_count", "medium_count", "hard_count"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    ),
    output_parser=parser
)
```

### Usage Example

```python
# Generate quiz from Wikipedia content
quiz_result = quiz_chain.run(
    article_title="Machine Learning",
    article_summary="Machine learning is a subset of artificial intelligence...",
    article_sections=["Introduction", "Types", "Applications", "History"],
    article_content="Detailed article content here...",
    question_count=8,
    easy_count=3,
    medium_count=4,
    hard_count=1
)

# The result is a structured QuizGeneration object
print(f"Generated {len(quiz_result.questions)} questions")
for question in quiz_result.questions:
    print(f"Q: {question.question}")
    print(f"Difficulty: {question.difficulty}")
    print(f"Answer: {question.answer}")
```

## Quality Assurance Guidelines

### Question Validation Checklist

1. **Content Accuracy**
   - [ ] All questions are factually correct based on the article
   - [ ] Answers can be verified from the provided content
   - [ ] Explanations accurately reflect article information

2. **Difficulty Appropriateness**
   - [ ] Easy questions test basic facts and definitions
   - [ ] Medium questions test concepts and relationships
   - [ ] Hard questions test analysis and synthesis

3. **Question Quality**
   - [ ] Questions are clear and unambiguous
   - [ ] All options are plausible and relevant
   - [ ] Distractors represent common misconceptions
   - [ ] Explanations are educational and comprehensive

4. **Coverage Balance**
   - [ ] Questions cover multiple sections of the article
   - [ ] Mix of factual, conceptual, and analytical questions
   - [ ] Appropriate distribution across difficulty levels

### Common Pitfalls to Avoid

1. **Question Design Issues**
   - Avoid questions that are too obvious or trivial
   - Don't create questions that can be answered without reading the article
   - Ensure all options are grammatically consistent
   - Avoid negative phrasing unless necessary

2. **Content Issues**
   - Don't introduce information not present in the article
   - Avoid questions that require external knowledge
   - Ensure technical terms are used correctly
   - Maintain consistent terminology with the article

3. **Technical Issues**
   - Always validate JSON output format
   - Ensure proper escaping of special characters
   - Verify all required fields are present
   - Check for consistent difficulty labeling

## Future Enhancements

### Advanced Prompt Templates

1. **Adaptive Difficulty**: Adjust question difficulty based on user performance
2. **Personalized Questions**: Tailor questions to user interests and knowledge level
3. **Multi-language Support**: Generate questions in different languages
4. **Accessibility Features**: Create questions suitable for different learning abilities

### Integration Improvements

1. **Caching**: Store generated questions to reduce API calls
2. **Batch Processing**: Generate multiple quizzes simultaneously
3. **Real-time Feedback**: Provide immediate validation during quiz taking
4. **Analytics**: Track question performance and user engagement

This documentation provides the foundation for implementing sophisticated AI-powered quiz generation that creates educational, engaging, and accurate assessments from Wikipedia content.