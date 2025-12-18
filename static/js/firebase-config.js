/**
 * Firebase Configuration
 * Canvas Speed Grader
 *
 * SETUP INSTRUCTIONS:
 * 1. Go to Firebase Console (https://console.firebase.google.com)
 * 2. Select your project (or create one)
 * 3. Click the gear icon > Project settings
 * 4. Scroll to "Your apps" > Web app (create one if needed)
 * 5. Copy the config values below
 *
 * IMPORTANT: These values are safe to expose in client-side code.
 * Firebase security rules protect your data, not these keys.
 */

// Firebase configuration - replace with your project's config
const firebaseConfig = {
  apiKey: "YOUR_API_KEY",                           // e.g., "AIzaSyB..."
  authDomain: "YOUR_PROJECT.firebaseapp.com",       // e.g., "my-app.firebaseapp.com"
  projectId: "YOUR_PROJECT_ID",                     // e.g., "my-app-12345"
  storageBucket: "YOUR_PROJECT.appspot.com",        // e.g., "my-app-12345.appspot.com"
  messagingSenderId: "YOUR_SENDER_ID",              // e.g., "123456789"
  appId: "YOUR_APP_ID"                              // e.g., "1:123456789:web:abc123"
};

// Initialize Firebase
if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}

// Initialize Firestore
const db = firebase.firestore();

// Enable persistence for offline support
db.enablePersistence()
  .catch((err) => {
    if (err.code === 'failed-precondition') {
      console.warn('Multiple tabs open, persistence can only be enabled in one tab at a time.');
    } else if (err.code === 'unimplemented') {
      console.warn('Persistence is not available in this browser.');
    }
  });

// Export for use in other modules
window.firebaseConfig = firebaseConfig;
window.db = db;
