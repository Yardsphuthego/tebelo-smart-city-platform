(function () {
  function dismiss(notice) {
    notice.classList.add('is-dismissed');
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-command-notice]').forEach((notice) => {
      const text = notice.querySelector('[data-command-notice-text]');
      const close = notice.querySelector('[data-command-notice-close]');
      close?.addEventListener('click', () => dismiss(notice));
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        window.setTimeout(() => dismiss(notice), 4500);
      } else {
        text?.addEventListener('animationend', () => dismiss(notice), { once: true });
      }
    });
  });
}());
