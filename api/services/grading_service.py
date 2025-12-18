"""
AI Grading Service
Handles AI-powered grading using OpenAI and Gemini
"""

import os
import json
import re
from typing import Dict, List, Any, Optional

import openai
import google.generativeai as genai


class GradingService:
    """Service for AI-powered grading of submissions"""

    def __init__(self):
        """Initialize grading service with AI clients"""
        # Initialize OpenAI
        self.openai_client = openai.OpenAI(
            api_key=os.environ.get('OPENAI_API_KEY')
        )
        self.openai_model = "gpt-4o-mini"

        # Initialize Gemini
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
        self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-lite')

        # Prompts
        self.grading_system_prompt = self._get_grading_system_prompt()
        self.fairness_system_prompt = self._get_fairness_system_prompt()

    def _get_grading_system_prompt(self) -> str:
        """Get the system prompt for grading"""
        return """You are an expert educational grader assisting a teacher in evaluating student submissions.
Your role is to provide fair, consistent, and constructive grading based on the provided rubric.

GRADING PRINCIPLES:
1. Evidence-Based: Only award points for clearly demonstrated work in the submission
2. Consistency: Apply the same standards to all submissions
3. Constructive: Provide specific, actionable feedback
4. Fair: Grade based on content, not presentation style or personal preferences
5. Binary Approach: For each criterion, award full points or zero - no partial credit unless explicitly allowed

RESPONSE FORMAT:
You must respond with valid JSON only. No markdown, no explanations outside the JSON.
{
  "criteria": {
    "<criterion_id>": {
      "score": <number>,
      "feedback": "<specific feedback explaining the score>"
    }
  },
  "total": <sum of all scores>,
  "general_feedback": "<overall feedback for the student>"
}"""

    def _get_fairness_system_prompt(self) -> str:
        """Get the system prompt for fairness review"""
        return """You are a fairness reviewer for AI-generated grades.
Your role is to check if the grading is fair and consistent with the rubric.

Review the original submission and the assigned grade. Check for:
1. Grading errors: Points deducted for work that was completed correctly
2. Missed credit: Work that was completed but not given credit
3. Inconsistent application of rubric standards
4. Bias in feedback language

RESPONSE FORMAT:
You must respond with valid JSON only.
{
  "flagged": <true/false>,
  "confidence": <0.0 to 1.0>,
  "issues": ["<issue 1>", "<issue 2>"],
  "suggested_adjustments": {
    "<criterion_id>": {
      "current_score": <number>,
      "suggested_score": <number>,
      "reason": "<explanation>"
    }
  },
  "message": "<summary for the teacher if flagged>"
}"""

    def extract_text_from_files(self, file_paths: List[str]) -> str:
        """Extract text content from submission files"""
        from PyPDF2 import PdfReader
        import docx

        all_text = []

        for file_path in file_paths:
            try:
                if file_path.lower().endswith('.pdf'):
                    text = self._extract_pdf_text(file_path)
                elif file_path.lower().endswith('.docx'):
                    text = self._extract_docx_text(file_path)
                elif file_path.lower().endswith('.txt'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                else:
                    # Try to read as text
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            text = f.read()
                    except Exception:
                        text = f"[Unable to read file: {os.path.basename(file_path)}]"

                if text:
                    all_text.append(f"--- File: {os.path.basename(file_path)} ---\n{text}")

            except Exception as e:
                all_text.append(f"[Error reading {os.path.basename(file_path)}: {str(e)}]")

        return "\n\n".join(all_text)

    def _extract_pdf_text(self, file_path: str) -> str:
        """Extract text from PDF file"""
        from PyPDF2 import PdfReader

        try:
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            full_text = "\n".join(text_parts)

            # If no text extracted, might be scanned - try OCR
            if not full_text.strip():
                full_text = self._ocr_pdf(file_path)

            return full_text

        except Exception as e:
            return f"[Error reading PDF: {str(e)}]"

    def _extract_docx_text(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        import docx

        try:
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs]
            return "\n".join(paragraphs)
        except Exception as e:
            return f"[Error reading DOCX: {str(e)}]"

    def _ocr_pdf(self, file_path: str) -> str:
        """Perform OCR on PDF file"""
        try:
            import pytesseract
            from pdf2image import convert_from_path

            images = convert_from_path(file_path)
            text_parts = []

            for image in images:
                text = pytesseract.image_to_string(image)
                if text:
                    text_parts.append(text)

            return "\n".join(text_parts)

        except Exception as e:
            return f"[OCR failed: {str(e)}]"

    def grade_submission(self, files: List[str], rubric: List[Dict],
                         assignment: Dict) -> Dict:
        """
        Grade a submission using AI

        Args:
            files: List of file paths for the submission
            rubric: List of rubric criteria
            assignment: Assignment details

        Returns:
            Dictionary with grades and feedback for each criterion
        """
        # Extract text from files
        submission_text = self.extract_text_from_files(files)

        if not submission_text or submission_text.startswith('['):
            return self._create_empty_grade(rubric, "Unable to read submission files")

        # Truncate if too long
        max_chars = 15000
        if len(submission_text) > max_chars:
            submission_text = submission_text[:max_chars] + "\n\n[Content truncated due to length...]"

        # Format rubric for prompt
        rubric_text = self._format_rubric(rubric)

        # Create grading prompt
        user_prompt = f"""Grade the following student submission based on the rubric.

ASSIGNMENT: {assignment.get('name', 'Unknown Assignment')}

RUBRIC CRITERIA:
{rubric_text}

STUDENT SUBMISSION:
{submission_text}

Grade each criterion and provide specific feedback. Respond with JSON only."""

        try:
            # Call OpenAI
            response = self.openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {"role": "system", "content": self.grading_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            grade_result = self._parse_json_response(result_text)

            # Validate and normalize
            return self._validate_grade_result(grade_result, rubric)

        except Exception as e:
            print(f"Grading error: {str(e)}")
            return self._create_empty_grade(rubric, f"Grading failed: {str(e)}")

    def _format_rubric(self, rubric: List[Dict]) -> str:
        """Format rubric for the prompt"""
        lines = []
        for criterion in rubric:
            lines.append(f"- {criterion['description']} ({criterion['points']} points)")
            if criterion.get('long_description'):
                lines.append(f"  Details: {criterion['long_description']}")
            if criterion.get('ratings'):
                for rating in criterion['ratings']:
                    lines.append(f"  * {rating.get('description', '')}: {rating.get('points', 0)} pts")
        return "\n".join(lines)

    def _parse_json_response(self, text: str) -> Dict:
        """Parse JSON from AI response"""
        # Try to extract JSON from the response
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])

        # Try to parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        raise ValueError("Could not parse JSON response from AI")

    def _validate_grade_result(self, result: Dict, rubric: List[Dict]) -> Dict:
        """Validate and normalize grade result"""
        validated = {
            'criteria': {},
            'total': 0,
            'general_feedback': result.get('general_feedback', '')
        }

        criteria = result.get('criteria', {})

        for criterion in rubric:
            criterion_id = criterion['id']
            max_points = criterion['points']

            if criterion_id in criteria:
                score = float(criteria[criterion_id].get('score', 0))
                # Clamp score to valid range
                score = max(0, min(score, max_points))
                feedback = criteria[criterion_id].get('feedback', '')
            else:
                score = 0
                feedback = 'No assessment provided'

            validated['criteria'][criterion_id] = {
                'score': score,
                'feedback': feedback
            }
            validated['total'] += score

        return validated

    def _create_empty_grade(self, rubric: List[Dict], message: str) -> Dict:
        """Create empty grade result with error message"""
        result = {
            'criteria': {},
            'total': 0,
            'general_feedback': message,
            'error': True
        }

        for criterion in rubric:
            result['criteria'][criterion['id']] = {
                'score': 0,
                'feedback': 'Unable to grade'
            }

        return result

    def fairness_review(self, files: List[str], rubric: List[Dict],
                        grade_result: Dict) -> Dict:
        """
        Review a grade for fairness using Gemini

        Args:
            files: List of file paths for the submission
            rubric: List of rubric criteria
            grade_result: The grade result to review

        Returns:
            Dictionary with fairness review results
        """
        if grade_result.get('error'):
            return {'flagged': False, 'message': 'Skipped - grading error'}

        try:
            # Extract text from files
            submission_text = self.extract_text_from_files(files)

            # Truncate if too long
            max_chars = 10000
            if len(submission_text) > max_chars:
                submission_text = submission_text[:max_chars] + "\n[Truncated...]"

            # Format the grade result
            grade_summary = self._format_grade_for_review(grade_result, rubric)

            # Create review prompt
            prompt = f"""{self.fairness_system_prompt}

RUBRIC:
{self._format_rubric(rubric)}

SUBMISSION:
{submission_text}

ASSIGNED GRADES:
{grade_summary}

Review this grading for fairness and respond with JSON only."""

            # Call Gemini
            response = self.gemini_model.generate_content(prompt)
            result_text = response.text.strip()

            # Parse response
            review_result = self._parse_json_response(result_text)

            return {
                'flagged': review_result.get('flagged', False),
                'confidence': review_result.get('confidence', 0.5),
                'issues': review_result.get('issues', []),
                'suggested_adjustments': review_result.get('suggested_adjustments', {}),
                'message': review_result.get('message', '')
            }

        except Exception as e:
            print(f"Fairness review error: {str(e)}")
            return {
                'flagged': False,
                'message': f'Review skipped: {str(e)}'
            }

    def _format_grade_for_review(self, grade_result: Dict, rubric: List[Dict]) -> str:
        """Format grade result for fairness review"""
        lines = []
        criteria = grade_result.get('criteria', {})

        for criterion in rubric:
            criterion_id = criterion['id']
            grade_data = criteria.get(criterion_id, {})
            score = grade_data.get('score', 0)
            feedback = grade_data.get('feedback', 'No feedback')

            lines.append(f"Criterion: {criterion['description']}")
            lines.append(f"  Score: {score}/{criterion['points']}")
            lines.append(f"  Feedback: {feedback}")
            lines.append("")

        lines.append(f"Total: {grade_result.get('total', 0)}")
        lines.append(f"General Feedback: {grade_result.get('general_feedback', '')}")

        return "\n".join(lines)

    def regrade_with_adjustments(self, grade_result: Dict,
                                 adjustments: Dict) -> Dict:
        """
        Apply fairness adjustments to a grade

        Args:
            grade_result: Original grade result
            adjustments: Suggested adjustments from fairness review

        Returns:
            Updated grade result
        """
        updated = {
            'criteria': dict(grade_result.get('criteria', {})),
            'total': 0,
            'general_feedback': grade_result.get('general_feedback', ''),
            'adjusted': True
        }

        for criterion_id, adjustment in adjustments.items():
            if criterion_id in updated['criteria']:
                updated['criteria'][criterion_id]['score'] = adjustment['suggested_score']
                updated['criteria'][criterion_id]['feedback'] += f"\n[Adjusted: {adjustment['reason']}]"

        # Recalculate total
        for criterion_data in updated['criteria'].values():
            updated['total'] += criterion_data.get('score', 0)

        return updated
