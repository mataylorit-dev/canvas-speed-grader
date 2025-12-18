# Canvas Speed Grader

AI-powered grading assistant for Canvas LMS. Save hours grading assignments with intelligent AI analysis, fairness review, and seamless Canvas integration.

## Features

- **AI-Powered Grading**: Automatically grade submissions using OpenAI GPT-4 against your rubrics
- **Fairness Review**: Secondary AI review using Gemini to ensure consistent, fair grading
- **Canvas Integration**: Seamlessly fetch assignments and post grades back to Canvas
- **Student Privacy**: Anonymized grading ensures unbiased evaluation
- **Beautiful UI**: Modern, responsive design optimized for educators
- **Firebase Hosting**: Deploy as a serverless application on Firebase

## Project Structure

```
updated/
├── static/                 # Frontend assets
│   ├── css/
│   │   ├── design-system.css   # Core design tokens and components
│   │   └── main.css            # Page-specific styles
│   ├── js/
│   │   ├── firebase-config.js  # Firebase initialization
│   │   ├── auth.js             # Authentication module
│   │   ├── api.js              # API client
│   │   └── app.js              # Main application logic
│   └── images/
│       └── favicon.svg
├── templates/              # HTML templates
│   ├── index.html          # Landing page
│   ├── login.html          # Sign in page
│   ├── register.html       # Registration page
│   ├── dashboard.html      # Main dashboard
│   ├── grading.html        # Grading interface
│   └── settings.html       # Account settings
├── api/                    # Backend API (Cloud Functions)
│   ├── main.py             # Flask application
│   ├── requirements.txt    # Python dependencies
│   └── services/
│       ├── canvas_service.py   # Canvas LMS integration
│       ├── grading_service.py  # AI grading logic
│       └── payment_service.py  # Stripe payments
├── firebase.json           # Firebase configuration
├── firestore.rules         # Firestore security rules
└── firestore.indexes.json  # Firestore indexes
```

## Setup

### Prerequisites

- Node.js 18+
- Python 3.11+
- Firebase CLI (`npm install -g firebase-tools`)
- A Firebase project with Firestore and Authentication enabled

### Environment Variables

Create a `.env` file or set the following environment variables:

```env
# OpenAI
OPENAI_API_KEY=your-openai-api-key

# Google Gemini
GEMINI_API_KEY=your-gemini-api-key

# Stripe
STRIPE_SECRET_KEY=your-stripe-secret-key
STRIPE_WEBHOOK_SECRET=your-stripe-webhook-secret
STRIPE_PRICE_SINGLE=price_xxx
STRIPE_PRICE_BUNDLE=price_xxx

# Optional: Free access users (comma-separated emails)
FREE_ACCESS_USERS=test@example.com
```

### Firebase Configuration

1. Update `static/js/firebase-config.js` with your Firebase project configuration:

```javascript
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID"
};
```

2. Enable Authentication methods in Firebase Console:
   - Email/Password
   - Google Sign-In

3. Set up Firestore database in Native mode

### Local Development

1. Install dependencies:

```bash
cd api
pip install -r requirements.txt
```

2. Start the backend:

```bash
python main.py
```

3. Serve the frontend (use any static file server):

```bash
npx serve static
```

### Deployment

1. Login to Firebase:

```bash
firebase login
```

2. Initialize Firebase in your project:

```bash
firebase init
```

3. Deploy:

```bash
firebase deploy
```

## Usage

### For Teachers

1. **Create an Account**: Sign up with your email or Google account
2. **Connect Canvas**: Enter your Canvas URL and API token
3. **Select Assignment**: Choose an assignment with a rubric
4. **Start AI Grading**: Click "Start AI Grading" to begin
5. **Review & Edit**: Review AI-generated grades and make adjustments
6. **Post to Canvas**: Post final grades with one click

### Getting a Canvas API Token

1. Log into Canvas
2. Go to **Account** > **Settings**
3. Scroll to **Approved Integrations**
4. Click **+ New Access Token**
5. Give it a name and click **Generate Token**
6. Copy the token (it won't be shown again!)

## API Endpoints

### Authentication Required

All API endpoints require a Firebase ID token in the Authorization header:

```
Authorization: Bearer <firebase-id-token>
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/assignments | Get all assignments with rubrics |
| GET | /api/assignments/:id | Get specific assignment |
| GET | /api/assignments/:id/submissions | Get submissions for assignment |
| POST | /api/grading/start | Start AI grading job |
| GET | /api/grading/status/:jobId | Get grading job status |
| POST | /api/grading/post | Post grades to Canvas |
| GET | /api/user/profile | Get user profile |
| PUT | /api/user/profile | Update user profile |
| POST | /api/billing/checkout | Create Stripe checkout session |

## Security

- **Firebase Authentication**: Secure user authentication with email/password and Google SSO
- **Firestore Rules**: Row-level security ensuring users can only access their own data
- **Encrypted Tokens**: Canvas API tokens are stored securely in Firestore
- **Anonymization**: Student identities are anonymized during grading to prevent bias

## License

MIT License - see LICENSE file for details.

## Support

For issues or feature requests, please open an issue on GitHub.
