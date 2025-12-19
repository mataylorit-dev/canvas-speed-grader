/**
 * Authentication Module
 * Canvas Speed Grader
 */

const Auth = {
  /**
   * Sign in with email and password
   */
  async signInWithEmail(email, password) {
    try {
      const userCredential = await firebase.auth().signInWithEmailAndPassword(email, password);

      // Update last login
      await db.collection('users').doc(userCredential.user.uid).update({
        last_login: firebase.firestore.FieldValue.serverTimestamp()
      });

      return userCredential.user;
    } catch (error) {
      console.error('Sign in error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Sign in with Google
   */
  async signInWithGoogle() {
    try {
      const provider = new firebase.auth.GoogleAuthProvider();
      provider.addScope('email');
      provider.addScope('profile');

      const result = await firebase.auth().signInWithPopup(provider);
      const user = result.user;
      const isNewUser = result.additionalUserInfo?.isNewUser || false;

      // Check if user document exists
      const userDoc = await db.collection('users').doc(user.uid).get();

      if (!userDoc.exists) {
        // Create new user document
        await db.collection('users').doc(user.uid).set({
          email: user.email,
          display_name: user.displayName,
          photo_url: user.photoURL,
          auth_type: 'google',
          created_at: firebase.firestore.FieldValue.serverTimestamp(),
          last_login: firebase.firestore.FieldValue.serverTimestamp(),
          courses: [],
          canvas_url: null,
          canvas_token: null
        });
      } else {
        // Update last login
        await db.collection('users').doc(user.uid).update({
          last_login: firebase.firestore.FieldValue.serverTimestamp()
        });
      }

      return { user, isNewUser: isNewUser || !userDoc.exists };
    } catch (error) {
      console.error('Google sign in error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Create a new account with email and password
   */
  async createAccount(email, password, canvasDetails) {
    try {
      // Validate password
      if (!this.validatePassword(password)) {
        throw new Error('Password must be at least 8 characters with uppercase, lowercase, and a number');
      }

      // Create Firebase auth account
      const userCredential = await firebase.auth().createUserWithEmailAndPassword(email, password);
      const user = userCredential.user;

      // Create user document in Firestore
      await db.collection('users').doc(user.uid).set({
        email: email,
        auth_type: 'email',
        canvas_url: canvasDetails.canvasUrl,
        canvas_token: canvasDetails.canvasToken, // In production, encrypt this
        course_id: canvasDetails.courseId,
        courses: [{
          id: canvasDetails.courseId,
          canvas_url: canvasDetails.canvasUrl,
          added_at: new Date().toISOString()
        }],
        created_at: firebase.firestore.FieldValue.serverTimestamp(),
        last_login: firebase.firestore.FieldValue.serverTimestamp()
      });

      return user;
    } catch (error) {
      console.error('Create account error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Sign out
   */
  async signOut() {
    try {
      await firebase.auth().signOut();
    } catch (error) {
      console.error('Sign out error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Send password reset email
   */
  async sendPasswordReset(email) {
    try {
      await firebase.auth().sendPasswordResetEmail(email);
    } catch (error) {
      console.error('Password reset error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Get current user
   */
  getCurrentUser() {
    return firebase.auth().currentUser;
  },

  /**
   * Get current user's data from Firestore
   */
  async getUserData() {
    const user = this.getCurrentUser();
    if (!user) return null;

    try {
      const doc = await db.collection('users').doc(user.uid).get();
      if (doc.exists) {
        return { id: doc.id, ...doc.data() };
      }
      return null;
    } catch (error) {
      console.error('Get user data error:', error);
      return null;
    }
  },

  /**
   * Update user profile
   */
  async updateProfile(updates) {
    const user = this.getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    try {
      await db.collection('users').doc(user.uid).update(updates);
    } catch (error) {
      console.error('Update profile error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Add a new course
   */
  async addCourse(courseDetails) {
    const user = this.getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    try {
      await db.collection('users').doc(user.uid).update({
        courses: firebase.firestore.FieldValue.arrayUnion({
          id: courseDetails.courseId,
          canvas_url: courseDetails.canvasUrl,
          added_at: new Date().toISOString()
        })
      });
    } catch (error) {
      console.error('Add course error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Set active course
   */
  async setActiveCourse(courseId) {
    const user = this.getCurrentUser();
    if (!user) throw new Error('Not authenticated');

    try {
      await db.collection('users').doc(user.uid).update({
        course_id: courseId
      });
    } catch (error) {
      console.error('Set active course error:', error);
      throw this.formatError(error);
    }
  },

  /**
   * Validate password requirements
   */
  validatePassword(password) {
    const hasUppercase = /[A-Z]/.test(password);
    const hasLowercase = /[a-z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    const hasMinLength = password.length >= 8;
    return hasUppercase && hasLowercase && hasNumber && hasMinLength;
  },

  /**
   * Format Firebase errors to user-friendly messages
   */
  formatError(error) {
    const errorMessages = {
      'auth/email-already-in-use': 'This email is already registered. Please sign in instead.',
      'auth/invalid-email': 'Please enter a valid email address.',
      'auth/operation-not-allowed': 'This sign-in method is not enabled.',
      'auth/weak-password': 'Please choose a stronger password.',
      'auth/user-disabled': 'This account has been disabled.',
      'auth/user-not-found': 'No account found with this email.',
      'auth/wrong-password': 'Incorrect password. Please try again.',
      'auth/too-many-requests': 'Too many failed attempts. Please try again later.',
      'auth/popup-closed-by-user': 'Sign-in popup was closed. Please try again.',
      'auth/network-request-failed': 'Network error. Please check your connection.'
    };

    const message = errorMessages[error.code] || error.message || 'An error occurred. Please try again.';
    return new Error(message);
  },

  /**
   * Listen for auth state changes
   */
  onAuthStateChanged(callback) {
    return firebase.auth().onAuthStateChanged(callback);
  },

  /**
   * Get ID token for API requests
   */
  async getIdToken() {
    const user = this.getCurrentUser();
    if (!user) return null;

    try {
      return await user.getIdToken();
    } catch (error) {
      console.error('Get ID token error:', error);
      return null;
    }
  }
};

// Export for use in other modules
window.Auth = Auth;
