"""
Canvas LMS Integration Service
Handles all communication with the Canvas LMS API
"""

import os
import tempfile
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from canvasapi import Canvas


class CanvasService:
    """Service for interacting with Canvas LMS API"""

    def __init__(self, canvas_url: str, canvas_token: str, course_id: str = None):
        """
        Initialize Canvas service

        Args:
            canvas_url: Base URL for Canvas instance (e.g., https://school.instructure.com)
            canvas_token: API token for authentication
            course_id: Optional course ID to work with
        """
        self.canvas_url = canvas_url.rstrip('/')
        self.canvas_token = canvas_token
        self.course_id = course_id
        self.canvas = None
        self.course = None

        self._init_canvas()

    def _init_canvas(self):
        """Initialize Canvas API client"""
        try:
            self.canvas = Canvas(self.canvas_url, self.canvas_token)
            if self.course_id:
                self.course = self.canvas.get_course(self.course_id)
        except Exception as e:
            raise ValueError(f"Failed to initialize Canvas connection: {str(e)}")

    def validate_credentials(self) -> bool:
        """Validate Canvas credentials by fetching user info"""
        try:
            self.canvas.get_current_user()
            return True
        except Exception:
            return False

    def get_courses(self) -> List[Dict]:
        """Get list of courses for the current user"""
        try:
            courses = self.canvas.get_courses(enrollment_type='teacher')
            return [
                {
                    'id': str(course.id),
                    'name': course.name,
                    'code': getattr(course, 'course_code', '')
                }
                for course in courses
            ]
        except Exception as e:
            raise ValueError(f"Failed to fetch courses: {str(e)}")

    def get_course_name(self) -> str:
        """Get the name of the current course"""
        if self.course:
            return self.course.name
        return "Unknown Course"

    def get_assignments_with_rubrics(self) -> List[Dict]:
        """Get all assignments that have rubrics attached"""
        if not self.course:
            raise ValueError("No course selected")

        assignments = []
        try:
            for assignment in self.course.get_assignments():
                # Check if assignment has a rubric
                rubric = self._get_assignment_rubric(assignment)
                if rubric:
                    assignments.append({
                        'id': str(assignment.id),
                        'name': assignment.name,
                        'description': getattr(assignment, 'description', ''),
                        'due_at': getattr(assignment, 'due_at', None),
                        'points_possible': getattr(assignment, 'points_possible', 0),
                        'has_rubric': True,
                        'submission_types': getattr(assignment, 'submission_types', [])
                    })
        except Exception as e:
            raise ValueError(f"Failed to fetch assignments: {str(e)}")

        # Sort by due date (most recent first)
        assignments.sort(key=lambda x: x['due_at'] or '', reverse=True)
        return assignments

    def get_assignment(self, assignment_id: str) -> Dict:
        """Get a specific assignment"""
        if not self.course:
            raise ValueError("No course selected")

        try:
            assignment = self.course.get_assignment(assignment_id)
            return {
                'id': str(assignment.id),
                'name': assignment.name,
                'description': getattr(assignment, 'description', ''),
                'due_at': getattr(assignment, 'due_at', None),
                'points_possible': getattr(assignment, 'points_possible', 0),
                'submission_types': getattr(assignment, 'submission_types', [])
            }
        except Exception as e:
            raise ValueError(f"Failed to fetch assignment: {str(e)}")

    def get_rubric(self, assignment_id: str) -> List[Dict]:
        """Get rubric for an assignment"""
        if not self.course:
            raise ValueError("No course selected")

        try:
            assignment = self.course.get_assignment(assignment_id)
            rubric = self._get_assignment_rubric(assignment)
            return rubric if rubric else []
        except Exception as e:
            raise ValueError(f"Failed to fetch rubric: {str(e)}")

    def _get_assignment_rubric(self, assignment) -> Optional[List[Dict]]:
        """Extract rubric from assignment object"""
        rubric_data = getattr(assignment, 'rubric', None)
        if not rubric_data:
            return None

        rubric = []
        for criterion in rubric_data:
            rubric.append({
                'id': criterion.get('id', ''),
                'description': criterion.get('description', ''),
                'long_description': criterion.get('long_description', ''),
                'points': criterion.get('points', 0),
                'ratings': criterion.get('ratings', [])
            })
        return rubric

    def get_submissions(self, assignment_id: str, filters: Dict = None) -> List[Dict]:
        """Get submissions for an assignment with optional filtering"""
        if not self.course:
            raise ValueError("No course selected")

        filters = filters or {}

        try:
            assignment = self.course.get_assignment(assignment_id)
            all_submissions = assignment.get_submissions(include=['user', 'submission_comments'])

            submissions = []
            for sub in all_submissions:
                status = self._get_submission_status(sub, assignment)

                # Apply filters
                if not self._passes_filter(status, filters):
                    continue

                # Create anonymized ID
                anonymous_id = f"user{str(sub.user_id)[-4:].zfill(4)}"

                submissions.append({
                    'id': str(sub.id),
                    'user_id': str(sub.user_id),
                    'anonymous_id': anonymous_id,
                    'status': status,
                    'submitted_at': getattr(sub, 'submitted_at', None),
                    'score': getattr(sub, 'score', None),
                    'grade': getattr(sub, 'grade', None),
                    'attachments': self._get_attachments(sub),
                    'attempt': getattr(sub, 'attempt', 1)
                })

            return submissions

        except Exception as e:
            raise ValueError(f"Failed to fetch submissions: {str(e)}")

    def _get_submission_status(self, submission, assignment) -> str:
        """Determine submission status"""
        workflow_state = getattr(submission, 'workflow_state', 'unsubmitted')
        submitted_at = getattr(submission, 'submitted_at', None)
        due_at = getattr(assignment, 'due_at', None)
        attempt = getattr(submission, 'attempt', 1)

        if workflow_state == 'unsubmitted' or not submitted_at:
            return 'Missing'

        if attempt and attempt > 1:
            return 'Resubmitted'

        if due_at and submitted_at:
            due_date = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            submit_date = datetime.fromisoformat(submitted_at.replace('Z', '+00:00'))
            if submit_date > due_date:
                return 'Late'

        return 'On Time'

    def _passes_filter(self, status: str, filters: Dict) -> bool:
        """Check if submission passes the filter criteria"""
        status_map = {
            'On Time': 'ontime',
            'Late': 'late',
            'Resubmitted': 'resubmitted',
            'Missing': 'missing'
        }

        filter_key = status_map.get(status, 'ontime')
        return filters.get(filter_key, True)

    def _get_attachments(self, submission) -> List[Dict]:
        """Get file attachments from submission"""
        attachments = getattr(submission, 'attachments', [])
        return [
            {
                'id': str(att.get('id', '')),
                'filename': att.get('filename', ''),
                'url': att.get('url', ''),
                'content_type': att.get('content-type', '')
            }
            for att in attachments
        ]

    def get_submission_stats(self, assignment_id: str) -> Dict:
        """Get submission statistics for an assignment"""
        if not self.course:
            raise ValueError("No course selected")

        try:
            assignment = self.course.get_assignment(assignment_id)
            submissions = assignment.get_submissions()

            stats = {
                'total': 0,
                'graded': 0,
                'pending': 0,
                'late': 0,
                'missing': 0
            }

            for sub in submissions:
                stats['total'] += 1
                status = self._get_submission_status(sub, assignment)

                if getattr(sub, 'score', None) is not None:
                    stats['graded'] += 1
                else:
                    stats['pending'] += 1

                if status == 'Late':
                    stats['late'] += 1
                elif status == 'Missing':
                    stats['missing'] += 1

            return stats

        except Exception as e:
            raise ValueError(f"Failed to get submission stats: {str(e)}")

    def download_submission_files(self, submission: Dict) -> List[str]:
        """Download submission files to temporary directory"""
        files = []
        attachments = submission.get('attachments', [])

        for attachment in attachments:
            url = attachment.get('url')
            filename = attachment.get('filename', 'unknown')

            if not url:
                continue

            try:
                # Download file
                response = requests.get(url, headers={
                    'Authorization': f'Bearer {self.canvas_token}'
                })
                response.raise_for_status()

                # Save to temp file
                temp_dir = tempfile.mkdtemp()
                file_path = os.path.join(temp_dir, filename)

                with open(file_path, 'wb') as f:
                    f.write(response.content)

                files.append(file_path)

            except Exception as e:
                print(f"Failed to download {filename}: {str(e)}")

        return files

    def cleanup_files(self, files: List[str]):
        """Clean up temporary files"""
        import shutil
        for file_path in files:
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    # Also remove parent temp directory if empty
                    parent_dir = os.path.dirname(file_path)
                    if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                        shutil.rmtree(parent_dir)
            except Exception:
                pass

    def post_grade(self, assignment_id: str, submission_id: str, score: float,
                   comment: str = '', rubric_scores: Dict = None) -> bool:
        """Post grade to Canvas"""
        if not self.course:
            raise ValueError("No course selected")

        try:
            assignment = self.course.get_assignment(assignment_id)

            # Build submission data
            submission_data = {
                'submission': {
                    'posted_grade': str(score)
                }
            }

            # Add rubric assessment if available
            if rubric_scores:
                rubric_assessment = {}
                for criterion_id, criterion_data in rubric_scores.items():
                    rubric_assessment[criterion_id] = {
                        'points': criterion_data.get('score', 0),
                        'comments': criterion_data.get('feedback', '')
                    }
                submission_data['rubric_assessment'] = rubric_assessment

            # Get submission and update
            # Using requests directly for more control
            url = f"{self.canvas_url}/api/v1/courses/{self.course_id}/assignments/{assignment_id}/submissions/{submission_id}"

            response = requests.put(url, json=submission_data, headers={
                'Authorization': f'Bearer {self.canvas_token}',
                'Content-Type': 'application/json'
            })
            response.raise_for_status()

            # Add comment with AI disclosure
            if comment:
                full_comment = f"{comment}\n\n---\nThis grade was generated with AI assistance and reviewed by the instructor."
                self._add_submission_comment(assignment_id, submission_id, full_comment)

            return True

        except Exception as e:
            print(f"Failed to post grade: {str(e)}")
            return False

    def _add_submission_comment(self, assignment_id: str, submission_id: str, comment: str):
        """Add a comment to a submission"""
        try:
            url = f"{self.canvas_url}/api/v1/courses/{self.course_id}/assignments/{assignment_id}/submissions/{submission_id}"
            response = requests.put(url, json={
                'comment': {
                    'text_comment': comment
                }
            }, headers={
                'Authorization': f'Bearer {self.canvas_token}',
                'Content-Type': 'application/json'
            })
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to add comment: {str(e)}")
