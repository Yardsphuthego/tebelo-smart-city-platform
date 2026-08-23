(() => {
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const validSettings = new Set(['light', 'dark', 'system']);

  function getSetting() {
    try {
      const saved = localStorage.getItem('tebelo-theme');
      return validSettings.has(saved) ? saved : 'system';
    } catch (_) {
      return 'system';
    }
  }

  function resolvedTheme(setting) {
    return setting === 'system' ? (media.matches ? 'dark' : 'light') : setting;
  }

  function applyTheme(setting, persist = false) {
    const resolved = resolvedTheme(setting);
    document.documentElement.dataset.themeSetting = setting;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
    if (persist) {
      try { localStorage.setItem('tebelo-theme', setting); } catch (_) { /* no-op */ }
    }
    document.querySelectorAll('[data-theme-option]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.themeOption === setting));
    });
    document.querySelectorAll('[data-theme-label]').forEach((label) => {
      label.textContent = setting === 'system' ? 'System' : `${setting[0].toUpperCase()}${setting.slice(1)}`;
    });
    const themeColour = document.querySelector('meta[name="theme-color"]');
    if (themeColour) themeColour.content = resolved === 'dark' ? '#0d1521' : '#ffffff';
  }

  applyTheme(getSetting());
  document.addEventListener('DOMContentLoaded', () => {
    applyTheme(getSetting());
    document.querySelectorAll('[data-theme-option]').forEach((button) => {
      button.addEventListener('click', () => {
        applyTheme(button.dataset.themeOption, true);
        button.closest('details')?.removeAttribute('open');
      });
    });
  });
  media.addEventListener('change', () => {
    if (getSetting() === 'system') applyTheme('system');
  });
})();
