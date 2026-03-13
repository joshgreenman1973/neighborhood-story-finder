// =============================================================================
// NYC Neighborhood Story Finder
// =============================================================================

const DATA_BASE = 'data/output';
const NYC_CENTER = [-73.98, 40.74];

let map;
let districtsData = null;
let trendsData = null;
let selectedDistrict = null;
let activeCategory = null;
let currentView = 'map'; // 'map' or 'hotspots'
let popup = null;

// Color ramp for activity scores (low → high)
const SCORE_COLORS = [
  [0,   '#1a1a2e'],
  [20,  '#16213e'],
  [35,  '#394882'],
  [50,  '#217ebe'],
  [65,  '#dde44c'],
  [80,  '#ff7c53'],
  [95,  '#d2232a'],
];

const CATEGORY_COLORS = {
  'heat/hot water': '#ff4500',
  'noise':          '#c084fc',
  'parking':        '#f5c542',
  'streets':        '#a0a0a0',
  'housing':        '#ff7c53',
  'safety':         '#d2232a',
  'transit':        '#217ebe',
  'sanitation':     '#dde44c',
  'pests':          '#f59e0b',
  'development':    '#394882',
  'infrastructure': '#707175',
  'environment':    '#57aa4a',
  'health':         '#e7466d',
  'education':      '#9b59b6',
  'government':     '#9b9fbc',
};

// =============================================================================
// Initialize
// =============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  initMap();
  initControls();
  await loadData();
});

function initMap() {
  map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {
        'carto-dark': {
          type: 'raster',
          tiles: [
            'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
            'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
            'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
          ],
          tileSize: 256,
          attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        },
      },
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      layers: [
        { id: 'carto-dark', type: 'raster', source: 'carto-dark', minzoom: 0, maxzoom: 20 },
      ],
    },
    center: NYC_CENTER,
    zoom: 11,
    maxBounds: [[-74.5, 40.3], [-73.4, 41.1]],
    minZoom: 9,
    maxZoom: 16,
  });

  map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
}

// =============================================================================
// Data Loading
// =============================================================================

async function loadData() {
  try {
    const [districtsResp, trendsResp, geoResp] = await Promise.all([
      fetch(`${DATA_BASE}/districts.json`),
      fetch(`${DATA_BASE}/trends.json`),
      fetch(`${DATA_BASE}/geo/community_districts.geojson`),
    ]);

    districtsData = await districtsResp.json();
    trendsData = await trendsResp.json();
    const geoJSON = await geoResp.json();

    // Inject activity scores into GeoJSON features
    for (const feature of geoJSON.features) {
      const cd = feature.properties.cd_code || feature.properties.boro_cd;
      if (cd && districtsData.districts[cd]) {
        feature.properties.cd_code = String(cd);
        feature.properties.activity_score = districtsData.districts[cd].activity_score || 0;
        feature.properties.name = districtsData.districts[cd].name || `District ${cd}`;
      }
    }

    // Add layers once map style is ready
    function onMapReady() {
      addDistrictLayers(geoJSON);
      showOverview();
      hideLoading();
      updateTimestamp();
    }

    if (map.isStyleLoaded()) {
      onMapReady();
    } else {
      map.once('load', onMapReady);
    }

  } catch (err) {
    console.error('Failed to load data:', err);
    document.getElementById('loading-text').textContent = 'Error loading data. Run the pipeline first.';
  }
}

function addDistrictLayers(geoJSON) {
  map.addSource('districts', { type: 'geojson', data: geoJSON });

  // Choropleth fill
  map.addLayer({
    id: 'district-fill',
    type: 'fill',
    source: 'districts',
    paint: {
      'fill-color': [
        'interpolate', ['linear'],
        ['coalesce', ['get', 'activity_score'], 0],
        ...SCORE_COLORS.flat(),
      ],
      'fill-opacity': 0.6,
    },
  });

  // Outline
  map.addLayer({
    id: 'district-outline',
    type: 'line',
    source: 'districts',
    paint: {
      'line-color': 'rgba(255,255,255,0.25)',
      'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.5, 14, 1.5],
    },
  });

  // Highlight outline (selected)
  map.addLayer({
    id: 'district-highlight',
    type: 'line',
    source: 'districts',
    paint: {
      'line-color': '#dde44c',
      'line-width': 2.5,
    },
    filter: ['==', 'cd_code', ''],
  });

  // Labels (requires glyphs in style; skip gracefully if unavailable)
  try {
    map.addLayer({
      id: 'district-labels',
      type: 'symbol',
      source: 'districts',
      layout: {
        'text-field': ['get', 'name'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10, 9, 13, 12],
        'text-font': ['Open Sans Semibold'],
        'text-anchor': 'center',
        'text-max-width': 8,
      },
      paint: {
        'text-color': 'rgba(255,255,255,0.7)',
        'text-halo-color': 'rgba(0,0,0,0.7)',
        'text-halo-width': 1.5,
      },
      minzoom: 11.5,
    });
  } catch (_) { /* glyphs may not be available */ }

  // Interactions
  map.on('click', 'district-fill', (e) => {
    if (!e.features || !e.features[0]) return;
    const cd = e.features[0].properties.cd_code;
    if (cd) selectDistrict(cd);
  });

  map.on('mousemove', 'district-fill', (e) => {
    map.getCanvas().style.cursor = 'pointer';
    if (!e.features || !e.features[0]) return;
    const cd = e.features[0].properties.cd_code;
    const d = districtsData?.districts[cd];
    if (!d) return;

    if (popup) popup.remove();
    popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 15 })
      .setLngLat(e.lngLat)
      .setHTML(`
        <h3>${d.name}</h3>
        <div class="score">Activity Score: ${d.activity_score}</div>
        ${d.themes.slice(0, 2).map(t =>
          `<div style="font-size:11px;color:rgba(255,255,255,0.6);margin-top:2px;">• ${t.label}</div>`
        ).join('')}
      `)
      .addTo(map);
  });

  map.on('mouseleave', 'district-fill', () => {
    map.getCanvas().style.cursor = '';
    if (popup) { popup.remove(); popup = null; }
  });
}

// =============================================================================
// District Selection
// =============================================================================

async function selectDistrict(cd) {
  selectedDistrict = cd;
  const d = districtsData.districts[cd];
  if (!d) return;

  // Hide search + filters when viewing a district
  document.querySelector('.search-bar').style.display = 'none';
  document.querySelector('.filters').style.display = 'none';
  document.querySelector('.view-toggle').style.display = 'none';

  // Highlight on map
  map.setFilter('district-highlight', ['==', 'cd_code', cd]);

  // Fly to district
  // (could compute centroid from GeoJSON but simpler to just zoom in to existing view)

  // Update sidebar header
  const header = document.querySelector('.sidebar-header');
  header.innerHTML = `
    <button class="back-btn visible" onclick="showOverview()">← All Districts</button>
    <h2>${d.name}</h2>
    <div class="district-meta">
      ${d.borough} · CD ${cd} · Activity Score: <strong>${d.activity_score}</strong>
      ${d.complaint_change_pct !== null ?
        `· <span style="color:${d.complaint_change_pct > 0 ? '#d2232a' : '#57aa4a'}">${d.complaint_change_pct > 0 ? '+' : ''}${d.complaint_change_pct}%</span> vs 2wk ago`
        : ''
      }
    </div>
  `;

  // Load detail data
  try {
    const resp = await fetch(`${DATA_BASE}/districts/${cd}.json`);
    const detail = await resp.json();
    renderDistrictDetail(d, detail);
  } catch (err) {
    console.error(`Failed to load detail for ${cd}:`, err);
    renderDistrictSummary(d);
  }
}

function renderDistrictDetail(summary, detail) {
  const content = document.querySelector('.sidebar-content');
  let html = '';

  // Themes
  const themes = detail.themes_detail || [];
  if (themes.length) {
    html += `<div class="section">
      <div class="section-title">Story Leads</div>
      ${themes.map(t => renderThemeCard(t)).join('')}
    </div>`;
  }

  // 311 Spikes
  const spikes = detail.complaints?.spikes || [];
  if (spikes.length) {
    const ageLabels = ['this week', 'last week', '2 wk ago', '3 wk ago'];
    html += `<div class="section">
      <div class="section-title">311 Anomalies (vs 8-week baseline)</div>
      ${spikes.slice(0, 6).map(s => {
        const age = ageLabels[s.weeks_ago ?? 0] || 'recent';
        return `
        <div class="spike-alert ${s.severity}">
          <div class="spike-direction ${s.direction}">${s.direction === 'up' ? '↑' : '↓'}</div>
          <div class="spike-detail">
            <div class="spike-type">${s.type} <span class="spike-age">${age}</span></div>
            <div class="spike-pct">
              ${s.current_week} complaints vs ${s.baseline_avg} wkly avg
              · ${s.pct_change > 0 ? '+' : ''}${s.pct_change}%
              ${s.sustained_weeks ? ` · sustained ${s.sustained_weeks} wk` : ''}
            </div>
          </div>
        </div>`;
      }).join('')}
    </div>`;
  }

  // Top 311 complaints with sparklines
  const complaints = summary.top_complaints || [];
  if (complaints.length) {
    html += `<div class="section">
      <div class="section-title">Top 311 Complaints (12 weeks)</div>
      ${complaints.map(c => `
        <div class="complaint-row">
          <div class="complaint-type" title="${c.type}">${c.type}</div>
          <div class="sparkline-container">
            <canvas class="sparkline-canvas"
              data-values='${JSON.stringify(c.sparkline)}'
              data-spike='${spikes.some(s => s.type === c.type) ? 'true' : 'false'}'
              width="80" height="24"
              style="width:80px;height:24px;">
            </canvas>
          </div>
          <div class="complaint-count">${c.count}</div>
        </div>
      `).join('')}
    </div>`;
  }

  // Reddit posts
  const posts = detail.reddit_posts || [];
  if (posts.length) {
    html += `<div class="section">
      <div class="section-title">Reddit Discussions (${posts.length}, last 2 weeks)</div>
      ${posts.slice(0, 8).map(p => `
        <div class="reddit-post">
          <a href="${p.url}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
          <div class="reddit-meta">
            <span>r/${p.subreddit}</span>
            <span>↑ ${p.score}</span>
            <span>💬 ${p.num_comments}</span>
            <span>${p.date}</span>
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  // News articles
  const news = detail.news || [];
  if (news.length) {
    html += `<div class="section">
      <div class="section-title">Local News (${news.length}, last 2 weeks)</div>
      ${news.slice(0, 6).map(a => `
        <div class="news-article">
          <a href="${a.link}" target="_blank" rel="noopener">${escapeHtml(a.title)}</a>
          <div class="news-outlet">${a.outlet} · ${a.date}</div>
        </div>
      `).join('')}
    </div>`;
  }

  // Community board
  const cb = detail.community_board;
  if (cb && (cb.next_meeting || cb.meetings?.length || cb.topics?.length || cb.url)) {
    const meetings = cb.meetings || [];
    const upcoming = meetings.filter(m => m.days_away != null && m.days_away >= 0);
    const recent = meetings.filter(m => m.days_away != null && m.days_away < 0);
    html += `<div class="section">
      <div class="section-title">Community Board Meetings</div>
      <div class="cb-info">
        ${cb.committees_active?.length ? `<div class="cb-committees">Active committees: ${cb.committees_active.map(c => `<span class="theme-tag">${c}</span>`).join(' ')}</div>` : ''}
        ${upcoming.length ? `
          <div class="cb-upcoming-label">Upcoming</div>
          ${upcoming.slice(0, 5).map(m => `
            <div class="cb-meeting-item">
              <div class="cb-meeting-title">
                ${m.url ? `<a href="${m.url}" target="_blank" rel="noopener">${escapeHtml(m.title)}</a>` : escapeHtml(m.title)}
              </div>
              <div class="cb-meeting-meta">
                <span class="cb-meeting-date">${m.date}</span>
                <span class="theme-tag">${m.committee}</span>
                ${m.days_away === 0 ? '<span class="recency-badge recency-this-week">today</span>' :
                  m.days_away <= 7 ? '<span class="recency-badge recency-this-week">this week</span>' : ''}
              </div>
              ${m.location ? `<div class="cb-meeting-location">${escapeHtml(m.location)}</div>` : ''}
              ${m.description ? `<div class="cb-meeting-desc">${escapeHtml(m.description)}</div>` : ''}
            </div>
          `).join('')}
        ` : ''}
        ${recent.length ? `
          <div class="cb-upcoming-label">Recent</div>
          ${recent.slice(0, 3).map(m => `
            <div class="cb-meeting-item cb-meeting-past">
              <div class="cb-meeting-title">${escapeHtml(m.title)}</div>
              <div class="cb-meeting-meta">
                <span class="cb-meeting-date">${m.date}</span>
                <span class="theme-tag">${m.committee}</span>
              </div>
            </div>
          `).join('')}
        ` : ''}
        ${cb.topics?.length ? `<div class="cb-topics">Topics in play: ${cb.topics.join(', ')}</div>` : ''}
        ${cb.url ? `<div class="cb-link"><a href="${cb.events_url || cb.url}" target="_blank" rel="noopener">All meetings →</a></div>` : ''}
      </div>
    </div>`;
  }

  // Budget requests
  const budgetReqs = detail.budget_requests || [];
  if (budgetReqs.length) {
    html += `<div class="section">
      <div class="section-title">CB Budget Requests (${budgetReqs.length})</div>
      ${budgetReqs.slice(0, 8).map(r => `
        <div class="budget-request">
          <div class="budget-request-text">${escapeHtml(r.request)}</div>
          <div class="budget-request-meta">
            <span class="theme-tag">${r.category}</span>
            <span>${r.agency}</span>
            ${r.priority ? `<span class="budget-priority">${r.priority}</span>` : ''}
          </div>
          ${r.response ? `<div class="budget-response">${escapeHtml(r.response)}</div>` : ''}
        </div>
      `).join('')}
    </div>`;
  }

  // Land use / ULURP
  const landUse = detail.land_use || [];
  if (landUse.length) {
    html += `<div class="section">
      <div class="section-title">Active Land Use / ULURP (${landUse.length})</div>
      ${landUse.slice(0, 6).map(p => `
        <div class="land-use-project">
          <div class="land-use-name">${escapeHtml(p.name)}</div>
          ${p.brief ? `<div class="land-use-brief">${escapeHtml(p.brief)}</div>` : ''}
          <div class="land-use-meta">
            <span class="theme-tag">${p.type || 'ULURP'}</span>
            <span>${p.status}</span>
            ${p.milestone_date ? `<span>${p.milestone_date}</span>` : ''}
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  // DOB permits
  const dob = detail.dob_permits || {};
  if (dob.total) {
    const byType = Object.entries(dob.by_type || {}).sort((a, b) => b[1] - a[1]);
    html += `<div class="section">
      <div class="section-title">Building Permits (${dob.total} filings, 90d)</div>
      <div class="dob-types">
        ${byType.slice(0, 5).map(([type, count]) => `
          <div class="dob-type-row">
            <span class="dob-type-name">${type}</span>
            <span class="dob-type-count">${count}</span>
          </div>
        `).join('')}
      </div>
      ${(dob.notable || []).length ? `
        <div class="dob-notable-label">Notable filings:</div>
        ${dob.notable.slice(0, 5).map(n => `
          <div class="dob-notable">
            <span class="dob-notable-type">${n.type}</span>
            ${escapeHtml(n.address)}
            <span class="dob-notable-date">${n.date}</span>
          </div>
        `).join('')}
      ` : ''}
    </div>`;
  }

  // Council services
  const council = detail.council_services || {};
  if (council.total) {
    html += `<div class="section">
      <div class="section-title">Council Constituent Cases (${council.total}, 90 days)</div>
      ${(council.top_types || []).slice(0, 6).map(([type, count]) => `
        <div class="complaint-row">
          <div class="complaint-type">${type}</div>
          <div class="complaint-count">${count}</div>
        </div>
      `).join('')}
    </div>`;
  }

  // Sources
  const cdNum = selectedDistrict;
  if (cdNum) {
    const borough = Math.floor(parseInt(cdNum) / 100);
    const boroName = {1:'MANHATTAN',2:'BRONX',3:'BROOKLYN',4:'QUEENS',5:'STATEN ISLAND'}[borough] || '';
    const boardNum = String(parseInt(cdNum) % 100).padStart(2, '0');
    const openDataUrl = `https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/erm2-nwe9/explore/query/SELECT%20*%20WHERE%20community_board%20%3D%20%27${boardNum}%20${encodeURIComponent(boroName)}%27%20ORDER%20BY%20created_date%20DESC`;
    html += `<div class="section sources-section">
      <div class="section-title">Sources</div>
      <div class="sources-list">
        <a href="${openDataUrl}" target="_blank" rel="noopener">311 data on NYC Open Data →</a>
        <a href="https://www.reddit.com/search/?q=${encodeURIComponent(summary.name + ' NYC')}" target="_blank" rel="noopener">Search Reddit →</a>
        ${detail.community_board?.url ? `<a href="${detail.community_board.url}" target="_blank" rel="noopener">Community Board page →</a>` : ''}
        <a href="https://data.cityofnewyork.us/City-Government/Register-Of-Community-Board-Budget-Requests/vn4m-mk4t" target="_blank" rel="noopener">CB Budget Requests →</a>
        <a href="https://zap.planning.nyc.gov/" target="_blank" rel="noopener">Zoning Application Portal →</a>
        <a href="https://data.cityofnewyork.us/Housing-Development/DOB-NOW-Build-Job-Application-Filings/w9ak-ipjd" target="_blank" rel="noopener">DOB Permit Filings →</a>
      </div>
    </div>`;
  }

  if (!html) {
    html = '<div class="empty-state"><p>No data available for this district yet. Run the pipeline to collect data.</p></div>';
  }

  content.innerHTML = html;

  // Render sparklines after DOM update
  requestAnimationFrame(renderAllSparklines);
}

function renderDistrictSummary(d) {
  const content = document.querySelector('.sidebar-content');
  let html = '';

  if (d.themes.length) {
    html += `<div class="section">
      <div class="section-title">Top Concerns</div>
      ${d.themes.map(t => `
        <div class="theme-card ${t.intensity}">
          <div class="theme-label">${t.label}</div>
          <div class="theme-meta">
            <span class="theme-tag">${t.category}</span>
            <span class="theme-tag severity-${t.intensity}">${t.intensity}</span>
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  if (d.top_complaints.length) {
    html += `<div class="section">
      <div class="section-title">Top 311 Complaints</div>
      ${d.top_complaints.map(c => `
        <div class="complaint-row">
          <div class="complaint-type">${c.type}</div>
          <div class="sparkline-container">
            <canvas class="sparkline-canvas"
              data-values='${JSON.stringify(c.sparkline)}'
              width="80" height="24"
              style="width:80px;height:24px;">
            </canvas>
          </div>
          <div class="complaint-count">${c.count}</div>
        </div>
      `).join('')}
    </div>`;
  }

  content.innerHTML = html;
  requestAnimationFrame(renderAllSparklines);
}

function renderThemeCard(theme) {
  const ss = theme.story_score || {};
  const recency = theme.recency || (ss.freshness === 'high' ? 'this week' : '');
  return `
    <div class="theme-card ${theme.intensity}">
      <div class="theme-label">
        ${escapeHtml(theme.label)}
        ${recency ? `<span class="recency-badge recency-${recency.replace(/\s+/g, '-')}">${recency}</span>` : ''}
      </div>
      <div class="theme-summary">${escapeHtml(theme.summary || '')}</div>
      <div class="theme-meta">
        <span class="theme-tag">${theme.category}</span>
        <span class="theme-tag severity-${theme.intensity}">${theme.intensity}</span>
        ${ss.verifiability === 'high' ? '<span class="theme-tag verifiable">verifiable</span>' : ''}
      </div>
      ${Object.keys(ss).length ? `
        <div class="story-score">
          ${ss.severity ? `<span class="score-badge severity-${ss.severity}">severity: ${ss.severity}</span>` : ''}
          ${ss.verifiability ? `<span class="score-badge verifiability-${ss.verifiability}">verify: ${ss.verifiability}</span>` : ''}
          ${ss.editorial_potential ? `<span class="score-badge ${ss.editorial_potential}">${ss.editorial_potential}</span>` : ''}
        </div>
      ` : ''}
      ${theme.evidence?.length ? `
        <ul class="evidence-list">
          ${theme.evidence.map(e => `<li>${escapeHtml(e)}</li>`).join('')}
        </ul>
      ` : ''}
    </div>
  `;
}

// =============================================================================
// Overview (no district selected)
// =============================================================================

function showOverview() {
  selectedDistrict = null;
  map.setFilter('district-highlight', ['==', 'cd_code', '']);

  // Restore search + filters
  document.querySelector('.search-bar').style.display = '';
  document.querySelector('.filters').style.display = '';
  document.querySelector('.view-toggle').style.display = '';

  const header = document.querySelector('.sidebar-header');
  header.innerHTML = `
    <h2>NYC Neighborhood Story Finder</h2>
    <div class="district-meta">Click a district on the map to explore story leads</div>
    <button class="about-toggle" onclick="toggleAbout()">About this tool</button>
  `;

  if (currentView === 'hotspots') {
    renderHotSpots();
  } else {
    renderOverviewList();
  }
}

function renderOverviewList() {
  if (!districtsData) return;
  const content = document.querySelector('.sidebar-content');

  const query = (document.getElementById('search-input')?.value || '').toLowerCase().trim();

  // Sort districts by activity score descending
  let sorted = Object.entries(districtsData.districts)
    .sort((a, b) => b[1].activity_score - a[1].activity_score);

  // Filter by search query — match name, borough, themes, complaints
  // Synonym map: common terms → 311 official complaint type keywords
  const SEARCH_SYNONYMS = {
    'trash': 'dirty conditions sanitation litter missed collection overflowing',
    'garbage': 'dirty conditions sanitation litter missed collection overflowing',
    'litter': 'dirty conditions litter basket overflowing sanitation',
    'dog': 'unsanitary condition animal sanitation dirty',
    'poop': 'unsanitary condition sanitation dirty',
    'waste': 'unsanitary condition sanitation dirty missed collection',
    'dirty': 'dirty conditions sanitation unsanitary',
    'filth': 'dirty conditions sanitation unsanitary',
    'rat': 'rodent pest pests',
    'rats': 'rodent pest pests',
    'mice': 'rodent pest pests',
    'mouse': 'rodent pest pests',
    'roach': 'pest unsanitary pests',
    'cockroach': 'pest unsanitary pests',
    'bedbug': 'bed bugs pest pests',
    'bedbugs': 'bed bugs pest pests',
    'bugs': 'bed bugs pest pests rodent',
    'vermin': 'rodent pest pests bed bugs',
    'scaffold': 'scaffold safety construction',
    'scaffolding': 'scaffold safety construction',
    'construction': 'construction general construction building crane scaffold',
    'pothole': 'pothole street condition',
    'noise': 'noise residential commercial street sidewalk vehicle helicopter',
    'parking': 'illegal parking blocked driveway broken parking meter',
    'heat': 'heat hot water',
    'water': 'water leak water system plumbing',
    'homeless': 'homeless person assistance encampment',
    'encampment': 'encampment homeless',
    'tree': 'dead tree overgrown tree new tree request',
    'graffiti': 'graffiti',
    'bike': 'bike roller skate',
    'sewer': 'sewer catch basin',
    'sidewalk': 'sidewalk condition',
    'elevator': 'elevator',
    'mold': 'mold',
    'lead': 'lead paint',
    'air': 'air quality',
    'food': 'food poisoning food establishment',
  };

  if (query) {
    // Expand query with synonyms
    const expandedTerms = query.split(/\s+/).map(term => {
      const syn = SEARCH_SYNONYMS[term];
      return syn ? `${term} ${syn}` : term;
    });

    sorted = sorted.filter(([cd, d]) => {
      const haystack = [
        d.name, d.borough, cd,
        ...d.themes.map(t => `${t.label} ${t.summary || ''} ${t.category}`),
        ...(d.top_complaints || []).map(c => c.type),
        ...(d.all_complaint_types || []),
      ].join(' ').toLowerCase();
      // Each original query term must match (either directly or via synonym expansion)
      return query.split(/\s+/).every(term => {
        const syn = SEARCH_SYNONYMS[term];
        const candidates = syn ? [term, ...syn.split(' ')] : [term];
        return candidates.some(c => haystack.includes(c));
      });
    });
  }

  const title = query
    ? `Search results (${sorted.length})`
    : activeCategory
      ? `Districts with "${activeCategory}" activity (${sorted.length})`
      : `Districts by Activity (${sorted.length})`;

  let html = '';

  // Filter context banner
  if (activeCategory && !query) {
    html += `<div class="filter-banner">
      <span>Showing districts with <strong>${activeCategory}</strong> complaints or activity. Map highlights these districts. Click the pill again to clear.</span>
    </div>`;
  }

  // Top stories — only show on default view with no search active
  if (!query && !activeCategory && trendsData?.top_stories?.length) {
    const recencyLabels = { 'this week': 'THIS WEEK', 'last 2 weeks': 'LAST 2 WK', 'last month': 'LAST MONTH', 'ongoing': 'ONGOING' };
    html += `<div class="section top-stories-section">
      <div class="section-title">What's Happening Now</div>
      ${trendsData.top_stories.slice(0, 8).map(s => `
        <div class="top-story-card" onclick="selectDistrict('${s.cd}')">
          <div class="top-story-header">
            <span class="top-story-district">${s.district_name}</span>
            <span class="recency-badge recency-${(s.recency || 'ongoing').replace(/\s+/g, '-')}">${recencyLabels[s.recency] || s.recency || ''}</span>
          </div>
          <div class="top-story-label">${escapeHtml(s.label)}</div>
          <div class="top-story-summary">${escapeHtml(s.summary)}</div>
          <div class="top-story-meta">
            <span class="theme-tag">${s.category}</span>
            <span class="theme-tag severity-${s.intensity}">${s.intensity}</span>
          </div>
        </div>
      `).join('')}
    </div>`;
  }

  html += `<div class="section">
    <div class="section-title">${title}</div>
    ${sorted.length === 0 ? '<div class="empty-state"><p>No matching districts</p></div>' : ''}
    ${sorted.map(([cd, d], i) => `
      <div class="hotspot-item" onclick="selectDistrict('${cd}')">
        <div class="hotspot-rank">${i + 1}</div>
        <div class="hotspot-info">
          <div class="hotspot-name">${d.name}</div>
          <div class="hotspot-theme">
            ${d.themes[0] ? d.themes[0].label : `${d.complaint_total} complaints (90d)`}
            ${d.spike_counts.high ? ` · <span style="color:#d2232a">${d.spike_counts.high} alerts</span>` : ''}
          </div>
        </div>
        <div class="hotspot-score" style="background:${getScoreColor(d.activity_score)}44;color:${getScoreColor(d.activity_score)}">
          ${d.activity_score}
        </div>
      </div>
    `).join('')}
  </div>`;

  content.innerHTML = html;
}

function renderHotSpots() {
  if (!trendsData) return renderOverviewList();
  const content = document.querySelector('.sidebar-content');

  const hotSpots = trendsData.hot_spots || [];
  if (!hotSpots.length) return renderOverviewList();

  let html = `<div class="section">
    <div class="section-title">Hot Spots — Where Stories Are Brewing</div>
    ${hotSpots.map((h, i) => `
      <div class="hotspot-item" onclick="selectDistrict('${h.cd}')">
        <div class="hotspot-rank">${i + 1}</div>
        <div class="hotspot-info">
          <div class="hotspot-name">${h.name}</div>
          <div class="hotspot-theme">
            ${h.top_theme || 'Multiple spikes detected'}
            · <span style="color:#d2232a">${h.high_spikes} high-severity</span>
          </div>
        </div>
        <div class="hotspot-score" style="background:${getScoreColor(h.activity_score)}44;color:${getScoreColor(h.activity_score)}">
          ${h.activity_score}
        </div>
      </div>
    `).join('')}
  </div>`;

  // Trending topics
  const topics = trendsData.trending_topics || [];
  if (topics.length) {
    html += `<div class="section">
      <div class="section-title">Trending Categories</div>
      ${topics.map(([topic, count]) => `
        <div style="display:flex;align-items:center;gap:8px;padding:4px 0;">
          <span class="filter-pill" style="cursor:default;border-color:${CATEGORY_COLORS[topic] || '#555'}44;color:${CATEGORY_COLORS[topic] || '#888'}">
            ${topic}
          </span>
          <span style="font-size:12px;color:var(--sd2)">${count} districts</span>
        </div>
      `).join('')}
    </div>`;
  }

  content.innerHTML = html;
}

// =============================================================================
// Controls
// =============================================================================

function initControls() {
  // Category filter pills
  document.querySelectorAll('.filter-pill[data-category]').forEach(pill => {
    pill.addEventListener('click', () => {
      const cat = pill.dataset.category;
      if (activeCategory === cat) {
        activeCategory = null;
        pill.classList.remove('active');
      } else {
        document.querySelectorAll('.filter-pill[data-category]').forEach(p => p.classList.remove('active'));
        activeCategory = cat;
        pill.classList.add('active');
      }
      updateMapColors();
      if (!selectedDistrict) {
        if (currentView === 'hotspots') renderHotSpots();
        else renderOverviewList();
      }
    });
  });

  // View toggle
  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentView = btn.dataset.view;
      if (!selectedDistrict) {
        if (currentView === 'hotspots') renderHotSpots();
        else renderOverviewList();
      }
    });
  });

  // Search
  const searchInput = document.getElementById('search-input');
  let searchTimeout = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      if (!selectedDistrict) renderOverviewList();
    }, 150);
  });
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { searchInput.value = ''; renderOverviewList(); }
  });
}

function toggleAbout() {
  const panel = document.getElementById('about-panel');
  panel.style.display = panel.style.display === 'none' ? '' : 'none';
}

function updateMapColors() {
  if (!map.getLayer('district-fill') || !districtsData) return;

  if (!activeCategory) {
    // Reset to activity score choropleth
    map.setPaintProperty('district-fill', 'fill-color', [
      'interpolate', ['linear'],
      ['coalesce', ['get', 'activity_score'], 0],
      ...SCORE_COLORS.flat(),
    ]);
    map.setPaintProperty('district-fill', 'fill-opacity', 0.6);
    return;
  }

  // Color by whether district has themes in this category
  // Build a match expression
  const expression = ['match', ['get', 'cd_code']];
  for (const [cd, d] of Object.entries(districtsData.districts)) {
    const hasCategory = d.themes.some(t => t.category === activeCategory);
    const spikeInCategory = d.spike_counts?.high > 0; // simplified
    expression.push(cd, hasCategory ? (CATEGORY_COLORS[activeCategory] || '#dde44c') : '#1a1a2e');
  }
  expression.push('#1a1a2e'); // default

  map.setPaintProperty('district-fill', 'fill-color', expression);
  map.setPaintProperty('district-fill', 'fill-opacity', 0.7);
}

// =============================================================================
// Helpers
// =============================================================================

function getScoreColor(score) {
  for (let i = SCORE_COLORS.length - 1; i >= 0; i--) {
    if (score >= SCORE_COLORS[i][0]) return SCORE_COLORS[i][1];
  }
  return SCORE_COLORS[0][1];
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function hideLoading() {
  const overlay = document.getElementById('loading-overlay');
  overlay.classList.add('fade-out');
  setTimeout(() => { overlay.style.display = 'none'; }, 500);
}

function updateTimestamp() {
  const el = document.querySelector('.updated');
  if (el && districtsData?.updated) {
    const d = new Date(districtsData.updated);
    el.textContent = `Updated ${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  }
}
