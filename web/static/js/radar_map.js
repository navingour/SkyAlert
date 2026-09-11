/**
 * SkyAlert Interactive Radar Map Engine
 * Leaflet.js dark radar visualization with fixed station, range rings, heading-rotated markers, and flight tracks.
 */

class SkyAlertRadarMap {
    constructor(containerId = "leaflet-radar-map") {
        this.containerId = containerId;
        this.map = null;
        this.stationLat = 22.5726;
        this.stationLon = 88.3639;
        this.markers = {};
        this.trackLayer = null;
        this.rangeRingsLayer = null;
        this.isInitialized = false;
    }

    init(stationLat = 22.5726, stationLon = 88.3639) {
        if (this.isInitialized || !document.getElementById(this.containerId)) return;
        
        this.stationLat = stationLat;
        this.stationLon = stationLon;

        // Create Leaflet map
        this.map = L.map(this.containerId, {
            center: [this.stationLat, this.stationLon],
            zoom: 8,
            zoomControl: false,
            attributionControl: false
        });

        L.control.zoom({ position: 'bottomright' }).addTo(this.map);

        // Dark Basemap Tiles
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
            subdomains: 'abcd'
        }).addTo(this.map);

        this.trackLayer = L.layerGroup().addTo(this.map);
        this.drawRangeRings();
        this.drawStationMarker();

        this.isInitialized = true;
    }

    drawStationMarker() {
        const stationIcon = L.divIcon({
            className: 'station-map-marker',
            html: `
                <div style="
                    position: relative;
                    width: 24px;
                    height: 24px;
                    background: rgba(56, 189, 248, 0.2);
                    border: 2px solid #38bdf8;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 0 15px #38bdf8;
                ">
                    <div style="width: 6px; height: 6px; background: #fff; border-radius: 50%;"></div>
                </div>
            `,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });

        L.marker([this.stationLat, this.stationLon], { icon: stationIcon })
            .addTo(this.map)
            .bindTooltip(`<b>SkyAlert Fixed Station</b><br>Lat: ${this.stationLat.toFixed(4)}, Lon: ${this.stationLon.toFixed(4)}`, {
                direction: 'top',
                className: 'sky-map-tooltip'
            });
    }

    drawRangeRings() {
        if (this.rangeRingsLayer) {
            this.rangeRingsLayer.clearLayers();
        } else {
            this.rangeRingsLayer = L.layerGroup().addTo(this.map);
        }

        const rangesKm = [50, 100, 150, 200, 250];
        rangesKm.forEach(distKm => {
            const circle = L.circle([this.stationLat, this.stationLon], {
                radius: distKm * 1000,
                color: 'rgba(56, 189, 248, 0.2)',
                weight: 1,
                fill: false,
                dashArray: '4, 8'
            });
            this.rangeRingsLayer.addLayer(circle);

            // Ring distance label on North axis
            const labelLat = this.stationLat + (distKm / 111.0);
            const labelMarker = L.marker([labelLat, this.stationLon], {
                icon: L.divIcon({
                    className: 'range-label',
                    html: `<span style="font-size: 9px; font-family: monospace; color: #64748b; background: rgba(7,10,19,0.8); padding: 1px 4px; border-radius: 2px;">${distKm} km</span>`,
                    iconSize: [40, 14],
                    iconAnchor: [20, 7]
                })
            });
            this.rangeRingsLayer.addLayer(labelMarker);
        });
    }

    getAltitudeColor(altitudeFt) {
        if (!altitudeFt) return '#38bdf8';
        if (altitudeFt < 5000) return '#22c55e';    // Low (Green)
        if (altitudeFt < 15000) return '#eab308';   // Mid-low (Yellow)
        if (altitudeFt < 28000) return '#f97316';   // Mid (Orange)
        if (altitudeFt < 38000) return '#38bdf8';   // High (Cyan)
        return '#a855f7';                           // Very High (Purple)
    }

    updateAircraftMarkers(aircraftList) {
        if (!this.map) return;
        const currentHexes = new Set();

        aircraftList.forEach(plane => {
            const live = plane.live || {};
            const identity = plane.identity || {};

            const lat = plane.latitude || plane.lat || live.lat;
            const lon = plane.longitude || plane.lon || live.lon;
            if (lat === undefined || lon === undefined || lat === null || lon === null) return;

            const hex = (plane.icao_hex || identity.icao_hex || live.hex || plane.hex || plane.id || "").toUpperCase();
            if (!hex) return;
            currentHexes.add(hex);

            const track = plane.track !== undefined ? plane.track : (live.track || 0);
            const alt = plane.altitude_ft || plane.altitude_baro || plane.alt_baro || live.alt_baro || 0;
            const color = this.getAltitudeColor(alt);
            const callsign = (plane.callsign && plane.callsign !== "-") ? plane.callsign : (identity.callsign || live.flight || hex);
            const reg = (plane.registration && plane.registration !== "-") ? plane.registration : (identity.registration || hex);
            const opCandidates = [plane.operator, identity.operator, plane.operator_name, identity.operator_name];
            const validOp = opCandidates.find(o => o && !['Unknown', 'Unknown Operator', 'Commercial Operator', 'In Transit', '-', 'null', 'None', ''].includes(String(o).trim()));
            const op = validOp || 'Unknown Operator';

            const modelCandidates = [
                plane.model, identity.model, plane.aircraft_type, identity.aircraft_type,
                identity.type_code, identity.icao_aircraft_type, live.t, plane.t, plane.description
            ];
            const validModel = modelCandidates.find(m => m && !['Unknown', 'Unknown Type', 'Unknown Operator', '-', 'null', 'None', ''].includes(String(m).trim()));
            const model = validModel || 'Unknown Type';
            const rawSpeed = plane.speed_kts || live.gs || plane.gs;
            const speedStr = rawSpeed ? `${Math.round(rawSpeed * 1.852)} km/h` : (plane.speed_kmh ? `${Math.round(plane.speed_kmh)} km/h` : 'Unknown');
            const distStr = plane.distance_km ? `${plane.distance_km} km` : (live.r_dst ? `${live.r_dst} km` : 'N/A');
            const bearingStr = plane.bearing ? `${plane.bearing}°` : (live.r_dir ? `${live.r_dir}°` : 'N/A');

            const oatVal = plane.oat !== undefined && plane.oat !== null ? plane.oat : live.oat;
            const tatVal = plane.tat !== undefined && plane.tat !== null ? plane.tat : live.tat;
            const wsVal = plane.ws !== undefined && plane.ws !== null ? plane.ws : live.ws;
            const wdVal = plane.wd !== undefined && plane.wd !== null ? plane.wd : live.wd;
            const seenVal = plane.seen !== undefined && plane.seen !== null ? plane.seen : live.seen;

            const tempStr = (oatVal !== undefined && oatVal !== null) ? `${Math.round(oatVal * 10) / 10}°C` : ((tatVal !== undefined && tatVal !== null) ? `${Math.round(tatVal * 10) / 10}°C` : null);
            const windMs = (wsVal !== undefined && wsVal !== null) ? `${Math.round(wsVal * 0.514444 * 10) / 10} m/s` : null;
            const windStr = (wdVal !== undefined && wdVal !== null && windMs) ? `${wdVal}° / ${windMs}` : windMs;
            const contactStr = (seenVal !== undefined && seenVal !== null) ? (seenVal < 60 ? `${Math.round(seenVal * 10) / 10}s ago` : `${Math.round(seenVal / 60)}m ago`) : null;

            const planeSvg = `
                <svg width="28" height="28" viewBox="0 0 24 24" style="transform: rotate(${track}deg); filter: drop-shadow(0 0 4px ${color});">
                    <path fill="${color}" d="M21,16L21,14L13,9L13,3.5A1.5,1.5 0 0,0 11.5,2A1.5,1.5 0 0,0 10,3.5L10,9L2,14L2,16L10,13.5L10,19L8,20.5L8,22L11.5,21L15,22L15,20.5L13,19L13,13.5L21,16Z"/>
                </svg>
            `;

            const icon = L.divIcon({
                className: 'aircraft-map-icon',
                html: `
                    <div style="display: flex; flex-direction: column; align-items: center; cursor: pointer;">
                        ${planeSvg}
                        <span style="font-family: monospace; font-size: 10px; font-weight: 700; color: #fff; background: rgba(13,19,34,0.85); padding: 1px 4px; border-radius: 3px; border: 1px solid rgba(255,255,255,0.1); margin-top: -2px; white-space: nowrap;">
                            ${callsign}
                        </span>
                    </div>
                `,
                iconSize: [60, 42],
                iconAnchor: [30, 14]
            });

            const popupContent = `
                <div style="font-family: sans-serif; min-width: 180px; color: #f8fafc;">
                    <div style="font-weight: 700; font-size: 14px; color: #38bdf8; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 4px; margin-bottom: 6px;">
                        ${callsign} (${reg})
                    </div>
                    <div style="font-size: 11px; line-height: 1.6; color: #94a3b8;">
                        <div><b>ICAO:</b> <span style="font-family: monospace; color:#fff;">${hex}</span></div>
                        <div><b>Type:</b> ${model}</div>
                        <div><b>Operator:</b> ${op}</div>
                        <div><b>Altitude:</b> ${alt ? alt.toLocaleString() + ' ft' : 'Unknown'}</div>
                        <div><b>Speed:</b> ${speedStr}</div>
                        <div><b>Distance:</b> ${distStr}</div>
                        <div><b>Bearing:</b> ${bearingStr}</div>
                        ${tempStr ? `<div><b>Temp (OAT):</b> ${tempStr}</div>` : ''}
                        ${windStr ? `<div><b>Wind Speed:</b> ${windStr}</div>` : ''}
                        ${contactStr ? `<div><b>Last Contact:</b> ${contactStr}</div>` : ''}
                    </div>
                    <button onclick="window.SkyAlertApp.openAircraftProfile('${hex}')" style="margin-top: 8px; width: 100%; background: #38bdf8; color: #070a13; font-weight: 700; font-size: 11px; padding: 5px; border: none; border-radius: 4px; cursor: pointer;">
                        View Intelligence Profile
                    </button>
                </div>
            `;

            if (this.markers[hex]) {
                this.markers[hex].setLatLng([lat, lon]);
                this.markers[hex].setIcon(icon);
                this.markers[hex].getPopup().setContent(popupContent);
            } else {
                const marker = L.marker([lat, lon], { icon: icon })
                    .addTo(this.map)
                    .bindPopup(popupContent, { className: 'sky-map-popup' });
                this.markers[hex] = marker;
            }
        });

        // Remove markers no longer active
        for (const [hex, marker] of Object.entries(this.markers)) {
            if (!currentHexes.has(hex)) {
                this.map.removeLayer(marker);
                delete this.markers[hex];
            }
        }
    }

    displaySessionTrack(trackPoints) {
        if (!this.map || !this.trackLayer) return;
        this.trackLayer.clearLayers();

        if (!trackPoints || trackPoints.length === 0) return;

        const latLngs = trackPoints
            .filter(p => p.latitude && p.longitude)
            .map(p => [p.latitude, p.longitude]);

        if (latLngs.length === 0) return;

        const polyline = L.polyline(latLngs, {
            color: '#38bdf8',
            weight: 3,
            opacity: 0.8,
            dashArray: '6, 6'
        }).addTo(this.trackLayer);

        // Fit map bounds to track
        this.map.fitBounds(polyline.getBounds(), { padding: [40, 40] });
    }

    invalidateSize() {
        if (this.map) {
            setTimeout(() => this.map.invalidateSize(), 200);
        }
    }
}

window.SkyAlertRadarMap = SkyAlertRadarMap;
