(function () {
  const root = document.documentElement;
  let timer = null;
  let layer = null;

  function buildLayer() {
    if (layer) return layer;
    layer = document.createElement('div');
    layer.className = 'tebelo-loading-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = [
      '<div class="tebelo-skeleton-shell">',
      '<div class="tebelo-skeleton-heading"><i></i><span></span></div>',
      '<div class="tebelo-skeleton-metrics"><i></i><i></i><i></i><i></i></div>',
      '<div class="tebelo-skeleton-workspace"><section><b></b><span></span><span></span><span></span><span></span></section><aside><b></b><span></span><span></span><span></span></aside></div>',
      '</div>',
    ].join('');
    document.body.appendChild(layer);
    return layer;
  }

  function show(delay) {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      buildLayer();
      root.classList.add('tebelo-is-loading');
    }, delay == null ? 120 : delay);
  }

  function hide() {
    window.clearTimeout(timer);
    root.classList.remove('tebelo-is-loading');
  }

  function shouldHandleLink(event, link) {
    if (!link || event.defaultPrevented || event.button !== 0) return false;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
    if (link.target && link.target !== '_self') return false;
    if (link.hasAttribute('download') || link.dataset.noSkeleton !== undefined) return false;
    const url = new URL(link.href, window.location.href);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin) return false;
    if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return false;
    return true;
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    if (shouldHandleLink(event, link)) show(120);
  }, true);

  document.addEventListener('submit', (event) => {
    if (event.defaultPrevented || event.target.dataset.noSkeleton !== undefined) return;
    const submitter = event.submitter;
    if (submitter) submitter.setAttribute('aria-busy', 'true');
    show(80);
  }, true);

  document.addEventListener('click', (event) => {
    document.querySelectorAll('.admin-account-menu[open]').forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute('open');
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    document.querySelectorAll('.admin-account-menu[open]').forEach((menu) => menu.removeAttribute('open'));
  });

  window.addEventListener('pageshow', hide);
  window.addEventListener('pagehide', () => show(0));
  window.TebeloLoading = { show, hide };
}());
