const menuButton = document.querySelector('[data-public-menu-toggle]');
const publicNavigation = document.querySelector('[data-public-navigation]');
const navDropdowns = document.querySelectorAll('[data-public-navigation] details');

function syncDropdownState() {
  const hasOpenDropdown = Array.from(navDropdowns).some((dropdown) => dropdown.open);
  document.body.classList.toggle('public-dropdown-active', hasOpenDropdown);
}

function setPublicMenu(open) {
  if (!menuButton || !publicNavigation) return;
  publicNavigation.classList.toggle('is-open', open);
  menuButton.setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('public-menu-open', open);
  if (!open) {
    navDropdowns.forEach((dropdown) => dropdown.removeAttribute('open'));
    syncDropdownState();
  }
}

if (menuButton) {
  menuButton.addEventListener('click', () => {
    setPublicMenu(!publicNavigation.classList.contains('is-open'));
  });
}

navDropdowns.forEach((dropdown) => {
  dropdown.addEventListener('toggle', () => {
    if (dropdown.open) {
      navDropdowns.forEach((other) => {
        if (other !== dropdown) other.removeAttribute('open');
      });
    }
    syncDropdownState();
  });
});

document.addEventListener('click', (event) => {
  if (event.target.closest('.public-nav-dropdown')) return;
  navDropdowns.forEach((dropdown) => dropdown.removeAttribute('open'));
  syncDropdownState();
});

if (publicNavigation) publicNavigation.addEventListener('click', (event) => {
  if (!event.target.closest('a[href]')) return;
  setPublicMenu(false);
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    setPublicMenu(false);
    menuButton?.focus();
  }
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 980) setPublicMenu(false);
});
