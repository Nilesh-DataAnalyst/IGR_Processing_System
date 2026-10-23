/**
 * Sogaon Data Processing Pipeline - Web Controller
 * Handles 19-step UI rendering, state management, live polling & console streaming.
 */

// Step Definitions (1 to 19)
const PIPELINE_STEPS = [
  {
    id: 1,
    name: "Input File Ingestion",
    desc: "Loads the LLM-completed file as an input file and validates source tabular structures.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 2,
    name: "DictToColumn Processing",
    desc: "Extracts nested dictionary LLM output strings into standardized flat DataFrame columns.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 3,
    name: "Project Name Resolution",
    desc: "Creates final_project_name from project_name_en and building_name_en fallback.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 4,
    name: "Static Transaction Mapping",
    desc: "Maps transaction types from document names using static dictionary definitions (e.g., deeds containing 'गहाणखत' to 'Mortgage').",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 5,
    name: "Transaction Categorization",
    desc: "Classifies documents into Sale, Lease, or Other category groupings.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 6,
    name: "Standardization & Area Conversion",
    desc: "Cleans project names, calculates net carpet area & converts area measures -> exports _for_manual.xlsx.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 7,
    name: "Manual Corrected File Load",
    desc: "Loads verified/corrected Excel file to resume subsequent enrichment steps.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 8,
    name: "Column Renaming & Standardizing",
    desc: "Normalizes internal column names to DB naming standards (e.g., location_name).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 9,
    name: "Property Type Categorization",
    desc: "Maps raw property types into standard categories (Apartment, Commercial, etc.).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 10,
    name: "Buyer Location & Pincode Lookup",
    desc: "Extracts buyer pincode from buyer_name and enriches locality, district, and state from postal mapping.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 11,
    name: "RERA Grand Reference Matching",
    desc: "Matches project names against city RERA dataset to extract coordinates, BHK, and standard location.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 12,
    name: "PostgreSQL NR Index Assignment",
    desc: "Queries max NR sequence for target city from public.transactions and assigns new nr IDs.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 13,
    name: "Location Coordinates Lookup",
    desc: "Enriches location_latitude & longitude from public.dim_location table.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 14,
    name: "Project Coordinates (Google Places API)",
    desc: "Enriches project coordinates via Google Places API.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 15,
    name: "DB Schema Column Alignment",
    desc: "Filters and orders columns strictly to the 66-field DB_SEQUENCE schema.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 16,
    name: "Title Casing",
    desc: "Applies Title Case to all object/string text columns.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 17,
    name: "Final Output Save (Drive & Local)",
    desc: "Saves final 66-column database-ready file directly to Google Drive (4. Final processed file) with local backup.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  }
];

// Dubai Land Department (DLD) 2-Step Pipeline Definitions
const DUBAI_STEPS = [
  {
    id: 1,
    name: "Dubai Portal Scraping (dubai_scraper.py)",
    desc: "Extracts latest transactions from DLD portal (open.data.gov.ae) using auto-detected start date and saves raw CSV to Google Drive (1. Download Files(Row)).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 2,
    name: "Dubai Pipeline Processing (dld_pipeline.py)",
    desc: "Loads latest raw CSV from 1. Download Files(Row), standardizes columns, assigns NR IDs, enriches coordinates via dim_location & Google Places API, and saves processed Excel to 2.Processed Files.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  }
];

// App State
let appState = {
  mode: "1",
  isRunning: false,
  pollTimer: null,
  startTime: null,
  timerInterval: null,
  currentStep: 0,
  lastLogIndex: 0,
  logs: [],
  step7SelectedFiles: [],
  scannedLocationsData: [],
  // Production Navigation & Pagination Additions
  activeTab: "config",
  layoutMode: "tabbed",
  stepFilter: "all",
  allLogs: [],
  consolePage: 1,
  consolePageSize: 50,
  consoleFilterLevel: "all",
  consoleSearchQuery: "",
  consoleLiveFollow: true,
  unreadNewLogsCount: 0
};

// DOM Elements
const mode1Radio = document.getElementById("mode1-radio");
const mode2Radio = document.getElementById("mode2-radio");
const mode3Radio = document.getElementById("mode3-radio");
const mode4Radio = document.getElementById("mode4-radio");
const mode5Radio = document.getElementById("mode5-radio");
const mode1Label = document.getElementById("mode1-label");
const mode2Label = document.getElementById("mode2-label");
const mode3Label = document.getElementById("mode3-label");
const mode4Label = document.getElementById("mode4-label");
const mode5Label = document.getElementById("mode5-label");

const inputFileGroup = document.getElementById("input-file-group");
const manualFileGroup = document.getElementById("manual-file-group");
const finalFileGroup = document.getElementById("final-file-group");
const inputFilePath = document.getElementById("input-file-path");
const manualFilePath = document.getElementById("manual-file-path");
const finalFilePath = document.getElementById("final-file-path");
const cityIdInput = document.getElementById("city-id");
const cityDetectBadge = document.getElementById("city-detect-badge");
const outputPath = document.getElementById("output-path");
const pipelineForm = document.getElementById("pipeline-form");
const btnRun = document.getElementById("btn-run");
const btnStop = document.getElementById("btn-stop");

// Mode 4 Database Upload Pipeline DOM Elements
const mode4UploadContainer = document.getElementById("mode4-upload-container");
const mode4ActiveDbName = document.getElementById("mode4-active-db-name");
const btnMode4LaunchTerminal = document.getElementById("btn-mode4-launch-terminal");

// Mode 5 Outlier Detection DOM Elements
const mode5LocationContainer = document.getElementById("mode5-location-container");
const mode5AllLocations = document.getElementById("mode5-all-locations");
const mode5LocationInput = document.getElementById("mode5-location-input");
const outlierLocationSelect = document.getElementById("outlier-location-select");
const outlierChipsRow = document.getElementById("outlier-chips-row");
const outlierCityBadgeText = document.getElementById("outlier-city-badge-text");
const btnRefreshOutlierLocs = document.getElementById("btn-refresh-outlier-locs");

// Advanced Collapsible Options
const toggleAdvancedSettings = document.getElementById("toggle-advanced-settings");
const advancedSettingsBody = document.getElementById("advanced-settings-body");
const advArrow = document.getElementById("adv-arrow");
const autoUploadCb = document.getElementById("auto-upload");
const autoOutlierCb = document.getElementById("auto-outlier");
const saveOutlierReportCb = document.getElementById("save-outlier-report");
const includeGeocodingCb = document.getElementById("include-geocoding");
const btnRunOutlierManual = document.getElementById("btn-run-outlier-manual");
const btnLaunchUploadManual = document.getElementById("btn-launch-upload-manual");

const progressBar = document.getElementById("progress-bar");
const progressPercent = document.getElementById("progress-percent");
const currentStepText = document.getElementById("current-step-text");
const metricRows = document.getElementById("metric-rows");
const metricRera = document.getElementById("metric-rera");
const metricReused = document.getElementById("metric-reused");
const metricNr = document.getElementById("metric-nr");
const metricTime = document.getElementById("metric-time");
const stepsStatusSummary = document.getElementById("steps-status-summary");

const stepsGrid = document.getElementById("steps-grid");
const consoleOutput = document.getElementById("console-output");
const autoscrollCb = document.getElementById("autoscroll-cb");
const btnClearConsole = document.getElementById("btn-clear-console");
const serverStatus = document.getElementById("server-status");

// Step 7 Pause & Resume elements
const pauseCard = document.getElementById("pause-card");
const pauseV1Path = document.getElementById("pause-v1-path");
const resumeFilePath = document.getElementById("resume-file-path");
const btnResume = document.getElementById("btn-resume");

// Step 7 Multi-File Selection & Report elements
const step7SelectedFilesContainer = document.getElementById("step7-selected-files-container");
const step7SelectedFilesList = document.getElementById("step7-selected-files-list");
const step7FilesCountBadge = document.getElementById("step7-files-count-badge");
const btnStep7SelectAll = document.getElementById("btn-step7-select-all");
const btnStep7ClearAll = document.getElementById("btn-step7-clear-all");
const step7MergeReportCard = document.getElementById("step7-merge-report-card");
const step7MergeStatusBadge = document.getElementById("step7-merge-status-badge");
const step7MergeStatusMessage = document.getElementById("step7-merge-status-message");
const step7MergeReportTbody = document.getElementById("step7-merge-report-tbody");

// Mode 2 Multi-File Selection Elements (Tab 1)
const mode2SelectedFilesContainer = document.getElementById("mode2-selected-files-container");
const mode2SelectedFilesList = document.getElementById("mode2-selected-files-list");
const mode2FilesCountBadge = document.getElementById("mode2-files-count-badge");
const btnMode2SelectAll = document.getElementById("btn-mode2-select-all");
const btnMode2ClearAll = document.getElementById("btn-mode2-clear-all");
const mode2LocationChips = document.getElementById("mode2-location-chips");
const manualDriveLink = document.getElementById("manual-drive-link");
const inputDriveLink = document.getElementById("input-drive-link");
const finalDriveLink = document.getElementById("final-drive-link");

// Tab 4 Report Hub Dynamic Drive Elements
const hubTitleInput = document.getElementById("hub-title-input");
const hubLinkInput = document.getElementById("hub-link-input");
const hubTitleManual = document.getElementById("hub-title-manual");
const hubLinkManual = document.getElementById("hub-link-manual");
const hubTitleFinal = document.getElementById("hub-title-final");
const hubLinkFinal = document.getElementById("hub-link-final");

// Step 19 Parquet Pause & Confirmation elements
const parquetPauseCard = document.getElementById("parquet-pause-card");
const parquetVerifyPath = document.getElementById("parquet-verify-path");
const parquetConfirmFilePath = document.getElementById("parquet-confirm-file-path");
const parquetVerifyLocationSelect = document.getElementById("parquet-verify-location-select");
const btnRefreshParquetLocs = document.getElementById("btn-refresh-parquet-locs");
const btnConfirmParquet = document.getElementById("btn-confirm-parquet");
const btnSkipParquet = document.getElementById("btn-skip-parquet");

// Google Drive Location Selectors & Refresh Buttons
const driveInputLocationSelect = document.getElementById("drive-input-location-select");
const driveManualLocationSelect = document.getElementById("drive-manual-location-select");
const driveFinalLocationSelect = document.getElementById("drive-final-location-select");
const pauseLocationSelect = document.getElementById("pause-location-select");
const btnRefreshInputLocs = document.getElementById("btn-refresh-input-locs");
const btnRefreshManualLocs = document.getElementById("btn-refresh-manual-locs");
const btnRefreshFinalLocs = document.getElementById("btn-refresh-final-locs");
const btnRefreshPauseLocs = document.getElementById("btn-refresh-pause-locs");

// Optional Email Sharing Elements
const toggleSharePanel = document.getElementById("toggle-share-panel");
const sharePanel = document.getElementById("share-panel");
const shareArrow = document.getElementById("share-arrow");
const shareEmailRecipients = document.getElementById("share-email-recipients");
const btnSendShareEmail = document.getElementById("btn-send-share-email");
const shareEmailDeadline = document.getElementById("share-email-deadline");
const shareEmailCc = document.getElementById("share-email-cc");
const shareStatusMsg = document.getElementById("share-status-msg");

// Dubai Land Department 2-Step Workflow Elements
const dubaiWorkflowCard = document.getElementById("dubai-workflow-card");
const dubaiRunScraping = document.getElementById("dubai-run-scraping");
const dubaiFromDate = document.getElementById("dubai-from-date");
const dubaiToDate = document.getElementById("dubai-to-date");
const dubaiRunProcessing = document.getElementById("dubai-run-processing");
const dubaiCustomCsv = document.getElementById("dubai-custom-csv");
const stepsSectionTitle = document.getElementById("steps-section-title");
const modeSwitchGroup = document.querySelector(".mode-switch-group");
const outputPathGroup = document.getElementById("output-path-group");
const advancedSettingsWrapper = document.getElementById("advanced-settings-wrapper");
const dbSelect = document.getElementById("db-select");
const dbDot = document.getElementById("db-dot");

// Navigation & Pagination DOM Elements
const appNavTabsBar = document.getElementById("app-nav-bar");
const tabBtnConfig = document.getElementById("tab-btn-config");
const tabBtnProgress = document.getElementById("tab-btn-progress");
const tabBtnConsole = document.getElementById("tab-btn-console");
const tabBtnReports = document.getElementById("tab-btn-reports");
const btnModeTabbed = document.getElementById("btn-mode-tabbed");
const btnModeScroll = document.getElementById("btn-mode-scroll");

const paneConfig = document.getElementById("pane-config");
const paneProgress = document.getElementById("pane-progress");
const paneConsole = document.getElementById("pane-console");
const paneReports = document.getElementById("pane-reports");

const tabBadgeCity = document.getElementById("tab-badge-city");
const tabBadgeProgress = document.getElementById("tab-badge-progress");
const tabBadgeLogs = document.getElementById("tab-badge-logs");
const tabBadgeReports = document.getElementById("tab-badge-reports");

const compactStepLabel = document.getElementById("compact-step-label");
const compactProgressBar = document.getElementById("compact-progress-bar");
const compactProgressPercent = document.getElementById("compact-progress-percent");

const consoleTotalBadge = document.getElementById("console-total-badge");
const btnExportLogs = document.getElementById("btn-export-logs");
const consoleSearchInput = document.getElementById("console-search-input");
const btnClearSearch = document.getElementById("btn-clear-search");
const logPageSizeSelect = document.getElementById("log-page-size-select");
const logPageFirst = document.getElementById("log-page-first");
const logPagePrev = document.getElementById("log-page-prev");
const logPageNext = document.getElementById("log-page-next");
const logPageLast = document.getElementById("log-page-last");
const logPageInfo = document.getElementById("log-page-info");
const liveFollowCb = document.getElementById("live-follow-cb");
const btnJumpLatestLogs = document.getElementById("btn-jump-latest-logs");

const countLogAll = document.getElementById("count-log-all");
const countLogInfo = document.getElementById("count-log-info");
const countLogSuccess = document.getElementById("count-log-success");
const countLogWarning = document.getElementById("count-log-warning");
const countLogError = document.getElementById("count-log-error");

const countStepAll = document.getElementById("count-step-all");
const countStepRunning = document.getElementById("count-step-running");
const countStepCompleted = document.getElementById("count-step-completed");
const countStepPending = document.getElementById("count-step-pending");

// =========================================================
// DATABASE SELECTION & MANAGEMENT
// =========================================================
function getSelectedDb() {
  return localStorage.getItem("igr_selected_db") || "nilesh";
}

function updateDbBadge(dbName) {
  if (dbDot) {
    dbDot.className = "db-status-dot";
    if (dbName === "nilesh") {
      dbDot.classList.add("prod");
    } else if (dbName === "test") {
      dbDot.classList.add("staging");
    } else {
      dbDot.classList.add("custom");
    }
  }
  if (mode4ActiveDbName) {
    mode4ActiveDbName.textContent = dbName === "nilesh" ? "nilesh (Production)" : (dbName === "test" ? "test (Staging)" : `${dbName} (Custom)`);
  }
}

async function handleDatabaseChange(newDb, isInitial = false) {
  if (newDb === "__custom__") {
    const customDb = prompt("Enter PostgreSQL database name:", "nilesh");
    if (!customDb || !customDb.trim()) {
      if (dbSelect) dbSelect.value = getSelectedDb();
      return;
    }
    newDb = customDb.trim();
    if (dbSelect) {
      let opt = Array.from(dbSelect.options).find(o => o.value === newDb);
      if (!opt) {
        opt = document.createElement("option");
        opt.value = newDb;
        opt.textContent = `${newDb} (Custom)`;
        dbSelect.insertBefore(opt, dbSelect.querySelector("option[value='__custom__']"));
      }
      dbSelect.value = newDb;
    }
  }

  localStorage.setItem("igr_selected_db", newDb);
  updateDbBadge(newDb);

  try {
    const res = await fetch("/api/set-db", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ database: newDb })
    });
    if (res.ok && !isInitial) {
      logToConsole(`[Database] Active database switched to: ${newDb}`);
    }
  } catch (err) {
    console.error("Failed to notify server of DB change:", err);
  }

  // If Dubai is active, re-query latest date from the newly selected DB
  if (cityIdInput && cityIdInput.value === "15") {
    fetchDubaiConfig(true);
  }
}

function initDatabaseSelector() {
  if (!dbSelect) return;
  const savedDb = getSelectedDb();
  let opt = Array.from(dbSelect.options).find(o => o.value === savedDb);
  if (!opt && savedDb) {
    opt = document.createElement("option");
    opt.value = savedDb;
    opt.textContent = `${savedDb} (Custom)`;
    dbSelect.insertBefore(opt, dbSelect.querySelector("option[value='__custom__']"));
  }
  dbSelect.value = savedDb;
  updateDbBadge(savedDb);

  dbSelect.addEventListener("change", (e) => {
    handleDatabaseChange(e.target.value);
  });

  handleDatabaseChange(savedDb, true);
}

// Auto-detect city from input path or filename
function detectCityFromPath(filepath) {
  if (!filepath || !cityIdInput) return;
  // If the user has explicitly selected a target city from the dropdown, do not let typing/path override it
  if (appState.userManuallySelectedCity) return;
  const lower = filepath.toLowerCase().trim();
  if (lower.length < 5) return;

  const cityMap = [
    { id: "9", patterns: ["pune", "chikhali", "sogaon", "haveli", "pcmc", "mohmadwadi"] },
    { id: "8", patterns: ["mumbai", "andheri", "borivali", "kurla", "bandra", "chembur", "dadar", "goregaon", "malad", "powai", "thane_mumbai"] },
    { id: "12", patterns: ["thane", "kalyan", "dombivli", "navi mumbai", "mira bhayandar"] },
    { id: "2", patterns: ["ahmedabad", "amd"] },
    { id: "3", patterns: ["bangalore", "banglore", "bengaluru"] },
    { id: "6", patterns: ["hyderabad", "secunderabad"] },
    { id: "5", patterns: ["ghaziabad"] },
    { id: "7", patterns: ["medchal"] },
    { id: "10", patterns: ["rangareddy"] },
    { id: "11", patterns: ["sangareddy"] },
    { id: "13", patterns: ["yadadri", "bhuvanagiri"] },
    { id: "1", patterns: ["abu_dhabi", "abudhabi"] },
    { id: "15", patterns: ["dubai"] }
  ];

  for (const item of cityMap) {
    if (item.patterns.some(p => lower.includes(p))) {
      const prevId = cityIdInput.value;
      if (prevId !== item.id) {
        cityIdInput.value = item.id;
        handleCityChange(item.id);
      }
      if (cityDetectBadge) {
        cityDetectBadge.classList.remove("hidden");
        const optText = cityIdInput.options[cityIdInput.selectedIndex] ? cityIdInput.options[cityIdInput.selectedIndex].text.split(" (")[0] : "City";
        cityDetectBadge.textContent = `✨ Auto-detected: ${optText}`;
      }
      return;
    }
  }
}

// =========================================================
// INITIALIZATION
// =========================================================
document.addEventListener("DOMContentLoaded", () => {
  initDatabaseSelector();
  initLayoutMode();
  initNavTabs();
  initConsoleControls();
  initStepFilters();
  renderStepCards();
  initDefaultPaths();
  attachEventListeners();
  handleCityChange(cityIdInput ? cityIdInput.value : "9");
  checkServerHealth();
});

// Render the step cards in the grid (17 steps for India, 2 steps for Dubai)
function renderStepCards(isDubai = false) {
  stepsGrid.innerHTML = "";
  const steps = isDubai ? DUBAI_STEPS : PIPELINE_STEPS;

  steps.forEach(step => {
    const card = document.createElement("div");
    card.className = `step-card ${step.status}`;
    card.id = `step-card-${step.id}`;

    card.innerHTML = `
      <div class="step-top">
        <div class="step-num-group">
          <span class="step-num">${String(step.id).padStart(2, "0")}</span>
          <span class="step-name">${step.name}</span>
        </div>
        <span class="step-badge badge-${step.status}" id="step-badge-${step.id}">
          ${getBadgeIcon(step.status)} ${step.status}
        </span>
      </div>
      <p class="step-desc">${step.desc}</p>
      <div class="step-bottom">
        <span class="step-detail" id="step-detail-${step.id}">${step.detail}</span>
        <span class="step-duration" id="step-duration-${step.id}">${step.duration}</span>
      </div>
    `;

    stepsGrid.appendChild(card);
  });

  if (stepsStatusSummary) {
    stepsStatusSummary.textContent = `0 / ${steps.length} Completed`;
  }
  updateStepCounts();
}

// Dubai 2-Step Workflow Controller Functions
async function fetchDubaiConfig(forceRefresh = false) {
  try {
    const activeDb = getSelectedDb();
    const res = await fetch(`/api/dubai/config?db=${encodeURIComponent(activeDb)}`);
    if (!res.ok) return;
    const data = await res.json();
    if (dubaiFromDate && (forceRefresh || !dubaiFromDate.value)) {
      dubaiFromDate.value = data.from_date || "12/08/2026";
    }
    if (dubaiToDate && (forceRefresh || !dubaiToDate.value)) {
      dubaiToDate.value = data.to_date;
    }
    logToConsole(`[Dubai DB (${activeDb})] Auto-detected start date: ${data.from_date || "N/A"}`);
  } catch (err) {
    console.error("Failed to fetch Dubai config:", err);
  }
}

function enableDubaiView() {
  if (modeSwitchGroup) modeSwitchGroup.classList.remove("hidden");
  if (mode1Label) {
    const s = mode1Label.querySelector("span");
    if (s) s.textContent = "Mode 1: Start (Dubai 2-Step)";
  }
  if (mode2Label) mode2Label.classList.add("hidden");
  if (mode3Label) {
    const s = mode3Label.querySelector("span");
    if (s) s.textContent = "Mode 3: Parquet (2.Processed Files)";
  }
  if (mode4Label) mode4Label.classList.add("hidden");
  if (mode5Label) mode5Label.classList.add("hidden");

  if (outputPathGroup) outputPathGroup.classList.add("hidden");
  if (advancedSettingsWrapper) advancedSettingsWrapper.classList.add("hidden");
  const quickToolsStrip = document.querySelector(".quick-tools-strip");
  if (quickToolsStrip) quickToolsStrip.classList.add("hidden");

  if (inputFilePath) inputFilePath.required = false;
  if (manualFilePath) manualFilePath.required = false;
  if (finalFilePath) finalFilePath.required = false;

  fetchDubaiConfig();

  // If user is already in Mode 3, preserve that mode!
  if (appState.mode === "3") {
    setMode("3");
    return;
  }

  // Otherwise, default to Mode 1 (Dubai 2-Step)
  setMode("1");
}

function disableDubaiView() {
  if (mode1Label) {
    const s = mode1Label.querySelector("span");
    if (s) s.textContent = "Mode 1: Start (Steps 1 → 17)";
  }
  if (mode2Label) {
    mode2Label.classList.remove("hidden");
    const s = mode2Label.querySelector("span");
    if (s) s.textContent = "Mode 2: Resume (Step 7 → 17)";
  }
  if (mode3Label) {
    mode3Label.classList.remove("hidden");
    const s = mode3Label.querySelector("span");
    if (s) s.textContent = "Mode 3: Parquet Conversion";
  }
  if (mode4Label) {
    mode4Label.classList.remove("hidden");
    const s = mode4Label.querySelector("span");
    if (s) s.textContent = "Mode 4: Database Upload";
  }
  if (mode5Label) {
    mode5Label.classList.remove("hidden");
    const s = mode5Label.querySelector("span");
    if (s) s.textContent = "Mode 5: Outlier Detection";
  }

  if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
  if (modeSwitchGroup) modeSwitchGroup.classList.remove("hidden");
  if (outputPathGroup) outputPathGroup.classList.remove("hidden");
  if (advancedSettingsWrapper) advancedSettingsWrapper.classList.remove("hidden");
  const quickToolsStrip = document.querySelector(".quick-tools-strip");
  if (quickToolsStrip) quickToolsStrip.classList.remove("hidden");
  if (stepsSectionTitle) stepsSectionTitle.textContent = "Pipeline Execution Steps (1 to 17)";

  renderStepCards(false);
  if (appState.mode === "dubai") appState.mode = "1";
  setMode(appState.mode);
}

function updateCityDriveLinks(cityId) {
  const cid = String(cityId || (cityIdInput ? cityIdInput.value : "9"));
  const driveConfigs = {
    "9": {
      name: "Pune",
      input: "https://drive.google.com/drive/folders/1i-dPwAQce86kR552YF03XcvLHsOoDjb-?usp=drive_link",
      manual: "https://drive.google.com/drive/folders/1oQ3JQ_v9shWZQlW4JYDpLPXKFOEdAqRW?usp=drive_link",
      final: "https://drive.google.com/drive/folders/1l-HFh36Yk8pSs-NmoSK60if6cP2cjztM"
    },
    "8": {
      name: "Mumbai",
      input: "https://drive.google.com/drive/folders/1rT8PvmuS_s03yrsMvK93luMghbE-9rwD?usp=drive_link",
      manual: "https://drive.google.com/drive/folders/1ywb1-CSRDXNV80Yc8AXYm5Bgze34TXFA?usp=drive_link",
      final: "https://drive.google.com/drive/folders/1Fxf1yTUo4FZWRHjm_XrpA7jq93kG7diO?usp=drive_link"
    },
    "12": {
      name: "Thane",
      input: null,
      manual: null,
      final: null
    },
    "15": {
      name: "Dubai",
      input: "https://drive.google.com/drive/folders/1CyL3ecimjHLcpUv2AfP8d6fJXNbOcVVE?usp=drive_link",
      manual: null,
      final: "https://drive.google.com/drive/folders/1TvDEGGW5dahnxRO4JfxJ8TUinK3DKXO8?usp=drive_link"
    }
  };

  const cfg = driveConfigs[cid] || { name: `City ${cid}`, input: null, manual: null, final: null };

  // Tab 4: Pipeline Output Reports & File Audits Cards
  if (hubTitleInput) hubTitleInput.textContent = `📁 2. LLM Processed Data (${cfg.name})`;
  if (hubLinkInput) {
    if (cfg.input) {
      hubLinkInput.href = cfg.input;
      hubLinkInput.textContent = `Open ${cfg.name} Drive ↗`;
      hubLinkInput.style.display = "inline-flex";
    } else {
      hubLinkInput.style.display = "none";
    }
  }

  if (hubTitleManual) hubTitleManual.textContent = `📁 3. Manually Corrected (${cfg.name})`;
  if (hubLinkManual) {
    if (cfg.manual) {
      hubLinkManual.href = cfg.manual;
      hubLinkManual.textContent = `Open ${cfg.name} Drive ↗`;
      hubLinkManual.style.display = "inline-flex";
    } else {
      hubLinkManual.style.display = "none";
    }
  }

  if (hubTitleFinal) hubTitleFinal.textContent = `📁 4. Final Processed Files (${cfg.name})`;
  if (hubLinkFinal) {
    if (cfg.final) {
      hubLinkFinal.href = cfg.final;
      hubLinkFinal.textContent = `Open ${cfg.name} Drive ↗`;
      hubLinkFinal.style.display = "inline-flex";
    } else {
      hubLinkFinal.style.display = "none";
    }
  }

  // Tab 1 & Tab 2 Links
  if (inputDriveLink && cfg.input) {
    inputDriveLink.href = cfg.input;
    inputDriveLink.textContent = `🌐 Open ${cfg.name} Drive Folder ↗`;
    inputDriveLink.style.display = "inline-flex";
  }

  if (manualDriveLink) {
    if (cfg.manual) {
      manualDriveLink.href = cfg.manual;
      manualDriveLink.textContent = `🌐 Open ${cfg.name} Drive Folder ↗`;
      manualDriveLink.style.display = "inline-flex";
    } else {
      manualDriveLink.style.display = "none";
    }
  }

  const pauseDriveLink = document.getElementById("pause-drive-link") || document.querySelector(".pause-desc .drive-external-link");
  if (pauseDriveLink && cfg.manual) {
    pauseDriveLink.href = cfg.manual;
    pauseDriveLink.textContent = `🌐 Open ${cfg.name} Drive Folder ↗`;
  }

  const parquetLink = document.getElementById("parquet-verify-drive-link");
  if (parquetLink && cfg.final) {
    parquetLink.href = cfg.final;
    parquetLink.textContent = `🌐 Open ${cfg.name} 4. Final processed file ↗`;
  }

  if (finalDriveLink) {
    if (cfg.final) {
      finalDriveLink.href = cfg.final;
      finalDriveLink.textContent = `🌐 Open ${cfg.name} Drive Folder ↗`;
      finalDriveLink.style.display = "inline-flex";
    } else {
      finalDriveLink.style.display = "none";
    }
  }
}

function handleCityChange(cid, isManualSelection = false) {
  cid = String(cid || (cityIdInput ? cityIdInput.value : "9"));
  if (tabBadgeCity && cityIdInput) {
    const selOpt = cityIdInput.options[cityIdInput.selectedIndex];
    const cityName = selOpt ? selOpt.text.split(" (")[0] : `City ${cid}`;
    tabBadgeCity.textContent = `${cityName} (ID: ${cid})`;
  }

  // Update all external Google Drive links across all tabs immediately
  updateCityDriveLinks(cid);

  // If user changed city explicitly, reset input paths and previous selected files
  if (isManualSelection) {
    appState.userManuallySelectedCity = true;
    if (inputFilePath) inputFilePath.value = "";
    if (manualFilePath) manualFilePath.value = "";
    if (finalFilePath) finalFilePath.value = "";
    if (resumeFilePath) resumeFilePath.value = "";
    clearStep7Files();
    appState.selectedLocation = null;
  }

  if (cid === "15") {
    enableDubaiView();
  } else {
    disableDubaiView();
    loadInputDriveLocations(cid);
    loadManualDriveLocations(cid);
    loadFinalDriveLocations(cid);
    loadOutlierLocations(cid);
  }
}

function getBadgeIcon(status) {
  switch (status) {
    case "completed": return "✓";
    case "running": return "⟳";
    case "skipped": return "↷";
    case "failed": return "✕";
    default: return "⏳";
  }
}

// Do not prefill default paths as per user requirement
function initDefaultPaths() {
  inputFilePath.value = "";
  manualFilePath.value = "";
  outputPath.value = "";
}

// =========================================================
// EVENT LISTENERS
// =========================================================
function attachEventListeners() {
  // Mode selection
  mode1Radio.addEventListener("change", () => setMode("1"));
  mode2Radio.addEventListener("change", () => setMode("2"));
  if (mode3Radio) mode3Radio.addEventListener("change", () => setMode("3"));
  if (mode4Radio) mode4Radio.addEventListener("change", () => setMode("4"));
  if (mode5Radio) mode5Radio.addEventListener("change", () => setMode("5"));

  const btnDubaiQuickParquet = document.getElementById("btn-dubai-quick-parquet");
  if (btnDubaiQuickParquet) {
    btnDubaiQuickParquet.addEventListener("click", () => {
      setMode("3");
    });
  }

  // Auto-detect city from path input
  inputFilePath.addEventListener("input", () => detectCityFromPath(inputFilePath.value));
  manualFilePath.addEventListener("input", () => detectCityFromPath(manualFilePath.value));
  if (finalFilePath) finalFilePath.addEventListener("input", () => detectCityFromPath(finalFilePath.value));
  cityIdInput.addEventListener("change", () => {
    if (cityDetectBadge) cityDetectBadge.classList.add("hidden");
    const cid = cityIdInput.value;
    handleCityChange(cid, true);
  });

  // Google Drive Location Dropdowns
  if (driveInputLocationSelect) {
    driveInputLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        inputFilePath.value = val;
        const opt = e.target.selectedOptions[0];
        if (opt && opt.dataset.location) {
          appState.selectedLocation = opt.dataset.location;
        }
        detectCityFromPath(val);
        logToConsole(`[Drive Input] Selected location file: ${val}`, "info");
      }
    });
  }

  if (driveManualLocationSelect) {
    driveManualLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        manualFilePath.value = val;
        const opt = e.target.selectedOptions[0];
        if (opt && opt.dataset.location) {
          appState.selectedLocation = opt.dataset.location;
        }
        detectCityFromPath(val);
        logToConsole(`[Drive Manual] Selected location file: ${val}`, "info");
      }
    });
  }

  if (driveFinalLocationSelect) {
    driveFinalLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        if (finalFilePath) finalFilePath.value = val;
        const opt = e.target.selectedOptions[0];
        if (opt && opt.dataset.location) {
          appState.selectedLocation = opt.dataset.location;
        }
        detectCityFromPath(val);
        logToConsole(`[Drive Final] Selected final file: ${val}`, "info");
      }
    });
  }

  if (pauseLocationSelect) {
    pauseLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        resumeFilePath.value = val;
        const opt = e.target.selectedOptions[0];
        if (opt && opt.dataset.location) {
          appState.selectedLocation = opt.dataset.location;
        }
        const pauseDriveLink = document.getElementById("pause-drive-link") || document.querySelector(".pause-desc .drive-external-link");
        if (pauseDriveLink) {
          const locDriveUrl = opt?.dataset?.driveUrl || (opt?.dataset?.location?.toLowerCase() === "bandra" || val.toLowerCase().includes("bandra") ? "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link" : null);
          if (locDriveUrl) {
            pauseDriveLink.href = locDriveUrl;
            pauseDriveLink.textContent = `🌐 Open ${opt?.dataset?.location || "Drive"} Folder ↗`;
          }
        }
        logToConsole(`[Step 7] Selected alternate manual file: ${val}`, "info");
      } else if (pauseV1Path && pauseV1Path.textContent) {
        resumeFilePath.value = pauseV1Path.textContent;
      }
    });
  }

  // Refresh Drive Folders buttons
  if (btnRefreshInputLocs) {
    btnRefreshInputLocs.addEventListener("click", () => {
      const cid = cityIdInput ? cityIdInput.value : "9";
      loadInputDriveLocations(cid);
      logToConsole(`[Drive] Refreshed input location folders for city ID ${cid}.`, "info");
    });
  }
  if (btnRefreshManualLocs) {
    btnRefreshManualLocs.addEventListener("click", () => {
      const cid = cityIdInput ? cityIdInput.value : "9";
      loadManualDriveLocations(cid);
      logToConsole(`[Drive] Refreshed manual location folders for city ID ${cid}.`, "info");
    });
  }
  if (btnRefreshFinalLocs) {
    btnRefreshFinalLocs.addEventListener("click", () => {
      const cid = cityIdInput ? cityIdInput.value : "9";
      loadFinalDriveLocations(cid);
      logToConsole(`[Drive] Refreshed final location folders for city ID ${cid}.`, "info");
    });
  }
  if (btnRefreshPauseLocs) {
    btnRefreshPauseLocs.addEventListener("click", () => {
      loadManualDriveLocations();
      logToConsole("[Step 7] Refreshed manual correction folders from Google Drive.", "info");
    });
  }

  // Email Sharing Panel in Step 7 Pause Card
  if (toggleSharePanel && sharePanel) {
    toggleSharePanel.addEventListener("click", () => {
      const isHidden = sharePanel.classList.toggle("hidden");
      if (shareArrow) {
        shareArrow.textContent = isHidden ? "▾" : "▴";
      }
    });
  }

  // Contact chips
  document.querySelectorAll(".contact-pill:not(.cc-pill)").forEach(pill => {
    pill.addEventListener("click", () => {
      const email = pill.dataset.email;
      if (email && shareEmailRecipients) {
        shareEmailRecipients.value = email;
      }
    });
  });

  // CC Toggle chips
  document.querySelectorAll(".cc-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const email = pill.dataset.cc;
      if (!email || !shareEmailCc) return;
      let current = shareEmailCc.value.split(",").map(s => s.trim()).filter(Boolean);
      const idx = current.indexOf(email);
      if (idx >= 0) {
        current.splice(idx, 1);
        pill.classList.remove("active");
        if (!pill.textContent.startsWith("+ ")) {
          pill.textContent = "+ " + pill.textContent.replace(/^[\s+]+/, "");
        }
      } else {
        current.push(email);
        pill.classList.add("active");
        pill.textContent = pill.textContent.replace(/^\+\s*/, "");
      }
      shareEmailCc.value = current.join(", ");
    });
  });

  if (btnSendShareEmail) {
    btnSendShareEmail.addEventListener("click", () => {
      handleShareEmail();
    });
  }

  // Deadline quick presets & clear
  function formatLocalISO(d) {
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  document.querySelectorAll(".deadline-preset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (!shareEmailDeadline) return;
      if (btn.id === "btn-clear-deadline") {
        shareEmailDeadline.value = "";
        return;
      }
      const now = new Date();
      let target = new Date();
      if (btn.dataset.hours) {
        target = new Date(now.getTime() + parseInt(btn.dataset.hours, 10) * 3600 * 1000);
      } else if (btn.dataset.preset === "today-eod") {
        target.setHours(18, 0, 0, 0);
        if (target <= now) target.setDate(target.getDate() + 1);
      } else if (btn.dataset.preset === "tomorrow-12pm") {
        target.setDate(target.getDate() + 1);
        target.setHours(12, 0, 0, 0);
      } else if (btn.dataset.preset === "tomorrow-eod") {
        target.setDate(target.getDate() + 1);
        target.setHours(18, 0, 0, 0);
      }
      shareEmailDeadline.value = formatLocalISO(target);
    });
  });

  // Form submission (Run Pipeline)
  pipelineForm.addEventListener("submit", (e) => {
    e.preventDefault();
    startPipeline();
  });

  // Stop pipeline
  btnStop.addEventListener("click", () => {
    stopPipeline();
  });

  // Clear console
  btnClearConsole.addEventListener("click", () => {
    consoleOutput.innerHTML = '<div class="console-line info">[Console cleared]</div>';
  });

  // Resume pipeline at Step 7
  btnResume.addEventListener("click", async () => {
    const manualPath = (resumeFilePath ? resumeFilePath.value.trim() : "") || (manualFilePath ? manualFilePath.value.trim() : "");
    if (!manualPath) {
      alert("Please enter or select the path to the manual corrected file.");
      return;
    }
    btnResume.disabled = true;
    btnResume.innerHTML = '<span class="btn-icon">⏳</span> Resuming...';
    try {
      const res = await fetch("/api/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manual_file: manualPath,
          location_name: appState.selectedLocation || (pauseLocationSelect?.selectedOptions[0]?.dataset.location) || (driveManualLocationSelect?.selectedOptions[0]?.dataset.location) || null,
          output_path: outputPath.value.trim(),
          city_id: parseInt(cityIdInput.value, 10) || 9,
          include_geocoding: document.getElementById("include-geocoding") ? document.getElementById("include-geocoding").checked : false,
          auto_upload: document.getElementById("auto-upload") ? document.getElementById("auto-upload").checked : true,
          auto_outlier: document.getElementById("auto-outlier") ? document.getElementById("auto-outlier").checked : true,
          save_outlier_report: document.getElementById("save-outlier-report") ? document.getElementById("save-outlier-report").checked : false
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to resume pipeline.");
      logToConsole(`[Resume] Sent manual file path: ${manualPath}`, "info");
      pauseCard.classList.add("hidden");

      // Set running state and start polling & timer
      appState.isRunning = true;
      btnRun.disabled = true;
      btnStop.disabled = false;
      btnStop.classList.remove("hidden");
      startTimer();
      switchDashboardTab("progress");
      startPolling();
    } catch (err) {
      alert(`Error resuming pipeline: ${err.message}`);
      logToConsole(`[Resume Error] ${err.message}`, "error");
    } finally {
      btnResume.disabled = false;
      btnResume.innerHTML = '<span class="btn-icon">▶</span> <span class="btn-text">Resume (Steps 7 → 20)</span>';
    }
  });

  // Parquet Verification Buttons (Step 17 pause card)
  if (btnConfirmParquet) {
    btnConfirmParquet.addEventListener("click", async () => {
      const confirmedPath = (parquetConfirmFilePath ? parquetConfirmFilePath.value.trim() : "") || (finalFilePath ? finalFilePath.value.trim() : "");

      // If user selected Mode 3 directly or pipeline is not currently running, launch Mode 3 via startPipeline
      if (appState.mode === "3" || !appState.isRunning) {
        if (!confirmedPath) {
          alert("Please select or enter the final processed file (.xlsx) for Parquet conversion.");
          return;
        }
        if (finalFilePath) finalFilePath.value = confirmedPath;
        if (parquetConfirmFilePath) parquetConfirmFilePath.value = confirmedPath;
        appState.mode = "3";
        startPipeline();
        return;
      }

      btnConfirmParquet.disabled = true;
      btnConfirmParquet.innerHTML = '<span class="btn-icon">⏳</span> Converting...';
      try {
        const curCityId = parseInt(cityIdInput ? cityIdInput.value : "9", 10) || appState.cityId || 9;
        const res = await fetch("/api/confirm-parquet", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "proceed", file_path: confirmedPath, city_id: curCityId })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to confirm Parquet conversion.");
        if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
        if (data.status === "started") {
          appState.isRunning = true;
          startPolling();
        }
        logToConsole(`[Parquet Confirmed] Proceeding with file: ${confirmedPath || "(Drive default)"}`, "success");
      } catch (err) {
        alert(`Error: ${err.message}`);
        logToConsole(`[Parquet Error] ${err.message}`, "error");
      } finally {
        btnConfirmParquet.disabled = false;
        btnConfirmParquet.innerHTML = '<span class="btn-icon">✓</span> <span class="btn-text">Yes, Convert to Parquet</span>';
      }
    });
  }

  if (btnSkipParquet) {
    btnSkipParquet.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to skip Parquet conversion (Step 18)?")) return;
      btnSkipParquet.disabled = true;
      btnSkipParquet.innerHTML = '<span class="btn-icon">⏳</span> Skipping...';
      try {
        const res = await fetch("/api/confirm-parquet", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "skip" })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to skip Parquet conversion.");
        if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
        logToConsole("[Parquet] User chose to skip Parquet conversion.", "warning");
      } catch (err) {
        alert(`Error: ${err.message}`);
        logToConsole(`[Parquet Error] ${err.message}`, "error");
      } finally {
        btnSkipParquet.disabled = false;
        btnSkipParquet.innerHTML = '<span class="btn-icon">⏩</span> <span class="btn-text">Skip Parquet</span>';
      }
    });
  }

  if (parquetVerifyLocationSelect) {
    parquetVerifyLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val && parquetConfirmFilePath) {
        parquetConfirmFilePath.value = val;
        logToConsole(`[Step 18] Selected alternate file: ${val}`, "info");
      }
    });
  }

  if (btnRefreshParquetLocs) {
    btnRefreshParquetLocs.addEventListener("click", () => {
      loadFinalDriveLocations();
      logToConsole("[Step 18] Refreshed final location folders from Google Drive.", "info");
    });
  }

  // Sync Mode 2 manual file inputs & multi-file selection between top form & Step 7 card
  if (resumeFilePath && manualFilePath) {
    resumeFilePath.addEventListener("input", (e) => {
      manualFilePath.value = e.target.value;
      const raw = e.target.value.trim();
      if (raw) {
        const paths = raw.split(",").map(p => p.trim()).filter(Boolean);
        appState.step7SelectedFiles = paths.map(p => ({
          path: p,
          name: p.split(/[\\/]/).pop(),
          location: ""
        }));
        renderStep7SelectedFilesList();
      } else {
        clearStep7Files();
      }
    });
    manualFilePath.addEventListener("input", (e) => {
      resumeFilePath.value = e.target.value;
      const raw = e.target.value.trim();
      if (raw) {
        const paths = raw.split(",").map(p => p.trim()).filter(Boolean);
        appState.step7SelectedFiles = paths.map(p => ({
          path: p,
          name: p.split(/[\\/]/).pop(),
          location: ""
        }));
        renderStep7SelectedFilesList();
      } else {
        clearStep7Files();
      }
    });
  }
  if (pauseLocationSelect) {
    pauseLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        const opt = e.target.selectedOptions[0];
        const loc = opt ? (opt.dataset.location || "") : "";
        const name = opt ? (opt.dataset.name || val.split(/[\\/]/).pop()) : val.split(/[\\/]/).pop();
        addStep7File(val, name, loc);
      }
    });
  }
  if (driveManualLocationSelect) {
    driveManualLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        const opt = e.target.selectedOptions[0];
        const loc = opt ? (opt.dataset.location || "") : "";
        const name = opt ? (opt.dataset.name || val.split(/[\\/]/).pop()) : val.split(/[\\/]/).pop();
        addStep7File(val, name, loc);
      }
    });
  }
  if (btnStep7SelectAll) {
    btnStep7SelectAll.addEventListener("click", () => {
      if (Array.isArray(appState.scannedLocationsData)) {
        appState.scannedLocationsData.forEach(loc => {
          if (Array.isArray(loc.files)) {
            loc.files.forEach(f => addStep7File(f.path, f.name, loc.location));
          }
        });
        document.querySelectorAll(".loc-folder-chip").forEach(c => c.classList.add("active"));
        logToConsole(`[Step 7] Selected all scanned location folders for multi-file merge.`, "info");
      }
    });
  }
  if (btnStep7ClearAll) {
    btnStep7ClearAll.addEventListener("click", () => {
      clearStep7Files();
      document.querySelectorAll(".loc-folder-chip").forEach(c => c.classList.remove("active"));
      logToConsole(`[Step 7] Cleared selected files.`, "info");
    });
  }

  if (btnMode2SelectAll) {
    btnMode2SelectAll.addEventListener("click", () => {
      if (Array.isArray(appState.scannedLocationsData)) {
        appState.scannedLocationsData.forEach(loc => {
          if (Array.isArray(loc.files)) {
            loc.files.forEach(f => addStep7File(f.path, f.name, loc.location));
          }
        });
        document.querySelectorAll(".loc-folder-chip").forEach(c => c.classList.add("active"));
        logToConsole(`[Mode 2] Selected all scanned location folders for multi-file merge.`, "info");
      }
    });
  }
  if (btnMode2ClearAll) {
    btnMode2ClearAll.addEventListener("click", () => {
      clearStep7Files();
      document.querySelectorAll(".loc-folder-chip").forEach(c => c.classList.remove("active"));
      logToConsole(`[Mode 2] Cleared selected files.`, "info");
    });
  }

  // Mode 4 Database Upload Terminal Launcher
  if (btnMode4LaunchTerminal) {
    btnMode4LaunchTerminal.addEventListener("click", () => {
      launchUploadPipeline();
    });
  }

  // Sync Mode 3 final file inputs between top form & Step 18 card
  if (parquetConfirmFilePath && finalFilePath) {
    parquetConfirmFilePath.addEventListener("input", () => {
      finalFilePath.value = parquetConfirmFilePath.value;
    });
    finalFilePath.addEventListener("input", () => {
      parquetConfirmFilePath.value = finalFilePath.value;
    });
  }
  if (driveFinalLocationSelect) {
    driveFinalLocationSelect.addEventListener("change", (e) => {
      if (parquetConfirmFilePath) parquetConfirmFilePath.value = e.target.value;
    });
  }

  // Outlier Mode 5 UI Listeners
  if (mode5AllLocations) {
    mode5AllLocations.addEventListener("change", () => {
      if (mode5LocationInput) {
        mode5LocationInput.disabled = mode5AllLocations.checked;
        if (mode5AllLocations.checked) {
          mode5LocationInput.value = "";
          if (outlierLocationSelect) outlierLocationSelect.value = "";
          document.querySelectorAll(".outlier-chip").forEach(c => c.classList.remove("active"));
          const allChip = document.querySelector(".outlier-chip.chip-all");
          if (allChip) allChip.classList.add("active");
        } else {
          mode5LocationInput.focus();
        }
      }
    });
  }

  if (outlierLocationSelect) {
    outlierLocationSelect.addEventListener("change", (e) => {
      const val = e.target.value;
      if (!val) {
        if (mode5AllLocations) mode5AllLocations.checked = true;
        if (mode5LocationInput) {
          mode5LocationInput.value = "";
          mode5LocationInput.disabled = true;
        }
        document.querySelectorAll(".outlier-chip").forEach(c => c.classList.remove("active"));
        const allChip = document.querySelector(".outlier-chip.chip-all");
        if (allChip) allChip.classList.add("active");
      } else {
        if (mode5AllLocations) mode5AllLocations.checked = false;
        if (mode5LocationInput) {
          mode5LocationInput.value = val;
          mode5LocationInput.disabled = false;
        }
        document.querySelectorAll(".outlier-chip").forEach(c => {
          if (c.dataset.loc === val) {
            c.classList.add("active");
          } else {
            c.classList.remove("active");
          }
        });
      }
    });
  }

  if (mode5LocationInput) {
    mode5LocationInput.addEventListener("input", (e) => {
      const val = e.target.value.trim();
      const enteredLocs = val.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
      const isAll = (enteredLocs.length === 0);
      if (mode5AllLocations) {
        mode5AllLocations.checked = isAll;
      }
      document.querySelectorAll(".outlier-chip").forEach(c => {
        if (c.classList.contains("chip-all")) {
          c.classList.toggle("active", isAll);
        } else {
          const locName = (c.dataset.loc || "").trim().toLowerCase();
          c.classList.toggle("active", enteredLocs.includes(locName));
        }
      });
      if (outlierLocationSelect) {
        if (enteredLocs.length === 1) {
          const matchingOpt = Array.from(outlierLocationSelect.options).find(o => o.value.trim().toLowerCase() === enteredLocs[0]);
          outlierLocationSelect.value = matchingOpt ? matchingOpt.value : "";
        } else {
          outlierLocationSelect.value = "";
        }
      }
    });
  }

  if (btnRefreshOutlierLocs) {
    btnRefreshOutlierLocs.addEventListener("click", () => {
      const cid = cityIdInput ? cityIdInput.value : "9";
      loadOutlierLocations(cid);
      logToConsole(`[Outlier] Refreshed locations list for city ID ${cid}.`, "info");
    });
  }

  // Collapsible Advanced Settings Accordion
  if (toggleAdvancedSettings && advancedSettingsBody) {
    toggleAdvancedSettings.addEventListener("click", () => {
      const isHidden = advancedSettingsBody.classList.toggle("hidden");
      if (advArrow) {
        advArrow.textContent = isHidden ? "▾" : "▴";
      }
    });
  }

  // Manual launch buttons for Standalone Tools
  if (btnLaunchUploadManual) {
    btnLaunchUploadManual.addEventListener("click", () => {
      launchUploadPipeline();
    });
  }

  if (btnRunOutlierManual) {
    btnRunOutlierManual.addEventListener("click", () => {
      runOutlierDetection();
    });
  }
}

function setMode(mode) {
  appState.mode = mode;
  const currentCityId = cityIdInput ? cityIdInput.value : "9";
  const isDubai = (currentCityId === "15");

  if (mode === "1") {
    mode1Label.classList.add("active");
    mode2Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    if (mode4Label) mode4Label.classList.remove("active");
    if (mode5Label) mode5Label.classList.remove("active");

    if (isDubai) {
      if (dubaiWorkflowCard) dubaiWorkflowCard.classList.remove("hidden");
      inputFileGroup.classList.add("hidden");
      manualFileGroup.classList.add("hidden");
      if (finalFileGroup) finalFileGroup.classList.add("hidden");
      if (mode4UploadContainer) mode4UploadContainer.classList.add("hidden");
      if (mode5LocationContainer) mode5LocationContainer.classList.add("hidden");

      if (!appState.isRunning) {
        if (pauseCard) pauseCard.classList.add("hidden");
        if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
      }

      inputFilePath.required = false;
      manualFilePath.required = false;
      if (finalFilePath) finalFilePath.required = false;
      btnRun.innerHTML = '<span class="btn-icon">🚀</span> <span class="btn-text">Start Dubai 2-Step Execution</span>';
      if (stepsSectionTitle) stepsSectionTitle.textContent = "🏙️ Dubai Land Department Pipeline Steps (1 to 2)";
      renderStepCards(true);
      logToConsole("[Mode] Selected Mode 1: Dubai 2-Step Workflow (Scraping -> Processing)");
      return;
    }

    if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
    inputFileGroup.classList.remove("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    if (mode4UploadContainer) mode4UploadContainer.classList.add("hidden");
    if (mode5LocationContainer) mode5LocationContainer.classList.add("hidden");

    if (!appState.isRunning) {
      if (pauseCard) pauseCard.classList.add("hidden");
      if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
    }

    inputFilePath.required = true;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = false;
    btnRun.innerHTML = '<span class="btn-icon">🚀</span> <span class="btn-text">Start Pipeline Execution</span>';
    if (stepsSectionTitle) stepsSectionTitle.textContent = "Pipeline Execution Steps (1 to 17)";
    renderStepCards(false);

    // Reset marks on steps 1 to 17
    for (let i = 1; i <= 17; i++) {
      updateStepUI(i, "pending", "Waiting...", "-");
    }
    logToConsole("[Mode] Selected Mode 1: Run from START (Step 1 to Step 17)");

    // Smooth redirect/scroll to Mode 1 Input section
    setTimeout(() => {
      inputFileGroup.scrollIntoView({ behavior: "smooth", block: "center" });
      if (inputFilePath) inputFilePath.focus();
    }, 120);

  } else if (mode === "2") {
    if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
    mode2Label.classList.add("active");
    mode1Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    if (mode4Label) mode4Label.classList.remove("active");
    if (mode5Label) mode5Label.classList.remove("active");

    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.remove("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    if (mode4UploadContainer) mode4UploadContainer.classList.add("hidden");
    if (mode5LocationContainer) mode5LocationContainer.classList.add("hidden");

    if (!appState.isRunning) {
      if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
    }

    // Reveal and prepare the Step 7 Resume Card
    if (pauseCard) {
      pauseCard.classList.remove("hidden");
      const pBadge = document.getElementById("pause-card-badge");
      if (pBadge) pBadge.textContent = "⚡ Mode 2: Resume Pipeline from Step 7";
      const pTitle = document.getElementById("pause-card-title");
      if (pTitle) pTitle.textContent = "Manual Verification & Resume (Steps 7 → 17)";
      const pSaveStatus = document.getElementById("pause-save-status");
      if (pSaveStatus && (!appState.isRunning || !appState.v1_saved_at)) pSaveStatus.style.display = "none";
      const pInstructions = document.getElementById("pause-card-instructions");
      if (pInstructions) {
        pInstructions.textContent = "Pick or enter manual corrected file(s) from Google Drive (3. Manually Corrected) below, then click Resume to continue pipeline execution from Step 7 to 17.";
      }
    }

    inputFilePath.required = false;
    manualFilePath.required = true;
    if (finalFilePath) finalFilePath.required = false;
    btnRun.innerHTML = '<span class="btn-icon">🚀</span> <span class="btn-text">Start Pipeline Execution</span>';
    if (stepsSectionTitle) stepsSectionTitle.textContent = "Pipeline Execution Steps (1 to 17)";
    renderStepCards(false);

    // Visually mark steps 1-6 as skipped, 7-17 as pending
    for (let i = 1; i <= 6; i++) {
      updateStepUI(i, "skipped", "Skipped in Mode 2", "-");
    }
    for (let i = 7; i <= 17; i++) {
      updateStepUI(i, "pending", "Waiting...", "-");
    }
    logToConsole("[Mode] Selected Mode 2: Resume from Step 7 (Steps 7 to 17)");

    loadManualDriveLocations(currentCityId);

    // Smooth redirect/scroll right down to Mode 2 / Step 7 Resume Card
    setTimeout(() => {
      if (pauseCard) {
        pauseCard.scrollIntoView({ behavior: "smooth", block: "center" });
        if (resumeFilePath) resumeFilePath.focus();
      } else {
        manualFileGroup.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 120);

  } else if (mode === "3") {
    if (mode3Label) mode3Label.classList.add("active");
    mode1Label.classList.remove("active");
    mode2Label.classList.remove("active");
    if (mode4Label) mode4Label.classList.remove("active");
    if (mode5Label) mode5Label.classList.remove("active");

    if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.remove("hidden");
    if (mode4UploadContainer) mode4UploadContainer.classList.add("hidden");
    if (mode5LocationContainer) mode5LocationContainer.classList.add("hidden");

    if (!appState.isRunning) {
      if (pauseCard) pauseCard.classList.add("hidden");
    }

    // Reveal Parquet Card (parquetPauseCard)
    if (parquetPauseCard) {
      parquetPauseCard.classList.remove("hidden");
      const pqBadge = document.getElementById("parquet-card-badge");
      if (pqBadge) pqBadge.textContent = isDubai ? "⚡ Mode 3: Direct Dubai Parquet Conversion" : "⚡ Mode 3: Parquet Conversion";
      const pqTitle = document.getElementById("parquet-card-title");
      if (pqTitle) pqTitle.textContent = isDubai ? "Select Dubai Processed File for Parquet Conversion" : "Select Final Processed File for Parquet Conversion";
      const pqInstructions = document.getElementById("parquet-card-instructions");
      if (pqInstructions) {
        pqInstructions.textContent = isDubai
          ? "Pick or enter a Dubai processed file from Google Drive (2.Processed Files) below, then click 'Yes, Convert to Parquet' or Start Pipeline."
          : "Pick or enter a final processed file from Google Drive (4. Final processed file) below, then click 'Yes, Convert to Parquet' to proceed with Parquet conversion.";
      }
    }

    inputFilePath.required = false;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = true;
    btnRun.innerHTML = isDubai
      ? '<span class="btn-icon">⚡</span> <span class="btn-text">Convert Dubai File to Parquet</span>'
      : '<span class="btn-icon">⚡</span> <span class="btn-text">Convert to Parquet</span>';

    if (stepsSectionTitle) stepsSectionTitle.textContent = isDubai ? "🏙️ Dubai Pipeline Steps (Parquet Conversion)" : "⚡ Mode 3: Parquet Conversion";
    renderStepCards(false);

    // Visually mark steps 1-17 as skipped
    for (let i = 1; i <= 17; i++) {
      updateStepUI(i, "skipped", "Stand-alone Parquet Mode", "-");
    }
    logToConsole(`[Mode] Selected Mode 3: Parquet Conversion Directly (${isDubai ? "Dubai" : "City ID " + currentCityId})`);

    loadFinalDriveLocations(currentCityId);

    // Smooth redirect/scroll right to the Parquet Card
    setTimeout(() => {
      if (parquetPauseCard) {
        parquetPauseCard.scrollIntoView({ behavior: "smooth", block: "center" });
        if (parquetConfirmFilePath) parquetConfirmFilePath.focus();
      } else if (finalFileGroup) {
        finalFileGroup.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 120);

  } else if (mode === "4") {
    if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
    if (mode4Label) mode4Label.classList.add("active");
    mode1Label.classList.remove("active");
    mode2Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    if (mode5Label) mode5Label.classList.remove("active");

    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    if (mode4UploadContainer) mode4UploadContainer.classList.remove("hidden");
    if (mode5LocationContainer) mode5LocationContainer.classList.add("hidden");

    if (!appState.isRunning) {
      if (pauseCard) pauseCard.classList.add("hidden");
      if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
    }

    inputFilePath.required = false;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = false;
    btnRun.innerHTML = '<span class="btn-icon">🚀</span> <span class="btn-text">Launch Database Upload (final_code.py)</span>';

    if (stepsSectionTitle) stepsSectionTitle.textContent = "🚀 Mode 4: Database Upload Pipeline (final_code.py)";
    renderStepCards(false);

    // Visually mark steps 1-17 as skipped
    for (let i = 1; i <= 17; i++) {
      updateStepUI(i, "skipped", "Stand-alone Upload Pipeline", "-");
    }
    logToConsole("[Mode] Selected Mode 4: Database Upload Pipeline (triggers final_code.py)");

    // Smooth redirect/scroll right to Mode 4 upload container
    setTimeout(() => {
      if (mode4UploadContainer) {
        mode4UploadContainer.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 120);

  } else if (mode === "5") {
    if (dubaiWorkflowCard) dubaiWorkflowCard.classList.add("hidden");
    if (mode5Label) mode5Label.classList.add("active");
    mode1Label.classList.remove("active");
    mode2Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    if (mode4Label) mode4Label.classList.remove("active");

    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    if (mode4UploadContainer) mode4UploadContainer.classList.add("hidden");
    if (mode5LocationContainer) mode5LocationContainer.classList.remove("hidden");

    if (!appState.isRunning) {
      if (pauseCard) pauseCard.classList.add("hidden");
      if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
    }

    inputFilePath.required = false;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = false;
    btnRun.innerHTML = '<span class="btn-icon">📊</span> <span class="btn-text">Run Outlier Detection</span>';

    if (stepsSectionTitle) stepsSectionTitle.textContent = "📊 Mode 5: Outlier Detection & Database Update";
    renderStepCards(false);

    // Visually mark steps 1-17 as skipped
    for (let i = 1; i <= 17; i++) {
      updateStepUI(i, "skipped", "Stand-alone Outlier Mode", "-");
    }
    loadOutlierLocations(currentCityId);
    logToConsole("[Mode] Selected Mode 5: Outlier Detection & Database Update");

    // Smooth redirect/scroll right to Outlier section
    setTimeout(() => {
      if (mode5LocationContainer) {
        mode5LocationContainer.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 120);
  }
}

// =========================================================
// PIPELINE RUNNER & POLLING
// =========================================================
async function startPipeline() {
  const isDubai = cityIdInput && cityIdInput.value === "15";

  // Standalone triggers for Mode 4 and Mode 5
  if (appState.mode === "4") {
    launchUploadPipeline();
    return;
  }

  if (appState.mode === "5") {
    runOutlierDetection();
    return;
  }

  // Dubai scraping & processing is ONLY run for Mode 1 (or default Dubai mode).
  // If Mode 3 (Parquet conversion) is selected, DO NOT run scraping!
  if (isDubai && appState.mode !== "3") {
    const runScraping = dubaiRunScraping ? dubaiRunScraping.checked : true;
    const runProcessing = dubaiRunProcessing ? dubaiRunProcessing.checked : true;

    if (!runScraping && !runProcessing) {
      alert("Please enable at least Step 1 (Scraping) or Step 2 (Processing).");
      return;
    }

    const fromDate = dubaiFromDate ? dubaiFromDate.value.trim() : "";
    const toDate = dubaiToDate ? dubaiToDate.value.trim() : "";
    const customCsv = dubaiCustomCsv ? dubaiCustomCsv.value.trim() : "";
    const dubaiGeocodingCb = document.getElementById("dubai-include-geocoding");
    const includeGeocoding = dubaiGeocodingCb ? dubaiGeocodingCb.checked : true;

    const payload = {
      city_id: 15,
      city_name: "Dubai",
      city_key: "dubai",
      mode: "1",
      from_date: fromDate,
      to_date: toDate,
      input_file: customCsv,
      database: getSelectedDb(),
      skip_scraping: !runScraping,
      skip_processing: !runProcessing,
      include_geocoding: includeGeocoding
    };

    // Reset UI
    appState.isRunning = true;
    appState.lastLogIndex = 0;
    btnRun.disabled = true;
    btnStop.disabled = false;
    btnStop.classList.remove("hidden");
    startTimer();
    switchDashboardTab("progress");

    logToConsole(`\n[Execution] Triggering Dubai Land Department (DLD) 2-Step Pipeline...`);
    if (runScraping) logToConsole(`  - Step 1 (Scraping): Date range ${fromDate || "Auto DB"} to ${toDate || "Yesterday"}`);
    if (runProcessing) logToConsole(`  - Step 2 (Processing): Input ${customCsv ? customCsv : "Latest from 1. Download Files(Row)"}`);

    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to start Dubai pipeline.");
      }

      logToConsole(`[Server] Dubai pipeline worker thread started successfully.`);
      startPolling();
    } catch (err) {
      logToConsole(`[Error] ${err.message}`, "error");
      alert(`Could not start Dubai pipeline: ${err.message}`);
      resetRunState();
    }
    return;
  }

  const isMode3 = appState.mode === "3";

  let chosenFinalFile = "";
  if (isMode3) {
    chosenFinalFile = (finalFilePath ? finalFilePath.value.trim() : "") || (parquetConfirmFilePath ? parquetConfirmFilePath.value.trim() : "");
    if (!chosenFinalFile) {
      alert("Please select or enter the final processed file (.xlsx) for Parquet conversion.");
      return;
    }
  }

  const targetOutput = isMode3 ? chosenFinalFile : outputPath.value.trim();
  if (!isMode3 && targetOutput && !targetOutput.toLowerCase().endsWith(".xlsx")) {
    alert("Output file path must end with '.xlsx'. Please correct it.");
    return;
  }

  const autoUploadCb = document.getElementById("auto-upload");
  const autoOutlierCb = document.getElementById("auto-outlier");
  const saveOutlierCb = document.getElementById("save-outlier-report");
  const geocodingCb = document.getElementById("include-geocoding");

  const payload = {
    mode: appState.mode,
    input_file: isMode3 ? chosenFinalFile : inputFilePath.value.trim(),
    manual_file: manualFilePath.value.trim(),
    final_file: isMode3 ? chosenFinalFile : "",
    location_name: appState.selectedLocation || (driveInputLocationSelect?.selectedOptions[0]?.dataset.location) || null,
    city_id: parseInt(cityIdInput.value, 10) || (isDubai ? 15 : 9),
    output_path: isMode3 ? chosenFinalFile : targetOutput,
    database: getSelectedDb(),
    include_geocoding: geocodingCb ? geocodingCb.checked : false,
    auto_upload: autoUploadCb ? autoUploadCb.checked : true,
    auto_outlier: autoOutlierCb ? autoOutlierCb.checked : true,
    save_outlier_report: saveOutlierCb ? saveOutlierCb.checked : false
  };

  // Reset UI
  appState.isRunning = true;
  appState.lastLogIndex = 0;
  btnRun.disabled = true;
  btnStop.disabled = false;
  btnStop.classList.remove("hidden");
  startTimer();
  switchDashboardTab("progress");

  logToConsole(`\n[Execution] Triggering Pipeline Run in Mode ${appState.mode}...`);
  logToConsole(`[Target Output] ${targetOutput}`);

  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Failed to start pipeline.");
    }

    logToConsole(`[Server] Pipeline worker thread started successfully.`);
    startPolling();
  } catch (err) {
    logToConsole(`[Error] ${err.message}`, "error");
    alert(`Could not start pipeline: ${err.message}`);
    resetRunState();
  }
}

async function stopPipeline() {
  try {
    await fetch("/api/stop", { method: "POST" });
    logToConsole("[System] Stop signal sent to server.", "warning");
  } catch (err) {
    logToConsole(`[Error stopping] ${err.message}`, "error");
  }
}

function startPolling() {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  appState.pollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const status = await res.json();
      applyStatusUpdate(status);

      if (status.state === "completed" || status.state === "failed" || status.state === "stopped") {
        clearInterval(appState.pollTimer);
        appState.pollTimer = null;
        resetRunState();

        if (status.state === "completed") {
          const fileMsg = status.output_file && status.output_file !== "Database Updated" 
            ? `\nSaved to: ${status.output_file}` 
            : "";
          logToConsole(`\n🎉 [Pipeline Finished] Completed successfully!${fileMsg}`, "success");
          alert(`🎉 Pipeline execution completed successfully!${fileMsg}`);
        } else if (status.state === "failed") {
          logToConsole(`\n❌ [Pipeline Failed] Error: ${status.error}`, "error");
        }
      }
    } catch (err) {
      console.error("Polling error:", err);
    }
  }, 700);
}

function applyStatusUpdate(status) {
  // Only auto-switch to Dubai 2-Step view if the active mode is Dubai 2-step (Mode 1 / "dubai")
  const isDubai2Step = (status.city_id === 15 || status.city_key === "dubai") && (status.mode === "dubai" || (status.steps && status.steps.length === 2));
  const currentlyShowingDubai2Step = stepsGrid.querySelectorAll(".step-card").length === 2;

  if (isDubai2Step && !currentlyShowingDubai2Step && appState.mode !== "3" && appState.mode !== "4") {
    if (cityIdInput && cityIdInput.value !== "15") cityIdInput.value = "15";
    enableDubaiView();
  } else if (!isDubai2Step && currentlyShowingDubai2Step && !appState.isRunning && cityIdInput && cityIdInput.value !== "15") {
    disableDubaiView();
  }

  // Update progress percentage
  const pct = Math.min(100, Math.max(0, status.progress || 0));
  progressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${pct}%`;
  currentStepText.textContent = status.current_step_name || "Executing...";

  if (compactProgressBar) compactProgressBar.style.width = `${pct}%`;
  if (compactProgressPercent) compactProgressPercent.textContent = `${pct}%`;
  if (compactStepLabel) compactStepLabel.textContent = status.current_step_name || "Executing...";
  if (tabBadgeProgress) tabBadgeProgress.textContent = `${pct}%`;

  // Update metrics
  if (status.metrics) {
    if (status.metrics.total_rows !== undefined && status.metrics.total_rows !== null) metricRows.textContent = status.metrics.total_rows.toLocaleString();
    if (status.metrics.rera_matched !== undefined && status.metrics.rera_matched !== null) metricRera.textContent = status.metrics.rera_matched.toLocaleString();
    if (status.metrics.reused_matched !== undefined && status.metrics.reused_matched !== null && metricReused) metricReused.textContent = status.metrics.reused_matched.toLocaleString();
    if (status.metrics.nr_assigned !== undefined && status.metrics.nr_assigned !== null) metricNr.textContent = status.metrics.nr_assigned.toLocaleString();
  }

  // Update step cards
  if (status.steps && Array.isArray(status.steps)) {
    let completedCount = 0;
    status.steps.forEach(s => {
      updateStepUI(s.id, s.status, s.detail, s.duration);
      if (s.status === "completed") completedCount++;
    });
    stepsStatusSummary.textContent = `${completedCount} / ${status.steps.length} Completed`;
    updateStepCounts();
  }

  if (status.step7_merge_report) {
    renderStep7MergeReport(status.step7_merge_report);
    if (tabBadgeReports) {
      tabBadgeReports.textContent = `${status.step7_merge_report.files?.length || 1} files`;
    }
    mirrorStep7MergeReportToTab4(status.step7_merge_report);
  }

  // Handle Step 7 and Step 18 Pause States (strictly hide for Dubai)
  const isDubaiActive = (cityIdInput && cityIdInput.value === "15") || isDubai2Step || (status.city_id === 15) || (status.city_key === "dubai") || appState.mode === "dubai";

  if (isDubaiActive) {
    if (pauseCard) pauseCard.classList.add("hidden");
    if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
  } else {
    // Handle Step 7 Pause State (or active Mode 2 when idle)
    if (status.state === "awaiting_manual_file") {
      const isFirstTimePaused = pauseCard.classList.contains("hidden");
      pauseCard.classList.remove("hidden");
      if (status.v1_file) {
        pauseV1Path.textContent = status.v1_file;
        if ((!appState.step7SelectedFiles || appState.step7SelectedFiles.length === 0) && !resumeFilePath.value) {
          addStep7File(status.v1_file, status.v1_file.split(/[\\/]/).pop(), "Step 6 Default");
        }
      }
      const pauseSaveTime = document.getElementById("pause-save-time");
      if (pauseSaveTime) {
        pauseSaveTime.textContent = status.v1_saved_at || "Just now";
      }
      const pSaveStatus = document.getElementById("pause-save-status");
      if (pSaveStatus) pSaveStatus.style.display = "inline-flex";
      const pBadge = document.getElementById("pause-card-badge");
      if (pBadge) pBadge.textContent = "⏸️ Step 6 Complete — Paused at Step 7";
      const pTitle = document.getElementById("pause-card-title");
      if (pTitle) pTitle.textContent = "Manual Verification Required";

      if (status.location_name) {
        appState.selectedLocation = status.location_name;
      }
      const pauseDriveLink = document.getElementById("pause-drive-link") || document.querySelector(".pause-desc .drive-external-link");
      if (pauseDriveLink && (status.manual_drive_url || (status.location_name && status.location_name.toLowerCase() === "bandra"))) {
        const bandraUrl = "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link";
        const targetUrl = (status.location_name && status.location_name.toLowerCase() === "bandra") ? bandraUrl : status.manual_drive_url;
        pauseDriveLink.href = targetUrl;
        pauseDriveLink.textContent = `🌐 Open ${status.location_name || "Drive"} Folder ↗`;
      }
      if (isFirstTimePaused) {
        loadManualDriveLocations();
        switchDashboardTab("progress");
        pauseCard.scrollIntoView({ behavior: "smooth", block: "center" });
        logToConsole(`\n⏸️ [Action Required] Step 6 Complete! File saved to Google Drive at ${status.v1_saved_at || "just now"}. Please review/correct project names in Google Drive or select file below.`, "warning");
      }
    } else if (appState.mode === "2" && !appState.isRunning) {
      if (pauseCard) pauseCard.classList.remove("hidden");
    } else {
      if (pauseCard) pauseCard.classList.add("hidden");
    }

    // Handle Step 18 Parquet Confirmation Pause State (or active Mode 3 when idle)
    if (status.state === "awaiting_parquet_confirmation") {
      if (parquetPauseCard) {
        const isFirstTimePaused = parquetPauseCard.classList.contains("hidden");
        parquetPauseCard.classList.remove("hidden");
        if (status.output_file) {
          if (parquetVerifyPath) parquetVerifyPath.textContent = status.output_file;
          if (parquetConfirmFilePath && (!parquetConfirmFilePath.value || isFirstTimePaused)) {
            parquetConfirmFilePath.value = status.output_file;
          }
        }
        const pBadge = document.getElementById("parquet-card-badge");
        if (pBadge) pBadge.textContent = "⏸️ Step 17 Complete — Parquet Conversion Review";
        const pTitle = document.getElementById("parquet-card-title");
        if (pTitle) pTitle.textContent = "Is the Final Processed File Correct?";

        const verifyDriveLink = document.getElementById("parquet-verify-drive-link");
        if (verifyDriveLink) {
          const finalUrl = status.final_drive_url || (status.city_id == 8 ? "https://drive.google.com/drive/folders/1Fxf1yTUo4FZWRHjm_XrpA7jq93kG7diO?usp=drive_link" : (status.city_id == 9 ? "https://drive.google.com/drive/folders/1l-HFh36Yk8pSs-NmoSK60if6cP2cjztM" : null));
          if (finalUrl) {
            verifyDriveLink.href = finalUrl;
            verifyDriveLink.textContent = `🌐 Open ${status.city_name || "4. Final processed file"} ↗`;
          }
        }
        if (isFirstTimePaused) {
          loadFinalDriveLocations(status.city_id || (cityIdInput ? cityIdInput.value : ""));
          switchDashboardTab("progress");
          parquetPauseCard.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    } else if (appState.mode === "3" && !appState.isRunning) {
      if (parquetPauseCard) parquetPauseCard.classList.remove("hidden");
    } else {
      if (parquetPauseCard) {
        parquetPauseCard.classList.add("hidden");
      }
    }
  }

  // Append new logs without duplicate spam
  if (status.logs && Array.isArray(status.logs)) {
    if (status.logs.length < appState.lastLogIndex) {
      appState.lastLogIndex = 0;
    }
    const newLogs = status.logs.slice(appState.lastLogIndex);
    newLogs.forEach(log => {
      logToConsole(log.text, log.level);
      if (log.text.includes("MANUAL CAPTCHA ACTION REQUIRED") || log.text.includes("solve the image puzzle")) {
        updateStepUI(1, "running", "🧩 Action Required: Solve CAPTCHA puzzle in Chrome window!");
      } else if (log.text.includes("CAPTCHA SOLVED") || log.text.includes("AUTO-VERIFIED")) {
        updateStepUI(1, "running", "✔ CAPTCHA verified! Resuming automation...");
      }
    });
    appState.lastLogIndex = status.logs.length;
  }
}

function updateStepUI(id, status, detail, duration) {
  const card = document.getElementById(`step-card-${id}`);
  const badge = document.getElementById(`step-badge-${id}`);
  const detailEl = document.getElementById(`step-detail-${id}`);
  const durationEl = document.getElementById(`step-duration-${id}`);

  if (!card || !badge) return;

  card.className = `step-card ${status}`;
  badge.className = `step-badge badge-${status}`;
  badge.innerHTML = `${getBadgeIcon(status)} ${status}`;

  if (detail) detailEl.textContent = detail;
  if (duration) durationEl.textContent = duration;

  // Respect active filter on step cards
  if (appState.stepFilter && appState.stepFilter !== "all") {
    card.style.display = (appState.stepFilter === status) ? "" : "none";
  } else {
    card.style.display = "";
  }
}

function resetRunState() {
  appState.isRunning = false;
  btnRun.disabled = false;
  btnStop.disabled = true;
  btnStop.classList.add("hidden");
  stopTimer();
  if (pauseCard) pauseCard.classList.add("hidden");
  if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
}

// =========================================================
// TIMER & LOGGING HELPERS
// =========================================================
function startTimer() {
  appState.startTime = Date.now();
  if (appState.timerInterval) clearInterval(appState.timerInterval);
  appState.timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - appState.startTime) / 1000);
    const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
    const secs = String(elapsed % 60).padStart(2, "0");
    metricTime.textContent = `${mins}:${secs}`;
  }, 1000);
}

function stopTimer() {
  if (appState.timerInterval) {
    clearInterval(appState.timerInterval);
    appState.timerInterval = null;
  }
}

function getConsolePageSize() {
  const val = logPageSizeSelect ? logPageSizeSelect.value : "50";
  if (val === "all") return Infinity;
  const num = parseInt(val, 10);
  return isNaN(num) ? 50 : num;
}

function getFilteredLogs() {
  const levelFilter = appState.consoleFilterLevel || "all";
  const search = (appState.consoleSearchQuery || "").toLowerCase().trim();

  return (appState.allLogs || []).filter(log => {
    if (levelFilter !== "all" && log.level !== levelFilter) {
      return false;
    }
    if (search && !log.text.toLowerCase().includes(search)) {
      return false;
    }
    return true;
  });
}

function updateLogStats() {
  const total = appState.allLogs ? appState.allLogs.length : 0;
  let info = 0, success = 0, warning = 0, error = 0;

  for (let i = 0; i < total; i++) {
    const l = appState.allLogs[i].level;
    if (l === "info") info++;
    else if (l === "success") success++;
    else if (l === "warning") warning++;
    else if (l === "error") error++;
  }

  if (consoleTotalBadge) consoleTotalBadge.textContent = `${total.toLocaleString()} events`;
  if (tabBadgeLogs) tabBadgeLogs.textContent = total > 999 ? `${(total / 1000).toFixed(1)}k` : `${total} Logs`;

  if (countLogAll) countLogAll.textContent = total;
  if (countLogInfo) countLogInfo.textContent = info;
  if (countLogSuccess) countLogSuccess.textContent = success;
  if (countLogWarning) countLogWarning.textContent = warning;
  if (countLogError) countLogError.textContent = error;
}

function updateConsolePaginationUI(filteredCount, totalPages) {
  if (logPageInfo) {
    if (filteredCount === 0) {
      logPageInfo.textContent = "No logs match filter";
    } else {
      const page = appState.consolePage || 1;
      logPageInfo.textContent = `Page ${page} of ${totalPages} (${filteredCount.toLocaleString()} total)`;
    }
  }

  const curPage = appState.consolePage || 1;
  if (logPageFirst) logPageFirst.disabled = (curPage <= 1);
  if (logPagePrev) logPagePrev.disabled = (curPage <= 1);
  if (logPageNext) logPageNext.disabled = (curPage >= totalPages || filteredCount === 0);
  if (logPageLast) logPageLast.disabled = (curPage >= totalPages || filteredCount === 0);
}

function renderConsoleLogs() {
  if (!consoleOutput) return;

  const filtered = getFilteredLogs();
  const pageSize = getConsolePageSize();
  const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));

  // Bound current page
  if (appState.consolePage > totalPages) appState.consolePage = totalPages;
  if (appState.consolePage < 1) appState.consolePage = 1;

  updateConsolePaginationUI(filtered.length, totalPages);

  const startIdx = pageSize === Infinity ? 0 : (appState.consolePage - 1) * pageSize;
  const endIdx = pageSize === Infinity ? filtered.length : startIdx + pageSize;
  const pageItems = filtered.slice(startIdx, endIdx);

  consoleOutput.innerHTML = "";

  if (pageItems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "console-empty-notice";
    empty.style.padding = "28px 16px";
    empty.style.textAlign = "center";
    empty.style.color = "var(--text-muted)";
    empty.style.fontSize = "0.85rem";
    empty.textContent = (!appState.allLogs || appState.allLogs.length === 0)
      ? "Terminal ready. Start a pipeline run to stream real-time execution logs."
      : "No log entries match the current filter or search criteria.";
    consoleOutput.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  const search = (appState.consoleSearchQuery || "").toLowerCase().trim();

  pageItems.forEach(item => {
    const line = document.createElement("div");
    line.className = `console-line ${item.level}`;

    if (search && item.text.toLowerCase().includes(search)) {
      const raw = item.text;
      const lower = raw.toLowerCase();
      const idx = lower.indexOf(search);
      const before = raw.slice(0, idx);
      const match = raw.slice(idx, idx + search.length);
      const after = raw.slice(idx + search.length);

      line.appendChild(document.createTextNode(before));
      const mark = document.createElement("mark");
      mark.style.background = "#fbbf24";
      mark.style.color = "#000";
      mark.style.borderRadius = "2px";
      mark.style.padding = "0 3px";
      mark.style.fontWeight = "600";
      mark.textContent = match;
      line.appendChild(mark);
      line.appendChild(document.createTextNode(after));
    } else {
      line.textContent = item.text;
    }
    frag.appendChild(line);
  });

  consoleOutput.appendChild(frag);

  // Auto-scroll if enabled and we are viewing the latest page
  if (autoscrollCb && autoscrollCb.checked && (appState.consolePage >= totalPages)) {
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }
}

function exportLogsToFile() {
  if (!appState.allLogs || appState.allLogs.length === 0) {
    alert("No console logs to export.");
    return;
  }

  const logLines = appState.allLogs.map(l => `[${l.timestamp}] [${(l.level || "INFO").toUpperCase()}] ${l.text}`);
  const blob = new Blob([logLines.join("\r\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  const timeStr = now.toTimeString().slice(0, 8).replace(/:/g, "-");
  a.download = `IGR_Pipeline_Logs_${dateStr}_${timeStr}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function logToConsole(message, level = "info") {
  if (!message) return;
  if (!appState.allLogs) appState.allLogs = [];

  const logItem = {
    id: appState.allLogs.length + 1,
    text: String(message),
    level: level || "info",
    timestamp: new Date().toLocaleTimeString()
  };
  appState.allLogs.push(logItem);

  updateLogStats();

  const pageSize = getConsolePageSize();
  const filtered = getFilteredLogs();
  const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));

  if (appState.consoleLiveFollow) {
    appState.consolePage = totalPages;
    appState.unreadNewLogsCount = 0;
    if (btnJumpLatestLogs) btnJumpLatestLogs.classList.add("hidden");
    renderConsoleLogs();
  } else {
    // User is browsing an earlier page, increment unread logs counter without jumping view
    appState.unreadNewLogsCount = (appState.unreadNewLogsCount || 0) + 1;
    if (btnJumpLatestLogs) {
      btnJumpLatestLogs.classList.remove("hidden");
      btnJumpLatestLogs.textContent = `⬇ +${appState.unreadNewLogsCount} new logs (Jump to latest)`;
    }
    updateConsolePaginationUI(filtered.length, totalPages);
  }
}

async function checkServerHealth() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      serverStatus.className = "status-indicator online";
      serverStatus.querySelector(".status-text").textContent = "Server Online";

      const status = await res.json();
      applyStatusUpdate(status);

      // If server is actively executing or paused at Step 7, restore polling and timers
      if (status.state === "running" || status.state === "awaiting_manual_file") {
        appState.isRunning = true;
        btnRun.disabled = true;
        btnStop.disabled = false;
        btnStop.classList.remove("hidden");
        if (!appState.startTime) startTimer();
        startPolling();
      }
    }
  } catch (e) {
    serverStatus.className = "status-indicator";
    serverStatus.style.background = "rgba(239, 68, 68, 0.1)";
    serverStatus.style.color = "#f87171";
    serverStatus.querySelector(".status-dot").style.background = "#ef4444";
    serverStatus.querySelector(".status-text").textContent = "Server Offline";
  }
}

// Manually trigger final_code.py database upload pipeline
async function launchUploadPipeline() {
  logToConsole("[Upload] Requesting launch of final_code.py in interactive console...", "info");
  try {
    const res = await fetch("/api/launch-upload", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      const pathInfo = data.path ? ` (${data.path})` : "";
      logToConsole(`[Upload] 🚀 final_code.py launched successfully in terminal window!${pathInfo}`, "success");
      alert(`🚀 Database Upload Pipeline (final_code.py) has been launched in an interactive terminal window!\n\nPath: ${data.path || "final_code.py"}`);
    } else {
      throw new Error(data.error || "Failed to launch upload pipeline.");
    }
  } catch (err) {
    logToConsole(`[Upload Error] ${err.message}`, "error");
    alert(`Could not launch final_code.py: ${err.message}`);
  }
}

// =========================================================
// GOOGLE DRIVE LOCATION & EMAIL SHARING HANDLERS
// =========================================================
async function loadInputDriveLocations(cityId) {
  if (!driveInputLocationSelect) return;
  const currentCityId = cityId || (cityIdInput ? cityIdInput.value : "9");
  driveInputLocationSelect.disabled = true;
  driveInputLocationSelect.innerHTML = '<option value="" disabled selected>Scanning Google Drive folders...</option>';
  try {
    const res = await fetch(`/api/drive/input-locations?city_id=${encodeURIComponent(currentCityId)}`);
    if (!res.ok) throw new Error("Failed to fetch Drive input locations");
    const data = await res.json();
    const locations = data.locations || [];
    const cityName = data.city || "Selected City";

    // Dynamically update external Drive link
    const driveExtLink = document.querySelector(".drive-external-link");
    if (driveExtLink) {
      if (data.drive_url) {
        driveExtLink.href = data.drive_url;
        driveExtLink.style.display = "inline-flex";
        driveExtLink.textContent = `🌐 Open ${cityName} Drive Folder ↗`;
      } else {
        driveExtLink.style.display = "none";
      }
    }

    driveInputLocationSelect.innerHTML = "";
    if (locations.length === 0) {
      driveInputLocationSelect.innerHTML = `<option value="" disabled selected>⚠️ No Drive folders found for ${cityName}. Enter path manually.</option>`;
      return;
    }

    const defaultOpt = document.createElement("option");
    defaultOpt.value = "";
    defaultOpt.textContent = `-- Select Location from ${cityName} Drive (${locations.length} available) --`;
    driveInputLocationSelect.appendChild(defaultOpt);

    let firstValidFile = null;
    let firstLocation = null;

    locations.forEach(loc => {
      loc.files.forEach(f => {
        const opt = document.createElement("option");
        opt.value = f.path;
        opt.dataset.location = loc.location;
        opt.textContent = `📍 ${loc.location} / ${f.name}`;
        driveInputLocationSelect.appendChild(opt);
        if (!firstValidFile) {
          firstValidFile = f.path;
          firstLocation = loc.location;
        }
      });
    });

    // Auto-select first found location from Google Drive
    if (firstValidFile) {
      driveInputLocationSelect.value = firstValidFile;
      inputFilePath.value = firstValidFile;
      appState.selectedLocation = firstLocation;
      logToConsole(`[Drive] Connected to ${cityName} Drive location: ${firstLocation} (${firstValidFile})`, "info");
    }
  } catch (err) {
    console.error("Error loading input drive locations:", err);
    driveInputLocationSelect.innerHTML = '<option value="" disabled selected>⚠️ Error scanning Google Drive. Enter path manually.</option>';
  } finally {
    driveInputLocationSelect.disabled = false;
  }
}

async function loadManualDriveLocations(cityId) {
  const selects = [driveManualLocationSelect, pauseLocationSelect].filter(Boolean);
  selects.forEach(s => {
    s.disabled = true;
  });

  const chipContainers = [
    document.getElementById("pause-location-chips"),
    document.getElementById("mode2-location-chips")
  ].filter(Boolean);
  chipContainers.forEach(c => { c.innerHTML = ""; });

  const currentCityId = cityId || (cityIdInput ? cityIdInput.value : "9");

  try {
    const res = await fetch(`/api/drive/manual-locations?city_id=${encodeURIComponent(currentCityId)}`);
    if (!res.ok) throw new Error("Failed to fetch Drive manual locations");
    const data = await res.json();
    const locations = data.locations || [];

    selects.forEach(select => {
      const isPauseSelect = (select === pauseLocationSelect);
      select.innerHTML = "";

      const currentPath = isPauseSelect
        ? (resumeFilePath.value || (pauseV1Path ? pauseV1Path.textContent : ""))
        : manualFilePath.value;

      if (locations.length === 0) {
        const noOpt = document.createElement("option");
        noOpt.value = isPauseSelect ? (currentPath || "") : "";
        const fallbackName = currentPath ? currentPath.split(/[\\/]/).pop() : "Step 6 generated file";
        noOpt.textContent = isPauseSelect
          ? `📍 [CURRENT] ${fallbackName} (Step 6 Default)`
          : "⚠️ No location folders found in 3. Manually Corrected";
        select.appendChild(noOpt);
        return;
      }

      let matchedSelection = false;

      appState.scannedLocationsData = locations;

      locations.forEach(loc => {
        loc.files.forEach(f => {
          const opt = document.createElement("option");
          opt.value = f.path;
          opt.dataset.location = loc.location;
          opt.dataset.name = f.name;
          if (loc.drive_url) {
            opt.dataset.driveUrl = loc.drive_url;
          } else if (loc.location && loc.location.toLowerCase() === "bandra") {
            opt.dataset.driveUrl = "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link";
          }
          const isMatch = currentPath && (
            currentPath.toLowerCase() === f.path.toLowerCase() ||
            currentPath.toLowerCase().endsWith(f.name.toLowerCase())
          );
          if (isMatch) {
            matchedSelection = true;
            opt.selected = true;
            opt.textContent = `📍 [SELECTED] ${loc.location} / ${f.name}`;
          } else {
            opt.textContent = `📍 ${loc.location} / ${f.name}`;
          }
          select.appendChild(opt);
        });
      });

      // If current default wasn't in scanned list
      if (isPauseSelect && !matchedSelection && currentPath) {
        const defaultOpt = document.createElement("option");
        defaultOpt.value = currentPath;
        defaultOpt.selected = true;
        const fileName = currentPath.split(/[\\/]/).pop();
        defaultOpt.textContent = `📍 [SELECTED] ${fileName} (Step 6 Default)`;
        select.insertBefore(defaultOpt, select.firstChild);
      }
    });

    // Populate interactive location folder chips for both Step 7 pause card and Mode 2 container
    locations.forEach(loc => {
      chipContainers.forEach(container => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "loc-folder-chip";
        chip.dataset.loc = loc.location;
        const firstFile = loc.files[0];
        const allInLocSelected = loc.files.length > 0 && loc.files.every(f => 
          appState.step7SelectedFiles.some(sf => sf.path.toLowerCase() === f.path.toLowerCase())
        );
        if (allInLocSelected) chip.classList.add("active");

        chip.innerHTML = `📂 <strong>${loc.location}</strong> <span class="chip-count">(${loc.files.length} file${loc.files.length > 1 ? 's' : ''})</span>`;
        chip.title = `Click to toggle ${loc.location} folder files for merge`;

        chip.addEventListener("click", () => {
          const currentlyAllSelected = loc.files.length > 0 && loc.files.every(f => 
            appState.step7SelectedFiles.some(sf => sf.path.toLowerCase() === f.path.toLowerCase())
          );

          if (currentlyAllSelected) {
            loc.files.forEach(f => removeStep7File(f.path));
            document.querySelectorAll(`.loc-folder-chip[data-loc="${loc.location}"]`).forEach(c => c.classList.remove("active"));
            logToConsole(`[Manual Merge] Deselected location folder '${loc.location}'`, "info");
          } else {
            loc.files.forEach(f => addStep7File(f.path, f.name, loc.location));
            document.querySelectorAll(`.loc-folder-chip[data-loc="${loc.location}"]`).forEach(c => c.classList.add("active"));
            logToConsole(`[Manual Merge] Added ${loc.files.length} file(s) from '${loc.location}' for merge`, "info");
          }

          if (firstFile) {
            if (pauseLocationSelect) pauseLocationSelect.value = firstFile.path;
            if (driveManualLocationSelect) driveManualLocationSelect.value = firstFile.path;
            appState.selectedLocation = loc.location;
            const pauseDriveLink = document.getElementById("pause-drive-link") || document.querySelector(".pause-desc .drive-external-link");
            if (pauseDriveLink) {
              const targetDriveUrl = loc.drive_url || (loc.location.toLowerCase() === "bandra" ? "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link" : (data.drive_url || ""));
              if (targetDriveUrl) {
                pauseDriveLink.href = targetDriveUrl;
                pauseDriveLink.textContent = `🌐 Open ${loc.location} Drive Folder ↗`;
              }
            }
          }
        });
        container.appendChild(chip);
      });
    });
  } catch (err) {
    console.error("Error loading manual drive locations:", err);
  } finally {
    selects.forEach(s => { s.disabled = false; });
  }
}

async function handleShareEmail() {
  const targetFile = resumeFilePath.value.trim() || (pauseV1Path ? pauseV1Path.textContent.trim() : "");
  const recipient = shareEmailRecipients.value.trim();
  const deadline = shareEmailDeadline ? shareEmailDeadline.value.trim() : "";
  const ccVal = shareEmailCc ? shareEmailCc.value.trim() : "";
  const ccList = ccVal ? ccVal.split(",").map(c => c.trim()).filter(Boolean) : [];

  if (!recipient) {
    alert("Please enter a recipient email address.");
    return;
  }
  if (!targetFile) {
    alert("No manual correction file available to share.");
    return;
  }

  btnSendShareEmail.disabled = true;
  btnSendShareEmail.innerHTML = '<span class="btn-icon">⏳</span> <span class="btn-text">Sending...</span>';
  shareStatusMsg.className = "share-status-msg info";
  shareStatusMsg.textContent = "Connecting to mail server & uploading attachment (timeout: 300s)...";
  shareStatusMsg.classList.remove("hidden");

  const selectedLoc = appState.selectedLocation || (pauseLocationSelect?.selectedOptions[0]?.dataset.location) || "";
  let locDriveUrl = null;
  if (selectedLoc.toLowerCase() === "bandra" || targetFile.toLowerCase().includes("bandra")) {
    locDriveUrl = "https://drive.google.com/drive/folders/1wsvFldaqifK_yoyifZqqFpL8MsZKJZUq?usp=drive_link";
  } else if (pauseLocationSelect?.selectedOptions[0]?.dataset.driveUrl) {
    locDriveUrl = pauseLocationSelect.selectedOptions[0].dataset.driveUrl;
  }
  const effectiveLocation = selectedLoc || (targetFile.toLowerCase().includes("bandra") ? "Bandra" : (targetFile.toLowerCase().includes("borivali") ? "Borivali" : ""));

  try {
    const res = await fetch("/api/share-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: targetFile,
        recipients: [recipient],
        cc_emails: ccList,
        location_name: effectiveLocation,
        deadline: deadline,
        city_id: parseInt(cityIdInput?.value, 10) || 8,
        drive_url: locDriveUrl
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || "Failed to send email.");

    const deadlineInfo = result.deadline_formatted ? ` [⏰ Deadline: ${result.deadline_formatted}]` : (deadline ? ` [⏰ Deadline: ${deadline}]` : "");
    const actualCc = result.cc && result.cc.length > 0 ? ` (CC: ${result.cc.join(", ")})` : (ccList.length > 0 ? ` (CC: ${ccList.join(", ")})` : "");

    if (result.mode === "attachment") {
      shareStatusMsg.className = "share-status-msg success";
      shareStatusMsg.textContent = `✓ Email sent successfully with file attached to ${recipient}${actualCc}!${deadlineInfo}`;
      logToConsole(`[Email Share] ✓ Sent manual file with attachment to ${recipient}${actualCc}${deadlineInfo}`, "success");
    } else {
      shareStatusMsg.className = "share-status-msg warning";
      shareStatusMsg.textContent = `✓ Drive link notification sent to ${recipient}${actualCc} (fallback link mode).${deadlineInfo}`;
      logToConsole(`[Email Share] Sent Drive link notification to ${recipient}${actualCc}${deadlineInfo}`, "info");
    }
  } catch (err) {
    shareStatusMsg.className = "share-status-msg error";
    shareStatusMsg.textContent = `✕ Failed to send: ${err.message}`;
    logToConsole(`[Email Share Error] ${err.message}`, "error");
  } finally {
    btnSendShareEmail.disabled = false;
    btnSendShareEmail.innerHTML = '<span class="btn-icon">📤</span> <span class="btn-text">Send Email</span>';
  }
}



async function loadFinalDriveLocations(cityId) {
  const selects = [driveFinalLocationSelect, parquetVerifyLocationSelect].filter(Boolean);
  if (selects.length === 0) return;
  selects.forEach(s => {
    s.disabled = true;
    s.innerHTML = '<option value="" disabled selected>Scanning Google Drive folders...</option>';
  });

  const currentCityId = cityId || (cityIdInput ? cityIdInput.value : "9");

  try {
    const res = await fetch(`/api/drive/final-locations?city_id=${encodeURIComponent(currentCityId)}`);
    if (!res.ok) throw new Error("Failed to fetch Drive final locations");
    const data = await res.json();
    const locations = data.locations || [];
    const cityName = data.city || "Selected City";

    const verifyDriveLink = document.getElementById("parquet-verify-drive-link");
    if (verifyDriveLink && data.drive_url) {
      verifyDriveLink.href = data.drive_url;
      verifyDriveLink.textContent = `🌐 Open ${cityName} (4. Final processed file) ↗`;
    }

    selects.forEach(select => {
      const isVerifySelect = (select === parquetVerifyLocationSelect);
      select.innerHTML = "";
      const currentPath = isVerifySelect
        ? (parquetConfirmFilePath ? parquetConfirmFilePath.value : "")
        : (finalFilePath ? finalFilePath.value : "");

      if (locations.length === 0) {
        select.innerHTML = `<option value="" disabled selected>⚠️ No locations found in ${cityName} (4. Final processed file)</option>`;
        return;
      }

      const defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = `-- Select Location from ${cityName} (4. Final processed file, ${locations.length} available) --`;
      select.appendChild(defaultOpt);

      locations.forEach(loc => {
        loc.files.forEach(f => {
          const opt = document.createElement("option");
          opt.value = f.path;
          opt.dataset.location = loc.location;
          const isMatch = currentPath && (
            currentPath.toLowerCase() === f.path.toLowerCase() ||
            currentPath.toLowerCase().endsWith(f.name.toLowerCase())
          );
          if (isMatch) {
            opt.selected = true;
            opt.textContent = `📍 [SELECTED] ${loc.location} / ${f.name}`;
          } else {
            opt.textContent = `📍 ${loc.location} / ${f.name}`;
          }
          select.appendChild(opt);
        });
      });
    });

    if (driveFinalLocationSelect && locations.length > 0 && (!finalFilePath || !finalFilePath.value || !finalFilePath.value.includes(".shortcut-targets-by-id"))) {
      const firstLoc = locations[0];
      if (firstLoc && firstLoc.files && firstLoc.files[0]) {
        driveFinalLocationSelect.value = firstLoc.files[0].path;
        if (finalFilePath) finalFilePath.value = firstLoc.files[0].path;
        appState.selectedLocation = firstLoc.location;
      }
    }
  } catch (err) {
    console.error("Error loading final drive locations:", err);
    selects.forEach(s => {
      s.innerHTML = '<option value="" disabled selected>⚠️ Error scanning Google Drive. Enter path manually.</option>';
    });
  } finally {
    selects.forEach(s => { s.disabled = false; });
  }
}

// =========================================================
// OUTLIER LOCATIONS & MANUAL TRIGGER
// =========================================================
async function loadOutlierLocations(cityId) {
  const currentCityId = cityId || (cityIdInput ? cityIdInput.value : "9");
  const cityName = cityIdInput?.selectedOptions[0]?.text.split(" (")[0] || "City";
  if (outlierCityBadgeText) outlierCityBadgeText.textContent = `City: ${cityName}`;

  if (outlierLocationSelect) {
    outlierLocationSelect.disabled = true;
    outlierLocationSelect.innerHTML = '<option value="" selected>Scanning locations...</option>';
  }
  if (outlierChipsRow) {
    outlierChipsRow.innerHTML = '<span style="font-size: 0.76rem; color: #94a3b8;">Scanning locations...</span>';
  }

  let locList = [];

  try {
    const res = await fetch(`/api/outlier/locations?city_id=${encodeURIComponent(currentCityId)}`);
    if (res.ok) {
      const data = await res.json();
      locList = data.locations || [];
    }
  } catch (e) {
    // ignore
  }

  // Fallback: If locList is empty, fetch from final & input drive endpoints
  if (locList.length === 0) {
    try {
      const [finalRes, inputRes] = await Promise.all([
        fetch(`/api/drive/final-locations?city_id=${encodeURIComponent(currentCityId)}`),
        fetch(`/api/drive/input-locations?city_id=${encodeURIComponent(currentCityId)}`)
      ]);
      const set = new Set();
      if (finalRes.ok) {
        const d = await finalRes.json();
        (d.locations || []).forEach(l => { if (l.location) set.add(l.location.trim()); });
      }
      if (inputRes.ok) {
        const d = await inputRes.json();
        (d.locations || []).forEach(l => { if (l.location) set.add(l.location.trim()); });
      }
      locList = Array.from(set).sort((a, b) => a.localeCompare(b));
    } catch (e) {
      console.error("Fallback locations error:", e);
    }
  }

  // If Drive scan returned empty, provide known Drive location folders for the city
  if (locList.length === 0) {
    if (String(currentCityId) === "8") {
      locList = ["Andheri", "Bandra", "Borivali"];
    } else if (String(currentCityId) === "9") {
      locList = ["Chikhali", "Mohmadwadi", "Sogaon"];
    }
  }

  // Populate Select
  if (outlierLocationSelect) {
    outlierLocationSelect.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = `🌐 ALL Locations (${cityName} - Whole City)`;
    allOpt.selected = true;
    outlierLocationSelect.appendChild(allOpt);

    locList.forEach(loc => {
      const opt = document.createElement("option");
      opt.value = loc;
      opt.textContent = `📍 ${loc}`;
      outlierLocationSelect.appendChild(opt);
    });
    outlierLocationSelect.disabled = false;
  }

  // Populate Chips
  if (outlierChipsRow) {
    outlierChipsRow.innerHTML = "";
    const allChip = document.createElement("button");
    allChip.type = "button";
    allChip.className = "outlier-chip chip-all active";
    allChip.innerHTML = `🌐 <strong>ALL Locations</strong>`;
    allChip.addEventListener("click", () => {
      if (mode5AllLocations) mode5AllLocations.checked = true;
      if (mode5LocationInput) {
        mode5LocationInput.value = "";
        mode5LocationInput.disabled = true;
      }
      if (outlierLocationSelect) outlierLocationSelect.value = "";
      document.querySelectorAll(".outlier-chip").forEach(c => c.classList.remove("active"));
      allChip.classList.add("active");
    });
    outlierChipsRow.appendChild(allChip);

    locList.forEach(loc => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "outlier-chip";
      chip.dataset.loc = loc;
      chip.innerHTML = `📍 ${loc}`;
      chip.addEventListener("click", () => {
        // Toggle this chip
        const willBeActive = !chip.classList.contains("active");
        chip.classList.toggle("active", willBeActive);

        // Deselect ALL chip
        allChip.classList.remove("active");

        // Gather all currently active location chips
        const activeLocChips = Array.from(document.querySelectorAll(".outlier-chip.active:not(.chip-all)"));
        const activeLocNames = activeLocChips.map(c => c.dataset.loc).filter(Boolean);

        if (activeLocNames.length === 0) {
          // No location selected, revert to ALL
          allChip.classList.add("active");
          if (mode5AllLocations) mode5AllLocations.checked = true;
          if (mode5LocationInput) {
            mode5LocationInput.value = "";
            mode5LocationInput.disabled = true;
          }
          if (outlierLocationSelect) outlierLocationSelect.value = "";
        } else {
          if (mode5AllLocations) mode5AllLocations.checked = false;
          if (mode5LocationInput) {
            mode5LocationInput.disabled = false;
            mode5LocationInput.value = activeLocNames.join(", ");
          }
          if (outlierLocationSelect) {
            outlierLocationSelect.value = (activeLocNames.length === 1 ? activeLocNames[0] : "");
          }
        }
      });
      outlierChipsRow.appendChild(chip);
    });

    if (locList.length === 0) {
      const note = document.createElement("span");
      note.style.fontSize = "0.76rem";
      note.style.color = "#94a3b8";
      note.textContent = "No saved locations found. Enter location(s) manually below.";
      outlierChipsRow.appendChild(note);
    }
  }
}

async function runOutlierDetection() {
  const currentCityId = parseInt(cityIdInput ? cityIdInput.value : "9", 10) || 9;
  const cityName = cityIdInput?.selectedOptions[0]?.text.split(" (")[0] || "City";
  const isAll = mode5AllLocations ? mode5AllLocations.checked : true;
  const chosenLoc = isAll ? null : ((mode5LocationInput ? mode5LocationInput.value.trim() : "") || (outlierLocationSelect ? outlierLocationSelect.value.trim() : ""));
  const saveReport = saveOutlierReportCb ? saveOutlierReportCb.checked : false;

  const scopeMsg = chosenLoc ? `location(s) '${chosenLoc}'` : `ALL locations in ${cityName}`;
  if (!confirm(`Run Outlier Detection for ${scopeMsg} (City ID: ${currentCityId})?`)) return;

  logToConsole(`[Outlier] Requesting Outlier Detection for ${scopeMsg}...`, "info");

  try {
    const res = await fetch("/api/run-outlier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        city_id: currentCityId,
        location_name: chosenLoc,
        save_outlier_report: saveReport,
        database: getSelectedDb()
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to start outlier detection.");

    appState.isRunning = true;
    btnRun.disabled = true;
    btnStop.disabled = false;
    btnStop.classList.remove("hidden");
    startTimer();
    startPolling();
    logToConsole(`[Outlier] 🚀 Worker started for ${scopeMsg}!`, "success");
  } catch (err) {
    logToConsole(`[Outlier Error] ${err.message}`, "error");
    alert(`Could not run outlier detection: ${err.message}`);
  }
}

function renderStep7SelectedFilesList() {
  const files = appState.step7SelectedFiles || [];
  const count = files.length;

  if (step7FilesCountBadge) {
    step7FilesCountBadge.textContent = `${count} File${count !== 1 ? 's' : ''}`;
  }
  if (mode2FilesCountBadge) {
    mode2FilesCountBadge.textContent = `${count} File${count !== 1 ? 's' : ''}`;
  }

  const emptyHtml = `<span style="font-size: 0.78rem; color: #64748b; font-style: italic;">No files selected. Click location chips or select options above to add files for merge.</span>`;

  if (count === 0) {
    if (step7SelectedFilesList) step7SelectedFilesList.innerHTML = emptyHtml;
    if (mode2SelectedFilesList) mode2SelectedFilesList.innerHTML = emptyHtml;
    if (resumeFilePath) resumeFilePath.value = "";
    if (manualFilePath) manualFilePath.value = "";
    return;
  }

  const tagsHtml = files.map(f => `
    <span class="file-pill-tag" style="display: inline-flex; align-items: center; gap: 6px; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(251, 191, 36, 0.4); color: #f8fafc; padding: 4px 10px; border-radius: 9999px; font-size: 0.78rem;" title="${f.path}">
      <span>📄 <strong>${f.location ? f.location + ' / ' : ''}</strong>${f.name}</span>
      <button type="button" class="btn-remove-file" data-path="${encodeURIComponent(f.path)}" style="background: none; border: none; color: #f87171; font-weight: bold; cursor: pointer; font-size: 0.82rem; padding: 0 2px;">✕</button>
    </span>
  `).join("");

  [step7SelectedFilesList, mode2SelectedFilesList].forEach(listEl => {
    if (!listEl) return;
    listEl.innerHTML = tagsHtml;
    listEl.querySelectorAll(".btn-remove-file").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const pathToRemove = decodeURIComponent(btn.dataset.path);
        removeStep7File(pathToRemove);
      });
    });
  });

  const pathsStr = files.map(f => f.path).join(", ");
  if (resumeFilePath) resumeFilePath.value = pathsStr;
  if (manualFilePath) manualFilePath.value = pathsStr;
}

function addStep7File(path, name, location) {
  if (!path) return;
  const cleanPath = path.trim();
  const fileName = name || cleanPath.split(/[\\/]/).pop();

  if (!appState.step7SelectedFiles.some(f => f.path.toLowerCase() === cleanPath.toLowerCase())) {
    appState.step7SelectedFiles.push({
      path: cleanPath,
      name: fileName,
      location: location || ""
    });
    renderStep7SelectedFilesList();
  }
}

function removeStep7File(path) {
  appState.step7SelectedFiles = (appState.step7SelectedFiles || []).filter(f => f.path.toLowerCase() !== path.toLowerCase());
  renderStep7SelectedFilesList();
}

function clearStep7Files() {
  appState.step7SelectedFiles = [];
  renderStep7SelectedFilesList();
}

function renderStep7MergeReport(report) {
  if (!step7MergeReportCard || !report) return;

  step7MergeReportCard.classList.remove("hidden");

  if (step7MergeStatusBadge) {
    if (report.status_type === "PERFECT_MATCH") {
      step7MergeStatusBadge.style.background = "rgba(16, 185, 129, 0.2)";
      step7MergeStatusBadge.style.color = "#34d399";
      step7MergeStatusBadge.style.border = "1px solid rgba(16, 185, 129, 0.4)";
      step7MergeStatusBadge.innerHTML = `✓ Column Match (${report.total_unique_columns} cols)`;
    } else if (report.status_type === "COLUMN_MISMATCH") {
      step7MergeStatusBadge.style.background = "rgba(245, 158, 11, 0.2)";
      step7MergeStatusBadge.style.color = "#fbbf24";
      step7MergeStatusBadge.style.border = "1px solid rgba(245, 158, 11, 0.4)";
      step7MergeStatusBadge.innerHTML = `⚠️ Missing Columns Detected`;
    } else {
      step7MergeStatusBadge.style.background = "rgba(56, 189, 248, 0.2)";
      step7MergeStatusBadge.style.color = "#38bdf8";
      step7MergeStatusBadge.style.border = "1px solid rgba(56, 189, 248, 0.4)";
      step7MergeStatusBadge.innerHTML = `✓ Single File (${report.total_unique_columns} cols)`;
    }
  }

  if (step7MergeStatusMessage) {
    step7MergeStatusMessage.textContent = report.status_message || "";
  }

  if (step7MergeReportTbody && Array.isArray(report.files)) {
    step7MergeReportTbody.innerHTML = report.files.map(f => {
      let missingHtml = "";
      if (f.missing_count > 0 && Array.isArray(f.missing_columns)) {
        const pills = f.missing_columns.map(col => 
          `<span style="display: inline-block; background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 1px 6px; border-radius: 4px; font-size: 0.72rem; font-family: var(--font-mono); margin: 2px;">${col}</span>`
        ).join("");
        missingHtml = `<div style="display: flex; flex-wrap: wrap; gap: 2px; align-items: center;">${pills}</div>`;
      } else {
        missingHtml = `<span style="color: #34d399; font-weight: 500;">✓ All columns present</span>`;
      }

      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 6px 8px; font-weight: 600; color: #94a3b8;">${f.index}</td>
          <td style="padding: 6px 8px; font-weight: 600; color: #f8fafc;" title="${f.path}">${f.filename}</td>
          <td style="padding: 6px 8px; color: #cbd5e1;">${(f.row_count || 0).toLocaleString()}</td>
          <td style="padding: 6px 8px; font-weight: 600; color: #38bdf8;">${f.column_count}</td>
          <td style="padding: 6px 8px;">${missingHtml}</td>
        </tr>
      `;
    }).join("");
  }
}

// Global functions exposed for HTML inline onclick handlers
window.launchUploadPipeline = launchUploadPipeline;
window.runOutlierDetection = runOutlierDetection;
window.loadOutlierLocations = loadOutlierLocations;
window.setMode = setMode;
window.switchDashboardTab = switchDashboardTab;
window.setLayoutMode = setLayoutMode;

function mirrorStep7MergeReportToTab4(report) {
  const container = document.getElementById("step7-report-pane-container");
  if (!container || !report) return;

  let badgeColor = "#38bdf8";
  let badgeBg = "rgba(56, 189, 248, 0.2)";
  let badgeBorder = "rgba(56, 189, 248, 0.4)";
  let badgeText = `Single File (${report.total_unique_columns || 0} cols)`;

  if (report.status_type === "PERFECT_MATCH") {
    badgeColor = "#34d399";
    badgeBg = "rgba(16, 185, 129, 0.2)";
    badgeBorder = "rgba(16, 185, 129, 0.4)";
    badgeText = `✓ Perfect Column Match (${report.total_unique_columns || 0} cols)`;
  } else if (report.status_type === "COLUMN_MISMATCH") {
    badgeColor = "#fbbf24";
    badgeBg = "rgba(245, 158, 11, 0.2)";
    badgeBorder = "rgba(245, 158, 11, 0.4)";
    badgeText = `⚠️ Column Differences Detected`;
  }

  let rowsHtml = "";
  if (Array.isArray(report.files)) {
    rowsHtml = report.files.map(f => {
      let missingHtml = "";
      if (f.missing_count > 0 && Array.isArray(f.missing_columns)) {
        const pills = f.missing_columns.map(col =>
          `<span style="display: inline-block; background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 1px 6px; border-radius: 4px; font-size: 0.72rem; font-family: var(--font-mono); margin: 2px;">${col}</span>`
        ).join("");
        missingHtml = `<div style="display: flex; flex-wrap: wrap; gap: 2px; align-items: center;">${pills}</div>`;
      } else {
        missingHtml = `<span style="color: #34d399; font-weight: 500;">✓ All columns match</span>`;
      }

      return `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 8px 10px; font-weight: 600; color: #94a3b8;">${f.index}</td>
          <td style="padding: 8px 10px; font-weight: 600; color: #f8fafc;" title="${f.path}">${f.filename}</td>
          <td style="padding: 8px 10px; color: #cbd5e1;">${(f.row_count || 0).toLocaleString()}</td>
          <td style="padding: 8px 10px; font-weight: 600; color: #38bdf8;">${f.column_count}</td>
          <td style="padding: 8px 10px;">${missingHtml}</td>
        </tr>
      `;
    }).join("");
  }

  container.innerHTML = `
    <div style="padding: 16px; background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: var(--radius-sm);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px;">
        <span style="font-weight: 600; font-size: 0.92rem; color: #38bdf8; display: flex; align-items: center; gap: 6px;">
          📊 Step 7 Multi-File Merge Verification
        </span>
        <span style="font-size: 0.78rem; font-weight: 600; padding: 4px 10px; border-radius: 9999px; background: ${badgeBg}; color: ${badgeColor}; border: 1px solid ${badgeBorder};">
          ${badgeText}
        </span>
      </div>
      <div style="font-size: 0.82rem; color: #cbd5e1; margin-bottom: 12px; line-height: 1.4;">
        ${report.status_message || ""}
      </div>
      <div style="overflow-x: auto;">
        <table class="report-table" style="width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: left;">
          <thead>
            <tr style="background: rgba(15, 23, 42, 0.8); color: #94a3b8; border-bottom: 1px solid #334155;">
              <th style="padding: 8px 10px;">#</th>
              <th style="padding: 8px 10px;">File Name</th>
              <th style="padding: 8px 10px;">Rows</th>
              <th style="padding: 8px 10px;">Columns</th>
              <th style="padding: 8px 10px;">Missing Columns vs Master Union</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function initNavTabs() {
  const tabs = [
    { btn: tabBtnConfig, id: "config" },
    { btn: tabBtnProgress, id: "progress" },
    { btn: tabBtnConsole, id: "console" },
    { btn: tabBtnReports, id: "reports" }
  ];

  tabs.forEach(t => {
    if (t.btn) {
      t.btn.addEventListener("click", () => {
        switchDashboardTab(t.id);
      });
    }
  });

  // Footer navigation buttons across all panes
  document.querySelectorAll(".btn-nav-pane").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.target || btn.dataset.goto;
      if (target) {
        switchDashboardTab(target);
      }
    });
  });

  // Restore saved active tab from sessionStorage if available
  const savedTab = sessionStorage.getItem("igr_active_tab");
  if (savedTab && ["config", "progress", "console", "reports"].includes(savedTab)) {
    switchDashboardTab(savedTab, false);
  } else {
    switchDashboardTab("config", false);
  }
}

function switchDashboardTab(tabId, scroll = true) {
  appState.activeTab = tabId;
  sessionStorage.setItem("igr_active_tab", tabId);

  const tabBtns = [
    { btn: tabBtnConfig, id: "config" },
    { btn: tabBtnProgress, id: "progress" },
    { btn: tabBtnConsole, id: "console" },
    { btn: tabBtnReports, id: "reports" }
  ];

  tabBtns.forEach(t => {
    if (t.btn) {
      if (t.id === tabId) {
        t.btn.classList.add("active");
        t.btn.setAttribute("aria-selected", "true");
      } else {
        t.btn.classList.remove("active");
        t.btn.setAttribute("aria-selected", "false");
      }
    }
  });

  const panes = [
    { pane: paneConfig, id: "config" },
    { pane: paneProgress, id: "progress" },
    { pane: paneConsole, id: "console" },
    { pane: paneReports, id: "reports" }
  ];

  panes.forEach(p => {
    if (p.pane) {
      if (p.id === tabId) {
        p.pane.classList.add("active");
      } else {
        p.pane.classList.remove("active");
      }
    }
  });

  if (appState.layoutMode === "scroll") {
    const targetPane = document.getElementById(`pane-${tabId}`);
    if (targetPane) {
      targetPane.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } else if (scroll) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (tabId === "console") {
    renderConsoleLogs();
  }
}

function initLayoutMode() {
  const savedMode = localStorage.getItem("igr_layout_mode") || "tabbed";
  setLayoutMode(savedMode);

  if (btnModeTabbed) {
    btnModeTabbed.addEventListener("click", () => setLayoutMode("tabbed"));
  }
  if (btnModeScroll) {
    btnModeScroll.addEventListener("click", () => setLayoutMode("scroll"));
  }
}

function setLayoutMode(mode) {
  appState.layoutMode = mode;
  localStorage.setItem("igr_layout_mode", mode);

  if (mode === "scroll") {
    document.body.classList.remove("layout-tabbed");
    document.body.classList.add("layout-scroll");
    if (btnModeScroll) btnModeScroll.classList.add("active");
    if (btnModeTabbed) btnModeTabbed.classList.remove("active");
  } else {
    document.body.classList.remove("layout-scroll");
    document.body.classList.add("layout-tabbed");
    if (btnModeTabbed) btnModeTabbed.classList.add("active");
    if (btnModeScroll) btnModeScroll.classList.remove("active");
  }
}

function initConsoleControls() {
  if (consoleSearchInput) {
    consoleSearchInput.addEventListener("input", (e) => {
      appState.consoleSearchQuery = e.target.value.trim();
      appState.consolePage = 1;
      if (btnClearSearch) {
        btnClearSearch.style.display = e.target.value ? "inline" : "none";
      }
      renderConsoleLogs();
    });
  }

  if (btnClearSearch) {
    btnClearSearch.addEventListener("click", () => {
      if (consoleSearchInput) consoleSearchInput.value = "";
      appState.consoleSearchQuery = "";
      appState.consolePage = 1;
      btnClearSearch.style.display = "none";
      renderConsoleLogs();
    });
  }

  document.querySelectorAll(".log-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".log-filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      appState.consoleFilterLevel = btn.dataset.level || "all";
      appState.consolePage = 1;
      renderConsoleLogs();
    });
  });

  if (logPageSizeSelect) {
    logPageSizeSelect.addEventListener("change", (e) => {
      appState.consolePageSize = e.target.value;
      appState.consolePage = 1;
      renderConsoleLogs();
    });
  }

  if (logPageFirst) {
    logPageFirst.addEventListener("click", () => {
      appState.consolePage = 1;
      appState.consoleLiveFollow = false;
      if (liveFollowCb) liveFollowCb.checked = false;
      renderConsoleLogs();
    });
  }

  if (logPagePrev) {
    logPagePrev.addEventListener("click", () => {
      const curPage = appState.consolePage || 1;
      if (curPage > 1) {
        appState.consolePage = curPage - 1;
        appState.consoleLiveFollow = false;
        if (liveFollowCb) liveFollowCb.checked = false;
        renderConsoleLogs();
      }
    });
  }

  if (logPageNext) {
    logPageNext.addEventListener("click", () => {
      const filtered = getFilteredLogs();
      const pageSize = getConsolePageSize();
      const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));
      const curPage = appState.consolePage || 1;
      if (curPage < totalPages) {
        appState.consolePage = curPage + 1;
        renderConsoleLogs();
      }
    });
  }

  if (logPageLast) {
    logPageLast.addEventListener("click", () => {
      const filtered = getFilteredLogs();
      const pageSize = getConsolePageSize();
      const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));
      appState.consolePage = totalPages;
      renderConsoleLogs();
    });
  }

  if (liveFollowCb) {
    liveFollowCb.addEventListener("change", (e) => {
      appState.consoleLiveFollow = e.target.checked;
      if (e.target.checked) {
        const filtered = getFilteredLogs();
        const pageSize = getConsolePageSize();
        const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));
        appState.consolePage = totalPages;
        appState.unreadNewLogsCount = 0;
        if (btnJumpLatestLogs) btnJumpLatestLogs.classList.add("hidden");
        renderConsoleLogs();
      }
    });
  }

  if (btnJumpLatestLogs) {
    btnJumpLatestLogs.addEventListener("click", () => {
      appState.consoleLiveFollow = true;
      if (liveFollowCb) liveFollowCb.checked = true;
      const filtered = getFilteredLogs();
      const pageSize = getConsolePageSize();
      const totalPages = pageSize === Infinity ? 1 : Math.max(1, Math.ceil(filtered.length / pageSize));
      appState.consolePage = totalPages;
      appState.unreadNewLogsCount = 0;
      btnJumpLatestLogs.classList.add("hidden");
      renderConsoleLogs();
    });
  }

  if (btnExportLogs) {
    btnExportLogs.addEventListener("click", () => {
      exportLogsToFile();
    });
  }

  // Keyboard hotkeys (1-4 for tabs, V for view switcher)
  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) {
      return;
    }
    if (e.key === "1") {
      switchDashboardTab("config");
    } else if (e.key === "2") {
      switchDashboardTab("progress");
    } else if (e.key === "3") {
      switchDashboardTab("console");
    } else if (e.key === "4") {
      switchDashboardTab("reports");
    } else if (e.key === "v" || e.key === "V") {
      setLayoutMode(appState.layoutMode === "tabbed" ? "scroll" : "tabbed");
    }
  });
}

function initStepFilters() {
  document.querySelectorAll(".step-filter-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".step-filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      applyStepFilter(pill.dataset.filter || "all");
    });
  });
}

function applyStepFilter(filter) {
  appState.stepFilter = filter;
  const cards = document.querySelectorAll(".step-card");
  cards.forEach(card => {
    if (filter === "all") {
      card.style.display = "";
    } else if (filter === "running") {
      card.style.display = card.classList.contains("running") ? "" : "none";
    } else if (filter === "completed") {
      card.style.display = card.classList.contains("completed") ? "" : "none";
    } else if (filter === "pending") {
      card.style.display = card.classList.contains("pending") ? "" : "none";
    }
  });
}

function updateStepCounts() {
  const cards = document.querySelectorAll(".step-card");
  let running = 0, completed = 0, pending = 0;

  cards.forEach(c => {
    if (c.classList.contains("running")) running++;
    else if (c.classList.contains("completed")) completed++;
    else if (c.classList.contains("pending")) pending++;
  });

  const total = cards.length;
  if (countStepAll) countStepAll.textContent = total;
  if (countStepRunning) countStepRunning.textContent = running;
  if (countStepCompleted) countStepCompleted.textContent = completed;
  if (countStepPending) countStepPending.textContent = pending;

  // Re-apply current step filter if one is active
  if (appState.stepFilter && appState.stepFilter !== "all") {
    applyStepFilter(appState.stepFilter);
  }
}

