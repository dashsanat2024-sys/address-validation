const CLIENT_FIELDS = [
  ["co", "c/o"], ["street_2", "Street 2"], ["street_3", "Street 3"],
  ["street_house_number", "Street/House Number"], ["street_4", "Street 4"], ["street_5", "Street 5"],
  ["district", "District"], ["other_city", "Other City"], ["postal_code_city", "Postal Code/City"],
  ["country", "Country"], ["time_zone", "Time Zone"], ["transportation_zone", "Transportation Zone"],
  ["reg_struct_grp", "Reg. Struct. Grp."], ["undeliverable", "Undeliverable"],
  ["po_box_address", "PO Box Address"], ["po_box", "PO Box"], ["postal_code", "Postal Code"],
];

const DEFAULTS = { country: "GB", time_zone: "GMTUK" };
const state = { lastResult: null, queue: [], queueIndex: -1, queueStatus: {} };
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

async function loadServerConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    const label = cfg.validator_label || cfg.validator;
    $("validatorHint").textContent =
      `Server default uses ADDRESS_VALIDATOR from .env — currently ${label}.`;
    $("validator").options[0].textContent = `Server default (${cfg.validator})`;
    $("headerValidator").textContent = `Validator: ${cfg.validator}`;
    $("headerModel").textContent = `Model: ${cfg.model}`;
  } catch {
    $("validatorHint").textContent = "Server default = Postcodes.io (set ADDRESS_VALIDATOR in .env).";
    $("headerValidator").textContent = "Validator: postcodes_io";
    $("headerModel").textContent = "Model: qwen3:8b";
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
    setStatus("Choose a CSV file first.", false, "batchStatus");
    return;
  }

  $("processAllBtn").disabled = true;
  setProgress(0, "Starting batch processing…");
  setStatus("", true, "batchStatus");

  const fd = new FormData();
  fd.append("file", file);
  fd.append("skip_llm", $("useLlm").checked ? "false" : "true");
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
        if (evt.type === "progress") {
          const pct = Math.round((evt.current / evt.total) * 100);
          setProgress(
            pct,
            `#${evt.current}/${evt.total} · Customer ${evt.customer_id || "?"} · ${evt.success ? "Validated" : "Failed"}`
          );
          state.queueStatus[evt.current - 1] = evt.success;
          updateStats();
          if (state.queue.length >= evt.current) renderQueue();
        } else if (evt.type === "error") {
          throw new Error(evt.message);
        } else if (evt.type === "complete") {
          setProgress(100, `Complete — ${evt.stats.successful} succeeded, ${evt.stats.failed} failed`);
          downloadCsv(evt.csv, evt.filename || "db_client_addresses.csv");
          setStatus(
            `Downloaded ${evt.filename}. Import rows with Processing Status = SUCCESS into your database.`,
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

async function normalizeAddress(address, customerId, skipLlm) {
  const body = { address, customer_id: customerId, skip_llm: skipLlm };
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
    box.innerHTML = '<div class="queue-empty">Import a CSV to build a review queue, or process in batch above.</div>';
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
  setStatus("Normalizing address…", true);
  $("normalizeBtn").disabled = true;
  try {
    const result = await normalizeAddress(address, $("customerId").value.trim(), !$("useLlm").checked);
    state.lastResult = result;
    $("validationOut").textContent = JSON.stringify(result.postcode_validation || {}, null, 2);
    $("valBadge").textContent = result.success ? "Validated" : "Failed";
    $("valBadge").className = "badge " + (result.success ? "ok" : "warn");
    fillForm(result.normalized_address || {});
    $("saveReviewBtn").disabled = !result.normalized_address;
    setStatus(result.success ? "Address normalized to client format." : (result.errors || []).join("; "), result.success);
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
  setStatus(res.ok ? "Human correction saved for model improvement." : "Save failed", res.ok);
};

$("previewBtn").onclick = async () => {
  const file = $("csvFile").files[0];
  if (!file) { setStatus("Choose a CSV file first.", false, "batchStatus"); return; }
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
  if (!file) { setStatus("Choose a CSV file first.", false, "batchStatus"); return; }
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
  setStatus(`Imported ${state.queue.length} addresses into review queue.`, true, "batchStatus");
};

buildFieldForm();
setupDropzone();
setupCollapsibles();
loadServerConfig();
renderQueue();
