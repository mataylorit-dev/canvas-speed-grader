/**
 * API Client Module
 * Canvas Speed Grader
 *
 * Handles all API communication with the backend
 */

const API = {
  // API base URL - Cloud Run deployment
  baseUrl: 'https://speedgrade-api-891137567722.us-central1.run.app/api',

  /**
   * Make authenticated API request
   */
  async request(endpoint, options = {}) {
    const token = await Auth.getIdToken();
    if (!token) {
      throw new Error('Not authenticated');
    }

    const url = `${this.baseUrl}${endpoint}`;
    const config = {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers
      },
      ...options
    };

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || errorData.message || `Request failed with status ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API Error (${endpoint}):`, error);
      throw error;
    }
  },

  /**
   * Get assignments with rubrics
   */
  async getAssignments() {
    return this.request('/assignments');
  },

  /**
   * Get assignment details
   */
  async getAssignment(assignmentId) {
    return this.request(`/assignments/${assignmentId}`);
  },

  /**
   * Get submissions for an assignment
   */
  async getSubmissions(assignmentId, filters = {}) {
    const params = new URLSearchParams();
    if (filters.ontime) params.append('ontime', 'true');
    if (filters.late) params.append('late', 'true');
    if (filters.resubmitted) params.append('resubmitted', 'true');
    if (filters.missing) params.append('missing', 'true');

    const queryString = params.toString();
    return this.request(`/assignments/${assignmentId}/submissions${queryString ? '?' + queryString : ''}`);
  },

  /**
   * Grade assignment with AI
   * Supports progress callback for real-time updates
   */
  async gradeAssignment(assignmentId, filters = {}, onProgress = null) {
    // Start the grading job
    const startResponse = await this.request(`/grading/start`, {
      method: 'POST',
      body: JSON.stringify({ assignmentId, filters })
    });

    const jobId = startResponse.jobId;

    // Poll for progress
    return new Promise((resolve, reject) => {
      const pollInterval = setInterval(async () => {
        try {
          const status = await this.request(`/grading/status/${jobId}`);

          if (onProgress && status.progress) {
            onProgress(status.progress);
          }

          if (status.status === 'completed') {
            clearInterval(pollInterval);
            resolve(status.result);
          } else if (status.status === 'failed') {
            clearInterval(pollInterval);
            reject(new Error(status.error || 'Grading failed'));
          }
        } catch (error) {
          clearInterval(pollInterval);
          reject(error);
        }
      }, 1000); // Poll every second

      // Timeout after 10 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        reject(new Error('Grading timed out'));
      }, 600000);
    });
  },

  /**
   * Post grades to Canvas
   */
  async postGrades(assignmentId, grades) {
    return this.request(`/grading/post`, {
      method: 'POST',
      body: JSON.stringify({ assignmentId, grades })
    });
  },

  /**
   * Get grading history
   */
  async getGradingHistory(limit = 20) {
    return this.request(`/grading/history?limit=${limit}`);
  },

  /**
   * Get user profile
   */
  async getProfile() {
    return this.request('/user/profile');
  },

  /**
   * Update user profile
   */
  async updateProfile(updates) {
    return this.request('/user/profile', {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  },

  /**
   * Add a new course
   */
  async addCourse(courseDetails) {
    return this.request('/user/courses', {
      method: 'POST',
      body: JSON.stringify(courseDetails)
    });
  },

  /**
   * Set active course
   */
  async setActiveCourse(courseId) {
    return this.request('/user/courses/active', {
      method: 'PUT',
      body: JSON.stringify({ courseId })
    });
  },

  /**
   * Validate Canvas credentials
   */
  async validateCanvasCredentials(canvasUrl, canvasToken, save = false) {
    return this.request('/canvas/validate', {
      method: 'POST',
      body: JSON.stringify({ canvasUrl, canvasToken, save })
    });
  },

  /**
   * Get courses from Canvas
   */
  async getCanvasCourses() {
    return this.request('/canvas/courses');
  },

  // =========================================================================
  // Admin API Methods
  // =========================================================================

  /**
   * Check if current user is admin
   */
  async checkAdmin() {
    return this.request('/admin/check');
  },

  /**
   * Get platform statistics (admin only)
   */
  async getAdminStats() {
    return this.request('/admin/stats');
  },

  /**
   * Get all users (admin only)
   */
  async getAdminUsers(limit = 50, offset = 0) {
    return this.request(`/admin/users?limit=${limit}&offset=${offset}`);
  },

  /**
   * Get user details (admin only)
   */
  async getAdminUser(userId) {
    return this.request(`/admin/users/${userId}`);
  },

  /**
   * Delete user (admin only)
   */
  async deleteAdminUser(userId) {
    return this.request(`/admin/users/${userId}`, {
      method: 'DELETE'
    });
  },

  /**
   * Get subscription status
   */
  async getSubscription() {
    return this.request('/billing/subscription');
  },

  /**
   * Create checkout session
   */
  async createCheckoutSession(priceId) {
    return this.request('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ priceId })
    });
  },

  /**
   * Get payment history
   */
  async getPaymentHistory() {
    return this.request('/billing/history');
  },

  /**
   * Cancel subscription
   */
  async cancelSubscription() {
    return this.request('/billing/cancel', {
      method: 'POST'
    });
  }
};

// Export for use in other modules
window.API = API;
