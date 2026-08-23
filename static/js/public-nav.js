const menuButton = document.querySelector('[data-public-menu-toggle]');
const publicNavigation = document.querySelector('[data-public-navigation]');
const navDropdowns = document.querySelectorAll('[data-public-navigation] details');

function setPublicMenu(open) {
  if (!menuButton || !publicNavigation) return;
  publicNavigation.classList.toggle('is-open', open);
  menuButton.setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('public-menu-open', open);
  if (!open) navDropdowns.forEach((dropdown) => dropdown.removeAttribute('open'));
}

if (menuButton) {
  menuButton.addEventListener('click', () => {
    setPublicMenu(!publicNavigation.classList.contains('is-open'));
  });
}

navDropdowns.forEach((dropdown) => {
  dropdown.addEventListener('toggle', () => {
    if (!dropdown.open) return;
    navDropdowns.forEach((other) => {
      if (other !== dropdown) other.removeAttribute('open');
    });
  });
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') setPublicMenu(false);
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 980) setPublicMenu(false);
});
