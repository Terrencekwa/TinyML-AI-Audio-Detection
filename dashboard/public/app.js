/**
 * BioShield AI — Dark Purple Analytics Dashboard
 * Enhanced: Relative times, location names, habitat pins, enriched popups
 */

let detectionLogs = [];
let leafMap = null;
let markers = [];
let habitatMarkers = [];

// ══════════════════════════════════════════════════════════
// KNOWN LOCATIONS — for resolving coordinates to place names
// ══════════════════════════════════════════════════════════
const KNOWN_LOCATIONS = [
    { name: 'Royal Belum State Park', lat: 5.5443, lng: 101.4429, radius: 0.25 },
    { name: 'Temenggor Forest Reserve', lat: 5.4200, lng: 101.3300, radius: 0.20 },
    { name: 'Taman Negara National Park', lat: 4.3855, lng: 102.4357, radius: 0.30 },
    { name: 'Kinabatangan River', lat: 5.5683, lng: 118.4552, radius: 0.20 },
    { name: 'Danum Valley Conservation Area', lat: 4.9640, lng: 117.8090, radius: 0.15 },
    { name: 'Tabin Wildlife Reserve', lat: 5.1968, lng: 118.5037, radius: 0.20 },
    { name: 'Endau-Rompin National Park', lat: 2.5365, lng: 103.3457, radius: 0.20 },
    { name: 'Bako National Park', lat: 1.7178, lng: 110.4672, radius: 0.10 },
    { name: 'Gunung Mulu National Park', lat: 4.0480, lng: 114.8120, radius: 0.15 },
    { name: 'Ulu Temburong National Park', lat: 4.5500, lng: 115.1600, radius: 0.15 },
    { name: 'Krau Wildlife Reserve', lat: 3.7500, lng: 102.2000, radius: 0.15 },
    { name: 'Fraser\'s Hill', lat: 3.7156, lng: 101.7378, radius: 0.10 },
    { name: 'Cameron Highlands', lat: 4.4714, lng: 101.3767, radius: 0.10 },
    { name: 'Hulu Perak', lat: 5.3000, lng: 101.2000, radius: 0.25 },
];

// ══════════════════════════════════════════════════════════
// HORNBILL HABITATS — for map pins and sidebar
// ══════════════════════════════════════════════════════════
const HORNBILL_HABITATS = [
    {
        name: 'Royal Belum State Park',
        lat: 5.5443, lng: 101.4429,
        species: ['Rhinoceros Hornbill', 'Great Hornbill', 'Helmeted Hornbill'],
        description: 'One of the oldest rainforests in the world. Home to all 10 species of Malaysian hornbills.',
    },
    {
        name: 'Temenggor Forest Reserve',
        lat: 5.4200, lng: 101.3300,
        species: ['Rhinoceros Hornbill', 'White-crowned Hornbill', 'Bushy-crested Hornbill'],
        description: 'Critical hornbill corridor connecting Belum to the Thai border forests.',
    },
    {
        name: 'Taman Negara National Park',
        lat: 4.3855, lng: 102.4357,
        species: ['Great Hornbill', 'Rhinoceros Hornbill', 'Black Hornbill'],
        description: '130 million year old primary rainforest. Major hornbill nesting site.',
    },
    {
        name: 'Kinabatangan River',
        lat: 5.5683, lng: 118.4552,
        species: ['Rhinoceros Hornbill', 'Oriental Pied Hornbill', 'Wreathed Hornbill'],
        description: 'Sabah\'s longest river with rich riparian hornbill habitat along the floodplain.',
    },
    {
        name: 'Danum Valley Conservation Area',
        lat: 4.9640, lng: 117.8090,
        species: ['Helmeted Hornbill', 'Rhinoceros Hornbill', 'Wrinkled Hornbill'],
        description: 'Pristine lowland dipterocarp forest in Sabah. One of the best sites for rare hornbills.',
    },
    {
        name: 'Tabin Wildlife Reserve',
        lat: 5.1968, lng: 118.5037,
        species: ['Rhinoceros Hornbill', 'Oriental Pied Hornbill', 'White-crowned Hornbill'],
        description: 'Largest wildlife reserve in Sabah. Important hornbill breeding ground.',
    },
    {
        name: 'Ulu Temburong National Park',
        lat: 4.5500, lng: 115.1600,
        species: ['Rhinoceros Hornbill', 'Black Hornbill', 'Wreathed Hornbill'],
        description: 'Pristine rainforest near the Brunei border. Canopy walkway provides hornbill sightings.',
    },
    {
        name: 'Endau-Rompin National Park',
        lat: 2.5365, lng: 103.3457,
        species: ['Great Hornbill', 'Rhinoceros Hornbill', 'Oriental Pied Hornbill'],
        description: 'One of the last remaining lowland rainforests in Peninsular Malaysia.',
    },
    {
        name: 'Bako National Park',
        lat: 1.7178, lng: 110.4672,
        species: ['Oriental Pied Hornbill', 'Black Hornbill'],
        description: 'Sarawak\'s oldest national park with coastal and mangrove hornbill habitats.',
    },
    {
        name: 'Gunung Mulu National Park',
        lat: 4.0480, lng: 114.8120,
        species: ['Rhinoceros Hornbill', 'Wreathed Hornbill', 'Black Hornbill'],
        description: 'UNESCO World Heritage Site with karst pinnacles and montane hornbill populations.',
    },
];

// ══════════════════════════════════════════════════════════
// INITIALIZATION
// ══════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    startClock();
    initMap();
    connectWS();
    // Refresh relative times every 30 seconds
    setInterval(refreshRelativeTimes, 30000);
});

// ── Clock ──
function startClock() {
    const el = document.getElementById('header-clock');
    const tick = () => {
        const d = new Date();
        el.textContent = d.toLocaleTimeString('en-GB', { hour12: false });
    };
    tick();
    setInterval(tick, 1000);
}

// ══════════════════════════════════════════════════════════
// TIME FORMATTING
// ══════════════════════════════════════════════════════════
function formatRelativeTime(timestamp) {
    const now = Date.now();
    const elapsed = now - timestamp;

    if (elapsed < 0) return 'Just now';

    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);

    if (seconds < 60) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ${minutes % 60}m ago`;

    // Check if yesterday
    const detDate = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (detDate.toDateString() === yesterday.toDateString()) {
        return `Yesterday ${detDate.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })}`;
    }

    if (days < 30) return `${days}d ago`;
    if (months < 12) return `${months}mo ago`;
    return `${Math.floor(months / 12)}y ago`;
}

function formatAbsoluteTime(timestamp) {
    const d = new Date(timestamp);
    const now = new Date();

    const day = d.getDate();
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[d.getMonth()];
    const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });

    if (d.getFullYear() === now.getFullYear()) {
        return `${day} ${month}, ${time}`;
    }
    return `${day} ${month} ${d.getFullYear()}, ${time}`;
}

// ══════════════════════════════════════════════════════════
// LOCATION NAME RESOLVER
// ══════════════════════════════════════════════════════════
const addressCache = {};

async function fetchAddress(lat, lng) {
    if (!lat || !lng) return "Unknown Area";
    const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
    if (addressCache[key]) return addressCache[key];

    // Fallback to KNOWN_LOCATIONS first
    let closest = null;
    let closestDist = Infinity;
    for (const loc of KNOWN_LOCATIONS) {
        const dlat = lat - loc.lat;
        const dlng = lng - loc.lng;
        const dist = Math.sqrt(dlat * dlat + dlng * dlng);
        if (dist < loc.radius && dist < closestDist) {
            closest = loc;
            closestDist = dist;
        }
    }
    if (closest) {
        const addr = closestDist < 0.03 ? closest.name : `Near ${closest.name}`;
        addressCache[key] = addr;
        return addr;
    }

    try {
        const res = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=en`);
        const data = await res.json();
        if (data) {
            let addr = data.locality || data.city || data.principalSubdivision || data.countryName || "Unknown Area";
            addressCache[key] = addr;
            return addr;
        }
    } catch (e) {
        console.error("Geocoding failed", e);
    }
    
    addressCache[key] = "Unknown Area";
    return "Unknown Area";
}

// ══════════════════════════════════════════════════════════
// MAP
// ══════════════════════════════════════════════════════════
function initMap() {
    leafMap = L.map('detection-map', { zoomControl: true }).setView([4.2105, 108.9758], 6);

    // ── Tile Layers ──
    const streetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    });

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a> Satellite',
        maxZoom: 19
    });

    const topoMap = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
        maxZoom: 17
    });

    const darkMap = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">Carto</a>',
        subdomains: 'abcd',
        maxZoom: 19
    });

    // Default to street map for detail
    streetMap.addTo(leafMap);

    // Layer switcher control
    const baseMaps = {
        '🗺️ Street Map': streetMap,
        '🛰️ Satellite': satellite,
        '⛰️ Terrain': topoMap,
        '🌙 Dark Mode': darkMap
    };

    L.control.layers(baseMaps, null, { position: 'topright', collapsed: true }).addTo(leafMap);

    // Plot habitat markers
    plotHabitatMarkers();

    // Add map legend
    addMapLegend();

    // Force map to properly render (fixes gray tiles)
    setTimeout(() => leafMap.invalidateSize(), 200);
}

function plotHabitatMarkers() {
    HORNBILL_HABITATS.forEach(h => {
        const habitatIcon = L.divIcon({
            className: 'habitat-marker',
            html: `<div class="habitat-pin">
                <i class="fa-solid fa-tree"></i>
            </div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        });

        const speciesList = h.species.map(s => `<li>${s}</li>`).join('');

        const marker = L.marker([h.lat, h.lng], { icon: habitatIcon })
            .addTo(leafMap)
            .bindPopup(`
                <div class="habitat-popup">
                    <div class="habitat-popup-header">
                        <i class="fa-solid fa-tree"></i>
                        <strong>${h.name}</strong>
                    </div>
                    <p class="habitat-popup-desc">${h.description}</p>
                    <div class="habitat-popup-species">
                        <span class="species-label">Hornbill Species:</span>
                        <ul>${speciesList}</ul>
                    </div>
                    <div class="habitat-popup-coords">
                        <i class="fa-solid fa-location-crosshairs"></i>
                        ${h.lat.toFixed(4)}° N, ${h.lng.toFixed(4)}° E
                    </div>
                </div>
            `, { maxWidth: 280, className: 'habitat-popup-container' });

        habitatMarkers.push(marker);
    });
}

function addMapLegend() {
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = function () {
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = `
            <div class="legend-title">Map Legend</div>
            <div class="legend-item">
                <span class="legend-dot detection-dot"></span>
                <span>Detection</span>
            </div>
            <div class="legend-item">
                <span class="legend-dot habitat-dot"></span>
                <span>Hornbill Habitat</span>
            </div>
        `;
        return div;
    };
    legend.addTo(leafMap);
}

function flyToHabitat(lat, lng) {
    if (leafMap) leafMap.flyTo([lat, lng], 12, { animate: true, duration: 1.2 });
}

// ══════════════════════════════════════════════════════════
// WEBSOCKET
// ══════════════════════════════════════════════════════════
function connectWS() {
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`);

    ws.onopen = () => {
        const pill = document.getElementById('live-pill');
        pill.classList.remove('offline');
        pill.querySelector('span:last-child').textContent = 'Live';
    };

    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);

            if (msg.type === 'init') {
                detectionLogs = msg.detections || [];
                refreshAll();
            } else if (msg.type === 'detection') {
                detectionLogs.push(msg.data);
                addDetection(msg.data);
                refreshStats();
                showToast(msg.data);
                playChime();
            }
        } catch (err) {
            console.error('WS parse error', err);
        }
    };

    ws.onclose = () => {
        const pill = document.getElementById('live-pill');
        pill.classList.add('offline');
        pill.querySelector('span:last-child').textContent = 'Offline';
        setTimeout(connectWS, 5000);
    };
}

// ══════════════════════════════════════════════════════════
// REFRESH ALL UI
// ══════════════════════════════════════════════════════════
function refreshAll() {
    refreshStats();
    renderFeed();
    detectionLogs.forEach(d => plotMarker(d));
}

// ── Stats ──
function refreshStats() {
    const total = detectionLogs.length;
    document.getElementById('stat-detections').textContent = total;

    // Unique species
    const speciesSet = new Set(detectionLogs.map(d => d.species));
    document.getElementById('stat-species').textContent = speciesSet.size;

    // Average confidence
    if (total > 0) {
        const avg = detectionLogs.reduce((s, d) => s + (d.confidence || 0), 0) / total;
        document.getElementById('stat-accuracy').textContent = `${(avg * 100).toFixed(1)}%`;
    }

    // Last detection time — rich format
    if (total > 0) {
        const last = detectionLogs[total - 1];
        document.getElementById('stat-last-time').textContent = formatRelativeTime(last.timestamp);
    }

    document.getElementById('feed-count').textContent = total;
}

// ── Auto-refresh relative times ──
function refreshRelativeTimes() {
    refreshStats();
    // Update all feed items' time displays
    const feedItems = document.querySelectorAll('.feed-item');
    feedItems.forEach((el, idx) => {
        const reversedIdx = detectionLogs.length - 1 - idx;
        if (reversedIdx >= 0 && reversedIdx < detectionLogs.length) {
            const d = detectionLogs[reversedIdx];
            const relEl = el.querySelector('.feed-time-relative');
            if (relEl) relEl.textContent = formatRelativeTime(d.timestamp);
        }
    });
}

// ══════════════════════════════════════════════════════════
// FEED LIST
// ══════════════════════════════════════════════════════════
function renderFeed() {
    const list = document.getElementById('feed-list');
    list.innerHTML = '';

    if (detectionLogs.length === 0) {
        list.innerHTML = `
            <div class="feed-empty">
                <i class="fa-solid fa-satellite-dish"></i>
                <p>Waiting for detections...</p>
            </div>`;
        return;
    }

    [...detectionLogs].reverse().forEach(d => {
        list.appendChild(createFeedItem(d));
    });
}

function addDetection(d) {
    plotMarker(d);

    const list = document.getElementById('feed-list');
    const empty = list.querySelector('.feed-empty');
    if (empty) empty.remove();

    list.insertBefore(createFeedItem(d), list.firstChild);
}

function createFeedItem(d) {
    const el = document.createElement('div');
    el.className = 'feed-item';

    const confPct = ((d.confidence || 0) * 100).toFixed(1);
    const relativeTime = formatRelativeTime(d.timestamp);
    const absoluteTime = formatAbsoluteTime(d.timestamp);
    const lat = d.latitude ? d.latitude.toFixed(4) : '--';
    const lng = d.longitude ? d.longitude.toFixed(4) : '--';
    const locSpanId = 'loc-' + (d.id || Math.random().toString(36).substr(2, 9));
    
    el.innerHTML = `
        <div class="feed-dot"></div>
        <div class="feed-info">
            <span class="feed-species">${d.species}</span>
            <div class="feed-time">
                <span class="feed-time-relative"><i class="fa-regular fa-clock"></i> ${relativeTime}</span>
                <span class="feed-time-absolute">${absoluteTime}</span>
            </div>
            <div class="feed-location">
                <span class="feed-location-name" id="${locSpanId}"><i class="fa-solid fa-location-dot"></i> Loading location...</span>
                <span class="feed-location-coords">${lat}° N, ${lng}° E</span>
            </div>
            <div class="feed-conf">
                <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${confPct}%"></div></div>
                <span class="conf-value">${confPct}%</span>
            </div>
        </div>
    `;

    fetchAddress(d.latitude, d.longitude).then(addr => {
        const span = el.querySelector(`#${locSpanId}`);
        if (span) span.innerHTML = `<i class="fa-solid fa-location-dot"></i> ${addr}`;
    });

    // Click to fly to location on map
    if (d.latitude && d.longitude) {
        el.addEventListener('click', () => {
            leafMap.flyTo([d.latitude, d.longitude], 14, { animate: true });
        });
    }

    return el;
}

// ══════════════════════════════════════════════════════════
// MAP MARKERS — DETECTIONS
// ══════════════════════════════════════════════════════════
function plotMarker(d) {
    if (!leafMap || !d.latitude || !d.longitude) return;

    const icon = L.divIcon({
        className: 'detection-marker',
        html: `<div style="
            width:14px; height:14px; border-radius:50%;
            background:#7C3AED;
            border: 2px solid rgba(124,58,237,0.4);
            box-shadow: 0 0 12px rgba(124,58,237,0.5);
        "></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });

    const confPct = ((d.confidence || 0) * 100).toFixed(1);
    const relTime = formatRelativeTime(d.timestamp);
    const absTime = formatAbsoluteTime(d.timestamp);

    const marker = L.marker([d.latitude, d.longitude], { icon })
        .addTo(leafMap)
        .bindPopup(`
            <div class="detection-popup">
                <div class="detection-popup-species">${d.species}</div>
                <div class="detection-popup-location">
                    <i class="fa-solid fa-spinner fa-spin"></i>
                    <span>Loading address...</span>
                </div>
            </div>
        `, { maxWidth: 260, className: 'detection-popup-container' });

    fetchAddress(d.latitude, d.longitude).then(addr => {
        marker.setPopupContent(`
            <div class="detection-popup">
                <div class="detection-popup-species">${d.species}</div>
                <div class="detection-popup-confidence">
                    <span class="conf-label">Confidence</span>
                    <span class="conf-val">${confPct}%</span>
                </div>
                <div class="detection-popup-location">
                    <i class="fa-solid fa-location-dot"></i>
                    <span>${addr}</span>
                </div>
                <div class="detection-popup-coords">
                    ${d.latitude.toFixed(4)}° N, ${d.longitude.toFixed(4)}° E
                </div>
                <div class="detection-popup-time">
                    <i class="fa-regular fa-clock"></i>
                    <span>${relTime} · ${absTime}</span>
                </div>
            </div>
        `);
    });

    markers.push(marker);
    leafMap.flyTo([d.latitude, d.longitude], 14, { animate: true });
    document.getElementById('coord-display').textContent = `Lat: ${d.latitude.toFixed(4)}, Lng: ${d.longitude.toFixed(4)}`;
}

// ══════════════════════════════════════════════════════════
// TOAST & CHIME
// ══════════════════════════════════════════════════════════
function showToast(d) {
    const toast = document.getElementById('alert-toast');
    document.getElementById('toast-species').textContent = d.species;
    document.getElementById('toast-conf').textContent = `${((d.confidence || 0) * 100).toFixed(1)}% · Loading...`;

    fetchAddress(d.latitude, d.longitude).then(addr => {
        document.getElementById('toast-conf').textContent = `${((d.confidence || 0) * 100).toFixed(1)}% · ${addr}`;
    });

    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 4000);
}

function playChime() {
    const audio = document.getElementById('alert-chime');
    if (audio) {
        audio.currentTime = 0;
        audio.play().catch(() => {});
    }
}
