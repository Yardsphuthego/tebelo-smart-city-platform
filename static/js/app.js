const toggle = document.querySelector('.nav-toggle');
const sidebar = document.querySelector('.app-sidebar');
const overlay = document.querySelector('.sidebar-overlay');
const closeButton = document.querySelector('.sidebar-close');

function setSidebar(open) {
  if (!sidebar || !overlay) return;
  sidebar.classList.toggle('open', open);
  overlay.classList.toggle('open', open);
  if (toggle) toggle.setAttribute('aria-expanded', String(open));
}

if (toggle) toggle.addEventListener('click', () => setSidebar(true));
if (closeButton) closeButton.addEventListener('click', () => setSidebar(false));
if (overlay) overlay.addEventListener('click', () => setSidebar(false));
