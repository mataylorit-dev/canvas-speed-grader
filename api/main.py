"""
Canvas Speed Grader - Main API Entry Point
Flask application for Firebase Cloud Functions
"""

import os
import json
import uuid
import threading
from functools import wraps
from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, auth, firestore

# Import services
from services.canvas_service import CanvasService
from services.grading_service import GradingService
from services.payment_service import PaymentService

# Initialize Flask app
app = Flask(__name__)

# Configure CORS - allow specific origins or all for development
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*')
if allowed_origins != '*':
    allowed_origins = [origin.strip() for origin in allowed_origins.split(',')]
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})


def validate_env_vars():
    """Validate required environment variables on startup"""
    required_vars = {
        'OPENAI_API_KEY': 'OpenAI API key for grading',
        'GEMINI_API_KEY': 'Google Gemini API key for fairness review',
    }

    optional_vars = {
        'STRIPE_SECRET_KEY': 'Stripe secret key (required for payments)',
        'STRIPE_WEBHOOK_SECRET': 'Stripe webhook secret (required for payments)',
        'GOOGLE_APPLICATION_CREDENTIALS': 'Firebase service account path',
    }

    missing = []
    for var, description in required_vars.items():
        if not os.environ.get(var):
            missing.append(f"  - {var}: {description}")

    if missing:
        print("WARNING: Missing required environment variables:")
        print("\n".join(missing))
        print("\nThe application may not function correctly without these.")

    # Check optional vars and warn
    missing_optional = []
    for var, description in optional_vars.items():
        if not os.environ.get(var):
            missing_optional.append(f"  - {var}: {description}")

    if missing_optional:
        print("\nNote: Missing optional environment variables:")
        print("\n".join(missing_optional))


# Validate environment on startup
validate_env_vars()

# Initialize Firebase Admin
if not firebase_admin._apps:
    # Try to get credentials from environment or use default
    cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
    else:
        cred = credentials.ApplicationDefault()

    firebase_admin.initialize_app(cred)

# Initialize Firestore
db = firestore.client()

# Grading jobs storage (in production, use Redis or similar)
grading_jobs = {}


# =============================================================================
# Authentication Middleware
# =============================================================================

def require_auth(f):
    """Decorator to require Firebase authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        token = auth_header.split('Bearer ')[1]

        try:
            decoded_token = auth.verify_id_token(token)
            request.user_id = decoded_token['uid']
            request.user_email = decoded_token.get('email', '')
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401

    return decorated_function


def get_user_data(user_id):
    """Get user data from Firestore"""
    doc = db.collection('users').document(user_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


# =============================================================================
# Health Check
# =============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'canvas-speed-grader-api'
    })


# =============================================================================
# Assignment Routes
# =============================================================================

@app.route('/api/assignments', methods=['GET'])
@require_auth
def get_assignments():
    """Get all assignments with rubrics for the user's active course"""
    try:
        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        canvas_service = CanvasService(
            user_data['canvas_url'],
            user_data['canvas_token'],
            user_data['course_id']
        )

        assignments = canvas_service.get_assignments_with_rubrics()

        # Get submission counts and stats
        total_submissions = 0
        graded_count = 0
        pending_count = 0
        late_count = 0

        for assignment in assignments:
            stats = canvas_service.get_submission_stats(assignment['id'])
            assignment['submission_count'] = stats['total']
            total_submissions += stats['total']
            graded_count += stats['graded']
            pending_count += stats['pending']
            late_count += stats['late']

        return jsonify({
            'assignments': assignments,
            'course': {
                'id': user_data['course_id'],
                'name': canvas_service.get_course_name()
            },
            'totalSubmissions': total_submissions,
            'gradedCount': graded_count,
            'pendingCount': pending_count,
            'lateCount': late_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/assignments/<assignment_id>', methods=['GET'])
@require_auth
def get_assignment(assignment_id):
    """Get a specific assignment with its rubric"""
    try:
        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        canvas_service = CanvasService(
            user_data['canvas_url'],
            user_data['canvas_token'],
            user_data['course_id']
        )

        assignment = canvas_service.get_assignment(assignment_id)
        rubric = canvas_service.get_rubric(assignment_id)

        return jsonify({
            'assignment': assignment,
            'rubric': rubric
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/assignments/<assignment_id>/submissions', methods=['GET'])
@require_auth
def get_submissions(assignment_id):
    """Get submissions for an assignment"""
    try:
        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        # Get filter parameters
        filters = {
            'ontime': request.args.get('ontime', 'true').lower() == 'true',
            'late': request.args.get('late', 'true').lower() == 'true',
            'resubmitted': request.args.get('resubmitted', 'false').lower() == 'true',
            'missing': request.args.get('missing', 'false').lower() == 'true'
        }

        canvas_service = CanvasService(
            user_data['canvas_url'],
            user_data['canvas_token'],
            user_data['course_id']
        )

        submissions = canvas_service.get_submissions(assignment_id, filters)

        return jsonify({
            'submissions': submissions
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Grading Routes
# =============================================================================

@app.route('/api/grading/start', methods=['POST'])
@require_auth
def start_grading():
    """Start a grading job"""
    try:
        data = request.get_json()
        assignment_id = data.get('assignmentId')
        filters = data.get('filters', {})

        if not assignment_id:
            return jsonify({'error': 'Assignment ID is required'}), 400

        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        # Check subscription status
        payment_service = PaymentService(db)
        if not payment_service.has_active_subscription(request.user_id):
            return jsonify({'error': 'Active subscription required'}), 402

        # Create grading job
        job_id = str(uuid.uuid4())

        grading_jobs[job_id] = {
            'status': 'pending',
            'progress': {'current': 0, 'total': 0},
            'result': None,
            'error': None
        }

        # Start grading in background
        thread = threading.Thread(
            target=run_grading_job,
            args=(job_id, user_data, assignment_id, filters)
        )
        thread.start()

        return jsonify({'jobId': job_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_grading_job(job_id, user_data, assignment_id, filters):
    """Run grading job in background"""
    try:
        grading_jobs[job_id]['status'] = 'running'

        canvas_service = CanvasService(
            user_data['canvas_url'],
            user_data['canvas_token'],
            user_data['course_id']
        )

        grading_service = GradingService()

        # Get assignment and rubric
        assignment = canvas_service.get_assignment(assignment_id)
        rubric = canvas_service.get_rubric(assignment_id)

        # Get submissions
        submissions = canvas_service.get_submissions(assignment_id, filters)
        grading_jobs[job_id]['progress']['total'] = len(submissions)

        # Grade each submission
        grades = {}
        for i, submission in enumerate(submissions):
            grading_jobs[job_id]['progress']['current'] = i + 1
            grading_jobs[job_id]['progress']['currentStudent'] = submission.get('anonymous_id', f'Student {i+1}')

            # Download submission files
            files = canvas_service.download_submission_files(submission)

            # Grade with AI
            grade_result = grading_service.grade_submission(
                files=files,
                rubric=rubric,
                assignment=assignment
            )

            # Fairness review
            review_result = grading_service.fairness_review(
                files=files,
                rubric=rubric,
                grade_result=grade_result
            )

            grades[submission['id']] = {
                **grade_result,
                'fairness_flag': review_result.get('flagged', False),
                'fairness_message': review_result.get('message', '')
            }

            # Clean up temporary files
            canvas_service.cleanup_files(files)

        # Store result
        grading_jobs[job_id]['status'] = 'completed'
        grading_jobs[job_id]['result'] = {
            'assignment': {**assignment, 'rubric': rubric},
            'submissions': submissions,
            'grades': grades
        }

    except Exception as e:
        grading_jobs[job_id]['status'] = 'failed'
        grading_jobs[job_id]['error'] = str(e)


@app.route('/api/grading/status/<job_id>', methods=['GET'])
@require_auth
def get_grading_status(job_id):
    """Get status of a grading job"""
    job = grading_jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'status': job['status'],
        'progress': job['progress']
    }

    if job['status'] == 'completed':
        response['result'] = job['result']
    elif job['status'] == 'failed':
        response['error'] = job['error']

    return jsonify(response)


@app.route('/api/grading/post', methods=['POST'])
@require_auth
def post_grades():
    """Post grades to Canvas"""
    try:
        data = request.get_json()
        assignment_id = data.get('assignmentId')
        grades = data.get('grades', {})

        if not assignment_id:
            return jsonify({'error': 'Assignment ID is required'}), 400

        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        canvas_service = CanvasService(
            user_data['canvas_url'],
            user_data['canvas_token'],
            user_data['course_id']
        )

        # Post each grade to Canvas
        posted_count = 0
        for submission_id, grade_data in grades.items():
            success = canvas_service.post_grade(
                assignment_id=assignment_id,
                submission_id=submission_id,
                score=grade_data.get('total', 0),
                comment=grade_data.get('general_feedback', ''),
                rubric_scores=grade_data.get('criteria', {})
            )
            if success:
                posted_count += 1

        # Log grading history
        db.collection('grading_history').document(request.user_id).collection('history').add({
            'assignment_id': assignment_id,
            'submissions_count': len(grades),
            'posted_count': posted_count,
            'created_at': firestore.SERVER_TIMESTAMP
        })

        return jsonify({
            'success': True,
            'posted': posted_count,
            'total': len(grades)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/grading/history', methods=['GET'])
@require_auth
def get_grading_history():
    """Get grading history for the user"""
    try:
        limit = int(request.args.get('limit', 20))

        history_ref = db.collection('grading_history').document(request.user_id).collection('history')
        docs = history_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit).stream()

        history = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            history.append(data)

        return jsonify({'history': history})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# User Routes
# =============================================================================

@app.route('/api/user/profile', methods=['GET'])
@require_auth
def get_profile():
    """Get user profile"""
    user_data = get_user_data(request.user_id)
    if not user_data:
        return jsonify({'error': 'User not found'}), 404

    # Don't return sensitive data
    safe_data = {
        'email': user_data.get('email'),
        'display_name': user_data.get('display_name'),
        'canvas_url': user_data.get('canvas_url'),
        'course_id': user_data.get('course_id'),
        'courses': user_data.get('courses', []),
        'created_at': user_data.get('created_at'),
        'last_login': user_data.get('last_login')
    }

    return jsonify(safe_data)


@app.route('/api/user/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile"""
    try:
        data = request.get_json()

        # Only allow updating certain fields
        allowed_fields = ['display_name', 'canvas_url', 'canvas_token', 'course_id']
        updates = {k: v for k, v in data.items() if k in allowed_fields}

        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400

        db.collection('users').document(request.user_id).update(updates)

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/courses', methods=['POST'])
@require_auth
def add_course():
    """Add a new course"""
    try:
        data = request.get_json()
        course_id = data.get('courseId')
        canvas_url = data.get('canvasUrl')

        if not course_id:
            return jsonify({'error': 'Course ID is required'}), 400

        user_data = get_user_data(request.user_id)

        # Add to courses array
        courses = user_data.get('courses', [])
        courses.append({
            'id': course_id,
            'canvas_url': canvas_url or user_data.get('canvas_url'),
            'added_at': firestore.SERVER_TIMESTAMP
        })

        db.collection('users').document(request.user_id).update({
            'courses': courses
        })

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/courses/active', methods=['PUT'])
@require_auth
def set_active_course():
    """Set the active course"""
    try:
        data = request.get_json()
        course_id = data.get('courseId')

        if not course_id:
            return jsonify({'error': 'Course ID is required'}), 400

        db.collection('users').document(request.user_id).update({
            'course_id': course_id
        })

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Canvas Validation
# =============================================================================

@app.route('/api/canvas/validate', methods=['POST'])
@require_auth
def validate_canvas():
    """Validate Canvas credentials and optionally save them"""
    try:
        data = request.get_json()
        canvas_url = data.get('canvasUrl')
        canvas_token = data.get('canvasToken')
        save_credentials = data.get('save', False)

        if not canvas_url or not canvas_token:
            return jsonify({'error': 'Canvas URL and token are required'}), 400

        canvas_service = CanvasService(canvas_url, canvas_token)
        valid = canvas_service.validate_credentials()

        courses = canvas_service.get_courses() if valid else []

        # Optionally save credentials and courses to user profile
        if valid and save_credentials:
            db.collection('users').document(request.user_id).set({
                'canvas_url': canvas_url,
                'canvas_token': canvas_token,
                'courses': courses,
                'updated_at': firestore.SERVER_TIMESTAMP
            }, merge=True)

        return jsonify({
            'valid': valid,
            'courses': courses
        })

    except Exception as e:
        return jsonify({'error': str(e), 'valid': False}), 500


@app.route('/api/canvas/courses', methods=['GET'])
@require_auth
def get_canvas_courses():
    """Get courses from Canvas using saved credentials"""
    try:
        user_data = get_user_data(request.user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404

        canvas_url = user_data.get('canvas_url')
        canvas_token = user_data.get('canvas_token')

        if not canvas_url or not canvas_token:
            return jsonify({'error': 'Canvas credentials not configured', 'courses': []}), 400

        canvas_service = CanvasService(canvas_url, canvas_token)
        courses = canvas_service.get_courses()

        # Update courses in user profile
        db.collection('users').document(request.user_id).update({
            'courses': courses,
            'updated_at': firestore.SERVER_TIMESTAMP
        })

        return jsonify({'courses': courses})

    except Exception as e:
        return jsonify({'error': str(e), 'courses': []}), 500


# =============================================================================
# Billing Routes
# =============================================================================

@app.route('/api/billing/subscription', methods=['GET'])
@require_auth
def get_subscription():
    """Get subscription status"""
    try:
        payment_service = PaymentService(db)
        subscription = payment_service.get_subscription(request.user_id)

        return jsonify(subscription)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/billing/checkout', methods=['POST'])
@require_auth
def create_checkout():
    """Create Stripe checkout session"""
    try:
        data = request.get_json()
        price_id = data.get('priceId')
        quantity = data.get('quantity', 1)

        if not price_id:
            return jsonify({'error': 'Price ID is required'}), 400

        payment_service = PaymentService(db)
        checkout_url = payment_service.create_checkout_session(
            user_id=request.user_id,
            price_id=price_id,
            success_url=f"{request.host_url}settings.html?section=billing&payment=success",
            cancel_url=f"{request.host_url}settings.html?section=billing&payment=cancelled",
            quantity=int(quantity)
        )

        return jsonify({'checkoutUrl': checkout_url})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/billing/history', methods=['GET'])
@require_auth
def get_payment_history():
    """Get payment history"""
    try:
        payment_service = PaymentService(db)
        history = payment_service.get_payment_history(request.user_id)

        return jsonify({'history': history})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/billing/cancel', methods=['POST'])
@require_auth
def cancel_subscription():
    """Cancel subscription"""
    try:
        payment_service = PaymentService(db)
        success = payment_service.cancel_subscription(request.user_id)

        return jsonify({'success': success})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Stripe Webhook
# =============================================================================

@app.route('/api/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400

    # Handle the event
    payment_service = PaymentService(db)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        payment_service.handle_checkout_completed(session)

    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        payment_service.handle_subscription_updated(subscription)

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        payment_service.handle_subscription_cancelled(subscription)

    return jsonify({'received': True})


# =============================================================================
# Admin Routes
# =============================================================================

# Admin user emails (configure in environment)
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [email.strip() for email in ADMIN_EMAILS if email.strip()]


def require_admin(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401

        token = auth_header.split('Bearer ')[1]

        try:
            decoded_token = auth.verify_id_token(token)
            user_email = decoded_token.get('email', '')

            if user_email not in ADMIN_EMAILS:
                return jsonify({'error': 'Admin access required'}), 403

            request.user_id = decoded_token['uid']
            request.user_email = user_email
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401

    return decorated_function


@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def admin_stats():
    """Get overall platform statistics"""
    try:
        # Count users
        users_ref = db.collection('users')
        users = list(users_ref.stream())
        user_count = len(users)

        # Count users with Canvas configured
        canvas_configured = sum(1 for u in users if u.to_dict().get('canvas_token'))

        # Count subscriptions
        subs_ref = db.collection('subscriptions')
        subs = list(subs_ref.stream())
        active_subs = sum(1 for s in subs if s.to_dict().get('status') == 'active')

        # Recent grading sessions
        grading_count = 0
        for user in users:
            history_ref = db.collection('grading_history').document(user.id).collection('history')
            grading_count += len(list(history_ref.limit(100).stream()))

        return jsonify({
            'users': {
                'total': user_count,
                'canvasConfigured': canvas_configured
            },
            'subscriptions': {
                'total': len(subs),
                'active': active_subs
            },
            'gradingSessions': grading_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_list_users():
    """List all users"""
    try:
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        users_ref = db.collection('users').limit(limit).offset(offset)
        users = []

        for doc in users_ref.stream():
            user_data = doc.to_dict()
            # Don't return sensitive tokens
            users.append({
                'id': doc.id,
                'email': user_data.get('email'),
                'display_name': user_data.get('display_name'),
                'canvas_url': user_data.get('canvas_url'),
                'has_canvas_token': bool(user_data.get('canvas_token')),
                'course_count': len(user_data.get('courses', [])),
                'created_at': user_data.get('created_at'),
                'last_login': user_data.get('last_login')
            })

        return jsonify({'users': users})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users/<user_id>', methods=['GET'])
@require_admin
def admin_get_user(user_id):
    """Get detailed user info"""
    try:
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404

        user_data = user_doc.to_dict()

        # Get subscription info
        sub_doc = db.collection('subscriptions').document(user_id).get()
        subscription = sub_doc.to_dict() if sub_doc.exists else None

        # Get grading history count
        history_ref = db.collection('grading_history').document(user_id).collection('history')
        history_count = len(list(history_ref.stream()))

        return jsonify({
            'user': {
                'id': user_doc.id,
                'email': user_data.get('email'),
                'display_name': user_data.get('display_name'),
                'canvas_url': user_data.get('canvas_url'),
                'has_canvas_token': bool(user_data.get('canvas_token')),
                'courses': user_data.get('courses', []),
                'course_id': user_data.get('course_id'),
                'created_at': user_data.get('created_at'),
                'last_login': user_data.get('last_login')
            },
            'subscription': subscription,
            'gradingHistoryCount': history_count
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/users/<user_id>', methods=['DELETE'])
@require_admin
def admin_delete_user(user_id):
    """Delete a user"""
    try:
        # Delete from Firestore
        db.collection('users').document(user_id).delete()
        db.collection('subscriptions').document(user_id).delete()

        # Delete grading history
        history_ref = db.collection('grading_history').document(user_id).collection('history')
        for doc in history_ref.stream():
            doc.reference.delete()
        db.collection('grading_history').document(user_id).delete()

        # Delete from Firebase Auth
        try:
            auth.delete_user(user_id)
        except Exception:
            pass  # User might not exist in Auth

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/check', methods=['GET'])
@require_admin
def admin_check():
    """Check if current user is admin"""
    return jsonify({
        'isAdmin': True,
        'email': request.user_email
    })


# =============================================================================
# Error Handlers
# =============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# =============================================================================
# Export for Firebase Functions
# =============================================================================

import functions_framework

# Export the Flask app for Firebase Functions (2nd gen)
@functions_framework.http
def api(request):
    """HTTP Cloud Function entry point."""
    with app.request_context(request.environ):
        return app.full_dispatch_request()


if __name__ == '__main__':
    # Local development
    app.run(host='0.0.0.0', port=8080, debug=True)
