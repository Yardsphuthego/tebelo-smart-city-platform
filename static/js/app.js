const menuButton = document.querySelector('[data-workspace-menu-toggle]');
const navigationRows = document.querySelectorAll('[data-workspace-navigation]');
const account = document.querySelector('[data-workspace-account]');

function closeMenus() {
  navigationRows.forEach((navigation) => navigation.classList.remove('is-open'));
  if (menuButton) menuButton.setAttribute('aria-expanded', 'false');
  if (account) account.removeAttribute('open');
}

if (menuButton && navigationRows.length) menuButton.addEventListener('click', () => {
  const open = !Array.from(navigationRows).some((navigation) => navigation.classList.contains('is-open'));
  closeMenus();
  navigationRows.forEach((navigation) => navigation.classList.toggle('is-open', open));
  menuButton.setAttribute('aria-expanded', String(open));
});

document.addEventListener('click', (event) => {
  if (account && account.open && !account.contains(event.target)) account.removeAttribute('open');
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenus(); });
window.addEventListener('resize', () => {
  if (window.innerWidth > 980) navigationRows.forEach((navigation) => navigation.classList.remove('is-open'));
});
