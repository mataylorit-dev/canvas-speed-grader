/**
 * Grading Module
 * Canvas Speed Grader
 *
 * Handles the grading interface functionality
 */

const Grading = {
  // Current state
  assignment: null,
  submissions: [],
  grades: {},
  currentIndex: -1,

  /**
   * Initialize grading module
   */
  init() {
    this.bindEvents();
  },

  /**
   * Bind event listeners
   */
  bindEvents() {
    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        this.previousSubmission();
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        this.nextSubmission();
      }
    });
  },

  /**
   * Load assignment data
   */
  async loadAssignment(assignmentId) {
    try {
      const response = await API.getAssignment(assignmentId);
      this.assignment = response.assignment;
      this.assignment.rubric = response.rubric;
      return this.assignment;
    } catch (error) {
      console.error('Failed to load assignment:', error);
      throw error;
    }
  },

  /**
   * Load submissions
   */
  async loadSubmissions(assignmentId, filters) {
    try {
      const response = await API.getSubmissions(assignmentId, filters);
      this.submissions = response.submissions;
      return this.submissions;
    } catch (error) {
      console.error('Failed to load submissions:', error);
      throw error;
    }
  },

  /**
   * Start AI grading
   */
  async startGrading(assignmentId, filters, onProgress) {
    try {
      const result = await API.gradeAssignment(assignmentId, filters, onProgress);
      this.assignment = result.assignment;
      this.submissions = result.submissions;
      this.grades = result.grades;
      return result;
    } catch (error) {
      console.error('Grading failed:', error);
      throw error;
    }
  },

  /**
   * Select a submission by index
   */
  selectSubmission(index) {
    if (index < 0 || index >= this.submissions.length) return;
    this.currentIndex = index;
    return this.getCurrentSubmission();
  },

  /**
   * Get current submission
   */
  getCurrentSubmission() {
    if (this.currentIndex < 0) return null;
    return this.submissions[this.currentIndex];
  },

  /**
   * Get grade for current submission
   */
  getCurrentGrade() {
    const submission = this.getCurrentSubmission();
    if (!submission) return null;
    return this.grades[submission.id] || null;
  },

  /**
   * Navigate to previous submission
   */
  previousSubmission() {
    if (this.currentIndex > 0) {
      return this.selectSubmission(this.currentIndex - 1);
    }
    return null;
  },

  /**
   * Navigate to next submission
   */
  nextSubmission() {
    if (this.currentIndex < this.submissions.length - 1) {
      return this.selectSubmission(this.currentIndex + 1);
    }
    return null;
  },

  /**
   * Update score for a criterion
   */
  updateCriterionScore(criterionId, score) {
    const submission = this.getCurrentSubmission();
    if (!submission) return;

    if (!this.grades[submission.id]) {
      this.grades[submission.id] = { criteria: {}, total: 0 };
    }

    if (!this.grades[submission.id].criteria[criterionId]) {
      this.grades[submission.id].criteria[criterionId] = {};
    }

    this.grades[submission.id].criteria[criterionId].score = parseFloat(score) || 0;
    this.recalculateTotal(submission.id);
  },

  /**
   * Update feedback for a criterion
   */
  updateCriterionFeedback(criterionId, feedback) {
    const submission = this.getCurrentSubmission();
    if (!submission) return;

    if (!this.grades[submission.id]) {
      this.grades[submission.id] = { criteria: {}, total: 0 };
    }

    if (!this.grades[submission.id].criteria[criterionId]) {
      this.grades[submission.id].criteria[criterionId] = {};
    }

    this.grades[submission.id].criteria[criterionId].feedback = feedback;
  },

  /**
   * Update general feedback
   */
  updateGeneralFeedback(feedback) {
    const submission = this.getCurrentSubmission();
    if (!submission) return;

    if (!this.grades[submission.id]) {
      this.grades[submission.id] = { criteria: {}, total: 0 };
    }

    this.grades[submission.id].general_feedback = feedback;
  },

  /**
   * Recalculate total score for a submission
   */
  recalculateTotal(submissionId) {
    const grade = this.grades[submissionId];
    if (!grade || !grade.criteria) return 0;

    let total = 0;
    Object.values(grade.criteria).forEach(c => {
      total += parseFloat(c.score) || 0;
    });

    grade.total = total;
    return total;
  },

  /**
   * Get summary statistics
   */
  getSummaryStats() {
    const scores = Object.values(this.grades).map(g => g.total || 0);

    if (scores.length === 0) {
      return { average: 0, highest: 0, lowest: 0, count: 0 };
    }

    const sum = scores.reduce((a, b) => a + b, 0);

    return {
      average: (sum / scores.length).toFixed(1),
      highest: Math.max(...scores),
      lowest: Math.min(...scores),
      count: scores.length
    };
  },

  /**
   * Export grades to CSV
   */
  exportToCSV() {
    if (!this.assignment || !this.submissions.length) {
      throw new Error('No grades to export');
    }

    const headers = ['Student ID', 'Status', 'Total Score'];

    // Add rubric criteria headers
    if (this.assignment.rubric) {
      this.assignment.rubric.forEach(c => {
        headers.push(`${c.description} (Score)`);
        headers.push(`${c.description} (Feedback)`);
      });
    }

    headers.push('General Feedback');

    const rows = this.submissions.map(sub => {
      const grade = this.grades[sub.id] || { criteria: {}, total: 0 };
      const row = [
        sub.anonymous_id,
        sub.status,
        grade.total || 0
      ];

      if (this.assignment.rubric) {
        this.assignment.rubric.forEach(c => {
          const criterionGrade = grade.criteria?.[c.id] || {};
          row.push(criterionGrade.score || 0);
          row.push(`"${(criterionGrade.feedback || '').replace(/"/g, '""')}"`);
        });
      }

      row.push(`"${(grade.general_feedback || '').replace(/"/g, '""')}"`);
      return row;
    });

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    return csv;
  },

  /**
   * Download CSV file
   */
  downloadCSV() {
    const csv = this.exportToCSV();
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `grades_${this.assignment?.name?.replace(/[^a-z0-9]/gi, '_') || 'export'}.csv`);
    link.style.visibility = 'hidden';

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  },

  /**
   * Post grades to Canvas
   */
  async postGrades() {
    if (!this.assignment || !Object.keys(this.grades).length) {
      throw new Error('No grades to post');
    }

    return await API.postGrades(this.assignment.id, this.grades);
  },

  /**
   * Reset grading state
   */
  reset() {
    this.assignment = null;
    this.submissions = [];
    this.grades = {};
    this.currentIndex = -1;
  }
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  Grading.init();
});

// Export for use in other modules
window.Grading = Grading;
