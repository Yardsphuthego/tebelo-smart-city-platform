const menuButton = document.querySelector('[data-workspace-menu-toggle]');
const navigation = document.querySelector('[data-workspace-navigation]');
const account = document.querySelector('[data-workspace-account]');

function closeMenus() {
  if (navigation) navigation.classList.remove('is-open');
  if (menuButton) menuButton.setAttribute('aria-expanded', 'false');
  if (account) account.removeAttribute('open');
}

if (menuButton && navigation) menuButton.addEventListener('click', () => {
  const open = !navigation.classList.contains('is-open');
  closeMenus();
  navigation.classList.toggle('is-open', open);
  menuButton.setAttribute('aria-expanded', String(open));
});

document.addEventListener('click', (event) => {
  if (account && account.open && !account.contains(event.target)) account.removeAttribute('open');
});
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenus(); });
window.addEventListener('resize', () => { if (window.innerWidth > 980 && navigation) navigation.classList.remove('is-open'); });
