/**
 * Theme Management
 * Canvas Speed Grader
 * Handles light/dark/system theme switching
 */

const Theme = {
  STORAGE_KEY: 'speedgrader-theme',
  
  /**
   * Initialize theme on page load
   */
  init() {
    // Get saved preference or default to 'system'
    const savedTheme = localStorage.getItem(this.STORAGE_KEY) || 'system';
    this.apply(savedTheme);
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      const currentTheme = localStorage.getItem(this.STORAGE_KEY);
      if (currentTheme === 'system') {
        this.applySystemTheme();
      }
    });
  },
  
  /**
   * Apply a specific theme
   * @param {string} theme - 'light', 'dark', or 'system'
   */
  apply(theme) {
    localStorage.setItem(this.STORAGE_KEY, theme);
    
    if (theme === 'system') {
      this.applySystemTheme();
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
    
    // Update toggle UI if present
    this.updateToggleUI(theme);
  },
  
  /**
   * Apply system preference
   */
  applySystemTheme() {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  },
  
  /**
   * Get current theme setting
   * @returns {string} Current theme ('light', 'dark', or 'system')
   */
  get() {
    return localStorage.getItem(this.STORAGE_KEY) || 'system';
  },
  
  /**
   * Toggle between light and dark
   */
  toggle() {
    const current = document.documentElement.getAttribute('data-theme');
    const newTheme = current === 'dark' ? 'light' : 'dark';
    this.apply(newTheme);
  },
  
  /**
   * Update toggle UI elements
   * @param {string} theme - Current theme
   */
  updateToggleUI(theme) {
    // Update theme toggle buttons if they exist
    document.querySelectorAll('.theme-toggle-option').forEach(btn => {
      btn.classList.remove('active');
      if (btn.dataset.theme === theme) {
        btn.classList.add('active');
      }
    });
    
    // Update theme select if it exists
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) {
      themeSelect.value = theme;
    }
  },
  
  /**
   * Bind click handlers to theme toggle buttons
   */
  bindToggleButtons() {
    document.querySelectorAll('.theme-toggle-option').forEach(btn => {
      btn.addEventListener('click', () => {
        const theme = btn.dataset.theme;
        if (theme) {
          this.apply(theme);
        }
      });
    });
    
    // Bind theme select dropdown if it exists
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) {
      themeSelect.addEventListener('change', (e) => {
        this.apply(e.target.value);
      });
    }
  }
};

// Initialize theme on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    Theme.init();
    Theme.bindToggleButtons();
  });
} else {
  Theme.init();
  Theme.bindToggleButtons();
}

// Export for use in other modules
window.Theme = Theme;
