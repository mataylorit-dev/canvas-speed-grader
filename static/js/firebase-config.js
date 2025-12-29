/**
 * Firebase Configuration
 * Canvas Speed Grader
 */

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyC_pplhocY_qEjndq2u66KaQPvOOf494-o",
  authDomain: "speedgrade-96232.firebaseapp.com",
  projectId: "speedgrade-96232",
  storageBucket: "speedgrade-96232.firebasestorage.app",
  messagingSenderId: "891137567722",
  appId: "1:891137567722:web:b8db192a9a7d948e35a093",
  measurementId: "G-RQXDTH6R18"
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
