const CLIENT_FIELDS = [
  ["co", "c/o"], ["street_2", "Street 2"], ["street_3", "Street 3"],
  ["street_house_number", "Street/House Number"], ["street_4", "Street 4"], ["street_5", "Street 5"],
  ["district", "District"], ["other_city", "Other City"], ["postal_code_city", "Postal Code/City"],
  ["country", "Country"], ["time_zone", "Time Zone"], ["transportation_zone", "Transportation Zone"],
  ["reg_struct_grp", "Reg. Struct. Grp."], ["undeliverable", "Undeliverable"],
  ["po_box_address", "PO Box Address"], ["po_box", "PO Box"], ["postal_code", "Postal Code"],
];

const MODE_PRESETS = {
  recommended: { validation: true, llm: true },
  fast: { validation: true, llm: false },
  "llm-only": { validation: false, llm: true },
};

const DEFAULTS = { country: "GB", time_zone: "GMTUK" };
const state = { lastResult: null, queue: [], queueIndex: -1, queueStatus: {}, azureConfigured: false };
const $ = (id) => document.getElementById(id);

function buildFieldForm() {
  CLIENT_FIELDS.forEach(([key, label]) => {
    const wrap = document.createElement("div");
    wrap.className = "field";
    wrap.innerHTML = `<label for="f_${key}">${label}</label><input id="f_${key}" />`;
    $("addressFields").appendChild(wrap);
  });
  fillForm(DEFAULTS);
}

function setStatus(msg, ok, elId = "status") {
  const el = $(elId);
  if (!msg) {
    el.className = "status-msg";
    el.textContent = "";
    return;
  }
  el.textContent = msg;
  el.className = "status-msg visible " + (ok ? "ok" : "err");
}

function fillForm(addr) {
  CLIENT_FIELDS.forEach(([key]) => {
    const el = $("f_" + key);
    if (el) el.value = addr[key] ?? DEFAULTS[key] ?? "";
  });
}

function readForm() {
  const out = { customer_id: $("customerId").value.trim() };
  CLIENT_FIELDS.forEach(([key]) => { out[key] = ($("f_" + key)?.value || "").trim(); });
  if (!out.country) out.country = "GB";
  if (!out.time_zone) out.time_zone = "GMTUK";
  return out;
}

function updateStats() {
  const total = state.queue.length;
  const ok = Object.values(state.queueStatus).filter((v) => v === true).length;
  const fail = Object.values(state.queueStatus).filter((v) => v === false).length;
  $("statTotal").textContent = String(total);
  $("statOk").textContent = String(ok);
  $("statFail").textContent = String(fail);
  $("queueCount").textContent = String(total);
}

function setStatusPill(elId, label, stateClass) {
  const el = $(elId);
  if (!el) return;
  el.className = "status-item " + (stateClass || "");
  const lbl = el.querySelector(".status-label");
  if (lbl) lbl.textContent = label;
}

function getLlmProvider() {
  const checked = document.querySelector('input[name="llmProvider"]:checked');
  return checked ? checked.value : "arthavi";
}

function setupProviderToggle() {
  document.querySelectorAll(".provider-option").forEach((opt) => {
    opt.addEventListener("click", () => {
      if (opt.classList.contains("disabled")) return;
      const radio = opt.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
      document.querySelectorAll(".provider-option").forEach((o) => {
        o.classList.toggle("selected", o === opt);
      });
    });
  });
}

function formatUsd(value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(6)}`;
  return `$${n.toFixed(4)}`;
}

function renderLlmAnalysis(result) {
  const analysis = result?.llm_analysis;
  const card = $("analysisCard");
  const summary = $("analysisSummary");
  const metrics = $("analysisMetrics");
  const table = $("comparisonTable");
  const tbody = $("comparisonBody");
  const promptDetails = $("promptDetails");

  if (!analysis) {
    summary.textContent = "Run a single-address test to see token usage, prompts, and Arthavi vs Azure comparison.";
    metrics.innerHTML = "";
    table.hidden = true;
    promptDetails.hidden = true;
    return;
  }

  card?.classList.remove("collapsed");
  const provider = result.llm_provider || analysis.provider || "arthavi";
  const tokens = analysis.token_usage || analysis.cost_analysis?.tokens;
  const cost = analysis.cost_analysis?.cost_usd?.total_per_request;
  const latency = analysis.latency_ms;

  summary.textContent =
    provider === "azure"
      ? `Mapped with Azure OpenAI (${analysis.model || analysis.deployment || "deployment"}). Token and cost metrics below compared with local Arthavi LLM.`
      : `Mapped with local Arthavi LLM (${analysis.model || result.model}). $0 API cost; Azure comparison estimates shown when you switch provider.`;

  const metricItems = [
    { lbl: "Provider", val: provider === "azure" ? "Azure" : "Arthavi" },
    { lbl: "Latency", val: latency != null ? `${Math.round(latency)} ms` : "—" },
    {
      lbl: "Total tokens",
      val: tokens?.total != null ? tokens.total.toLocaleString() : provider === "arthavi" ? "N/A (local)" : "—",
    },
    { lbl: "Cost / request", val: formatUsd(cost ?? (provider === "arthavi" ? 0 : null)) },
  ];
  metrics.innerHTML = metricItems
    .map((m) => `<div class="analysis-metric"><div class="val">${m.val}</div><div class="lbl">${m.lbl}</div></div>`)
    .join("");

  const cmp = analysis.comparison || {};
  const arthavi = cmp.arthavi || {};
  const azure = cmp.azure || {};
  const rows = [
    ["Model", arthavi.model || result.model || "arthavi-address", azure.model || "Azure deployment"],
    [
      "Cost per request",
      formatUsd(arthavi.cost_usd_per_request ?? 0),
      formatUsd(azure.cost_usd_per_request ?? analysis.cost_analysis?.cost_usd?.total_per_request),
    ],
    [
      "Tokens per request",
      arthavi.tokens_per_request ?? "N/A (local)",
      azure.tokens_per_request ?? tokens?.total ?? "—",
    ],
    [
      "Latency",
      arthavi.latency_ms != null ? `${Math.round(arthavi.latency_ms)} ms` : arthavi.typical_latency_seconds ? `${arthavi.typical_latency_seconds}s typical` : "—",
      azure.latency_ms != null ? `${Math.round(azure.latency_ms)} ms` : azure.typical_latency_seconds ? `${azure.typical_latency_seconds}s typical` : "—",
    ],
    ["Data residency", arthavi.data_residency || "On-prem / local", azure.data_residency || "Azure cloud"],
    [
      "1,000 addresses (est.)",
      "$0.00",
      formatUsd(analysis.cost_analysis?.projections_usd?.per_1_000_addresses ?? cmp.savings_vs_azure_per_1k?.azure_cost_usd),
    ],
  ];
  tbody.innerHTML = rows.map(([label, a, z]) => `<tr><td>${label}</td><td>${a}</td><td>${z}</td></tr>`).join("");
  table.hidden = false;

  if (analysis.prompts?.system || analysis.prompts?.user) {
    $("systemPromptOut").textContent = analysis.prompts.system || "";
    $("userPromptOut").textContent = analysis.prompts.user || "";
    promptDetails.hidden = false;
  } else {
    promptDetails.hidden = true;
  }

  const rag = result.rag_metadata || analysis.rag_metadata;
  const ragDetails = $("ragDetails");
  const ragOut = $("ragOut");
  if (rag?.enabled && rag.hits?.length) {
    ragOut.textContent = JSON.stringify(rag.hits, null, 2);
    ragDetails.hidden = false;
  } else if (rag?.enabled) {
    ragOut.textContent = JSON.stringify({ note: rag.note || "No similar examples found", examples_count: rag.examples_count }, null, 2);
    ragDetails.hidden = false;
  } else {
    ragDetails.hidden = true;
  }
}

function getSelectedMode() {
  const checked = document.querySelector('input[name="mode"]:checked');
  return checked ? checked.value : "recommended";
}

function applyMode(mode) {
  const preset = MODE_PRESETS[mode] || MODE_PRESETS.recommended;
  $("useValidation").checked = preset.validation;
  $("useLlm").checked = preset.llm;
  document.querySelectorAll(".mode-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.mode === mode);
  });
  syncModeSummary();
}

function syncModeSummary() {
  const mode = getSelectedMode();
  const validation = $("useValidation").checked;
  const llm = $("useLlm").checked;
  const hints = {
    recommended:
      "Postcodes.io confirms the postcode exists, then arthavi-address maps flat, building, road, city and postcode into SAP fields — best accuracy.",
    fast:
      "Postcodes.io validation plus rule-based parsing. No Ollama — use for quick bulk checks before enabling AI mapping.",
    "llm-only":
      "Skips Postcodes.io. arthavi-address validates postcode format and maps all fields from the vendor text alone.",
  };
  $("modeHint").textContent = hints[mode] || hints.recommended;

  const estSec = llm ? 60 : 3;
  if ($("processAllBtn") && !$("processAllBtn").disabled) {
    const file = $("csvFile")?.files?.[0];
    if (file && !$("progressWrap").classList.contains("visible")) {
      /* no-op: hint shown on process start */
    }
  }
  return { validation, llm, estSec };
}

function setupModeCards() {
  document.querySelectorAll(".mode-card").forEach((card) => {
    card.addEventListener("click", () => {
      const mode = card.dataset.mode;
      const radio = card.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
      applyMode(mode);
    });
  });
}

async function loadServerConfig() {
  try {
    const [cfgRes, healthRes] = await Promise.all([
      fetch("/api/config"),
      fetch("/health"),
    ]);
    const cfg = await cfgRes.json();
    const health = await healthRes.json();
    const model = cfg.model || health.model || "arthavi-address";
    const validator = cfg.validator || health.validator || "postcodes_io";
    state.azureConfigured = cfg.azure_configured === true || health.azure_configured === true;

    const ollamaReachable = health.ollama_reachable === true;
    const ollamaEnabled = health.ollama_enabled !== false;
    setStatusPill(
      "statusOllama",
      ollamaReachable ? "Ollama online" : "Ollama offline",
      ollamaReachable ? "ok" : "err"
    );
    setStatusPill("statusModel", model, ollamaReachable ? "ok" : "warn");
    setStatusPill(
      "statusValidator",
      validator === "llm_only" ? "LLM only" : validator.replace(/_/g, " "),
      "ok"
    );
    const azureDep = cfg.azure_deployment || health.azure_deployment;
    setStatusPill(
      "statusAzure",
      state.azureConfigured ? `Azure · ${azureDep || "ready"}` : "Azure offline",
      state.azureConfigured ? "ok" : "warn"
    );

    const azureOpt = $("azureProviderOption");
    const azureHint = $("azureProviderHint");
    if (azureOpt && azureHint) {
      if (state.azureConfigured) {
        azureOpt.classList.remove("disabled");
        azureHint.textContent = `Deployment: ${azureDep || "configured"} · token + cost metrics`;
      } else {
        azureOpt.classList.add("disabled");
        azureHint.textContent = "Not configured — set AZURE_OPENAI_* in server .env";
        if (getLlmProvider() === "azure") {
          const arthaviRadio = document.querySelector('input[name="llmProvider"][value="arthavi"]');
          if (arthaviRadio) arthaviRadio.checked = true;
          document.querySelectorAll(".provider-option").forEach((o) => {
            o.classList.toggle("selected", o.querySelector('input[value="arthavi"]'));
          });
        }
      }
    }

    if (cfg.rag_enabled_default === false && $("useRag")) {
      $("useRag").checked = false;
    }

    $("validator").options[0].textContent = `Server default (${validator})`;

    const useValidation = !cfg.skip_validation_default;
    const useLlm = ollamaEnabled;
    let mode = "recommended";
    if (useValidation && !useLlm) mode = "fast";
    else if (!useValidation && useLlm) mode = "llm-only";
    const radio = document.querySelector(`input[name="mode"][value="${mode}"]`);
    if (radio) radio.checked = true;
    applyMode(mode);
  } catch {
    setStatusPill("statusOllama", "Ollama unknown", "warn");
    setStatusPill("statusModel", "arthavi-address", "warn");
    setStatusPill("statusValidator", "postcodes.io", "ok");
    applyMode("recommended");
  }
}

function downloadCsv(csvText, filename) {
  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function setProgress(pct, label) {
  $("progressWrap").classList.add("visible");
  $("progressFill").style.width = pct + "%";
  $("progressPct").textContent = pct + "%";
  $("progressLabel").textContent = label;
}

async function processAllAndDownload() {
  const file = $("csvFile").files[0];
  if (!file) {
    setStatus("Choose a CSV file first (Step 1).", false, "batchStatus");
    return;
  }

  const { llm, estSec } = syncModeSummary();
  $("processAllBtn").disabled = true;
  setProgress(0, `Starting batch… ~${estSec}s per row with current mode`);
  setStatus("", true, "batchStatus");

  const fd = new FormData();
  fd.append("file", file);
  fd.append("skip_llm", $("useLlm").checked ? "false" : "true");
  fd.append("skip_validation", $("useValidation").checked ? "false" : "true");
  const validator = $("validator").value;
  if (validator) fd.append("validator", validator);

  try {
    const res = await fetch("/api/import/batch/process", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Batch process failed");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        const evt = JSON.parse(line);
        if (evt.type === "started" || evt.type === "warming") {
          setProgress(0, evt.message || `Starting ${evt.total || ""} row(s)…`);
        } else if (evt.type === "row_start") {
          const pct = Math.round(((evt.current - 1) / evt.total) * 100);
          setProgress(
            pct,
            `#${evt.current}/${evt.total} · Customer ${evt.customer_id || "?"} · processing…`
          );
        } else if (evt.type === "progress") {
          const pct = Math.round((evt.current / evt.total) * 100);
          setProgress(
            pct,
            `#${evt.current}/${evt.total} · Customer ${evt.customer_id || "?"} · ${evt.success ? "OK" : "Failed"}`
          );
          state.queueStatus[evt.current - 1] = evt.success;
          updateStats();
          if (state.queue.length >= evt.current) renderQueue();
        } else if (evt.type === "error") {
          throw new Error(evt.message);
        } else if (evt.type === "complete") {
          setProgress(100, `Done — ${evt.stats.successful} succeeded, ${evt.stats.failed} failed`);
          downloadCsv(evt.csv, evt.filename || "db_client_addresses.csv");
          setStatus(
            `Downloaded ${evt.filename}. Import rows with Processing Status = SUCCESS. Review failures in Step 4.`,
            true,
            "batchStatus"
          );
        }
      }
    }
  } catch (e) {
    setStatus(String(e), false, "batchStatus");
  } finally {
    $("processAllBtn").disabled = false;
  }
}

async function normalizeAddress(address, customerId, skipLlm, skipValidation, llmProvider, useRag) {
  const body = {
    address,
    customer_id: customerId,
    skip_llm: skipLlm,
    skip_validation: skipValidation,
    llm_provider: llmProvider || "arthavi",
    use_rag: useRag !== false,
  };
  const validator = $("validator").value;
  if (validator) body.validator = validator;
  const res = await fetch("/api/normalize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

function renderQueue() {
  updateStats();
  const box = $("queue");
  if (!state.queue.length) {
    box.innerHTML = '<div class="queue-empty">Import a CSV to review rows one by one.</div>';
    return;
  }
  box.innerHTML = "";
  state.queue.forEach((item, idx) => {
    const div = document.createElement("div");
    let cls = "queue-item" + (idx === state.queueIndex ? " active" : "");
    if (state.queueStatus[idx] === true) cls += " done-ok";
    if (state.queueStatus[idx] === false) cls += " done-fail";
    div.className = cls;
    div.innerHTML = `
      <div class="queue-num">${idx + 1}</div>
      <div class="queue-body">
        <strong>${item.customer_id || "—"}</strong>
        <p>${item.vendor_address}</p>
      </div>`;
    div.onclick = () => loadQueueItem(idx);
    box.appendChild(div);
  });
}

function loadQueueItem(idx) {
  state.queueIndex = idx;
  const item = state.queue[idx];
  $("customerId").value = item.customer_id || "";
  $("vendorAddress").value = item.vendor_address || "";
  renderQueue();
  document.getElementById("step-review")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setupDropzone() {
  const zone = $("dropzone");
  const input = $("csvFile");
  const showFile = (file) => {
    if (file) $("fileName").textContent = `Selected: ${file.name}`;
    else $("fileName").textContent = "";
  };
  input.addEventListener("change", () => showFile(input.files[0]));
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      showFile(input.files[0]);
    }
  });
}

function setupCollapsibles() {
  document.querySelectorAll(".collapsible-head").forEach((head) => {
    head.addEventListener("click", () => {
      const card = document.getElementById(head.dataset.target);
      if (card) card.classList.toggle("collapsed");
    });
  });
}

$("processAllBtn").onclick = processAllAndDownload;

$("normalizeBtn").onclick = async () => {
  const address = $("vendorAddress").value.trim();
  if (!address) { setStatus("Enter a vendor address.", false); return; }
  const llmProvider = getLlmProvider();
  const useLlm = llmProvider === "azure" || $("useLlm").checked;
  if (llmProvider === "azure" && !state.azureConfigured) {
    setStatus("Azure OpenAI is not configured on the server.", false);
    return;
  }
  setStatus(
    llmProvider === "azure"
      ? "Normalizing with Azure OpenAI… capturing tokens and cost."
      : useLlm
        ? "Normalizing with arthavi-address… first call may take ~1 min while Ollama loads the model."
        : "Normalizing with rules…",
    true
  );
  $("normalizeBtn").disabled = true;
  try {
    const result = await normalizeAddress(
      address,
      $("customerId").value.trim(),
      llmProvider === "azure" ? false : !$("useLlm").checked,
      !$("useValidation").checked,
      llmProvider,
      $("useRag")?.checked !== false
    );
    state.lastResult = result;
    $("validationOut").textContent = JSON.stringify(result.postcode_validation || {}, null, 2);
    $("valBadge").textContent = result.success ? "Validated" : "Failed";
    $("valBadge").className = "badge " + (result.success ? "ok" : "warn");
    if (result.success && result.normalized_address && Object.keys(result.normalized_address).length) {
      fillForm(result.normalized_address);
      $("saveReviewBtn").disabled = false;
    } else {
      $("saveReviewBtn").disabled = true;
    }
    $("formatCard")?.classList.remove("collapsed");
    if (result.postcode_validation) $("validationCard")?.classList.remove("collapsed");
    renderLlmAnalysis(result);
    setStatus(
      result.success
        ? llmProvider === "azure"
          ? "Azure mapping complete. See LLM analysis panel for tokens, prompts, and cost comparison."
          : "Mapped to client format. Edit fields if needed, then Save correction to improve the model."
        : (result.errors || []).join("; ") || result.error || "Normalization failed",
      result.success
    );
  } catch (e) {
    setStatus(String(e), false);
  } finally {
    $("normalizeBtn").disabled = false;
  }
};

$("saveReviewBtn").onclick = async () => {
  const res = await fetch("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      vendor_address: $("vendorAddress").value.trim(),
      customer_id: readForm().customer_id,
      llm_output: state.lastResult?.normalized_address || {},
      human_corrected: readForm(),
    }),
  });
  setStatus(
    res.ok
      ? "Correction saved to data/review/corrections.csv — include in next training run (see guide panel)."
      : "Save failed",
    res.ok
  );
};

$("previewBtn").onclick = async () => {
  const file = $("csvFile").files[0];
  if (!file) { setStatus("Choose a CSV file first (Step 1).", false, "batchStatus"); return; }
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/import/preview", { method: "POST", body: fd });
  const data = await res.json();
  const pre = $("importPreview");
  pre.style.display = "block";
  pre.textContent = JSON.stringify(data, null, 2);
  setStatus(`Detected ${data.format_detected} format · ${data.total_rows} rows · header row ${data.header_row}`, res.ok, "batchStatus");
};

$("importBtn").onclick = async () => {
  const file = $("csvFile").files[0];
  if (!file) { setStatus("Choose a CSV file first (Step 1).", false, "batchStatus"); return; }
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/import/queue", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) { setStatus(data.error || "Import failed", false, "batchStatus"); return; }
  state.queue = data.rows || [];
  state.queueIndex = state.queue.length ? 0 : -1;
  state.queueStatus = {};
  renderQueue();
  if (state.queue.length) loadQueueItem(0);
  setStatus(`Imported ${state.queue.length} addresses. Review in Step 4.`, true, "batchStatus");
};

buildFieldForm();
setupDropzone();
setupCollapsibles();
setupModeCards();
setupProviderToggle();
loadServerConfig();
renderQueue();
