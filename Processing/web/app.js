/**
 * Sogaon Data Processing Pipeline - Web Controller
 * Handles 18-step UI rendering, state management, live polling & console streaming.
 */

// Step Definitions (1 to 20)
const PIPELINE_STEPS = [
  {
    id: 1,
    name: "Input File Ingestion",
    desc: "Loads raw extraction Excel file and validates source tabular structures.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 2,
    name: "DictToColumn Processing",
    desc: "Extracts nested dictionary strings into standardized flat dataframe columns.",
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
    desc: "Maps document names against static result dictionary definitions.",
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
    desc: "Cleans project names & converts area measures -> exports _processed_v1.xlsx.",
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
    name: "Net Carpet Area Calculation",
    desc: "Derives net carpet area from builtup/saleable using city divisor logic.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 9,
    name: "Column Renaming & Standardizing",
    desc: "Normalizes internal column names to DB naming standards (e.g., location_name).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 10,
    name: "Property Type Categorization",
    desc: "Maps raw property types into standard categories (Apartment, Commercial, etc.).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 11,
    name: "Buyer Location & Pincode Lookup",
    desc: "Extracts buyer pincode from buyer_name and enriches locality, district, and state from postal mapping.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 12,
    name: "RERA Grand Reference Matching",
    desc: "Matches project names against city RERA dataset to extract coordinates, BHK, and standard location.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 13,
    name: "PostgreSQL NR Index Assignment",
    desc: "Queries max NR sequence for target city from public.transactions and assigns new nr IDs.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 14,
    name: "Location Coordinates Lookup",
    desc: "Enriches location_latitude & longitude from public.dim_location table.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 15,
    name: "Project Coordinates (Google Places API)",
    desc: "Enriches project coordinates via Google Places API (Temporarily commented out in main.py).",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 16,
    name: "DB Schema Column Alignment",
    desc: "Filters and orders columns strictly to the 66-field DB_SEQUENCE schema.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 17,
    name: "Title Casing",
    desc: "Applies Title Case to all object/string text columns.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 18,
    name: "Final Output Save (Drive & Local)",
    desc: "Saves final 66-column database-ready file directly to Google Drive (4. Final processed file) with local backup.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 19,
    name: "Parquet Conversion",
    desc: "Converts Drive final processed file to Parquet format (converted_feather_parquet) with date normalization.",
    status: "pending",
    detail: "Waiting...",
    duration: "-"
  },
  {
    id: 20,
    name: "Database Upload Pipeline",
    desc: "Launches final_code.py in interactive terminal to verify, backup, and upload parquet records to PostgreSQL.",
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
  logs: []
};

// DOM Elements
const mode1Radio = document.getElementById("mode1-radio");
const mode2Radio = document.getElementById("mode2-radio");
const mode3Radio = document.getElementById("mode3-radio");
const mode1Label = document.getElementById("mode1-label");
const mode2Label = document.getElementById("mode2-label");
const mode3Label = document.getElementById("mode3-label");
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

const progressBar = document.getElementById("progress-bar");
const progressPercent = document.getElementById("progress-percent");
const currentStepText = document.getElementById("current-step-text");
const metricRows = document.getElementById("metric-rows");
const metricRera = document.getElementById("metric-rera");
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
const shareStatusMsg = document.getElementById("share-status-msg");

// Auto-detect city from input path or filename
function detectCityFromPath(filepath) {
  if (!filepath || !cityIdInput) return;
  const lower = filepath.toLowerCase();

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
        loadInputDriveLocations(item.id);
        loadManualDriveLocations(item.id);
        loadFinalDriveLocations(item.id);
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
  renderStepCards();
  initDefaultPaths();
  attachEventListeners();
  loadInputDriveLocations();
  loadManualDriveLocations();
  loadFinalDriveLocations();
  checkServerHealth();
});

// Render the 18 step cards in the grid
function renderStepCards() {
  stepsGrid.innerHTML = "";
  PIPELINE_STEPS.forEach(step => {
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
      ${step.id === 20 ? `
        <div class="step-actions-row">
          <button type="button" class="btn-step-action" onclick="launchUploadPipeline()" title="Launch final_code.py in interactive console">
            🚀 Launch final_code.py
          </button>
        </div>` : ''}
      <div class="step-bottom">
        <span class="step-detail" id="step-detail-${step.id}">${step.detail}</span>
        <span class="step-duration" id="step-duration-${step.id}">${step.duration}</span>
      </div>
    `;

    stepsGrid.appendChild(card);
  });
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

  // Auto-detect city from path input
  inputFilePath.addEventListener("input", () => detectCityFromPath(inputFilePath.value));
  manualFilePath.addEventListener("input", () => detectCityFromPath(manualFilePath.value));
  if (finalFilePath) finalFilePath.addEventListener("input", () => detectCityFromPath(finalFilePath.value));
  cityIdInput.addEventListener("change", () => {
    if (cityDetectBadge) cityDetectBadge.classList.add("hidden");
    const cid = cityIdInput.value;
    loadInputDriveLocations(cid);
    loadManualDriveLocations(cid);
    loadFinalDriveLocations(cid);
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
  document.querySelectorAll(".contact-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      const email = pill.dataset.email;
      if (email && shareEmailRecipients) {
        shareEmailRecipients.value = email;
      }
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
    const manualPath = resumeFilePath.value.trim();
    if (!manualPath) {
      alert("Please enter the path to the manual corrected file.");
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
          location_name: appState.selectedLocation || (pauseLocationSelect?.selectedOptions[0]?.dataset.location) || null,
          output_path: outputPath.value.trim(),
          city_id: parseInt(cityIdInput.value, 10) || 9,
          include_geocoding: document.getElementById("include-geocoding") ? document.getElementById("include-geocoding").checked : false,
          auto_upload: document.getElementById("auto-upload") ? document.getElementById("auto-upload").checked : true
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
      startPolling();
    } catch (err) {
      alert(`Error resuming pipeline: ${err.message}`);
      logToConsole(`[Resume Error] ${err.message}`, "error");
    } finally {
      btnResume.disabled = false;
      btnResume.innerHTML = '<span class="btn-icon">▶</span> <span class="btn-text">Resume (Steps 7 → 20)</span>';
    }
  });

  // Parquet Verification Buttons (Step 18 pause card)
  if (btnConfirmParquet) {
    btnConfirmParquet.addEventListener("click", async () => {
      const confirmedPath = parquetConfirmFilePath ? parquetConfirmFilePath.value.trim() : "";
      btnConfirmParquet.disabled = true;
      btnConfirmParquet.innerHTML = '<span class="btn-icon">⏳</span> Converting...';
      try {
        const res = await fetch("/api/confirm-parquet", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "proceed", file_path: confirmedPath })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to confirm Parquet conversion.");
        if (parquetPauseCard) parquetPauseCard.classList.add("hidden");
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
      if (!confirm("Are you sure you want to skip Parquet conversion (Step 19)?")) return;
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
        logToConsole(`[Step 19] Selected alternate file: ${val}`, "info");
      }
    });
  }

  if (btnRefreshParquetLocs) {
    btnRefreshParquetLocs.addEventListener("click", () => {
      loadFinalDriveLocations();
      logToConsole("[Step 19] Refreshed final location folders from Google Drive.", "info");
    });
  }

  // Manual launch button for final_code.py
  const btnLaunchUploadManual = document.getElementById("btn-launch-upload-manual");
  if (btnLaunchUploadManual) {
    btnLaunchUploadManual.addEventListener("click", () => {
      launchUploadPipeline();
    });
  }
}

function setMode(mode) {
  appState.mode = mode;
  if (mode === "1") {
    mode1Label.classList.add("active");
    mode2Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    inputFileGroup.classList.remove("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    inputFilePath.required = true;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = false;

    // Reset marks on steps
    for (let i = 1; i <= 20; i++) {
      updateStepUI(i, "pending", "Waiting...", "-");
    }
    logToConsole("[Mode] Selected Mode 1: Run from START (Step 1 to Step 20)");
  } else if (mode === "2") {
    mode2Label.classList.add("active");
    mode1Label.classList.remove("active");
    if (mode3Label) mode3Label.classList.remove("active");
    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.remove("hidden");
    if (finalFileGroup) finalFileGroup.classList.add("hidden");
    inputFilePath.required = false;
    manualFilePath.required = true;
    if (finalFilePath) finalFilePath.required = false;

    // Visually mark steps 1-6 as skipped
    for (let i = 1; i <= 6; i++) {
      updateStepUI(i, "skipped", "Skipped in Mode 2", "-");
    }
    for (let i = 7; i <= 20; i++) {
      updateStepUI(i, "pending", "Waiting...", "-");
    }
    logToConsole("[Mode] Selected Mode 2: Resume from Step 7 (Steps 7 to 20)");
  } else if (mode === "3") {
    if (mode3Label) mode3Label.classList.add("active");
    mode1Label.classList.remove("active");
    mode2Label.classList.remove("active");
    inputFileGroup.classList.add("hidden");
    manualFileGroup.classList.add("hidden");
    if (finalFileGroup) finalFileGroup.classList.remove("hidden");
    inputFilePath.required = false;
    manualFilePath.required = false;
    if (finalFilePath) finalFilePath.required = true;

    // Visually mark steps 1-18 as skipped
    for (let i = 1; i <= 18; i++) {
      updateStepUI(i, "skipped", "Skipped in Mode 3", "-");
    }
    updateStepUI(19, "pending", "Waiting for Parquet conversion...", "-");
    updateStepUI(20, "pending", "Waiting...", "-");
    logToConsole("[Mode] Selected Mode 3: Parquet Conversion Directly (Step 19 → 20)");
  }
}

// =========================================================
// PIPELINE RUNNER & POLLING
// =========================================================
async function startPipeline() {
  const targetOutput = outputPath.value.trim();
  if (targetOutput && !targetOutput.toLowerCase().endsWith(".xlsx")) {
    alert("Output file path must end with '.xlsx'. Please correct it.");
    return;
  }

  const autoUploadCb = document.getElementById("auto-upload");
  const geocodingCb = document.getElementById("include-geocoding");
  const payload = {
    mode: appState.mode,
    input_file: inputFilePath.value.trim(),
    manual_file: manualFilePath.value.trim(),
    location_name: appState.selectedLocation || (driveInputLocationSelect?.selectedOptions[0]?.dataset.location) || null,
    city_id: parseInt(cityIdInput.value, 10) || 9,
    output_path: appState.mode === "3" ? ((finalFilePath ? finalFilePath.value.trim() : "") || targetOutput) : targetOutput,
    include_geocoding: geocodingCb ? geocodingCb.checked : false,
    auto_upload: autoUploadCb ? autoUploadCb.checked : true
  };

  // Reset UI
  appState.isRunning = true;
  appState.lastLogIndex = 0;
  btnRun.disabled = true;
  btnStop.disabled = false;
  btnStop.classList.remove("hidden");
  startTimer();

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
          logToConsole(`\n🎉 [Pipeline Finished] File saved to: ${status.output_file}`, "success");
          alert(`🎉 Pipeline execution completed successfully!\nSaved to: ${status.output_file}`);
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
  // Update progress percentage
  const pct = Math.min(100, Math.max(0, status.progress || 0));
  progressBar.style.width = `${pct}%`;
  progressPercent.textContent = `${pct}%`;
  currentStepText.textContent = status.current_step_name || "Executing...";

  // Update metrics
  if (status.metrics) {
    if (status.metrics.total_rows) metricRows.textContent = status.metrics.total_rows.toLocaleString();
    if (status.metrics.rera_matched) metricRera.textContent = status.metrics.rera_matched.toLocaleString();
    if (status.metrics.nr_assigned) metricNr.textContent = status.metrics.nr_assigned.toLocaleString();
  }

  // Update step cards
  if (status.steps && Array.isArray(status.steps)) {
    let completedCount = 0;
    status.steps.forEach(s => {
      updateStepUI(s.id, s.status, s.detail, s.duration);
      if (s.status === "completed") completedCount++;
    });
    stepsStatusSummary.textContent = `${completedCount} / ${status.steps.length} Completed`;
  }

  // Handle Step 7 Pause State
  if (status.state === "awaiting_manual_file") {
    const isFirstTimePaused = pauseCard.classList.contains("hidden");
    pauseCard.classList.remove("hidden");
    if (status.v1_file) {
      pauseV1Path.textContent = status.v1_file;
      if (!resumeFilePath.value) {
        resumeFilePath.value = status.v1_file;
      }
    }
    if (status.location_name) {
      appState.selectedLocation = status.location_name;
    }
    if (isFirstTimePaused) {
      loadManualDriveLocations();
    }
  } else {
    pauseCard.classList.add("hidden");
  }

  // Handle Step 19 Parquet Confirmation Pause State
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
      if (isFirstTimePaused) {
        loadFinalDriveLocations();
        parquetPauseCard.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  } else {
    if (parquetPauseCard) {
      parquetPauseCard.classList.add("hidden");
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

function logToConsole(message, level = "info") {
  const line = document.createElement("div");
  line.className = `console-line ${level}`;
  line.textContent = message;
  consoleOutput.appendChild(line);

  if (autoscrollCb.checked) {
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
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
      if (!inputFilePath.value || !inputFilePath.value.includes(".shortcut-targets-by-id")) {
        driveInputLocationSelect.value = firstValidFile;
        inputFilePath.value = firstValidFile;
        appState.selectedLocation = firstLocation;
        logToConsole(`[Drive] Connected to ${cityName} Drive location: ${firstLocation} (${firstValidFile})`, "info");
      }
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

  const pauseChipsContainer = document.getElementById("pause-location-chips");
  if (pauseChipsContainer) pauseChipsContainer.innerHTML = "";

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
            matchedSelection = true;
            opt.selected = true;
            opt.textContent = `📍 [SELECTED] ${loc.location} / ${f.name}`;
          } else {
            opt.textContent = `📍 ${loc.location} / ${f.name}`;
          }
          select.appendChild(opt);
        });

        // Add interactive location folder chips for Step 7 pause card
        if (isPauseSelect && pauseChipsContainer) {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "loc-folder-chip";
          const firstFile = loc.files[0];
          const isSelected = currentPath && (currentPath.includes(loc.location) || (firstFile && currentPath.endsWith(firstFile.name)));
          if (isSelected) chip.classList.add("active");
          chip.innerHTML = `📂 <strong>${loc.location}</strong> <span class="chip-count">(${loc.files.length} file${loc.files.length > 1 ? 's' : ''})</span>`;
          chip.title = `Click to choose ${loc.location} folder (${firstFile ? firstFile.name : ''})`;
          chip.addEventListener("click", () => {
            if (firstFile) {
              resumeFilePath.value = firstFile.path;
              pauseLocationSelect.value = firstFile.path;
              appState.selectedLocation = loc.location;
              document.querySelectorAll(".loc-folder-chip").forEach(c => c.classList.remove("active"));
              chip.classList.add("active");
              logToConsole(`[Step 7] Selected location folder '${loc.location}' -> ${firstFile.name}`, "info");
            }
          });
          pauseChipsContainer.appendChild(chip);
        }
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

  try {
    const res = await fetch("/api/share-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: targetFile,
        recipients: [recipient],
        location_name: appState.selectedLocation || (pauseLocationSelect?.selectedOptions[0]?.dataset.location) || "Mohmadwadi",
        deadline: deadline,
        city_id: parseInt(cityIdInput?.value, 10) || 9
      })
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || "Failed to send email.");

    const deadlineInfo = result.deadline_formatted ? ` [⏰ Deadline: ${result.deadline_formatted}]` : (deadline ? ` [⏰ Deadline: ${deadline}]` : "");

    if (result.mode === "attachment") {
      shareStatusMsg.className = "share-status-msg success";
      shareStatusMsg.textContent = `✓ Email sent successfully with file attached to ${recipient}!${deadlineInfo}`;
      logToConsole(`[Email Share] ✓ Sent manual file with attachment to ${recipient}${deadlineInfo}`, "success");
    } else {
      shareStatusMsg.className = "share-status-msg warning";
      shareStatusMsg.textContent = `✓ Drive link notification sent to ${recipient} (fallback link mode).${deadlineInfo}`;
      logToConsole(`[Email Share] Sent Drive link notification to ${recipient}${deadlineInfo}`, "info");
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
