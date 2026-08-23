(function () {
  const element = document.querySelector('[data-tebelo-map]');
  if (!element) return;

  const mapContainer = element.parentElement;
  const feedback = mapContainer.querySelector('[data-map-feedback]');
  const locateButtons = document.querySelectorAll('[data-map-locate]');
  const setLoading = (loading) => {
    mapContainer.classList.toggle('is-loading', loading);
    element.setAttribute('aria-busy', String(loading));
  };
  const setFeedback = (message, state = '') => {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.dataset.state = state;
    feedback.hidden = !message;
  };

  if (typeof window.maplibregl === 'undefined' || typeof window.maplibregl.Map !== 'function') {
    setLoading(false);
    setFeedback('The interactive map library could not be loaded. Check your connection and try again.', 'error');
    return;
  }

  const overview = element.dataset.mode === 'overview';
  let map;
  try {
    map = new window.maplibregl.Map({
      container: element,
      style: element.dataset.styleUrl,
      center: [25.9231, -24.6282],
      zoom: 11.5,
      attributionControl: false,
      cooperativeGestures: overview,
    });
  } catch (error) {
    setLoading(false);
    setFeedback('This browser cannot initialise the interactive map. Enable hardware acceleration or use a current browser.', 'error');
    return;
  }
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  map.addControl(new window.maplibregl.AttributionControl({ compact: true }), 'bottom-left');

  const geolocate = new window.maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    trackUserLocation: false,
    showUserLocation: true,
    fitBoundsOptions: { maxZoom: 15 },
  });
  map.addControl(geolocate, 'bottom-right');
  locateButtons.forEach((button) => button.addEventListener('click', () => {
    button.disabled = true;
    button.textContent = 'Locating…';
    geolocate.trigger();
  }));
  geolocate.on('geolocate', () => {
    locateButtons.forEach((button) => { button.disabled = false; button.textContent = 'Find me'; });
    setFeedback('');
  });
  geolocate.on('error', () => {
    locateButtons.forEach((button) => { button.disabled = false; button.textContent = 'Find me'; });
    setFeedback('Your location could not be accessed. Check browser permissions.', 'error');
  });

  function popupContent(properties) {
    const wrapper = document.createElement('div');
    wrapper.className = 'incident-popup';
    const title = document.createElement('strong');
    title.textContent = properties.category || 'Incident';
    const summary = document.createElement('p');
    summary.textContent = properties.summary || 'Public incident information.';
    const meta = document.createElement('small');
    const reported = properties.reported_at ? new Date(properties.reported_at).toLocaleString() : '';
    meta.textContent = [properties.status, reported].filter(Boolean).join(' · ');
    wrapper.append(title, summary, meta);
    return wrapper;
  }

  function watchPopupContent(properties) {
    const wrapper = document.createElement('div');
    wrapper.className = 'incident-popup watch-popup';
    const label = document.createElement('small');
    label.textContent = 'Police-reviewed Neighborhood Watch';
    const title = document.createElement('strong');
    title.textContent = properties.name || 'Neighborhood Watch';
    const meta = document.createElement('p');
    const members = Number(properties.member_count || 0);
    meta.textContent = `${properties.area || 'Gaborone'} · ${members} active member${members === 1 ? '' : 's'}`;
    const link = document.createElement('a');
    link.href = properties.url;
    link.textContent = 'View group →';
    wrapper.append(label, title, meta, link);
    return wrapper;
  }

  const watchRequest = element.dataset.watchEndpoint
    ? fetch(element.dataset.watchEndpoint, { headers: { Accept: 'application/geo+json, application/json' } }).then((response) => {
      if (!response.ok) throw new Error(`Watch map data request failed (${response.status})`);
      return response.json();
    })
    : Promise.resolve({ type: 'FeatureCollection', features: [] });

  Promise.all([
    new Promise((resolve, reject) => {
      map.once('load', resolve);
      map.once('error', (event) => reject(event.error));
    }),
    fetch(element.dataset.endpoint, { headers: { Accept: 'application/geo+json, application/json' } }).then((response) => {
      if (!response.ok) throw new Error(`Map data request failed (${response.status})`);
      return response.json();
    }),
    watchRequest,
  ]).then(([, data, watchData]) => {
    map.addSource('incidents', { type: 'geojson', data });
    map.addLayer({
      id: 'incident-halo', type: 'circle', source: 'incidents',
      paint: { 'circle-radius': overview ? 10 : 11, 'circle-color': '#ffffff', 'circle-opacity': 0.9 },
    });
    map.addLayer({
      id: 'incidents', type: 'circle', source: 'incidents',
      paint: {
        'circle-radius': overview ? 6 : 7,
        'circle-color': [
          'case', ['==', ['get', 'priority'], 'critical'], '#b42318',
          ['match', ['get', 'domain'], 'safety', '#8f463f', 'traffic', '#9a741e', 'fire', '#b04a3f',
            'utilities', '#3a7769', 'infrastructure', '#526e68', 'medical', '#6d5b82',
            'environment', '#47745d', 'community', '#4b687d', '#176b5b'],
        ],
      },
    });
    map.on('mouseenter', 'incidents', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'incidents', () => { map.getCanvas().style.cursor = ''; });
    map.on('click', 'incidents', (event) => {
      const feature = event.features[0];
      new window.maplibregl.Popup({ offset: 12, maxWidth: '280px' })
        .setLngLat(feature.geometry.coordinates.slice())
        .setDOMContent(popupContent(feature.properties))
        .addTo(map);
    });
    if (watchData.features.length) {
      map.addSource('watch-groups', { type: 'geojson', data: watchData });
      map.addLayer({
        id: 'watch-coverage', type: 'fill', source: 'watch-groups',
        filter: ['==', ['get', 'feature_kind'], 'coverage'],
        paint: { 'fill-color': '#0a4f78', 'fill-opacity': 0.12 },
      });
      map.addLayer({
        id: 'watch-coverage-border', type: 'line', source: 'watch-groups',
        filter: ['==', ['get', 'feature_kind'], 'coverage'],
        paint: { 'line-color': '#0a4f78', 'line-width': 1.5 },
      });
      map.addLayer({
        id: 'watch-groups', type: 'circle', source: 'watch-groups',
        filter: ['==', ['get', 'feature_kind'], 'centre'],
        paint: {
          'circle-radius': overview ? 6 : 7,
          'circle-color': '#ffffff', 'circle-stroke-color': '#0a4f78', 'circle-stroke-width': 3,
        },
      });
      map.on('mouseenter', 'watch-groups', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'watch-groups', () => { map.getCanvas().style.cursor = ''; });
      map.on('click', 'watch-groups', (event) => {
        const feature = event.features[0];
        new window.maplibregl.Popup({ offset: 12, maxWidth: '300px' })
          .setLngLat(feature.geometry.coordinates.slice())
          .setDOMContent(watchPopupContent(feature.properties))
          .addTo(map);
      });
      map.on('click', 'watch-coverage', (event) => {
        if (map.queryRenderedFeatures(event.point, { layers: ['watch-groups'] }).length) return;
        const feature = event.features[0];
        new window.maplibregl.Popup({ offset: 12, maxWidth: '300px' })
          .setLngLat(event.lngLat)
          .setDOMContent(watchPopupContent(feature.properties))
          .addTo(map);
      });
    }
    if (!overview && (data.features.length || watchData.features.length)) {
      const bounds = new window.maplibregl.LngLatBounds();
      data.features.forEach((feature) => bounds.extend(feature.geometry.coordinates));
      watchData.features.forEach((feature) => {
        if (feature.geometry.type === 'Point') bounds.extend(feature.geometry.coordinates);
        if (feature.geometry.type === 'Polygon') feature.geometry.coordinates[0].forEach((coordinate) => bounds.extend(coordinate));
      });
      map.fitBounds(bounds, { padding: 70, maxZoom: 14, duration: 700 });
    }
    setLoading(false);
    setFeedback('');
  }).catch(() => {
    setLoading(false);
    setFeedback('The map service is temporarily unavailable. Please retry shortly.', 'error');
  });

  map.on('idle', () => setFeedback(''));
  const refreshSize = () => window.requestAnimationFrame(() => map.resize());
  window.addEventListener('resize', refreshSize);
  if ('ResizeObserver' in window) new ResizeObserver(refreshSize).observe(element);
  if ('IntersectionObserver' in window) new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) refreshSize();
  }).observe(element);
  setTimeout(refreshSize, 150);
}());
