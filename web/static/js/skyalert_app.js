/**
 * SkyAlert Web Application Controller
 * Single-page dynamic routing, live polling, interactive tables, charts, modals, and IST time format.
 */

class SkyAlertApp {
    constructor() {
        this.currentView = "dashboard";
        this.radarMap = null;
        this.selectedAircraftHex = null;
        this.livePollInterval = null;
        this.searchDebounceTimer = null;
        this.aircraftTableParams = {
            page: 1,
            pageSize: 25,
            search: "",
            operator: "",
            type: "",
            enriched: "",
            sortBy: "last_seen",
            order: "desc"
        };
        this.rareVisitsFilter = 5;
        this.rareViewMode = 'cards';
        this.rareScenario = 'all';
        this.rareSearchQuery = '';
        this.rawRareAircraftList = [];
        this.rareSearchDebounceTimer = null;
        this.operatorTimeframe = 'lifetime';
        this.dashboardTimeframe = 'today';
        this.rarePollInterval = null;
        this.formationPollInterval = null;
        this.trafficChart = null;
        this.aircraftChart = null;
        this.adsbdbCache = {};
    }

    init() {
        // Initialize Radar Map
        this.radarMap = new SkyAlertRadarMap("leaflet-radar-map");

        // Bind global events
        this.bindEvents();

        // Start station clock
        this.startStationClock();

        // Routing from URL Hash
        this.handleHashChange();
        window.addEventListener("hashchange", () => this.handleHashChange());

        // Start Live Polling
        this.startLivePolling();
    }

    startStationClock() {
        const updateClock = () => {
            const clockEl = document.getElementById("station-ist-clock");
            if (!clockEl) return;
            const now = new Date();
            // Format in IST
            const options = {
                timeZone: "Asia/Kolkata",
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false
            };
            const formatter = new Intl.DateTimeFormat("en-GB", options);
            clockEl.textContent = formatter.format(now) + " IST";
        };
        updateClock();
        setInterval(updateClock, 1000);
    }

    bindEvents() {
        // Navigation links
        document.querySelectorAll("[data-nav-target]").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const target = btn.getAttribute("data-nav-target");
                window.location.hash = target;
            });
        });

        // Global Search input & keyboard shortcut
        const searchInput = document.getElementById("global-search-input");
        if (searchInput) {
            searchInput.addEventListener("focus", () => this.openSearchModal());
        }

        window.addEventListener("keydown", (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                this.openSearchModal();
            } else if (e.key === "Escape") {
                this.closeAllModals();
            }
        });

        // Modal Search Input
        const modalSearchInput = document.getElementById("modal-search-field");
        if (modalSearchInput) {
            modalSearchInput.addEventListener("input", (e) => {
                clearTimeout(this.searchDebounceTimer);
                this.searchDebounceTimer = setTimeout(() => this.performSearch(e.target.value), 250);
            });
        }

        // Table filters
        const tblSearch = document.getElementById("table-filter-search");
        if (tblSearch) {
            tblSearch.addEventListener("input", (e) => {
                clearTimeout(this.tblSearchDebounceTimer);
                this.tblSearchDebounceTimer = setTimeout(() => {
                    this.aircraftTableParams.search = e.target.value;
                    this.aircraftTableParams.page = 1;
                    this.fetchAircraftTable();
                }, 250);
            });
        }

        const tblEnriched = document.getElementById("table-filter-enriched");
        if (tblEnriched) {
            tblEnriched.addEventListener("change", (e) => {
                this.aircraftTableParams.enriched = e.target.value;
                this.aircraftTableParams.page = 1;
                this.fetchAircraftTable();
            });
        }

        // Rare Aircraft Search Input
        const rareSearch = document.getElementById("rare-search-input");
        if (rareSearch) {
            rareSearch.addEventListener("input", (e) => {
                clearTimeout(this.rareSearchDebounceTimer);
                this.rareSearchDebounceTimer = setTimeout(() => {
                    this.rareSearchQuery = (e.target.value || '').trim();
                    this.renderFilteredRareAircraft();
                }, 200);
            });
        }
    }

    handleHashChange() {
        const hash = window.location.hash.replace("#", "") || "dashboard";
        if (hash.startsWith("aircraft-profile/")) {
            const hex = hash.split("/")[1];
            this.loadAircraftProfile(hex);
            return;
        }

        this.switchView(hash);
    }

    switchView(viewName) {
        this.currentView = viewName;

        // Update nav active classes
        document.querySelectorAll(".sky-nav-link").forEach(link => {
            if (link.getAttribute("data-nav-target") === viewName) {
                link.classList.add("active");
            } else {
                link.classList.remove("active");
            }
        });

        // Show/hide view sections
        document.querySelectorAll(".view-section").forEach(sec => {
            sec.classList.remove("active-view");
        });

        const targetSec = document.getElementById(`view-${viewName}`);
        if (targetSec) {
            targetSec.classList.add("active-view");
        }

        // Update topbar title
        const titles = {
            "dashboard": ["Dashboard", "Station Operations & ADS-B Analytics"],
            "live": ["Live Airspace", "Active Aircraft & Radar Coverage"],
            "aircraft": ["Aircraft Database", "Searchable ICAO Records & Historical Visits"],
            "sessions": ["Detection Sessions", "Continuous Passes & Station Visit Logs"],
            "analytics": ["Global Analytics", "24-Hour Traffic, Operators & Fleet Intelligence"],
            "weather": ["Weather Analytics", "Upper‑Air Thermal Profiles & Wind Shear"],
            "receiver": ["Receiver Analytics", "Signal Horizon & ADS‑B Quality"],
            "fleet": ["Fleet Analytics", "Turnaround Metrics & Traffic Density"],
            "formation": ["Formation Detection", "Real‑time Escort Flight Identification"],
            "map": ["Radar Map", "Fixed Station Range & Live Spatial Tracking"],
            "operators": ["Operator Intelligence", "Airlines & Fleet Analytics"],
            "types": ["Aircraft Types", "ICAO Type Performance & Visits"],
            "rare": ["Rare Aircraft", "Aircraft rarely detected by this receiver"],
            "rare-aircraft": ["Rare Aircraft", "Aircraft rarely detected by this receiver"],
            "unknown": ["Unknown Aircraft", "Un-enriched Airframes & Resolution Queue"],
            "telegram": ["Telegram Alerts & Target Tracking", "Bot Configuration, Proximity Triggers & Automated Broadcasts"],
            "settings": ["System Configuration", "Station Parameters & Alerting Rules"],
            "aircraft-profile": ["Aircraft Intelligence", "Comprehensive Airframe Profile & Visit History"]
        };

        const [mainTitle, subTitle] = titles[viewName] || ["SkyAlert", "Control Center"];
        const titleEl = document.getElementById("view-title-text");
        const subTitleEl = document.getElementById("view-subtitle-text");
        if (titleEl) titleEl.textContent = mainTitle;
        if (subTitleEl) subTitleEl.textContent = subTitle;

        // Clear rare polling if switching away
        if (this.rarePollInterval && viewName !== "rare" && viewName !== "rare-aircraft") {
            clearInterval(this.rarePollInterval);
            this.rarePollInterval = null;
        }
        // Clear formation polling if switching away
        if (this.formationPollInterval && viewName !== "formation") {
            clearInterval(this.formationPollInterval);
            this.formationPollInterval = null;
        }

        // View specific refresh
        if (viewName === "dashboard") {
            this.loadDashboardData();
        } else if (viewName === "live" || viewName === "map") {
            this.radarMap.init();
            this.radarMap.invalidateSize();
            this.fetchLiveAircraft();
        } else if (viewName === "aircraft") {
            this.fetchAircraftTable();
        } else if (viewName === "sessions") {
            this.loadSessionsView();
        } else if (viewName === "analytics") {
            this.loadAnalyticsView();
        } else if (viewName === "operators") {
            this.loadOperatorsView();
        } else if (viewName === "types") {
            this.loadTypesView();
        } else if (viewName === "weather") {
            this.loadWeatherView();
        } else if (viewName === "receiver") {
            this.loadReceiverView();
        } else if (viewName === "fleet") {
            this.loadFleetView();
        } else if (viewName === "formation") {
            this.loadFormationView();
            if (!this.formationPollInterval) {
                this.formationPollInterval = setInterval(() => {
                    if (this.currentView === "formation") {
                        this.loadFormationView(true);
                    }
                }, 5000);
            }
        } else if (viewName === "alerts-history") {
            this.loadAlertsHistoryView();
        } else if (viewName === "rare" || viewName === "rare-aircraft") {
            this.loadRareAircraft(this.rareVisitsFilter);
            if (!this.rarePollInterval) {
                this.rarePollInterval = setInterval(() => {
                    if (this.currentView === "rare" || this.currentView === "rare-aircraft") {
                        this.loadRareAircraft(this.rareVisitsFilter, true);
                    }
                }, 60000);
            }
        } else if (viewName === "telegram") {
            this.loadTelegramSettings();
        } else if (viewName === "unknown") {
            this.loadUnknownView();
        }
    }

    startLivePolling() {
        this.fetchLiveAircraft();
        this.loadDashboardKPIsOnly();
        if (this.livePollInterval) clearInterval(this.livePollInterval);
        let kpiCounter = 0;
        this.livePollInterval = setInterval(() => {
            this.fetchLiveAircraft();
            kpiCounter++;
            // Refresh dashboard KPIs every 14 seconds, or every poll when on dashboard view
            if (this.currentView === "dashboard" || kpiCounter % 4 === 0) {
                this.loadDashboardKPIsOnly();
            }
        }, 3500);
    }

    setDashboardTimeframe(tf) {
        this.dashboardTimeframe = tf;
        document.querySelectorAll('.dashboard-time-btn').forEach(btn => {
            if (btn.dataset.timeframe === tf) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            const res = await fetch(`/api/dashboard?timeframe=${this.dashboardTimeframe}`);
            const data = await res.json();
            if (data.error) return;

            // Render KPIs
            this.renderKPIs(data.kpis);

            // Render Topbar Quick Stats
            const quickLive = document.getElementById("quick-live-count");
            const quickToday = document.getElementById("quick-today-count");
            if (quickLive) quickLive.textContent = data.live_aircraft_count || 0;
            if (quickToday) quickToday.textContent = data.kpis.aircraft_seen_today || 0;

            // Render Live Aircraft Preview cards
            this.renderLivePreviewCards(data.live_aircraft_preview || []);

            // Render Recent Alerts
            this.renderRecentAlerts(data.recent_alerts || []);

            // Render 24h Traffic chart
            this.renderTrafficChart();
        } catch (e) {
            console.error("Failed to load dashboard data:", e);
        }
    }

    async loadDashboardKPIsOnly() {
        try {
            const res = await fetch(`/api/dashboard?timeframe=${this.dashboardTimeframe}`);
            const data = await res.json();
            if (data.kpis) {
                this.renderKPIs(data.kpis);
                const quickLive = document.getElementById("quick-live-count");
                if (quickLive) quickLive.textContent = data.live_aircraft_count || 0;
            }
        } catch (e) {}
    }

    renderKPIs(kpis) {
        const tf = this.dashboardTimeframe || 'today';
        const titleSeen = document.getElementById("kpi-title-seen");
        const subtextSeen = document.getElementById("kpi-subtext-seen");
        const titleVisits = document.getElementById("kpi-title-visits");
        const subtextVisits = document.getElementById("kpi-subtext-visits");
        const titleDetTime = document.getElementById("kpi-title-det-time");
        const subtextDetTime = document.getElementById("kpi-subtext-det-time");

        if (tf === 'week') {
            if (titleSeen) titleSeen.innerHTML = `Aircraft Seen This Week <span class="kpi-icon">✈</span>`;
            if (subtextSeen) subtextSeen.textContent = "Unique airframes detected this week";
            if (titleVisits) titleVisits.innerHTML = `Visits This Week <span class="kpi-icon">🔄</span>`;
            if (subtextVisits) subtextVisits.textContent = "Total continuous detection passes this week";
            if (titleDetTime) titleDetTime.innerHTML = `Detection Time This Week <span class="kpi-icon">⏱</span>`;
            if (subtextDetTime) subtextDetTime.textContent = "Cumulative flight duration this week";
        } else if (tf === 'month') {
            if (titleSeen) titleSeen.innerHTML = `Aircraft Seen This Month <span class="kpi-icon">✈</span>`;
            if (subtextSeen) subtextSeen.textContent = "Unique airframes detected this month";
            if (titleVisits) titleVisits.innerHTML = `Visits This Month <span class="kpi-icon">🔄</span>`;
            if (subtextVisits) subtextVisits.textContent = "Total continuous detection passes this month";
            if (titleDetTime) titleDetTime.innerHTML = `Detection Time This Month <span class="kpi-icon">⏱</span>`;
            if (subtextDetTime) subtextDetTime.textContent = "Cumulative flight duration this month";
        } else if (tf === 'lifetime') {
            if (titleSeen) titleSeen.innerHTML = `Lifetime Aircraft Seen <span class="kpi-icon">✈</span>`;
            if (subtextSeen) subtextSeen.textContent = "All-time unique airframes detected";
            if (titleVisits) titleVisits.innerHTML = `Lifetime Visits <span class="kpi-icon">🔄</span>`;
            if (subtextVisits) subtextVisits.textContent = "All-time continuous detection passes";
            if (titleDetTime) titleDetTime.innerHTML = `Lifetime Detection Time <span class="kpi-icon">⏱</span>`;
            if (subtextDetTime) subtextDetTime.textContent = "All-time cumulative flight duration";
        } else {
            if (titleSeen) titleSeen.innerHTML = `Aircraft Seen Today <span class="kpi-icon">✈</span>`;
            if (subtextSeen) subtextSeen.textContent = "Unique airframes detected today";
            if (titleVisits) titleVisits.innerHTML = `Visits Today <span class="kpi-icon">🔄</span>`;
            if (subtextVisits) subtextVisits.textContent = "Total continuous detection passes today";
            if (titleDetTime) titleDetTime.innerHTML = `Detection Time Today <span class="kpi-icon">⏱</span>`;
            if (subtextDetTime) subtextDetTime.textContent = "Cumulative flight duration today";
        }

        const map = {
            "kpi-seen-today": kpis.aircraft_seen_today ? kpis.aircraft_seen_today.toLocaleString() : "-",
            "kpi-visits-today": kpis.visits_today ? kpis.visits_today.toLocaleString() : "-",
            "kpi-active-aircraft": kpis.active_aircraft,
            "kpi-total-aircraft": kpis.total_aircraft ? kpis.total_aircraft.toLocaleString() : "-",
            "kpi-total-obs": kpis.total_observations ? kpis.total_observations.toLocaleString() : "-",
            "kpi-det-time-today": kpis.total_detection_time_today,
            "kpi-known-aircraft": kpis.known_enriched_aircraft,
            "kpi-unknown-aircraft": kpis.unknown_aircraft,
            "kpi-unique-ops": kpis.unique_operators_today,
            "kpi-longest-session": kpis.longest_detection_session_today,
            "kpi-avg-duration": kpis.average_visit_duration
        };

        for (const [id, val] of Object.entries(map)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val !== undefined && val !== null ? val : "-";
        }
    }

    renderLivePreviewCards(planes) {
        const container = document.getElementById("dashboard-live-cards-container");
        if (!container) return;

        if (planes.length === 0) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 30px;">No aircraft currently in station range.</div>`;
            return;
        }

        container.innerHTML = planes.map(plane => this.generateLiveCardHtml(plane)).join("");
    }

    generateLiveCardHtml(plane) {
        const live = plane.live || {};
        const identity = plane.identity || {};
        const route = plane.route || null;

        const hex = (plane.icao_hex || identity.icao_hex || live.hex || plane.id || "").toUpperCase();
        const callsign = (plane.callsign && plane.callsign !== "-") ? plane.callsign : (identity.callsign || live.flight || hex);
        const reg = (plane.registration && plane.registration !== "-") ? plane.registration : (identity.registration || hex);
        const opCandidates = [plane.operator, identity.operator, plane.operator_name, identity.operator_name];
        const validOp = opCandidates.find(o => o && !['Unknown', 'Unknown Operator', 'Commercial Operator', 'In Transit', '-', 'null', 'None', ''].includes(String(o).trim()));
        const op = validOp || "Unknown Operator";

        const modelCandidates = [
            plane.model, identity.model, plane.aircraft_type, identity.aircraft_type,
            identity.type_code, identity.icao_aircraft_type, live.t, plane.t, plane.description
        ];
        const validModel = modelCandidates.find(m => m && !['Unknown', 'Unknown Type', 'Unknown Operator', '-', 'null', 'None', ''].includes(String(m).trim()));
        const model = validModel || "Unknown Type";
        const dist = plane.distance_km ? `${plane.distance_km} km` : (live.r_dst ? `${live.r_dst} km` : "N/A");
        const altVal = plane.altitude_ft || live.alt_baro || plane.alt_baro;
        const alt = altVal ? `${altVal.toLocaleString()} ft` : "-";
        const rawSpeed = plane.speed_kts || live.gs || plane.gs;
        const gs = rawSpeed ? `${Math.round(rawSpeed * 1.852)} km/h` : (plane.speed_kmh ? `${Math.round(plane.speed_kmh)} km/h` : "-");
        const dur = plane.duration || "< 1m";

        const oatVal = plane.oat !== undefined && plane.oat !== null ? plane.oat : live.oat;
        const tatVal = plane.tat !== undefined && plane.tat !== null ? plane.tat : live.tat;
        const tempC = oatVal !== undefined && oatVal !== null ? `${Math.round(oatVal * 10) / 10}°C` : (tatVal !== undefined && tatVal !== null ? `${Math.round(tatVal * 10) / 10}°C` : null);

        const wsVal = plane.ws !== undefined && plane.ws !== null ? plane.ws : live.ws;
        const windMs = wsVal !== undefined && wsVal !== null ? `${Math.round(wsVal * 0.514444 * 10) / 10} m/s` : null;

        const seenVal = plane.seen !== undefined && plane.seen !== null ? plane.seen : live.seen;
        const lastContact = seenVal !== undefined && seenVal !== null ? (seenVal < 60 ? `${Math.round(seenVal * 10) / 10}s ago` : `${Math.round(seenVal / 60)}m ago`) : (plane.last_seen_ist || "Active");

        const statusText = plane.status || "LIVE";
        const statusClass = statusText === "LIVE" ? "live" : "recent";
        const phaseObj = plane.flight_phase || { label: "En-Route", color: "#38bdf8" };
        const phaseBadge = `<span class="live-badge" style="background: ${phaseObj.color}22; color: ${phaseObj.color}; border: 1px solid ${phaseObj.color}55; font-size: 10px; font-weight: 700;">${phaseObj.label}</span>`;

        const squawk = plane.squawk || live.squawk || "";
        const isEmergency = ["7500", "7600", "7700"].includes(String(squawk));
        const cardStyle = isEmergency ? 'border: 2px solid var(--radar-red); background: rgba(239, 68, 68, 0.05); box-shadow: 0 0 20px rgba(239, 68, 68, 0.3);' : '';
        const squawkBadge = isEmergency ? `<span class="live-badge" style="background: var(--radar-red); color: white; border: none; font-size: 10px; font-weight: 800; animation: pulse 1s infinite;">🚨 SQUAWK ${squawk}</span>` : '';

        let routeDisplay = 'Unavailable';
        let hasRoute = false;
        if (plane.route_short && plane.route_short !== 'Route unavailable' && plane.route_short !== '-') {
            routeDisplay = plane.route_short;
            hasRoute = true;
        } else if (route) {
            if (typeof route === 'string' && route !== 'Route unavailable' && route !== '-') {
                routeDisplay = route;
                hasRoute = true;
            } else if (route.origin_iata || route.origin_icao || route.destination_iata || route.destination_icao) {
                const orig = route.origin_iata || route.origin_icao || '???';
                const dest = route.destination_iata || route.destination_icao || '???';
                routeDisplay = `${orig} → ${dest}`;
                hasRoute = true;
            } else if (route.route && route.route !== 'Route unavailable' && route.route !== '-') {
                routeDisplay = route.route;
                hasRoute = true;
            }
        }

        return `
            <div class="live-card" style="${cardStyle}" onclick="window.SkyAlertApp.openAircraftProfile('${hex}')">
                <div class="live-card-header">
                    <div class="live-card-reg-flight">
                        <div class="live-card-callsign">${callsign}</div>
                        <div class="live-card-registration">${reg} · ${hex}</div>
                    </div>
                    <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
                        ${squawkBadge}
                        ${phaseBadge}
                        <span class="live-badge ${statusClass}">${statusText}</span>
                    </div>
                </div>
                <div class="live-card-meta">
                    <div class="live-meta-row">
                        <span>Operator</span>
                        <span class="live-meta-val">${op}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>Type</span>
                        <span class="live-meta-val">${model}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>Route</span>
                        <span class="live-meta-val" data-route-callsign="${callsign}" data-route-hex="${hex}" style="${hasRoute ? 'color: var(--radar-green); font-weight: 700;' : ''}">
                            ${routeDisplay}
                        </span>
                    </div>
                    ${tempC || windMs ? `
                    <div class="live-meta-row">
                        <span>Env / Weather</span>
                        <span class="live-meta-val" style="color: var(--radar-cyan);">${tempC ? tempC : ''} ${tempC && windMs ? '·' : ''} ${windMs ? windMs : ''}</span>
                    </div>
                    ` : ''}
                    <div class="live-meta-row">
                        <span>Last Contact</span>
                        <span class="live-meta-val mono" style="color: var(--radar-green); font-size: 11px;">${lastContact}</span>
                    </div>
                </div>
                <div class="live-telemetry-strip">
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Altitude</span>
                        <span class="telemetry-val">${alt}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Speed</span>
                        <span class="telemetry-val">${gs}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Distance</span>
                        <span class="telemetry-val">${dist}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Duration</span>
                        <span class="telemetry-val">${dur}</span>
                    </div>
                </div>
            </div>
        `;
    }

    async fetchAdsbdbRoute(callsign, hex) {
        return null;
    }

    async enrichLiveCardRoutes() {
        return;
    }

    async enrichAircraftProfileRoute(callsign, hex) {
        return;
    }

    renderRecentAlerts(alerts) {
        const container = document.getElementById("dashboard-alerts-container");
        if (!container) return;

        if (alerts.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">No alerts triggered today.</div>`;
            return;
        }

        container.innerHTML = alerts.map(a => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: var(--bg-secondary); border-radius: 6px; border: 1px solid var(--border-subtle); margin-bottom: 8px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 16px;">${a.title.includes('MILITARY') ? '🪖' : a.title.includes('EMERGENCY') ? '🚨' : '⭐'}</span>
                    <div>
                        <div style="font-weight: 700; font-size: 13px; color: var(--text-primary);">${a.flight || a.hex} · <span style="color: var(--radar-cyan);">${a.title}</span></div>
                        <div style="font-size: 11px; color: var(--text-muted);">${a.operator || 'Unknown Operator'} · ${a.aircraft_type || 'Unknown'}</div>
                    </div>
                </div>
                <div style="text-align: right; font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">
                    ${a.timestamp}
                </div>
            </div>
        `).join("");
    }

    async fetchLiveAircraft() {
        try {
            const res = await fetch("/api/live");
            const data = await res.json();
            if (!data.aircraft) return;

            // Update Map
            if (this.radarMap) {
                this.radarMap.updateAircraftMarkers(data.aircraft);
            }

            // Update Live Page Grid if active
            if (this.currentView === "live") {
                const grid = document.getElementById("live-airspace-grid");
                const countBadge = document.getElementById("live-view-count-badge");
                if (countBadge) countBadge.textContent = `${data.count} Aircraft`;
                if (grid) {
                    if (data.aircraft.length === 0) {
                        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 40px;">No active aircraft detected within receiver radius.</div>`;
                    } else {
                        grid.innerHTML = data.aircraft.map(p => this.generateLiveCardHtml(p)).join("");
                    }
                }
            }
            this.renderWeatherAnalytics(data.aircraft);
            this.renderReceiverAnalytics(data.aircraft);
        } catch (e) {
            console.error("Error fetching live aircraft:", e);
        }
    }

    renderReceiverData(data) {
        if (this.currentView !== "receiver" || !data) return;

        const countEl = document.getElementById("rx-total-planes");
        if (countEl) countEl.textContent = data.active_tracks || (data.signal_points ? data.signal_points.length : 0);

        const maxRangeEl = document.getElementById("rx-max-range");
        if (maxRangeEl) maxRangeEl.textContent = `${Math.round(data.max_range_horizon_km || 0)} km`;

        const avgRssiEl = document.getElementById("rx-avg-rssi");
        if (avgRssiEl) {
            avgRssiEl.textContent = data.average_rssi_dbm ? `${data.average_rssi_dbm} dBFS` : "-- dBFS";
        }

        const horizonBuckets = data.horizon_buckets || { "N": 0, "NE": 0, "E": 0, "SE": 0, "S": 0, "SW": 0, "W": 0, "NW": 0 };
        const labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
        const horizonData = labels.map(l => horizonBuckets[l] || 0);

        const horizonCtx = document.getElementById("rx-horizon-chart");
        if (horizonCtx) {
            if (this.rxHorizonChart) this.rxHorizonChart.destroy();
            this.rxHorizonChart = new Chart(horizonCtx, {
                type: 'polarArea',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Max Range (km)',
                        data: horizonData,
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.6)', 'rgba(16, 185, 129, 0.6)',
                            'rgba(245, 158, 11, 0.6)', 'rgba(239, 68, 68, 0.6)',
                            'rgba(139, 92, 246, 0.6)', 'rgba(236, 72, 153, 0.6)',
                            'rgba(14, 165, 233, 0.6)', 'rgba(249, 115, 22, 0.6)'
                        ],
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        r: {
                            ticks: { display: false },
                            grid: { color: 'rgba(255,255,255,0.1)' },
                            angleLines: { color: 'rgba(255,255,255,0.1)' }
                        }
                    },
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
        }

        const rssiPoints = (data.signal_points || []).map(p => ({
            x: p.distance_km,
            y: p.rssi,
            label: p.label || `${p.callsign || p.hex} (${p.distance_km} km, ${p.rssi} dBFS)`
        }));

        const rssiCtx = document.getElementById("rx-rssi-chart");
        if (rssiCtx) {
            if (this.rxRssiChart) this.rxRssiChart.destroy();
            this.rxRssiChart = new Chart(rssiCtx, {
                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'RSSI (dBFS)',
                        data: rssiPoints,
                        backgroundColor: 'rgba(16, 185, 129, 0.7)',
                        borderColor: '#10b981',
                        pointRadius: 4,
                        pointHoverRadius: 7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { 
                            title: { display: true, text: 'Distance (km)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        },
                        y: { 
                            title: { display: true, text: 'RSSI (dBFS)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        }
                    },
                    plugins: {
                        tooltip: {
                            callbacks: { label: (ctx) => ctx.raw.label || `${ctx.raw.x} km, ${ctx.raw.y} dBFS` }
                        },
                        legend: { display: false }
                    }
                }
            });
        }
    }

    renderReceiverAnalytics(aircraftList) {
        if (this.currentView !== "receiver" || !aircraftList) return;
        const now = Date.now();
        if (this.lastReceiverUpdate && (now - this.lastReceiverUpdate < 30000)) {
            return;
        }
        this.lastReceiverUpdate = now;
        this.loadReceiverView();
    }

    renderWeatherData(data) {
        if (this.currentView !== "weather" || !data) return;

        // Update Summary Cards
        const countEl = document.getElementById("wx-ac-count");
        if (countEl) countEl.textContent = data.aircraft_count || data.temperature_samples || 0;

        const maxWsEl = document.getElementById("wx-max-wind");
        if (maxWsEl) {
            const maxWind = data.max_wind_kmh || (data.max_jetstream_wind_ms ? Math.round(data.max_jetstream_wind_ms * 3.6) : 0);
            maxWsEl.textContent = maxWind > 0 ? `${Math.round(maxWind)} km/h` : "-- km/h";
        }

        const minTempEl = document.getElementById("wx-min-temp");
        if (minTempEl) {
            const minTemp = data.min_temperature_c !== undefined ? data.min_temperature_c : data.average_oat_c;
            minTempEl.textContent = minTemp !== undefined && minTemp !== 999 ? `${minTemp} °C` : "-- °C";
        }

        const thermalPoints = data.thermal_points || [];
        const windPoints = data.wind_points || [];

        // Render Thermal Chart
        const thermalCtx = document.getElementById("wx-thermal-chart");
        if (thermalCtx) {
            if (this.wxThermalChart) this.wxThermalChart.destroy();
            this.wxThermalChart = new Chart(thermalCtx, {
                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'Temperature (°C)',
                        data: thermalPoints,
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: '#3b82f6',
                        pointRadius: 5,
                        pointHoverRadius: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { 
                            title: { display: true, text: 'Temperature (°C)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        },
                        y: { 
                            title: { display: true, text: 'Altitude (ft)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        }
                    },
                    plugins: {
                        tooltip: {
                            callbacks: { 
                                label: (ctx) => ctx.raw.label || `${ctx.raw.x}°C @ ${ctx.raw.y} ft` 
                            }
                        },
                        legend: { display: false }
                    }
                }
            });
        }

        // Render Wind Chart
        const windCtx = document.getElementById("wx-wind-chart");
        if (windCtx) {
            if (this.wxWindChart) this.wxWindChart.destroy();
            this.wxWindChart = new Chart(windCtx, {
                type: 'scatter',
                data: {
                    datasets: [{
                        label: 'Wind Speed (km/h)',
                        data: windPoints,
                        backgroundColor: 'rgba(245, 158, 11, 0.7)',
                        borderColor: '#f59e0b',
                        pointRadius: 5,
                        pointHoverRadius: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { 
                            title: { display: true, text: 'Wind Speed (km/h)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        },
                        y: { 
                            title: { display: true, text: 'Altitude (ft)', color: '#888' }, 
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#888' }
                        }
                    },
                    plugins: {
                        tooltip: {
                            callbacks: { 
                                label: (ctx) => ctx.raw.label || `${ctx.raw.x} km/h @ ${ctx.raw.y} ft` 
                            }
                        },
                        legend: { display: false }
                    }
                }
            });
        }
    }

    renderWeatherAnalytics(aircraftList) {
        if (this.currentView !== "weather" || !aircraftList) return;
        const now = Date.now();
        if (this.lastWeatherUpdate && (now - this.lastWeatherUpdate < 60000)) {
            return;
        }
        this.lastWeatherUpdate = now;
        this.loadWeatherView();
    }

    async fetchAircraftTable() {
        const { page, pageSize, search, operator, type, enriched, sortBy, order } = this.aircraftTableParams;
        const tbody = document.getElementById("aircraft-table-body");
        if (!tbody) return;

        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--text-muted);">Loading aircraft intelligence database...</td></tr>`;

        try {
            const query = new URLSearchParams({
                page,
                page_size: pageSize,
                search,
                operator,
                aircraft_type: type,
                enriched,
                sort_by: sortBy,
                order
            });

            const res = await fetch(`/api/aircraft?${query.toString()}`);
            const data = await res.json();

            if (!data.items || data.items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--text-muted);">No aircraft found matching filter criteria.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.items.map(item => `
                <tr>
                    <td class="mono"><span class="reg-link" onclick="window.SkyAlertApp.openAircraftProfile('${item.icao_hex}')">${item.icao_hex}</span></td>
                    <td class="mono" style="font-weight: 600;">${item.callsign}</td>
                    <td class="mono">${item.registration}</td>
                    <td><span style="background: rgba(56,189,248,0.1); color: var(--radar-cyan); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11px;">${item.aircraft_type}</span></td>
                    <td>${item.manufacturer}</td>
                    <td>${item.model}</td>
                    <td>${item.operator}</td>
                    <td style="font-size: 12px; color: var(--text-muted);">${item.first_seen_ist}</td>
                    <td style="font-size: 12px; color: var(--text-muted);">${item.last_seen_ist}</td>
                    <td class="mono" style="text-align: center; font-weight: 700; color: var(--radar-green);">${item.lifetime_visits}</td>
                </tr>
            `).join("");

            // Update Pagination
            const pageInfo = document.getElementById("table-page-info");
            if (pageInfo) pageInfo.textContent = `Page ${data.page} of ${data.total_pages} (${data.total.toLocaleString()} total aircraft)`;

            const prevBtn = document.getElementById("table-prev-btn");
            const nextBtn = document.getElementById("table-next-btn");
            if (prevBtn) prevBtn.disabled = data.page <= 1;
            if (nextBtn) nextBtn.disabled = data.page >= data.total_pages;

        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--radar-red);">Failed to load aircraft database.</td></tr>`;
        }
    }

    tableNextPage() {
        this.aircraftTableParams.page++;
        this.fetchAircraftTable();
    }

    tablePrevPage() {
        if (this.aircraftTableParams.page > 1) {
            this.aircraftTableParams.page--;
            this.fetchAircraftTable();
        }
    }

    openAircraftProfile(idOrHex, inNewTab = true) {
        const hex = (idOrHex || '').trim().toUpperCase();
        if (!hex) return;
        if (inNewTab) {
            window.open(`/#aircraft-profile/${encodeURIComponent(hex)}`, '_blank');
        } else {
            window.location.hash = `aircraft-profile/${encodeURIComponent(hex)}`;
            this.loadAircraftProfile(hex);
        }
    }

    async loadAircraftProfile(idOrHex) {
        this.selectedAircraftHex = idOrHex;
        this.switchView("aircraft-profile");

        const container = document.getElementById("view-aircraft-profile");
        if (!container) return;

        container.innerHTML = `<div style="text-align: center; padding: 60px; color: var(--text-muted);">Loading Aircraft Intelligence Profile for ${idOrHex}...</div>`;

        try {
            const ts = new Date().getTime();
            const [profileRes, sessionsRes, telemetryRes] = await Promise.all([
                fetch(`/api/aircraft/${idOrHex}?_t=${ts}`),
                fetch(`/api/aircraft/${idOrHex}/sessions?_t=${ts}`),
                fetch(`/api/aircraft/${idOrHex}/telemetry?_t=${ts}`)
            ]);

            if (!profileRes.ok) throw new Error("Aircraft not found");

            const profile = await profileRes.json();
            const sessions = await sessionsRes.json();
            const telemetry = telemetryRes.ok ? await telemetryRes.json() : { latest: {}, history: [] };

            this.renderAircraftProfilePage(profile, sessions, telemetry);
        } catch (e) {
            container.innerHTML = `<div style="text-align: center; padding: 60px; color: var(--radar-red);">Aircraft not found in database.</div>`;
        }
    }

    renderAircraftProfilePage(p, sessions, telemetry = { latest: {}, history: [] }) {
        const container = document.getElementById("view-aircraft-profile");
        if (!container) return;

        const isLive = p.status === "LIVE";
        const statusBadge = isLive ? `<span class="live-badge live">● LIVE ACTIVE</span>` : `<span class="live-badge recent">INACTIVE</span>`;
        const tLatest = telemetry.latest || {};
        const tHistory = telemetry.history || [];

        // Build list of non-null telemetry rows dynamically (Rule 5: Do not display null fields)
        const telemetryRows = [];
        if (tLatest.altitude_baro !== undefined) telemetryRows.push({ label: "Altitude (Barometric)", val: `${tLatest.altitude_baro.toLocaleString()} ft` });
        if (tLatest.altitude_geom !== undefined) telemetryRows.push({ label: "Altitude (Geometric)", val: `${tLatest.altitude_geom.toLocaleString()} ft` });
        if (tLatest.ground_speed_kts !== undefined) telemetryRows.push({ label: "Ground Speed", val: `${tLatest.ground_speed_kts} kts (${Math.round(tLatest.ground_speed_kts * 1.852)} km/h)` });
        if (tLatest.indicated_airspeed_kts !== undefined) telemetryRows.push({ label: "Indicated Airspeed (IAS)", val: `${tLatest.indicated_airspeed_kts} kts` });
        if (tLatest.true_airspeed_kts !== undefined) telemetryRows.push({ label: "True Airspeed (TAS)", val: `${tLatest.true_airspeed_kts} kts` });
        if (tLatest.mach !== undefined) telemetryRows.push({ label: "Mach Number", val: `M${tLatest.mach}` });
        if (tLatest.track !== undefined) telemetryRows.push({ label: "Track / Course", val: `${tLatest.track}°` });
        if (tLatest.magnetic_heading !== undefined) telemetryRows.push({ label: "Magnetic Heading", val: `${tLatest.magnetic_heading}°` });
        if (tLatest.true_heading !== undefined) telemetryRows.push({ label: "True Heading", val: `${tLatest.true_heading}°` });
        if (tLatest.barometric_rate !== undefined) telemetryRows.push({ label: "Vertical Rate (Baro)", val: `${tLatest.barometric_rate} ft/min` });
        if (tLatest.geometric_rate !== undefined) telemetryRows.push({ label: "Vertical Rate (Geom)", val: `${tLatest.geometric_rate} ft/min` });
        if (tLatest.oat_c !== undefined) telemetryRows.push({ label: "Outside Air Temp (OAT)", val: `${tLatest.oat_c}°C` });
        if (tLatest.tat_c !== undefined) telemetryRows.push({ label: "Total Air Temp (TAT)", val: `${tLatest.tat_c}°C` });
        if (tLatest.wind_direction !== undefined) telemetryRows.push({ label: "Wind Direction", val: `${tLatest.wind_direction}°` });
        if (tLatest.wind_speed_ms !== undefined) telemetryRows.push({ label: "Wind Speed", val: `${tLatest.wind_speed_ms} m/s` });
        if (tLatest.rssi !== undefined) telemetryRows.push({ label: "Signal Strength (RSSI)", val: `${tLatest.rssi} dBm` });
        if (tLatest.distance_km !== undefined) telemetryRows.push({ label: "Station Distance", val: `${tLatest.distance_km} km` });
        if (tLatest.bearing !== undefined) telemetryRows.push({ label: "Bearing Angle", val: `${tLatest.bearing}°` });
        if (tLatest.last_contact_seconds !== undefined) {
            const sec = tLatest.last_contact_seconds;
            const contactTxt = sec < 60 ? `${sec}s ago` : `${Math.round(sec / 60)}m ago`;
            telemetryRows.push({ label: "Last Contact Made Time", val: `${contactTxt} (${tLatest.last_contact_ist || 'Recent'})` });
        } else if (tLatest.last_contact_ist) {
            telemetryRows.push({ label: "Last Contact Made Time", val: tLatest.last_contact_ist });
        }

        const currentSession = p.current_session || null;
        const routeHistory = p.route_history || [];
        const routeSummary = p.route_summary || { unique_routes_count: 0, observed_sessions_count: 0, days_observed_count: 0, most_observed_routes: [] };
        const mostObserved = routeSummary.most_observed_routes || [];

        // Photo Showcase
        const photo = p.photo || null;
        const photoHeroHtml = photo && photo.image_url ? `
            <!-- Aircraft Photo Showcase Hero -->
            <div class="profile-photo-hero">
                <img src="${photo.image_url}" alt="${p.registration} ${p.manufacturer.model}" onerror="this.parentElement.style.display='none';" />
                <div class="profile-photo-overlay"></div>
                <div class="profile-photo-reg-badge">
                    <span>✈</span>
                    <span>${p.registration !== 'Unknown' && p.registration !== '-' ? p.registration : p.icao_hex}</span>
                    <span style="font-size: 11px; color: var(--text-muted); font-weight: 600;">· ${p.manufacturer.manufacturer} ${p.manufacturer.model}</span>
                </div>
                <div class="profile-photo-attribution">
                    <span>📷 ${photo.copyright || 'Planespotters.net'}</span>
                    ${photo.link ? `<a href="${photo.link}" target="_blank">View Original ↗</a>` : ''}
                </div>
            </div>
        ` : '';

        // Technical Specifications (API Ninjas)
        const specs = p.technical_specs || null;
        let specsCards = [];
        if (specs) {
            if (specs.engine_type) {
                specsCards.push({ lbl: 'Engine Type', val: specs.engine_type, sub: specs.engine_thrust_lb_ft ? `${Number(specs.engine_thrust_lb_ft).toLocaleString()} lbf thrust` : '' });
            }
            if (specs.cruise_speed_knots || specs.cruise_speed_sl_knots) {
                const kts = specs.cruise_speed_knots || specs.cruise_speed_sl_knots;
                specsCards.push({ lbl: 'Cruise Speed', val: `${kts} kts`, sub: `${Math.round(Number(kts) * 1.852)} km/h` });
            }
            if (specs.max_speed_knots || specs.max_speed_sl_knots) {
                const kts = specs.max_speed_knots || specs.max_speed_sl_knots;
                specsCards.push({ lbl: 'Maximum Speed', val: `${kts} kts`, sub: `${Math.round(Number(kts) * 1.852)} km/h` });
            }
            if (specs.ceiling_ft) {
                specsCards.push({ lbl: 'Service Ceiling', val: `${Number(specs.ceiling_ft).toLocaleString()} ft`, sub: `FL${Math.round(Number(specs.ceiling_ft)/100)} (${Math.round(Number(specs.ceiling_ft)*0.3048).toLocaleString()} m)` });
            }
            if (specs.range_nautical_miles) {
                specsCards.push({ lbl: 'Maximum Range', val: `${Number(specs.range_nautical_miles).toLocaleString()} NM`, sub: `${Math.round(Number(specs.range_nautical_miles) * 1.852).toLocaleString()} km` });
            }
            if (specs.gross_weight_lbs) {
                specsCards.push({ lbl: 'Max Takeoff / Gross Wt', val: `${Number(specs.gross_weight_lbs).toLocaleString()} lbs`, sub: `${Math.round(Number(specs.gross_weight_lbs)*0.453592).toLocaleString()} kg` });
            }
            if (specs.empty_weight_lbs) {
                specsCards.push({ lbl: 'Operating Empty Wt', val: `${Number(specs.empty_weight_lbs).toLocaleString()} lbs`, sub: `${Math.round(Number(specs.empty_weight_lbs)*0.453592).toLocaleString()} kg` });
            }
            if (specs.wing_span_ft) {
                specsCards.push({ lbl: 'Wingspan', val: `${specs.wing_span_ft} ft`, sub: `${Math.round(Number(specs.wing_span_ft)*0.3048*10)/10} m` });
            }
            if (specs.main_rotor_diameter_ft) {
                specsCards.push({ lbl: 'Main Rotor Diameter', val: `${specs.main_rotor_diameter_ft} ft`, sub: `${Math.round(Number(specs.main_rotor_diameter_ft)*0.3048*10)/10} m (${specs.num_blades || 2} blades)` });
            }
            if (specs.length_ft) {
                specsCards.push({ lbl: 'Airframe Length', val: `${specs.length_ft} ft`, sub: `${Math.round(Number(specs.length_ft)*0.3048*10)/10} m` });
            }
            if (specs.height_ft) {
                specsCards.push({ lbl: 'Tail Height', val: `${specs.height_ft} ft`, sub: `${Math.round(Number(specs.height_ft)*0.3048*10)/10} m` });
            }
            if (specs.takeoff_ground_run_ft) {
                specsCards.push({ lbl: 'Takeoff Ground Roll', val: `${Number(specs.takeoff_ground_run_ft).toLocaleString()} ft`, sub: `${Math.round(Number(specs.takeoff_ground_run_ft)*0.3048).toLocaleString()} m` });
            }
            if (specs.fuel_capacity_gallons) {
                specsCards.push({ lbl: 'Fuel Capacity', val: `${Number(specs.fuel_capacity_gallons).toLocaleString()} gal`, sub: `${Math.round(Number(specs.fuel_capacity_gallons)*3.78541).toLocaleString()} L` });
            }
        }

        const specsPanelHtml = specsCards.length > 0 ? `
            <!-- Airframe Technical Specifications -->
            <div class="sky-panel" style="margin-top: 20px;">
                <div class="sky-panel-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="sky-panel-title">⚙️ AIRFRAME TECHNICAL SPECIFICATIONS (${specs.category_type || 'Aircraft'})</span>
                    <span style="font-size: 11px; color: var(--text-muted);">Source: API Ninjas Intelligence</span>
                </div>
                <div class="sky-panel-body">
                    <div class="profile-specs-grid">
                        ${specsCards.map(c => `
                            <div class="spec-card">
                                <span class="spec-card-lbl">${c.lbl}</span>
                                <span class="spec-card-val">${c.val}</span>
                                ${c.sub ? `<span class="spec-card-sub">${c.sub}</span>` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        ` : '';

        container.innerHTML = `
            ${photoHeroHtml}

            <!-- Top Identity Banner -->
            <div class="profile-header-banner">
                <div class="profile-identity-main">
                    <div class="profile-avatar-box">
                        ✈
                    </div>
                    <div class="profile-identity-titles">
                        <div class="profile-reg-callsign">
                            ${p.registration} · ${p.callsign}
                            <span class="profile-hex-badge">${p.icao_hex}</span>
                            ${statusBadge}
                        </div>
                        <div class="profile-model-desc">${p.manufacturer.manufacturer} ${p.manufacturer.model} (${p.identity.aircraft_type})</div>
                        <div class="profile-operator-sub">${p.operator.operator} · ${p.operator.country}</div>
                    </div>
                </div>
                <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="sky-btn" style="background: rgba(56, 189, 248, 0.15); color: var(--radar-cyan); border: 1px solid var(--radar-cyan);" onclick="window.SkyAlertApp.loadAircraftReplay('${p.icao_hex}')">
                        ▶ Play Trajectory Replay
                    </button>
                    <button class="sky-btn primary" onclick="window.SkyAlertApp.triggerEnrichment('${p.icao_hex}')">
                        ⚡ Refresh Enrichment
                    </button>
                    <button class="sky-btn" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid #f59e0b;" onclick="window.open('https://www.flightradar24.com/' + ('${p.registration}' !== 'Unknown' && '${p.registration}' !== '-' ? '${p.registration}' : '${p.icao_hex}'), '_blank')">
                        🌍 View on FlightRadar24
                    </button>
                    <button class="sky-btn" onclick="window.location.hash='aircraft'">
                        ← Back to Aircraft Table
                    </button>
                </div>
            </div>

            <!-- Current Flight Section -->
            <div class="sky-panel" style="margin-bottom: 20px;">
                <div class="sky-panel-header" style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="sky-panel-title">✈ CURRENT FLIGHT</span>
                    ${p.status === 'LIVE' || currentSession ? `<span class="live-badge live">● LIVE ACTIVE</span>` : `<span class="live-badge recent">INACTIVE</span>`}
                </div>
                <div class="sky-panel-body">
                    ${(currentSession || p.status === 'LIVE') ? `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; align-items: center;">
                        <div style="background: var(--bg-secondary); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700;">Callsign</div>
                            <div style="font-size: 20px; font-weight: 800; color: var(--radar-cyan); font-family: var(--font-mono); margin-top: 4px;">${currentSession ? currentSession.callsign : (p.callsign || '-')}</div>
                        </div>
                        <div style="background: var(--bg-secondary); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700;">Route Vector</div>
                            <div id="profile-route-vector" style="font-size: 20px; font-weight: 800; color: var(--radar-green); font-family: var(--font-mono); margin-top: 4px;">${currentSession ? currentSession.route_short : (p.route ? `${p.route.origin_iata || p.route.origin_icao || '???'} → ${p.route.destination_iata || p.route.destination_icao || '???'}` : 'Route unavailable')}</div>
                        </div>
                        <div style="background: var(--bg-secondary); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700;">Origin</div>
                            <div id="profile-route-origin" style="font-size: 14px; font-weight: 700; color: var(--text-primary); margin-top: 4px;">${currentSession ? (currentSession.origin_display || (currentSession.origin_iata ? `${currentSession.origin_iata} (${currentSession.origin_icao || ''})` : (currentSession.origin_icao || 'Unknown'))) : (p.route ? (p.route.origin_iata || p.route.origin_icao || 'Unknown') : 'Unknown')}</div>
                        </div>
                        <div style="background: var(--bg-secondary); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700;">Destination</div>
                            <div id="profile-route-dest" style="font-size: 14px; font-weight: 700; color: var(--text-primary); margin-top: 4px;">${currentSession ? (currentSession.destination_display || (currentSession.destination_iata ? `${currentSession.destination_iata} (${currentSession.destination_icao || ''})` : (currentSession.destination_icao || 'Unknown'))) : (p.route ? (p.route.destination_iata || p.route.destination_icao || 'Unknown') : 'Unknown')}</div>
                        </div>
                        <div style="background: var(--bg-secondary); padding: 12px 16px; border-radius: 8px; border: 1px solid var(--border-subtle);">
                            <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 700;">Detected Since</div>
                            <div style="font-size: 12px; font-weight: 700; color: var(--text-secondary); font-family: var(--font-mono); margin-top: 4px;">${currentSession ? currentSession.started_at_ist : (p.activity_summary ? p.activity_summary.last_seen_ist : 'Live')}</div>
                        </div>
                    </div>
                    ` : `
                    <div style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 13px;">
                        Currently not detected
                    </div>
                    `}
                </div>
            </div>

            <!-- Activity Summary KPI Grid -->
            <div class="kpi-grid">
                <div class="kpi-card accent-cyan">
                    <span class="kpi-title">Visits Today</span>
                    <span class="kpi-value">${p.activity_summary.visits_today}</span>
                    <span class="kpi-subtext">Duration: ${p.activity_summary.duration_today}</span>
                </div>
                <div class="kpi-card accent-green">
                    <span class="kpi-title">Visits This Week</span>
                    <span class="kpi-value">${p.activity_summary.visits_week}</span>
                    <span class="kpi-subtext">Duration: ${p.activity_summary.duration_week}</span>
                </div>
                <div class="kpi-card accent-amber">
                    <span class="kpi-title">Visits This Month</span>
                    <span class="kpi-value">${p.activity_summary.visits_month}</span>
                    <span class="kpi-subtext">Duration: ${p.activity_summary.duration_month}</span>
                </div>
                <div class="kpi-card accent-purple">
                    <span class="kpi-title">Lifetime Visits</span>
                    <span class="kpi-value">${p.activity_summary.lifetime_visits}</span>
                    <span class="kpi-subtext">Observations: ${p.activity_summary.lifetime_observations.toLocaleString()}</span>
                </div>
                <div class="kpi-card accent-blue">
                    <span class="kpi-title">Average Visit Duration</span>
                    <span class="kpi-value">${p.activity_summary.average_visit_duration}</span>
                    <span class="kpi-subtext">Longest: ${p.activity_summary.longest_visit}</span>
                </div>
            </div>

            <!-- Detailed Aircraft Metadata Sections -->
            <div class="profile-grid-sections">
                <!-- Identity & Classification -->
                <div class="sky-panel">
                    <div class="sky-panel-header">
                        <span class="sky-panel-title">🪪 Identity & Classification</span>
                    </div>
                    <div class="sky-panel-body">
                        <div class="info-item-row"><span class="info-label">ICAO Hex</span><span class="info-value mono">${p.identity.icao_hex}</span></div>
                        <div class="info-item-row"><span class="info-label">Registration</span><span class="info-value mono">${p.identity.registration}</span></div>
                        <div class="info-item-row"><span class="info-label">Callsign</span><span class="info-value mono">${p.identity.callsign}</span></div>
                        <div class="info-item-row"><span class="info-label">Aircraft Type</span><span class="info-value">${p.identity.aircraft_type}</span></div>
                        <div class="info-item-row"><span class="info-label">ICAO Type Code</span><span class="info-value mono">${p.identity.type_code}</span></div>
                        <div class="info-item-row"><span class="info-label">First Seen</span><span class="info-value">${p.activity_summary.first_seen_ist}</span></div>
                        <div class="info-item-row"><span class="info-label">Last Observed</span><span class="info-value">${p.activity_summary.last_seen_ist}</span></div>
                    </div>
                </div>

                <!-- Manufacturer & Airframe Specs -->
                <div class="sky-panel">
                    <div class="sky-panel-header">
                        <span class="sky-panel-title">🛠 Manufacturer & Airframe</span>
                    </div>
                    <div class="sky-panel-body">
                        <div class="info-item-row"><span class="info-label">Manufacturer</span><span class="info-value">${p.manufacturer.manufacturer}</span></div>
                        <div class="info-item-row"><span class="info-label">Model</span><span class="info-value">${p.manufacturer.model}</span></div>
                        <div class="info-item-row"><span class="info-label">Manufacturer ICAO</span><span class="info-value mono">${p.manufacturer.manufacturer_icao}</span></div>
                        <div class="info-item-row"><span class="info-label">Serial Number</span><span class="info-value mono">${p.ownership.serial_number}</span></div>
                        <div class="info-item-row"><span class="info-label">Year Built</span><span class="info-value">${p.history.built}</span></div>
                        <div class="info-item-row"><span class="info-label">First Flight Date</span><span class="info-value">${p.history.first_flight_date}</span></div>
                        <div class="info-item-row"><span class="info-label">Data Source</span><span class="info-value">${p.source.source}</span></div>
                    </div>
                </div>

                <!-- Operator & Ownership -->
                <div class="sky-panel">
                    <div class="sky-panel-header">
                        <span class="sky-panel-title">🏢 Operator & Fleet</span>
                    </div>
                    <div class="sky-panel-body">
                        <div class="info-item-row"><span class="info-label">Operator Name</span><span class="info-value">${p.operator.operator}</span></div>
                        <div class="info-item-row"><span class="info-label">Operator ICAO</span><span class="info-value mono">${p.operator.operator_icao}</span></div>
                        <div class="info-item-row"><span class="info-label">Operator IATA</span><span class="info-value mono">${p.operator.operator_iata}</span></div>
                        <div class="info-item-row"><span class="info-label">Registered Owner</span><span class="info-value">${p.ownership.owner}</span></div>
                        <div class="info-item-row"><span class="info-label">Country</span><span class="info-value">${p.operator.country}</span></div>
                        <div class="info-item-row"><span class="info-label">Enrichment Source</span><span class="info-value"><a href="${p.source.source_url}" target="_blank">${p.source.source} ↗</a></span></div>
                    </div>
                </div>

                <!-- Distance & Compass Direction -->
                <div class="sky-panel">
                    <div class="sky-panel-header">
                        <span class="sky-panel-title">🧭 Distance & Compass Bearing</span>
                    </div>
                    <div class="sky-panel-body" style="display: flex; flex-direction: column; align-items: center;">
                        <div class="compass-rose">
                            <span class="compass-direction n">N</span>
                            <span class="compass-direction e">E</span>
                            <span class="compass-direction s">S</span>
                            <span class="compass-direction w">W</span>
                            <div class="compass-needle" style="transform: rotate(${p.bearing_analytics.initial_bearing}deg);"></div>
                            <div class="compass-center-dot"></div>
                        </div>
                        <div style="width: 100%; margin-top: 16px;">
                            <div class="info-item-row"><span class="info-label">Closest Distance</span><span class="info-value mono" style="color: var(--radar-green); font-weight: 700;">${p.distance_analytics.closest_distance_km} km</span></div>
                            <div class="info-item-row"><span class="info-label">Farthest Distance</span><span class="info-value mono">${p.distance_analytics.farthest_distance_km} km</span></div>
                            <div class="info-item-row"><span class="info-label">Average Distance</span><span class="info-value mono">${p.distance_analytics.average_distance_km} km</span></div>
                            <div class="info-item-row"><span class="info-label">Initial Bearing</span><span class="info-value mono">${p.bearing_analytics.initial_bearing}°</span></div>
                            <div class="info-item-row"><span class="info-label">Final Bearing</span><span class="info-value mono">${p.bearing_analytics.final_bearing}°</span></div>
                        </div>
                    </div>
                </div>
            </div>

            ${specsPanelHtml}

            <!-- Route Summary & Repeated Route Analysis -->
            <div class="sky-panel" style="margin-top: 20px;">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">📊 ROUTE SUMMARY & REPEATED ROUTE ANALYSIS</span>
                </div>
                <div class="sky-panel-body">
                    <div class="kpi-grid" style="margin-bottom: 20px;">
                        <div class="kpi-card accent-cyan">
                            <span class="kpi-title">Unique Routes</span>
                            <span class="kpi-value" style="font-size: 22px;">${routeSummary.unique_routes_count}</span>
                        </div>
                        <div class="kpi-card accent-green">
                            <span class="kpi-title">Observed Sessions with Route</span>
                            <span class="kpi-value" style="font-size: 22px;">${routeSummary.observed_sessions_count}</span>
                        </div>
                        <div class="kpi-card accent-amber">
                            <span class="kpi-title">Days Observed</span>
                            <span class="kpi-value" style="font-size: 22px;">${routeSummary.days_observed_count}</span>
                        </div>
                    </div>

                    <h4 style="font-size: 13px; font-weight: 700; color: var(--text-secondary); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Most Observed Routes</h4>
                    <div class="table-responsive">
                        <table class="sky-table" style="font-size: 12px;">
                            <thead>
                                <tr>
                                    <th>Route</th>
                                    <th>Times Seen</th>
                                    <th>First Seen</th>
                                    <th>Last Seen</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${mostObserved.length === 0 ? `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 16px;">No repeated route history recorded yet.</td></tr>` :
                                    mostObserved.map(m => `
                                    <tr>
                                        <td class="mono" style="font-weight: 700; color: var(--radar-cyan);">${m.route}</td>
                                        <td class="mono" style="font-weight: 700;">${m.session_count} session${m.session_count === 1 ? '' : 's'}</td>
                                        <td class="mono">${m.first_observed_ist}</td>
                                        <td class="mono">${m.last_observed_ist}</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>
                    <div style="margin-top: 12px; font-size: 11px; color: var(--text-muted); font-style: italic;">
                        * Important: These statistics represent routes observed by THIS SkyAlert receiver.
                    </div>
                </div>
            </div>

            <!-- Route History Table -->
            <div class="sky-panel" style="margin-top: 20px;">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">🗺️ ROUTE HISTORY (${routeHistory.length} Sessions)</span>
                </div>
                <div class="sky-panel-body">
                    <div class="table-responsive">
                        <table class="sky-table" style="font-size: 12px;">
                            <thead>
                                <tr>
                                    <th>Date / Time (IST)</th>
                                    <th>Callsign</th>
                                    <th>Route</th>
                                    <th>Duration</th>
                                    <th>Observations</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${routeHistory.length === 0 ? `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">No historical flight routes recorded for this aircraft.</td></tr>` :
                                    routeHistory.map(rh => `
                                    <tr>
                                        <td class="mono" style="font-weight: 600;">${rh.started_at_ist}</td>
                                        <td class="mono" style="font-weight: 700; color: var(--text-primary);">${rh.callsign}</td>
                                        <td class="mono" style="font-weight: 700; color: var(--radar-cyan);">${rh.route}</td>
                                        <td class="mono" style="color: var(--radar-green);">${rh.duration}</td>
                                        <td class="mono">${rh.observation_count.toLocaleString()}</td>
                                        <td>
                                            <button class="sky-btn" style="padding: 4px 10px; font-size: 11px;" onclick="window.SkyAlertApp.openSessionDetailModal(${rh.id})">
                                                Details ↗
                                            </button>
                                        </td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ADS-B Telemetry & Flight Data (Latest Observation) -->
            ${telemetryRows.length > 0 ? `
            <div class="sky-panel" style="margin-top: 20px;">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">📡 ADS-B Telemetry & Flight Data (Latest Observation)</span>
                </div>
                <div class="sky-panel-body">
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px;">
                        ${telemetryRows.map(r => `
                            <div class="info-item-row" style="background: var(--bg-secondary); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-subtle);">
                                <span class="info-label" style="font-weight: 600;">${r.label}</span>
                                <span class="info-value mono" style="color: var(--radar-cyan); font-weight: 700;">${r.val}</span>
                            </div>
                        `).join("")}
                    </div>
                </div>
            </div>
            ` : ''}

            <!-- Historical Telemetry Trends -->
            ${tHistory.length > 0 ? `
            <div class="sky-panel" style="margin-top: 20px;">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">📈 Historical Telemetry Trends (${tHistory.length} Recent Points)</span>
                </div>
                <div class="sky-panel-body">
                    <div class="table-responsive">
                        <table class="sky-table" style="font-size: 12px;">
                            <thead>
                                <tr>
                                    <th>Timestamp (IST)</th>
                                    <th>Altitude (ft)</th>
                                    <th>Ground Speed</th>
                                    <th>Track / Course</th>
                                    <th>Temp (OAT)</th>
                                    <th>Wind Speed (m/s)</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${tHistory.map(h => `
                                    <tr>
                                        <td class="mono">${h.time_ist}</td>
                                        <td class="mono" style="color: var(--radar-cyan); font-weight: 600;">${h.altitude_ft.toLocaleString()} ft</td>
                                        <td class="mono">${h.speed_kmh} km/h (${h.ground_speed_kts} kts)</td>
                                        <td class="mono">${h.track}°</td>
                                        <td class="mono" style="color: var(--radar-amber);">${h.oat_c}°C</td>
                                        <td class="mono" style="color: var(--radar-green);">${h.wind_direction}° / ${h.wind_speed_ms} m/s</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            ` : ''}

            <!-- Visit History & Interactive Timeline -->
            <div class="sky-panel">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">🕒 Detection Sessions & Visits History (${sessions.length} Visits)</span>
                </div>
                <div class="sky-panel-body">
                    <div class="table-responsive">
                        <table class="sky-table">
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Time Interval (IST)</th>
                                    <th>Route</th>
                                    <th>Duration</th>
                                    <th>Observations</th>
                                    <th>Distance (First → Last)</th>
                                    <th>Bearing</th>
                                    <th>Status</th>
                                    <th>Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${sessions.length === 0 ? `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 20px;">No visit sessions recorded.</td></tr>` : 
                                    sessions.map(s => {
                                        let routeStr = 'Route unavailable';
                                        if (s.origin_iata && s.destination_iata) {
                                            routeStr = `${s.origin_iata} → ${s.destination_iata}`;
                                        } else if (s.origin_icao && s.destination_icao) {
                                            routeStr = `${s.origin_icao} → ${s.destination_icao}`;
                                        } else if (s.route && s.route !== "-" && s.route !== "Route unavailable") {
                                            routeStr = s.route;
                                        } else {
                                            if (p.current_session && p.current_session.route_short) {
                                                routeStr = p.current_session.route_short;
                                            } else if (p.frequent_routes && p.frequent_routes.length > 0 && p.frequent_routes[0].route) {
                                                routeStr = p.frequent_routes[0].route;
                                            }
                                        }
                                        return `
                                        <tr>
                                            <td style="font-weight: 600;">${s.date}</td>
                                            <td class="mono">${s.time_range}</td>
                                            <td class="mono" style="font-weight: 700; color: var(--radar-cyan);">${routeStr}</td>
                                            <td class="mono" style="font-weight: 700; color: var(--radar-green);">${s.duration}</td>
                                            <td class="mono">${s.observation_count.toLocaleString()}</td>
                                            <td class="mono">${s.first_distance_km || '-'} km → ${s.last_distance_km || '-'} km</td>
                                            <td class="mono">${s.first_bearing || '-'}° → ${s.last_bearing || '-'}°</td>
                                            <td><span class="live-badge ${s.status === 'ACTIVE' ? 'live' : 'recent'}">${s.status}</span></td>
                                            <td>
                                                <button class="sky-btn" onclick="window.SkyAlertApp.openSessionDetailModal(${s.id})">
                                                    Inspect ↗
                                                </button>
                                            </td>
                                        </tr>
                                    `;}).join("")}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            ${(p.frequent_routes && p.frequent_routes.length > 0) ? `
            <!-- Frequent Routes (DB Source of Truth) -->
            <div class="sky-panel" style="margin-top: 16px;">
                <div class="sky-panel-header">
                    <span class="sky-panel-title">🗺️ Observed Route Patterns (${p.frequent_routes.length} Routes)</span>
                    <span style="font-size: 11px; color: var(--text-muted);">From our detection database</span>
                </div>
                <div class="sky-panel-body">
                    <div class="table-responsive">
                        <table class="sky-table">
                            <thead>
                                <tr>
                                    <th>Route</th>
                                    <th>Origin ICAO</th>
                                    <th>Destination ICAO</th>
                                    <th style="text-align: center;">Times Observed</th>
                                    <th>First Detected</th>
                                    <th>Last Detected</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${p.frequent_routes.map((r, idx) => `
                                <tr>
                                    <td class="mono" style="font-weight: 700; color: ${idx === 0 ? 'var(--radar-cyan)' : 'var(--text-primary)'}; font-size: 15px;">
                                        ${r.route}
                                    </td>
                                    <td class="mono" style="color: var(--text-secondary);">${r.origin_icao || '-'}</td>
                                    <td class="mono" style="color: var(--text-secondary);">${r.destination_icao || '-'}</td>
                                    <td style="text-align: center;">
                                        <span class="live-badge recent" style="font-size: 12px; padding: 3px 10px;">${r.session_count} session${r.session_count !== 1 ? 's' : ''}</span>
                                    </td>
                                    <td class="mono" style="font-size: 11px; color: var(--text-muted);">${r.first_detected}</td>
                                    <td class="mono" style="font-size: 11px; color: var(--text-muted);">${r.last_detected}</td>
                                </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            ` : ''}
        `;

        this.enrichAircraftProfileRoute(p.callsign || (p.identity ? p.identity.callsign : ""), p.icao_hex);
    }


    async openSessionDetailModal(sessionId) {
        const modal = document.getElementById("session-detail-modal");
        const body = document.getElementById("session-modal-content");
        if (!modal || !body) return;

        body.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted);">Loading Session #${sessionId} Telemetry Track...</div>`;
        modal.classList.add("open");

        try {
            const res = await fetch(`/api/sessions/${sessionId}`);
            const data = await res.json();

            body.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 12px;">
                    <div>
                        <h2 style="font-size: 20px; font-weight: 700; color: var(--radar-cyan);">${data.callsign} (${data.registration})</h2>
                        <div style="font-size: 12px; color: var(--text-muted);">${data.manufacturer} ${data.model} · ${data.operator}</div>
                    </div>
                    <div style="text-align: right;">
                        <span class="live-badge ${data.status === 'ACTIVE' ? 'live' : 'recent'}">${data.status}</span>
                        <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-muted); margin-top: 4px;">Session ID: #${data.id}</div>
                    </div>
                </div>

                <div class="kpi-grid" style="margin-bottom: 20px;">
                    <div class="kpi-card accent-cyan">
                        <span class="kpi-title">Duration</span>
                        <span class="kpi-value" style="font-size: 20px;">${data.duration}</span>
                    </div>
                    <div class="kpi-card accent-green">
                        <span class="kpi-title">Observations</span>
                        <span class="kpi-value" style="font-size: 20px;">${data.observation_count}</span>
                    </div>
                    <div class="kpi-card accent-amber">
                        <span class="kpi-title">Distance Range</span>
                        <span class="kpi-value" style="font-size: 16px;">${data.first_distance_km || '-'} → ${data.last_distance_km || '-'} km</span>
                    </div>
                    <div class="kpi-card accent-purple">
                        <span class="kpi-title">Bearing Range</span>
                        <span class="kpi-value" style="font-size: 16px;">${data.first_bearing || '-'}° → ${data.last_bearing || '-'}°</span>
                    </div>
                </div>

                <h3 style="font-size: 14px; font-weight: 700; margin-bottom: 10px;">Observation Telemetry Track</h3>
                <div class="table-responsive" style="max-height: 280px; overflow-y: auto;">
                    <table class="sky-table">
                        <thead>
                            <tr>
                                <th>Timestamp (IST)</th>
                                <th>Altitude (Baro)</th>
                                <th>Speed</th>
                                <th>Heading</th>
                                <th>Distance</th>
                                <th>Bearing</th>
                                <th>Coordinates</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.track.length === 0 ? `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No individual positional telemetry points recorded for this pass.</td></tr>` :
                                data.track.map(t => `
                                <tr>
                                    <td class="mono" style="font-size: 11px;">${t.timestamp_ist}</td>
                                    <td class="mono">${t.altitude_baro ? t.altitude_baro.toLocaleString() + ' ft' : '-'}</td>
                                    <td class="mono">${t.ground_speed_kts ? Math.round(t.ground_speed_kts * 1.852) + ' km/h' : (t.speed_kmh ? Math.round(t.speed_kmh) + ' km/h' : '-')}</td>
                                    <td class="mono">${t.track ? t.track + '°' : '-'}</td>
                                    <td class="mono">${t.distance_km ? t.distance_km + ' km' : '-'}</td>
                                    <td class="mono">${t.bearing ? t.bearing + '°' : '-'}</td>
                                    <td class="mono" style="font-size: 11px;">${t.latitude ? t.latitude.toFixed(4) + ', ' + t.longitude.toFixed(4) : '-'}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
            `;
        } catch (e) {
            body.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--radar-red);">Failed to load session details.</div>`;
        }
    }

    async triggerEnrichment(hex) {
        try {
            const res = await fetch(`/api/aircraft/${hex}/enrich`, { method: "POST" });
            const data = await res.json();
            if (data.status === "success") {
                alert(`Enrichment updated for ${hex}`);
                this.loadAircraftProfile(hex);
            } else {
                alert(`Enrichment notice: ${data.message}`);
            }
        } catch (e) {
            alert(`Error triggering enrichment: ${e}`);
        }
    }

    async renderTrafficChart(canvasId = "traffic-24h-chart") {
        try {
            const res = await fetch("/api/analytics/traffic");
            const data = await res.json();
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;

            // Use a separate chart instance for analytics vs dashboard
            const chartKey = canvasId === "traffic-24h-chart" ? "trafficChart" : "analyticsTrafficChart";
            
            if (this[chartKey]) this[chartKey].destroy();

            const ctx = canvas.getContext("2d");
            this[chartKey] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Aircraft Count',
                            data: data.aircraft,
                            backgroundColor: 'rgba(56, 189, 248, 0.6)',
                            borderColor: '#38bdf8',
                            borderWidth: 1,
                            borderRadius: 4
                        },
                        {
                            label: 'Visits / Sessions',
                            data: data.visits,
                            backgroundColor: 'rgba(34, 197, 94, 0.6)',
                            borderColor: '#22c55e',
                            borderWidth: 1,
                            borderRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
                        },
                        y: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } }
                        }
                    }
                }
            });
        } catch (e) {
            console.error("Traffic chart error:", e);
        }
    }

    async loadSessionsView() {
        const tbody = document.getElementById("global-sessions-table-body");
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 30px; color: var(--text-muted);">Loading station visit sessions...</td></tr>`;

        try {
            const res = await fetch("/api/sessions?limit=100"); // Fetch global sessions across all aircraft
            const sessions = await res.json();
            if (!Array.isArray(sessions) || sessions.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 30px; color: var(--text-muted);">No visits recorded yet.</td></tr>`;
                return;
            }
            tbody.innerHTML = sessions.map(s => `
                <tr>
                    <td style="font-weight: 600;">${s.date}</td>
                    <td>
                        <span class="reg-link" onclick="window.SkyAlertApp.openAircraftProfile('${s.icao_hex}')" style="font-weight: 700; color: var(--radar-cyan); cursor: pointer;">
                            ${s.callsign && s.callsign !== '-' ? s.callsign : s.icao_hex}
                        </span>
                        <div style="font-size: 11px; color: var(--text-muted); font-family: monospace;">${s.icao_hex} • ${s.operator || s.aircraft_type || ''}</div>
                    </td>
                    <td class="mono">${s.time_range}</td>
                    <td class="mono" style="font-weight: 700; color: var(--radar-green);">${s.duration}</td>
                    <td class="mono">${s.observation_count}</td>
                    <td class="mono">${s.first_distance_km != null ? s.first_distance_km + ' km' : '-'} → ${s.last_distance_km != null ? s.last_distance_km + ' km' : '-'}</td>
                    <td class="mono">${s.first_bearing != null ? s.first_bearing + '°' : '-'} → ${s.last_bearing != null ? s.last_bearing + '°' : '-'}</td>
                    <td><span class="live-badge ${s.status === 'ACTIVE' ? 'live' : 'recent'}">${s.status}</span></td>
                    <td><button class="sky-btn" onclick="window.SkyAlertApp.openSessionDetailModal(${s.id})">Inspect ↗</button></td>
                </tr>
            `).join("");
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 30px; color: var(--radar-red);">Failed to load sessions.</td></tr>`;
        }
    }
    async loadAlertsHistoryView() {
        const tbody = document.getElementById("alerts-history-table");
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px;"><div class="radar-scan"></div><div style="margin-top: 15px; color: var(--radar-cyan);">Loading History...</div></td></tr>`;
        
        try {
            const res = await fetch("/api/alerts/history?limit=200");
            const data = await res.json();
            
            if (data.alerts && data.alerts.length > 0) {
                tbody.innerHTML = data.alerts.map(a => {
                    const priorityClass = a.priority === 1 ? "priority-1" : (a.priority === 2 ? "priority-2" : "priority-3");
                    const rawTime = a.timestamp_ist && a.timestamp_ist !== '-' && a.timestamp_ist !== '—' ? a.timestamp_ist : a.timestamp;
                    const timeStr = rawTime ? this.formatDateIst(rawTime) : '—';
                    const hexCode = a.hex || "-";
                    const flight = a.flight || "-";
                    const reg = a.registration || "-";
                    
                    return `
                        <tr>
                            <td class="mono" style="color: #94a3b8; font-size: 0.85rem;">${timeStr}</td>
                            <td><span class="live-badge" style="border: 1px solid var(--radar-red); color: var(--radar-red); background: rgba(239,68,68,0.1); font-weight: 700;">Level ${a.priority || 3}</span></td>
                            <td style="font-weight: 600; color: #f8fafc;">${a.title || a.alert_type}</td>
                            <td>
                                <div class="mono" style="color: var(--radar-cyan); font-weight: 600;">${flight} · ${reg}</div>
                                <div class="mono" style="font-size: 0.75rem; color: #64748b; cursor: pointer;" onclick="window.SkyAlertApp.openAircraftProfile('${hexCode}')">${hexCode} ↗</div>
                            </td>
                            <td class="mono" style="font-size: 0.8rem; color: #94a3b8;">
                                Alt: ${a.altitude || '-'} ft<br>
                                Spd: ${a.speed || '-'} kt
                            </td>
                            <td>
                                <div style="font-size: 0.8rem; color: #cbd5e1;">${a.operator || '-'}</div>
                                <div style="font-size: 0.75rem; color: #64748b;">Squawk: <span class="mono" style="color: var(--radar-amber);">${a.squawk || '-'}</span></div>
                            </td>
                        </tr>
                    `;
                }).join("");
            } else {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: #94a3b8;">No historical alerts found.</td></tr>`;
            }
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: var(--radar-red);">Failed to load alert history.</td></tr>`;
            console.error("Failed to load alerts:", e);
        }
    }

    async loadAnalyticsView() {
        this.renderTrafficChart("analytics-traffic-chart");
        try {
            const [opsRes, typesRes] = await Promise.all([
                fetch("/api/analytics/operators"),
                fetch("/api/analytics/types")
            ]);
            const operators = await opsRes.json();
            const types = await typesRes.json();

            const opsTable = document.getElementById("analytics-top-operators-table");
            if (opsTable) {
                opsTable.innerHTML = operators.slice(0, 10).map((op, idx) => `
                    <tr>
                        <td class="mono" style="color: var(--radar-cyan); font-weight: 700;">#${idx+1}</td>
                        <td style="font-weight: 600;">${op.operator}</td>
                        <td class="mono">${op.operator_icao}</td>
                        <td>${op.country}</td>
                        <td class="mono" style="font-weight: 700;">${op.aircraft_count}</td>
                        <td class="mono" style="color: var(--radar-cyan); font-weight: 700;">${op.unique_flights || op.aircraft_count}</td>
                        <td class="mono" style="color: var(--radar-green); font-weight: 700;">${op.total_visits}</td>
                        <td class="mono">${op.average_visit_duration}</td>
                    </tr>
                `).join("");
            }

            const typesTable = document.getElementById("analytics-top-types-table");
            if (typesTable) {
                typesTable.innerHTML = types.slice(0, 10).map((t, idx) => `
                    <tr>
                        <td class="mono" style="color: var(--radar-cyan); font-weight: 700;">#${idx+1}</td>
                        <td class="mono" style="font-weight: 700; color: var(--radar-cyan);">${t.type_code}</td>
                        <td>${t.model}</td>
                        <td>${t.manufacturer}</td>
                        <td class="mono" style="font-weight: 700;">${t.aircraft_count}</td>
                        <td class="mono" style="color: var(--radar-cyan); font-weight: 700;">${t.unique_flights || t.aircraft_count}</td>
                        <td class="mono" style="color: var(--radar-green); font-weight: 700;">${t.total_visits}</td>
                        <td class="mono">${t.average_visit_duration}</td>
                    </tr>
                `).join("");
            }
        } catch (e) {
            console.error("Analytics error:", e);
        }
    }

    setOperatorTimeframe(tf) {
        this.operatorTimeframe = tf;
        document.querySelectorAll('.operator-time-btn').forEach(btn => {
            if (btn.dataset.timeframe === tf) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        this.loadOperatorsView();
    }

    async loadOperatorsView() {
        const container = document.getElementById("operators-grid-container");
        if (!container) return;
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Loading operator intelligence (${this.operatorTimeframe})...</div>`;

        try {
            const res = await fetch(`/api/analytics/operators?timeframe=${this.operatorTimeframe}`);
            const operators = await res.json();
            if (!operators || operators.length === 0) {
                container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No operator records found for this timeframe.</div>`;
                return;
            }
            container.innerHTML = operators.map(op => `
                <div class="sky-panel" style="padding: 18px; border-top: 3px solid var(--radar-cyan);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 4px;">
                        <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);">${op.operator}</div>
                        <span style="font-size: 11px; font-family: var(--font-mono); color: var(--radar-cyan); background: rgba(56,189,248,0.12); padding: 2px 6px; border-radius: 4px;">${op.operator_icao}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">🌐 ${op.country}</div>
                    <div class="info-item-row"><span class="info-label">Unique Aircraft</span><span class="info-value mono" style="font-weight: 700;">${op.aircraft_count} Planes</span></div>
                    <div class="info-item-row"><span class="info-label">Unique Flights</span><span class="info-value mono" style="color: var(--radar-cyan); font-weight: 700;">${op.unique_flights || op.aircraft_count} Callsigns</span></div>
                    <div class="info-item-row"><span class="info-label">Total Visits</span><span class="info-value mono" style="color: var(--radar-green); font-weight: 700;">${op.total_visits} Sessions</span></div>
                    <div class="info-item-row"><span class="info-label">Total Observations</span><span class="info-value mono">${op.total_observations.toLocaleString()}</span></div>
                    <div class="info-item-row"><span class="info-label">Avg Visit Duration</span><span class="info-value mono">${op.average_visit_duration}</span></div>
                </div>
            `).join("");
        } catch (e) {
            console.error("Operator Intelligence load error:", e);
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--radar-red);">Failed to load operator intelligence.</div>`;
        }
    }

    async loadFleetView() {
        const container = document.getElementById("fleet-grid-container");
        if (!container) return;
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Loading fleet analytics...</div>`;

        try {
            const res = await fetch("/api/analytics/fleet");
            const data = await res.json();
            const operators = data.operators || [];
            if (!operators || operators.length === 0) {
                container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No fleet records found.</div>`;
                return;
            }
            container.innerHTML = operators.map(op => `
                <div class="sky-panel" style="padding: 18px; border-top: 3px solid var(--radar-green);">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 4px;">
                        <div style="font-size: 16px; font-weight: 700; color: var(--text-primary);">${op.operator}</div>
                        <span style="font-size: 11px; font-family: var(--font-mono); color: var(--radar-green); background: rgba(34,197,94,0.12); padding: 2px 6px; border-radius: 4px;">${op.operator_icao}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">🌐 ${op.country}</div>
                    <div class="info-item-row"><span class="info-label">Active Airframes</span><span class="info-value mono" style="font-weight: 700;">${op.aircraft_count} Planes</span></div>
                    <div class="info-item-row"><span class="info-label">Unique Flights</span><span class="info-value mono" style="color: var(--radar-cyan); font-weight: 700;">${op.unique_flights || op.aircraft_count} Callsigns</span></div>
                    <div class="info-item-row"><span class="info-label">Total Visits</span><span class="info-value mono" style="color: var(--radar-green); font-weight: 700;">${op.total_visits} Sessions</span></div>
                    <div class="info-item-row"><span class="info-label">Avg Turnaround / Duration</span><span class="info-value mono">${op.average_visit_duration}</span></div>
                    ${op.top_aircraft && op.top_aircraft.length > 0 ? `
                    <div style="margin-top: 10px; font-size: 11px; color: var(--text-muted);">
                        Key Fleet: ${op.top_aircraft.map(ac => `<span style="font-family: monospace; color: var(--radar-cyan);">${ac.reg || ac.hex}</span> (${ac.type || 'N/A'})`).join(', ')}
                    </div>
                    ` : ''}
                </div>
            `).join("");
        } catch (e) {
            console.error("Fleet Analytics load error:", e);
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--radar-red);">Failed to load fleet analytics.</div>`;
        }
    }

    async loadWeatherView() {
        this.lastWeatherUpdate = Date.now();
        try {
            const res = await fetch("/api/analytics/weather");
            const data = await res.json();
            this.renderWeatherData(data);
        } catch (e) {
            console.error("Failed to load weather analytics:", e);
        }
    }

    async loadReceiverView() {
        this.lastReceiverUpdate = Date.now();
        try {
            const res = await fetch("/api/analytics/receiver");
            const data = await res.json();
            this.renderReceiverData(data);
        } catch (e) {
            console.error("Failed to load receiver analytics:", e);
        }
    }

    async loadTypesView() {
        const container = document.getElementById("types-grid-container");
        if (!container) return;
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">Loading aircraft type intelligence...</div>`;

        try {
            const res = await fetch("/api/analytics/types");
            const types = await res.json();
            container.innerHTML = types.map(t => `
                <div class="sky-panel" style="padding: 18px;">
                    <div style="font-size: 18px; font-weight: 800; font-family: var(--font-mono); color: var(--radar-cyan); margin-bottom: 4px;">${t.type_code}</div>
                    <div style="font-size: 13px; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">${t.manufacturer} ${t.model}</div>
                    <div class="info-item-row"><span class="info-label">Unique Aircraft</span><span class="info-value mono" style="font-weight: 700;">${t.aircraft_count} Planes</span></div>
                    <div class="info-item-row"><span class="info-label">Unique Flights</span><span class="info-value mono" style="color: var(--radar-cyan); font-weight: 700;">${t.unique_flights || t.aircraft_count} Callsigns</span></div>
                    <div class="info-item-row"><span class="info-label">Total Visits</span><span class="info-value mono" style="color: var(--radar-green); font-weight: 700;">${t.total_visits} Sessions</span></div>
                    <div class="info-item-row"><span class="info-label">Total Observations</span><span class="info-value mono">${t.total_observations.toLocaleString()}</span></div>
                    <div class="info-item-row"><span class="info-label">Avg Session Duration</span><span class="info-value mono">${t.average_visit_duration}</span></div>
                </div>
            `).join("");
        } catch (e) {
            container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--radar-red);">Failed to load aircraft types.</div>`;
        }
    }

    // ────────────────────────────────────────────────────────────────
    // Formation Detection & Live Airspace Intelligence
    // ────────────────────────────────────────────────────────────────

    async loadFormationView(forceRefresh = false) {
        const anomEl = document.getElementById("formation-anomalies-container");
        const pairsEl = document.getElementById("formation-pairs-container");
        const rareEl = document.getElementById("formation-rare-container");
        if (!anomEl || !pairsEl || !rareEl) return;

        const setText = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };

        if (!forceRefresh) {
            anomEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">Scanning live feed for anomalies...</div>`;
            pairsEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">Analyzing proximity of tracked aircraft...</div>`;
            rareEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">Identifying new and special aircraft...</div>`;
        }

        try {
            const res = await fetch("/api/live");
            if (!res.ok) throw new Error(`Network error ${res.status}`);
            const data = await res.json();
            const aircraft = Array.isArray(data.aircraft) ? data.aircraft : [];
            const formations = Array.isArray(data.formations) ? data.formations : [];

            // ── Anomalies & emergencies ────────────────────────────
            const flagged = [];
            for (const p of aircraft) {
                const anomalies = Array.isArray(p.anomalies) ? p.anomalies : [];
                for (const a of anomalies) flagged.push({ plane: p, anomaly: a });
            }
            const high = flagged.filter(f => f.anomaly.priority === "HIGH");
            const medium = flagged.filter(f => f.anomaly.priority === "MEDIUM");
            const low = flagged.filter(f => f.anomaly.priority === "LOW");
            const ordered = [...high, ...medium, ...low];

            setText("formation-sum-anomalies", high.length + medium.length);
            setText("formation-sum-formations", formations.length);
            setText("formation-sum-total", data.count ?? aircraft.length);
            if (data.station_time) setText("formation-station-time", data.station_time);

            if (ordered.length === 0) {
                anomEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">✅ No anomalies or emergency squawks detected in the current feed.</div>`;
            } else {
                const prioStyle = {
                    HIGH:   { color: "var(--radar-red)",   icon: "🚨", label: "HIGH" },
                    MEDIUM: { color: "var(--radar-amber)", icon: "⚠️", label: "MEDIUM" },
                    LOW:    { color: "var(--radar-cyan)",  icon: "ℹ️", label: "LOW" }
                };
                anomEl.innerHTML = ordered.map(({ plane: p, anomaly: a }) => {
                    const st = prioStyle[a.priority] || prioStyle.LOW;
                    const hex = p.icao_hex || "";
                    const cs = (p.callsign && p.callsign !== "-") ? p.callsign : hex;
                    const phase = p.flight_phase ? p.flight_phase.label : "Unknown";
                    return `
                    <div class="sky-panel" style="padding: 16px; border-top: 3px solid ${st.color}; cursor: pointer;" onclick="window.SkyAlertApp.openAircraftProfile('${hex}')">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px;">
                            <div style="font-size: 16px; font-weight: 800; font-family: var(--font-mono); color: var(--text-primary);">${cs}</div>
                            <span style="font-size: 11px; font-weight: 700; color: ${st.color};">${st.icon} ${st.label}</span>
                        </div>
                        <div style="font-size: 13px; font-weight: 700; color: ${st.color}; margin-bottom: 4px;">${a.title}</div>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${a.desc}</div>
                        <div class="info-item-row"><span class="info-label">Aircraft</span><span class="info-value mono">${p.registration || hex} · ${p.aircraft_type || 'N/A'}</span></div>
                        <div class="info-item-row"><span class="info-label">Squawk</span><span class="info-value mono" style="color: ${st.color};">${p.squawk || '-'}</span></div>
                        <div class="info-item-row"><span class="info-label">Phase</span><span class="info-value">${phase}</span></div>
                    </div>`;
                }).join("");
            }

            // ── Formations / escort pairs ──────────────────────────
            if (formations.length === 0) {
                pairsEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">No formation or escort pairs detected right now.</div>`;
            } else {
                pairsEl.innerHTML = formations.map(f => {
                    const isEscort = f.type === "FORMATION_ESCORT";
                    const c = isEscort ? "var(--radar-red)" : "var(--radar-cyan)";
                    const label = isEscort ? "🛫 FORMATION / ESCORT" : "✈️ PROXIMITY PAIR";
                    return `
                    <div class="sky-panel" style="padding: 16px; border-top: 3px solid ${c};">
                        <div style="font-size: 11px; font-weight: 700; color: ${c}; letter-spacing: 0.5px; margin-bottom: 8px;">${label}</div>
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px;">
                            <span class="mono" style="font-weight: 700; color: var(--text-primary); cursor: pointer;" onclick="window.SkyAlertApp.openAircraftProfile('${f.hex_1}')">${f.aircraft_1}</span>
                            <span style="color: var(--text-muted);">⇄</span>
                            <span class="mono" style="font-weight: 700; color: var(--text-primary); cursor: pointer;" onclick="window.SkyAlertApp.openAircraftProfile('${f.hex_2}')">${f.aircraft_2}</span>
                        </div>
                        <div class="info-item-row"><span class="info-label">Lateral Separation</span><span class="info-value mono" style="color: ${c}; font-weight: 700;">${f.distance_km} km</span></div>
                        <div class="info-item-row"><span class="info-label">Vertical Separation</span><span class="info-value mono">${f.vertical_separation_ft} ft</span></div>
                    </div>`;
                }).join("");
            }

            // ── First sightings / rare & special ───────────────────
            const isSpecial = (p) => {
                // Note: ADS-B category A5 = "Heavy" (large airliners), NOT military.
                // Rely on operator/owner keywords only to avoid false positives.
                const op = ((p.operator || "") + " " + (p.owner || "")).toUpperCase();
                return /\b(AIR\s+FORCE|MILITARY|GOVERNMENT|ARMY|NAVY|NAVAL|POLICE|COAST\s+GUARD|BORDER|PATROL)\b/.test(op);
            };
            const rare = aircraft
                .map(p => ({ p, visits: p.total_sessions ?? p.lifetime_visits ?? 0 }))
                .filter(r => r.visits <= 3 || isSpecial(r.p))
                .sort((a, b) => a.visits - b.visits);

            setText("formation-sum-rare", rare.length);

            if (rare.length === 0) {
                rareEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--text-muted);">No new, rare, or special aircraft in the current feed.</div>`;
            } else {
                rareEl.innerHTML = rare.map(({ p, visits }) => {
                    const hex = p.icao_hex || "";
                    const cs = (p.callsign && p.callsign !== "-") ? p.callsign : hex;
                    const firstEver = visits <= 1;
                    const special = isSpecial(p);
                    const badge = firstEver
                        ? `<span style="font-size: 11px; font-weight: 700; color: var(--radar-amber);">✨ FIRST SIGHTING</span>`
                        : `<span style="font-size: 11px; font-weight: 700; color: var(--radar-cyan);">✦ RARE</span>`;
                    return `
                    <div class="sky-panel" style="padding: 16px; border-top: 3px solid ${firstEver ? 'var(--radar-amber)' : 'var(--radar-cyan)'}; cursor: pointer;" onclick="window.SkyAlertApp.openAircraftProfile('${hex}')">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px;">
                            <div style="font-size: 16px; font-weight: 800; font-family: var(--font-mono); color: var(--text-primary);">${cs}</div>
                            ${badge}
                        </div>
                        ${special ? `<div style="font-size: 11px; font-weight: 700; color: var(--radar-red); margin-bottom: 4px;">⭐ SPECIAL / MILITARY INTEREST</div>` : ''}
                        <div class="info-item-row"><span class="info-label">Aircraft</span><span class="info-value mono">${p.registration || hex} · ${p.aircraft_type || 'N/A'}</span></div>
                        <div class="info-item-row"><span class="info-label">Operator</span><span class="info-value">${p.operator || 'Unknown'}</span></div>
                        <div class="info-item-row"><span class="info-label">Lifetime Visits</span><span class="info-value mono" style="color: var(--radar-amber); font-weight: 700;">${visits}</span></div>
                        <div class="info-item-row"><span class="info-label">First Seen</span><span class="info-value">${p.first_seen_ist || '—'}</span></div>
                    </div>`;
                }).join("");
            }
        } catch (e) {
            console.error("Formation view load error:", e);
            anomEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--radar-red);">Failed to load live intelligence feed.</div>`;
            pairsEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--radar-red);">Failed to load formations.</div>`;
            rareEl.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 30px; color: var(--radar-red);">Failed to load rare aircraft.</div>`;
        }
    }

    async loadUnknownView() {
        const tbody = document.getElementById("unknown-table-body");
        if (!tbody) return;
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--text-muted);">Scanning un-enriched aircraft...</td></tr>`;

        try {
            const res = await fetch("/api/unknown");
            const unknown = await res.json();
            if (unknown.length === 0) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--radar-green);">All aircraft in database are fully enriched!</td></tr>`;
                return;
            }

            tbody.innerHTML = unknown.map(u => `
                <tr>
                    <td class="mono" style="font-weight: 700; color: var(--radar-cyan);">${u.icao_hex}</td>
                    <td class="mono">${u.callsign}</td>
                    <td style="font-size: 12px; color: var(--text-muted);">${u.first_seen_ist}</td>
                    <td style="font-size: 12px; color: var(--text-muted);">${u.last_seen_ist}</td>
                    <td class="mono">${u.visits}</td>
                    <td class="mono">${u.observations}</td>
                    <td>
                        <button class="sky-btn primary" onclick="window.SkyAlertApp.triggerEnrichment('${u.icao_hex}')">
                            ⚡ Enrich Aircraft
                        </button>
                    </td>
                </tr>
            `).join("");
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 30px; color: var(--radar-red);">Failed to load unknown aircraft.</td></tr>`;
        }
    }

    openSearchModal() {
        const modal = document.getElementById("global-search-modal");
        const input = document.getElementById("modal-search-field");
        if (modal) modal.classList.add("open");
        if (input) {
            input.value = "";
            setTimeout(() => input.focus(), 100);
        }
    }

    async performSearch(query) {
        const list = document.getElementById("modal-search-results-list");
        if (!list) return;
        if (!query || query.trim().length === 0) {
            list.innerHTML = "";
            return;
        }

        list.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted);">Searching aircraft records...</div>`;

        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();

            if (!data.results || data.results.length === 0) {
                list.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--text-muted);">No matching aircraft found for "${query}".</div>`;
                return;
            }

            list.innerHTML = data.results.map(r => `
                <div class="search-result-item" onclick="window.SkyAlertApp.closeAllModals(); window.SkyAlertApp.openAircraftProfile('${r.icao_hex}')">
                    <div style="display: flex; flex-direction: column;">
                        <div style="font-weight: 700; font-family: var(--font-mono); color: var(--radar-cyan);">
                            ${r.registration} · ${r.callsign}
                            <span style="font-size: 11px; color: var(--text-muted); margin-left: 8px;">${r.icao_hex}</span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-primary);">${r.manufacturer} ${r.model} (${r.aircraft_type})</div>
                        <div style="font-size: 11px; color: var(--text-muted);">${r.operator} · ${r.country}</div>
                    </div>
                    <div style="text-align: right; font-size: 11px; font-family: var(--font-mono); color: var(--text-muted);">
                        <div>${r.total_sessions} Visits</div>
                        <div>${r.last_seen_ist}</div>
                    </div>
                </div>
            `).join("");
        } catch (e) {
            list.innerHTML = `<div style="text-align: center; padding: 20px; color: var(--radar-red);">Search failed.</div>`;
        }
    }

    closeAllModals() {
        document.querySelectorAll(".sky-modal-backdrop").forEach(m => m.classList.remove("open"));
    }
    setRareViewMode(mode) {
        this.rareViewMode = mode;
        document.querySelectorAll('.rare-layout-btn').forEach(btn => {
            if (btn.dataset.mode === mode) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        this.loadRareAircraft(this.rareVisitsFilter);
    }

    setRareScenario(scenario) {
        this.rareScenario = scenario;
        document.querySelectorAll('.rare-scenario-btn').forEach(btn => {
            if (btn.dataset.scenario === scenario) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        this.renderFilteredRareAircraft();
    }

    setRareVisitsFilter(visits) {
        this.rareVisitsFilter = visits;
        document.querySelectorAll('.rare-filter-btn').forEach(btn => {
            if (parseInt(btn.dataset.visits) === visits) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        this.loadRareAircraft(visits);
    }

    async loadRareAircraft(maxVisits, forceRefresh = false) {
        const loadingEl = document.getElementById('rare-loading-indicator');
        const errorEl = document.getElementById('rare-error-state');
        const emptyEl = document.getElementById('rare-empty-state');
        const gridEl = document.getElementById('rare-aircraft-cards-grid');

        if (!forceRefresh) {
            if (loadingEl) loadingEl.style.display = 'block';
            if (errorEl) errorEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'none';
            if (gridEl) gridEl.innerHTML = '';
        }

        try {
            const res = await fetch(`/api/rare-aircraft?max_visits=${maxVisits}`);
            if (!res.ok) throw new Error(`Network error ${res.status}`);
            const data = await res.json();
            if (!data || !Array.isArray(data.rare_aircraft)) throw new Error('Invalid response format');

            this.rawRareAircraftList = data.rare_aircraft || [];

            // Update summary statistics area
            const veryRare = this.rawRareAircraftList.filter(a => (a.visits ?? a.visit_count ?? 1) === 1).length;
            const rare = this.rawRareAircraftList.filter(a => (a.visits ?? a.visit_count ?? 2) === 2).length;
            const occasional = this.rawRareAircraftList.filter(a => {
                const v = a.visits ?? a.visit_count ?? 0;
                return v >= 3 && v <= 5;
            }).length;
            const total = this.rawRareAircraftList.length;

            const setText = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
            setText('rare-sum-very-rare', veryRare);
            setText('rare-sum-rare', rare);
            setText('rare-sum-occasional', occasional);
            setText('rare-sum-total', total);

            // Compute Scenario Tab Counts
            const isHeli = (a) => a.is_helicopter || (a.aircraft_type && ['B429', 'B206', 'EC45', 'EC35', 'H125', 'R44', 'R66', 'AS50', 'A109'].includes(a.aircraft_type.toUpperCase())) || (a.manufacturer && a.manufacturer.toLowerCase().includes('bell'));
            const isMil = (a) => a.is_military || (a.operator && a.operator.toLowerCase().includes('air force'));
            const isOneTime = (a) => (a.visits ?? a.visit_count ?? a.total_sessions ?? 1) === 1;
            const isHeavy = (a) => a.is_heavy || (a.model && (a.model.includes('380') || a.model.includes('747') || a.model.includes('777') || a.model.includes('787') || a.model.includes('C17')));
            const isWl = (a) => a.is_watchlist;

            const countAll = this.rawRareAircraftList.length;
            const countHeli = this.rawRareAircraftList.filter(isHeli).length;
            const countMil = this.rawRareAircraftList.filter(isMil).length;
            const countOneTime = this.rawRareAircraftList.filter(isOneTime).length;
            const countHeavy = this.rawRareAircraftList.filter(isHeavy).length;
            const countWatchlist = this.rawRareAircraftList.filter(isWl).length;

            const setPill = (id, count) => {
                const el = document.getElementById(id);
                if (el) el.textContent = count > 0 ? count : '0';
            };
            setPill('rare-count-all', countAll);
            setPill('rare-count-helicopter', countHeli);
            setPill('rare-count-military', countMil);
            setPill('rare-count-one_time', countOneTime);
            setPill('rare-count-heavy', countHeavy);
            setPill('rare-count-watchlist', countWatchlist);

            this.renderFilteredRareAircraft();

        } catch (e) {
            console.error('Error loading rare aircraft:', e);
            if (errorEl) errorEl.style.display = 'block';
        } finally {
            if (loadingEl) loadingEl.style.display = 'none';
        }
    }

    renderFilteredRareAircraft() {
        const gridEl = document.getElementById('rare-aircraft-cards-grid');
        const emptyEl = document.getElementById('rare-empty-state');
        if (!gridEl) return;

        let list = this.rawRareAircraftList || [];

        const isHeli = (a) => a.is_helicopter || (a.aircraft_type && ['B429', 'B206', 'EC45', 'EC35', 'H125', 'R44', 'R66', 'AS50', 'A109'].includes(a.aircraft_type.toUpperCase())) || (a.manufacturer && a.manufacturer.toLowerCase().includes('bell'));
        const isMil = (a) => a.is_military || (a.operator && a.operator.toLowerCase().includes('air force'));
        const isOneTime = (a) => (a.visits ?? a.visit_count ?? a.total_sessions ?? 1) === 1;
        const isHeavy = (a) => a.is_heavy || (a.model && (a.model.includes('380') || a.model.includes('747') || a.model.includes('777') || a.model.includes('787') || a.model.includes('C17')));
        const isWl = (a) => a.is_watchlist;

        // 1. Scenario Filter
        if (this.rareScenario === 'helicopter') {
            list = list.filter(isHeli);
        } else if (this.rareScenario === 'military') {
            list = list.filter(isMil);
        } else if (this.rareScenario === 'one_time') {
            list = list.filter(isOneTime);
        } else if (this.rareScenario === 'heavy') {
            list = list.filter(isHeavy);
        } else if (this.rareScenario === 'watchlist') {
            list = list.filter(isWl);
        }

        // 2. Search Query Filter
        if (this.rareSearchQuery) {
            const q = this.rareSearchQuery.toUpperCase();
            list = list.filter(a => {
                const hex = (a.icao_hex || '').toUpperCase();
                const callsign = (a.callsign || '').toUpperCase();
                const reg = (a.registration || '').toUpperCase();
                const op = (a.operator || '').toUpperCase();
                const mdl = (a.model || '').toUpperCase();
                const mfr = (a.manufacturer || '').toUpperCase();
                const typ = (a.aircraft_type || '').toUpperCase();
                const ctry = (a.country || '').toUpperCase();
                return hex.includes(q) || callsign.includes(q) || reg.includes(q) ||
                       op.includes(q) || mdl.includes(q) || mfr.includes(q) ||
                       typ.includes(q) || ctry.includes(q);
            });
        }

        if (list.length === 0) {
            if (emptyEl) {
                emptyEl.style.display = 'block';
                const msgEl = emptyEl.querySelector('span:last-child');
                if (msgEl) {
                    msgEl.textContent = this.rareSearchQuery 
                        ? `No rare aircraft matching "${this.rareSearchQuery}".`
                        : `No rare aircraft in selected category.`;
                }
            }
            gridEl.innerHTML = '';
        } else {
            if (emptyEl) emptyEl.style.display = 'none';
            if (this.rareViewMode === 'table') {
                gridEl.innerHTML = `
                <div class="table-responsive">
                    <table class="sky-table rare-list-table">
                        <thead>
                            <tr>
                                <th>Category</th>
                                <th>Callsign</th>
                                <th>ICAO Hex</th>
                                <th>Registration</th>
                                <th>Aircraft</th>
                                <th>Operator</th>
                                <th>Country</th>
                                <th>First Seen</th>
                                <th>Last Seen</th>
                                <th style="text-align:center">Visits</th>
                                <th style="text-align:center">Obs.</th>
                                <th style="text-align:center">Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${list.map(ac => this.generateRareRowHtml(ac)).join('')}
                        </tbody>
                    </table>
                </div>`;
            } else {
                gridEl.innerHTML = `
                <div class="live-aircraft-grid">
                    ${list.map(ac => this.generateRareCardHtml(ac)).join('')}
                </div>`;
            }
        }
    }

    formatDateIst(val) {
        if (!val || val === '—' || val === '-' || val === 'None' || val === 'null') return '—';
        if (typeof val === 'string' && val.includes('IST')) return val;
        try {
            // Normalise Python datetime strings: "2026-09-14T10:01:22+00:00" or "2026-09-14T10:01:22"
            let str = String(val).trim();
            // Replace space separator with T (SQLite stores "2026-09-14 10:01:22")
            str = str.replace(' ', 'T');
            // If no timezone info present, assume UTC
            if (!str.endsWith('Z') && !str.includes('+') && str.length <= 19) {
                str += 'Z';
            }
            const d = new Date(str);
            if (isNaN(d.getTime())) return val;
            const options = {
                timeZone: "Asia/Kolkata",
                day: "numeric",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                hour12: false
            };
            return new Intl.DateTimeFormat("en-GB", options).format(d) + " IST";
        } catch {
            return val;
        }
    }


    generateRareCardHtml(ac) {
        const hex = (ac.icao_hex || '—').toUpperCase();
        const callsign = ac.callsign && ac.callsign !== 'None' && ac.callsign !== 'null' ? ac.callsign : hex;
        const reg = ac.registration && ac.registration !== 'None' && ac.registration !== 'null' && ac.registration !== '-' ? ac.registration : hex;
        const visits = ac.visits ?? ac.visit_count ?? ac.total_sessions ?? 1;
        const rarity = ac.rarity || (visits === 1 ? 'very_rare' : visits === 2 ? 'rare' : 'occasional');
        const mfr = ac.manufacturer && ac.manufacturer !== 'None' && ac.manufacturer !== 'null' ? ac.manufacturer : '';
        const model = ac.model && ac.model !== 'None' && ac.model !== 'null' ? ac.model : '';
        const acType = ac.aircraft_type && ac.aircraft_type !== 'None' && ac.aircraft_type !== 'null' ? ac.aircraft_type : '';
        const operator = ac.operator && ac.operator !== 'None' && ac.operator !== 'null' ? ac.operator : 'Unknown Operator';
        const country = ac.country && ac.country !== 'None' && ac.country !== 'null' ? ac.country : 'Unknown';
        const first = this.formatDateIst(ac.first_seen || ac.first_seen_ist);
        const last = this.formatDateIst(ac.last_seen || ac.last_seen_ist);
        const duration = ac.duration || (ac.average_duration ? `${ac.average_duration}m` : '—');
        const obs = ac.total_observations || 0;

        let badgeLabel = '⭐ VERY RARE';
        let badgeBg = 'rgba(245, 197, 24, 0.15)';
        let badgeBorder = '#f5c518';
        let badgeColor = '#f5c518';

        if (ac.is_helicopter || acType === 'B429' || acType === 'B206' || acType === 'EC45' || (mfr && mfr.toLowerCase().includes('bell'))) {
            badgeLabel = '🚁 HELICOPTER';
            badgeBg = 'rgba(56, 189, 248, 0.15)';
            badgeBorder = '#38bdf8';
            badgeColor = '#38bdf8';
        } else if (ac.is_military || (operator && operator.toLowerCase().includes('air force'))) {
            badgeLabel = '⚔️ MILITARY';
            badgeBg = 'rgba(239, 68, 68, 0.15)';
            badgeBorder = '#ef4444';
            badgeColor = '#ef4444';
        } else if (visits === 1) {
            badgeLabel = '⭐ VERY RARE';
            badgeBg = 'rgba(245, 197, 24, 0.15)';
            badgeBorder = '#f5c518';
            badgeColor = '#f5c518';
        } else if (visits === 2) {
            badgeLabel = '✦ RARE';
            badgeBg = 'rgba(56, 189, 248, 0.15)';
            badgeBorder = '#38bdf8';
            badgeColor = '#38bdf8';
        } else {
            badgeLabel = '◈ OCCASIONAL';
            badgeBg = 'rgba(167, 139, 250, 0.15)';
            badgeBorder = '#a78bfa';
            badgeColor = '#a78bfa';
        }

        const acDesc = [mfr, model].filter(Boolean).join(' ') || (acType ? acType : 'Unknown Type');
        const cardStyle = `border-left: 3px solid ${badgeBorder};`;

        return `
            <div class="live-card" style="${cardStyle}" onclick="window.SkyAlertApp.openAircraftProfile('${hex}')">
                <div class="live-card-header">
                    <div class="live-card-reg-flight">
                        <div class="live-card-callsign">${callsign}</div>
                        <div class="live-card-registration">${reg} · ${hex}</div>
                    </div>
                    <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
                        <span class="live-badge" style="background:${badgeBg}; color:${badgeColor}; border:1px solid ${badgeBorder}; font-weight:700;">
                            ${badgeLabel}
                        </span>
                        <span class="live-badge" style="background: rgba(34, 197, 94, 0.15); color: var(--radar-green); border: 1px solid rgba(34, 197, 94, 0.3); font-weight:700;">
                            ${visits} VISIT${visits === 1 ? '' : 'S'}
                        </span>
                    </div>
                </div>
                <div class="live-card-meta">
                    <div class="live-meta-row">
                        <span>Operator</span>
                        <span class="live-meta-val">${operator}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>Type / Airframe</span>
                        <span class="live-meta-val">${acDesc}${acType && acDesc !== acType ? ` (${acType})` : ''}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>Country</span>
                        <span class="live-meta-val">${country}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>First Seen</span>
                        <span class="live-meta-val mono" style="font-size: 11px;">${first}</span>
                    </div>
                    <div class="live-meta-row">
                        <span>Last Seen</span>
                        <span class="live-meta-val mono" style="font-size: 11px; color: var(--radar-green);">${last}</span>
                    </div>
                </div>
                <div class="live-telemetry-strip">
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Visits</span>
                        <span class="telemetry-val" style="color:${badgeColor}; font-weight:800;">${visits}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Observations</span>
                        <span class="telemetry-val">${obs.toLocaleString()}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Avg Duration</span>
                        <span class="telemetry-val">${duration}</span>
                    </div>
                    <div class="telemetry-cell">
                        <span class="telemetry-lbl">Station Status</span>
                        <span class="telemetry-val" style="font-size: 11px; color: var(--radar-cyan);">RECORDED</span>
                    </div>
                </div>
            </div>
        `;
    }

    generateRareRowHtml(ac) {
        const hex      = (ac.icao_hex || '—').toUpperCase();
        const callsign = ac.callsign && ac.callsign !== 'None' ? ac.callsign : hex;
        let reg        = ac.registration && ac.registration !== 'None' && ac.registration !== 'null' ? ac.registration : hex;
        const visits   = ac.visits ?? ac.visit_count ?? ac.total_sessions ?? 1;
        const mfr      = ac.manufacturer && ac.manufacturer !== 'None' ? ac.manufacturer : '';
        const model    = ac.model && ac.model !== 'None' ? ac.model : '';
        const acType   = ac.aircraft_type && ac.aircraft_type !== 'None' ? ac.aircraft_type : '';
        const operator = ac.operator && ac.operator !== 'None' && ac.operator !== 'null' ? ac.operator : 'Unknown Operator';
        const country  = ac.country && ac.country !== 'None' && ac.country !== 'null' ? ac.country : 'Unknown';
        const first    = this.formatDateIst(ac.first_seen || ac.first_seen_ist);
        const last     = this.formatDateIst(ac.last_seen || ac.last_seen_ist);
        const duration = ac.duration || '—';
        const obs      = ac.total_observations || 0;

        let badgeLabel = '⭐ Very Rare';
        let badgeColor = '#f5c518';

        if (ac.is_helicopter || acType === 'B429' || acType === 'B206' || acType === 'EC45' || (mfr && mfr.toLowerCase().includes('bell'))) {
            badgeLabel = '🚁 Helicopter';
            badgeColor = '#38bdf8';
        } else if (ac.is_military || (operator && operator.toLowerCase().includes('air force'))) {
            badgeLabel = '⚔️ Military';
            badgeColor = '#ef4444';
        } else if (visits === 1) {
            badgeLabel = '⭐ Very Rare';
            badgeColor = '#f5c518';
        } else if (visits === 2) {
            badgeLabel = '✦ Rare';
            badgeColor = '#38bdf8';
        } else {
            badgeLabel = '◈ Occasional';
            badgeColor = '#a78bfa';
        }

        const acDesc = [mfr, model].filter(Boolean).join(' ') || (acType ? acType : 'Unknown Type');
        const acDescFull = acType && acDesc !== acType ? `${acDesc} <span style="color:var(--text-muted);font-size:11px">(${acType})</span>` : acDesc;

        return `
            <tr class="rare-list-row" onclick="window.SkyAlertApp.openAircraftProfile('${hex}')"
                title="Click to open Aircraft Intelligence Profile">
                <td>
                    <span class="rare-rarity-badge" style="color:${badgeColor};">${badgeLabel}</span>
                </td>
                <td class="mono" style="font-weight:700; color:var(--radar-cyan);">${callsign}</td>
                <td class="mono" style="color:var(--text-muted); font-size:12px;">${hex}</td>
                <td class="mono">${reg}</td>
                <td style="font-size:12px;">${acDescFull}</td>
                <td style="font-size:12px; color:var(--text-secondary);">${operator}</td>
                <td style="font-size:12px; color:var(--text-secondary);">${country}</td>
                <td style="font-size:11px; color:var(--text-muted);">${first}</td>
                <td style="font-size:11px; color:var(--text-muted);">${last}</td>
                <td style="text-align:center; font-family:var(--font-mono); font-weight:700; color:${badgeColor};">${visits}</td>
                <td style="text-align:center; font-family:var(--font-mono); font-size:12px;">${obs.toLocaleString()}</td>
                <td style="text-align:center; font-size:12px; color:var(--text-muted);">${duration}</td>
            </tr>`;
    }

    async loadAircraftReplay(hex) {
        try {
            const res = await fetch(`/api/aircraft/${hex}/replay`);
            const data = await res.json();
            if (data.trajectory && data.trajectory.length > 0) {
                let msg = `✈ Trajectory Flight Replay Loaded for ${hex}:\nTotal Replay Points: ${data.trajectory.length}\n`;
                data.trajectory.slice(0, 5).forEach(pt => {
                    msg += `\nStep ${pt.step} (${pt.time_ist}): Lat ${pt.latitude}, Lon ${pt.longitude}, Alt ${pt.altitude_ft}ft, Speed ${pt.speed_kmh}km/h`;
                });
                alert(msg);
            } else {
                alert(`No trajectory replay points found for ${hex}.`);
            }
        } catch (e) {
            console.error("Replay error:", e);
        }
    }

    // =========================================================================
    // TELEGRAM CONFIGURATION & TARGET TRACKING AUTOMATION
    // =========================================================================

    async loadTelegramSettings() {
        try {
            const res = await fetch('/api/telegram/config');
            const data = await res.json();
            if (data.status !== 'success') {
                console.error("Failed to load Telegram config:", data);
                return;
            }

            // 1. Telegram Bot Settings
            const tg = data.telegram || {};
            const masterEnable = document.getElementById('tg-master-enable');
            const botToken = document.getElementById('tg-bot-token');
            const chatId = document.getElementById('tg-chat-id');
            const photoEnabled = document.getElementById('tg-photo-enabled');
            const silent = document.getElementById('tg-silent-notifications');

            if (masterEnable) masterEnable.checked = !!tg.enabled;
            if (botToken) botToken.value = tg.bot_token || '';
            if (chatId) chatId.value = tg.chat_id || '';
            if (photoEnabled) photoEnabled.checked = tg.photo_enabled !== false;
            if (silent) silent.checked = !!tg.silent;

            // 2. Scenario Alert Triggers
            const alerts = data.alerts || {};
            const squawk = document.getElementById('tg-alert-squawk');
            const military = document.getElementById('tg-alert-military');
            const gov = document.getElementById('tg-alert-government');
            const helis = document.getElementById('tg-alert-helicopters');
            const rare = document.getElementById('tg-alert-rare');
            const formation = document.getElementById('tg-alert-formation');
            const geofence = document.getElementById('tg-alert-geofence');

            if (squawk) squawk.checked = alerts.squawk !== false;
            if (military) military.checked = alerts.military !== false;
            if (gov) gov.checked = alerts.government !== false;
            if (helis) helis.checked = alerts.helicopters !== false;
            if (rare) rare.checked = alerts.rare_aircraft !== false;
            if (formation) formation.checked = !!alerts.formation;
            if (geofence) geofence.checked = !!alerts.geofence;

            // 3. Geofence & Station Settings
            const geo = data.geofence || {};
            const stLat = document.getElementById('tg-station-lat');
            const stLon = document.getElementById('tg-station-lon');
            const radiusSlider = document.getElementById('tg-radius-slider');
            const radiusVal = document.getElementById('tg-radius-val');
            const geoName = document.getElementById('tg-geofence-name');

            if (stLat) stLat.value = geo.latitude || 22.5726;
            if (stLon) stLon.value = geo.longitude || 88.3639;
            if (radiusSlider) {
                radiusSlider.value = geo.radius_km || 50;
                if (radiusVal) radiusVal.textContent = (geo.radius_km || 50) + ' km';
            }
            if (geoName) geoName.value = geo.name || 'Station Primary Vicinity Zone';

            // 4. Thresholds
            const th = data.thresholds || {};
            const thEnable = document.getElementById('tg-thresholds-enabled');
            const minAlt = document.getElementById('tg-min-altitude');
            const maxSpd = document.getElementById('tg-max-speed');

            if (thEnable) thEnable.checked = !!th.enabled;
            if (minAlt) minAlt.value = th.min_altitude || 5000;
            if (maxSpd) maxSpd.value = th.max_speed || 520;

            // 5. Watchlist & Tracked Targets
            this.renderTelegramTargets(data.watchlist || {});

            // Auto-verify bot connection
            if (tg.bot_token) {
                this.verifyTelegramBotToken(false);
            } else {
                const pill = document.getElementById('tg-bot-status-pill');
                if (pill) {
                    pill.className = 'tg-bot-status-pill disconnected';
                    pill.innerHTML = '<span class="status-dot"></span> Not Configured';
                }
            }

        } catch (e) {
            console.error("Error loading Telegram configuration:", e);
        }
    }

    renderTelegramTargets(watchlist) {
        const tbody = document.getElementById('tg-targets-table-body');
        if (!tbody) return;

        let rowsHtml = '';
        const targets = watchlist.targets || [];
        const hexes = watchlist.hex || [];
        const regs = watchlist.registrations || [];
        const flights = watchlist.flights || [];
        const ops = watchlist.operators || [];

        // Build list of all targets
        const combined = [...targets];

        // Include legacy hex entries if not already in targets
        hexes.forEach(h => {
            if (!combined.some(t => t.type === 'hex' && t.value.toUpperCase() === h.toUpperCase())) {
                combined.push({ type: 'hex', value: h, label: `ICAO Hex: ${h}`, radius_km: 0, enabled: true });
            }
        });

        // Include legacy reg entries
        regs.forEach(r => {
            if (!combined.some(t => t.type === 'reg' && t.value.toUpperCase() === r.toUpperCase())) {
                combined.push({ type: 'reg', value: r, label: `Tail: ${r}`, radius_km: 0, enabled: true });
            }
        });

        // Include legacy flight entries
        flights.forEach(f => {
            if (!combined.some(t => t.type === 'flight' && t.value.toUpperCase() === f.toUpperCase())) {
                combined.push({ type: 'flight', value: f, label: `Flight Prefix: ${f}`, radius_km: 0, enabled: true });
            }
        });

        // Include legacy operator entries
        ops.forEach(o => {
            if (!combined.some(t => t.type === 'operator' && t.value.toLowerCase() === o.toLowerCase())) {
                combined.push({ type: 'operator', value: o, label: `Operator: ${o}`, radius_km: 0, enabled: true });
            }
        });

        if (combined.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 24px; color: var(--text-muted);">
                        <span style="font-size: 20px;">🎯</span>
                        <div style="font-weight: 600; margin-top: 6px;">No target tracking rules configured.</div>
                        <div style="font-size: 12px; color: var(--text-dim); margin-top: 2px;">
                            Add a target above or use a Quick Preset to receive alerts when aircraft enter your vicinity.
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        combined.forEach(t => {
            const type = (t.type || 'hex').toLowerCase();
            const val = t.value || '';
            const label = t.label || val;
            const radius = t.radius_km ? `${t.radius_km} km` : 'Full Coverage';
            const radiusBadge = t.radius_km 
                ? `<span style="display:inline-flex; align-items:center; gap:4px; background:rgba(56,189,248,0.12); color:#38bdf8; padding:2px 8px; border-radius:12px; font-size:11px; font-family:var(--font-mono); font-weight:700;">📍 Within ${radius}</span>`
                : `<span style="color:var(--text-muted); font-size:11.5px;">🌐 Any Distance</span>`;

            let typeBadge = '';
            if (type === 'hex') typeBadge = `<span class="tg-target-pill hex">HEX</span>`;
            else if (type === 'reg' || type === 'registration') typeBadge = `<span class="tg-target-pill reg">TAIL #</span>`;
            else if (type === 'flight' || type === 'callsign') typeBadge = `<span class="tg-target-pill flight">FLIGHT</span>`;
            else if (type === 'operator') typeBadge = `<span class="tg-target-pill operator">OPERATOR</span>`;

            rowsHtml += `
                <tr>
                    <td>${typeBadge}</td>
                    <td class="mono" style="font-weight: 700; color: var(--text-primary); font-size: 13px;">${val}</td>
                    <td style="color: var(--text-secondary); font-size: 12.5px;">${label}</td>
                    <td>${radiusBadge}</td>
                    <td>
                        <span style="display:inline-flex; align-items:center; gap:5px; font-size:11.5px; color:#4ade80; font-weight:600;">
                            <span style="width:6px; height:6px; border-radius:50%; background:#4ade80;"></span> Active
                        </span>
                    </td>
                    <td style="text-align: right;">
                        <button class="sky-btn danger" style="padding: 4px 10px; font-size: 11px;" onclick="window.SkyAlertApp.deleteTrackedTarget('${type}', '${val}')" title="Remove target">
                            🗑️ Delete
                        </button>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = rowsHtml;
    }

    async addTrackedTarget() {
        const typeEl = document.getElementById('tg-new-target-type');
        const valEl = document.getElementById('tg-new-target-val');
        const radiusEl = document.getElementById('tg-new-target-radius');
        const labelEl = document.getElementById('tg-new-target-label');

        if (!valEl || !valEl.value.trim()) {
            alert("Please enter a Target Identifier / Value (e.g. Hex code, Tail #, or Callsign).");
            return;
        }

        const payload = {
            type: typeEl ? typeEl.value : 'hex',
            value: valEl.value.trim().toUpperCase(),
            radius_km: radiusEl ? parseFloat(radiusEl.value) : 50,
            label: labelEl ? labelEl.value.trim() : '',
            enabled: true
        };

        try {
            const res = await fetch('/api/telegram/watchlist/target', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'success') {
                valEl.value = '';
                if (labelEl) labelEl.value = '';
                this.loadTelegramSettings();
            } else {
                alert(`Error adding target: ${data.message || 'Unknown error'}`);
            }
        } catch (e) {
            console.error("Failed to add target:", e);
            alert("Failed to connect to backend server.");
        }
    }

    applyTargetPreset(type, value, label, radius) {
        const typeEl = document.getElementById('tg-new-target-type');
        const valEl = document.getElementById('tg-new-target-val');
        const radiusEl = document.getElementById('tg-new-target-radius');
        const labelEl = document.getElementById('tg-new-target-label');

        if (typeEl) typeEl.value = type;
        if (valEl) valEl.value = value;
        if (radiusEl) radiusEl.value = radius.toString();
        if (labelEl) labelEl.value = label;

        this.addTrackedTarget();
    }

    async deleteTrackedTarget(type, value) {
        if (!confirm(`Remove '${value}' from vicinity tracking watchlist?`)) {
            return;
        }

        try {
            const res = await fetch(`/api/telegram/watchlist/target?type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}`, {
                method: 'DELETE'
            });
            const data = await res.json();
            if (data.status === 'success') {
                this.loadTelegramSettings();
            } else {
                alert(`Error deleting target: ${data.message || 'Unknown error'}`);
            }
        } catch (e) {
            console.error("Failed to delete target:", e);
        }
    }

    async saveTelegramSettings() {
        const payload = {
            telegram: {
                enabled: document.getElementById('tg-master-enable')?.checked ?? true,
                bot_token: document.getElementById('tg-bot-token')?.value?.trim() ?? '',
                chat_id: document.getElementById('tg-chat-id')?.value?.trim() ?? '',
                photo_enabled: document.getElementById('tg-photo-enabled')?.checked ?? true,
                silent: document.getElementById('tg-silent-notifications')?.checked ?? false,
            },
            alerts: {
                squawk: document.getElementById('tg-alert-squawk')?.checked ?? true,
                military: document.getElementById('tg-alert-military')?.checked ?? true,
                government: document.getElementById('tg-alert-government')?.checked ?? true,
                helicopters: document.getElementById('tg-alert-helicopters')?.checked ?? true,
                rare_aircraft: document.getElementById('tg-alert-rare')?.checked ?? true,
                formation: document.getElementById('tg-alert-formation')?.checked ?? false,
                geofence: document.getElementById('tg-alert-geofence')?.checked ?? false,
                watchlist: true,
                thresholds: document.getElementById('tg-thresholds-enabled')?.checked ?? false,
            },
            geofence: {
                enabled: document.getElementById('tg-alert-geofence')?.checked ?? false,
                name: document.getElementById('tg-geofence-name')?.value?.trim() ?? 'Station Primary Vicinity Zone',
                latitude: parseFloat(document.getElementById('tg-station-lat')?.value ?? '22.5726'),
                longitude: parseFloat(document.getElementById('tg-station-lon')?.value ?? '88.3639'),
                radius_km: parseFloat(document.getElementById('tg-radius-slider')?.value ?? '50'),
            },
            thresholds: {
                enabled: document.getElementById('tg-thresholds-enabled')?.checked ?? false,
                min_altitude: parseInt(document.getElementById('tg-min-altitude')?.value ?? '5000'),
                max_speed: parseInt(document.getElementById('tg-max-speed')?.value ?? '520'),
            }
        };

        try {
            const res = await fetch('/api/telegram/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'success') {
                alert("✅ Telegram and alert tracking configuration saved successfully.");
                this.verifyTelegramBotToken(false);
            } else {
                alert(`Error saving configuration: ${data.message || 'Unknown error'}`);
            }
        } catch (e) {
            console.error("Save error:", e);
            alert("Failed to save configuration to backend.");
        }
    }

    async verifyTelegramBotToken(showAlert = true) {
        const tokenInput = document.getElementById('tg-bot-token');
        const token = tokenInput ? tokenInput.value.trim() : '';
        const pill = document.getElementById('tg-bot-status-pill');
        const infoBox = document.getElementById('tg-bot-info-box');

        if (!token) {
            if (pill) {
                pill.className = 'tg-bot-status-pill disconnected';
                pill.innerHTML = '<span class="status-dot"></span> Token Required';
            }
            if (infoBox) infoBox.style.display = 'none';
            if (showAlert) alert("Please enter a Telegram Bot Token to verify.");
            return;
        }

        if (pill) {
            pill.className = 'tg-bot-status-pill checking';
            pill.innerHTML = '<span class="status-dot"></span> Verifying...';
        }

        try {
            const res = await fetch(`/api/telegram/verify?token=${encodeURIComponent(token)}`);
            const data = await res.json();

            if (data.ok && data.bot) {
                if (pill) {
                    pill.className = 'tg-bot-status-pill connected';
                    pill.innerHTML = `<span class="status-dot"></span> 🟢 Connected (@${data.bot.username || data.bot.first_name})`;
                }
                if (infoBox) {
                    infoBox.style.display = 'flex';
                    const nameEl = document.getElementById('tg-bot-name');
                    const userEl = document.getElementById('tg-bot-username');
                    const idEl = document.getElementById('tg-bot-id');
                    if (nameEl) nameEl.textContent = data.bot.first_name || 'SkyAlert Bot';
                    if (userEl) userEl.textContent = `@${data.bot.username || 'unknown'}`;
                    if (idEl) idEl.textContent = `Bot ID: ${data.bot.id}`;
                }
                if (showAlert) {
                    alert(`✅ Bot Verified Successfully!\nName: ${data.bot.first_name}\nUsername: @${data.bot.username}\nID: ${data.bot.id}`);
                }
            } else {
                if (pill) {
                    pill.className = 'tg-bot-status-pill disconnected';
                    pill.innerHTML = '<span class="status-dot"></span> 🔴 Token Invalid';
                }
                if (infoBox) infoBox.style.display = 'none';
                if (showAlert) {
                    alert(`❌ Bot verification failed: ${data.error || 'Invalid Bot Token'}`);
                }
            }
        } catch (e) {
            if (pill) {
                pill.className = 'tg-bot-status-pill disconnected';
                pill.innerHTML = '<span class="status-dot"></span> Verification Error';
            }
            console.error("Verification error:", e);
        }
    }

    async sendTelegramTestAlert() {
        const token = document.getElementById('tg-bot-token')?.value?.trim();
        const chatId = document.getElementById('tg-chat-id')?.value?.trim();
        const photoEnabled = document.getElementById('tg-photo-enabled')?.checked ?? true;

        if (!token || !chatId) {
            alert("Please provide both a Telegram Bot Token and a Chat ID to test.");
            return;
        }

        try {
            const res = await fetch('/api/telegram/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bot_token: token,
                    chat_id: chatId,
                    photo_enabled: photoEnabled
                })
            });
            const data = await res.json();
            if (data.status === 'success') {
                alert("🚀 Test Alert Dispatched!\nCheck your Telegram chat/channel. The test card was delivered successfully.");
            } else {
                alert(`❌ Test delivery failed: ${data.message || 'Unknown error'}`);
            }
        } catch (e) {
            console.error("Test alert error:", e);
            alert("Failed to send test alert to Telegram.");
        }
    }

    toggleTokenVisibility() {
        const tokenInput = document.getElementById('tg-bot-token');
        const eye = document.getElementById('tg-token-eye');
        if (!tokenInput) return;

        if (tokenInput.type === 'password') {
            tokenInput.type = 'text';
            if (eye) eye.textContent = '🔒 Hide Token';
        } else {
            tokenInput.type = 'password';
            if (eye) eye.textContent = '👁️ Show Token';
        }
    }

    async toggleTelegramMaster(enabled) {
        try {
            await fetch('/api/telegram/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    telegram: { enabled: enabled }
                })
            });
        } catch (e) {
            console.error("Error toggling master telegram switch:", e);
        }
    }

}

// Instantiate on DOM load
document.addEventListener("DOMContentLoaded", () => {
    window.SkyAlertApp = new SkyAlertApp();

    window.SkyAlertApp.init();
});
