// --- Theme Toggle Logic ---

const darkIcon = document.getElementById('theme-toggle-dark-icon');
const lightIcon = document.getElementById('theme-toggle-light-icon-svg');
const themeToggleBtn = document.getElementById('theme-toggle');

// Function to apply the theme
const applyTheme = (isDark) => {
  if (isDark) {
    document.documentElement.classList.add('dark');
    darkIcon.classList.remove('hidden');
    lightIcon.classList.add('hidden');
  } else {
    document.documentElement.classList.remove('dark');
    darkIcon.classList.add('hidden');
    lightIcon.classList.remove('hidden');
  }
};

// Check for saved theme in localStorage or user's OS preference
const initializeTheme = () => {
  const isDarkMode = localStorage.getItem('color-theme') === 'dark' || 
                     (!('color-theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches);
  applyTheme(isDarkMode);
};

// Event listener for the toggle button
themeToggleBtn.addEventListener('click', () => {
  const isDark = document.documentElement.classList.contains('dark');
  localStorage.setItem('color-theme', isDark ? 'light' : 'dark');
  applyTheme(!isDark);
});

// Initialize theme on load
initializeTheme();
