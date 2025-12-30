/**
 * Firebase Configuration
 * Canvas Speed Grader
 */

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyA_bqTtyDgy7Mz0uk7ajFd1BT4zvgJwjpE",
  authDomain: "classcrew-app.firebaseapp.com",
  projectId: "classcrew-app",
  storageBucket: "classcrew-app.firebasestorage.app",
  messagingSenderId: "492504311516",
  appId: "1:492504311516:web:423417927897a1a500b619"
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

// Handle redirect result (catches the "missing initial state" error)
firebase.auth().getRedirectResult()
  .then((result) => {
    // Redirect sign-in successful (if any)
    if (result.user) {
      console.log('Redirect sign-in successful');
    }
  })
  .catch((error) => {
    // Ignore the "missing initial state" error - it's not critical
    if (error.message && error.message.includes('missing initial state')) {
      console.warn('Firebase auth redirect state warning (safe to ignore):', error.message);
    } else if (error.code !== 'auth/popup-closed-by-user') {
      console.error('Firebase auth error:', error);
    }
  });

// Export for use in other modules
window.firebaseConfig = firebaseConfig;
window.db = db;
