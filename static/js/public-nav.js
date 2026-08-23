const menuButton = document.querySelector('[data-public-menu-toggle]');
const publicNavigation = document.querySelector('[data-public-navigation]');
const navDropdowns = document.querySelectorAll('[data-public-navigation] details');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

function syncDropdownState() {
  const hasOpenDropdown = Array.from(navDropdowns).some((dropdown) => dropdown.open);
  document.body.classList.toggle('public-dropdown-active', hasOpenDropdown);
}

function finishClosing(dropdown) {
  window.clearTimeout(dropdown.tebeloCloseTimer);
  dropdown.classList.remove('is-closing');
  dropdown.removeAttribute('open');
  syncDropdownState();
}

function closeDropdown(dropdown, immediate = false) {
  if (!dropdown.open) return;
  if (immediate || reducedMotion.matches) {
    finishClosing(dropdown);
    return;
  }
  dropdown.classList.add('is-closing');
  window.clearTimeout(dropdown.tebeloCloseTimer);
  dropdown.tebeloCloseTimer = window.setTimeout(() => finishClosing(dropdown), 120);
}

function openDropdown(dropdown) {
  window.clearTimeout(dropdown.tebeloCloseTimer);
  dropdown.classList.remove('is-closing');
  navDropdowns.forEach((other) => {
    if (other !== dropdown) closeDropdown(other);
  });
  dropdown.setAttribute('open', '');
  syncDropdownState();
}

function closeAllDropdowns(immediate = false) {
  navDropdowns.forEach((dropdown) => closeDropdown(dropdown, immediate));
}

function setPublicMenu(open) {
  if (!menuButton || !publicNavigation) return;
  publicNavigation.classList.toggle('is-open', open);
  menuButton.setAttribute('aria-expanded', String(open));
  document.body.classList.toggle('public-menu-open', open);
  if (!open) closeAllDropdowns(true);
}

if (menuButton) {
  menuButton.addEventListener('click', () => {
    setPublicMenu(!publicNavigation.classList.contains('is-open'));
  });
}

navDropdowns.forEach((dropdown) => {
  const controller = dropdown.querySelector(':scope > summary');
  controller?.addEventListener('click', (event) => {
    event.preventDefault();
    if (dropdown.open && !dropdown.classList.contains('is-closing')) closeDropdown(dropdown);
    else openDropdown(dropdown);
  });
});

document.addEventListener('pointerdown', (event) => {
  if (event.target.closest('.public-nav-dropdown')) return;
  closeAllDropdowns();
}, true);

document.addEventListener('focusin', (event) => {
  if (event.target.closest('.public-nav-dropdown')) return;
  closeAllDropdowns();
});

if (publicNavigation) publicNavigation.addEventListener('click', (event) => {
  if (!event.target.closest('a[href]')) return;
  setPublicMenu(false);
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  const openDropdown = Array.from(navDropdowns).find((dropdown) => dropdown.open);
  if (window.innerWidth <= 980) setPublicMenu(false);
  else closeAllDropdowns();
  openDropdown?.querySelector(':scope > summary')?.focus();
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 980) setPublicMenu(false);
});
