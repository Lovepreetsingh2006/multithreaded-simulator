const API = {
  state: "/api/state",
  start: "/api/start",
  pause: "/api/pause",
  step: "/api/step",
  reset: "/api/reset",
  initDemo: "/api/init_demo",
  addThread: "/api/add_thread",
  setConfig: "/api/set",

  // Semaphore API
  semCreate: "/api/semaphore/create",
  semWait: "/api/semaphore/wait",
  semSignal: "/api/semaphore/signal",

  // Monitor API
  monCreate: "/api/monitor/create",
  monWait: "/api/monitor/wait",
  monSignal: "/api/monitor/signal",
  monBroadcast: "/api/monitor/broadcast",
};

let pollTimer = null;
let lastTick = 0;

// =======================================
//      SYNC MODE: SEMAPHORE / MONITOR
// =======================================
let currentSyncMode = "semaphore"; // switch via tabs


// =======================================
//              SEMAPHORES
// =======================================
function createSemaphore() {
  const name = document.getElementById("sem-name").value.trim();
  const init = parseInt(document.getElementById("sem-init").value, 10);

  if (!name) return alert("Enter semaphore name.");

  fetch(API.semCreate, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, initial: init }),
  }).then(refreshState);
}

function semaphoreWait(semName, threadId) {
  fetch(API.semWait, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: semName, thread_id: threadId }),
  }).then(refreshState);
}

function semaphoreSignal(semName) {
  fetch(API.semSignal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: semName }),
  }).then(refreshState);
}


// =======================================
//                MONITORS
// =======================================
function createMonitor() {
  const name = document.getElementById("mon-name").value.trim();
  if (!name) return alert("Enter monitor name.");

  fetch(API.monCreate, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }).then(refreshState);
}

function monitorWait(monitor, threadId) {
  fetch(API.monWait, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitor, thread_id: threadId, cond: "default" }),
  }).then(refreshState);
}

function monitorSignal(monitor) {
  fetch(API.monSignal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitor, cond: "default" }),
  }).then(refreshState);
}

function monitorBroadcast(monitor) {
  fetch(API.monBroadcast, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ monitor, cond: "default" }),
  }).then(refreshState);
}


// =======================================
//           API REQUEST HELPERS
// =======================================
async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  return res.json();
}

async function apiGet(url) {
  const res = await fetch(url);
  return res.json();
}


// =======================================
//     BUILD THREAD ACTION BUTTONS
// =======================================
function makeThreadActions(thread, semaphores, monitors) {
  if (thread.state === "TERMINATED") return "-";
  if (thread.state === "BLOCKED") return "<em>BLOCKED</em>";

  let html = "";

  // Show ONLY semaphore buttons
  if (currentSyncMode === "semaphore") {
    for (let name of Object.keys(semaphores)) {
      html += `
        <button class="btn-primary" onclick="semaphoreWait('${name}', ${thread.id})">
          WAIT ${name}
        </button>
      `;
    }
  }

  // Show ONLY monitor buttons
  if (currentSyncMode === "monitor") {
    for (let name of Object.keys(monitors)) {
      html += `
        <button class="btn-primary" onclick="monitorWait('${name}', ${thread.id})">
          WAIT ${name}
        </button>
      `;
    }
  }

  return html || "<em>No actions</em>";
}


// =======================================
//             RENDER UI STATE
// =======================================
function renderState(state) {
  // Stats
  document.getElementById("stat-tick").textContent = state.tick;
  document.getElementById("stat-threads").textContent = state.threads.length;
  document.getElementById("stat-completed").textContent = state.stats.completed;
  document.getElementById("stat-context-switches").textContent =
    state.stats.context_switches;

  // Update badges
  document.getElementById("badge-model").textContent = `Model: ${state.model}`;
  document.getElementById("badge-quantum").textContent = `Quantum: ${state.quantum}`;

  // ---------------- THREAD TABLE ----------------
  const tbody = document.getElementById("threads-tbody");
  tbody.innerHTML = "";

  state.threads.forEach((t) => {
    const tr = document.createElement("tr");

    const running = state.kernels.some((k) => k.current_thread === t.id);
    if (running) tr.classList.add("thread-row-running");

    const stateClass =
      t.state === "RUNNING" ? "state-running" :
      t.state === "READY" ? "state-ready" :
      t.state === "BLOCKED" ? "state-blocked" :
      "state-terminated";

    const stateCell = `
      <div class="thread-state-pill ${stateClass}">
        <span class="thread-state-dot"></span>
        <span>${t.state}</span>
      </div>
    `;

    tr.innerHTML = `
      <td>${t.id}</td>
      <td>${t.name}</td>
      <td>${stateCell}</td>
      <td>${t.remaining}</td>
      <td>${t.priority}</td>
      <td>${t.mapped_kernel ?? "-"}</td>
      <td>${makeThreadActions(t, state.semaphores, state.monitors)}</td>
    `;

    tbody.appendChild(tr);
  });

  // ---------------- CORES ----------------
  const coresGrid = document.getElementById("cores-grid");
  coresGrid.innerHTML = "";

  state.kernels.forEach((k) => {
    const div = document.createElement("div");
    const busy = k.current_thread !== null;

    const threadObj = state.threads.find((t) => t.id === k.current_thread);

    div.className = "core-card" + (busy ? " busy" : "");
    div.innerHTML = `
      <div class="core-pulse"></div>
      <div class="core-header">
        <span class="core-name">Core #${k.id}</span>
        <span class="core-status ${busy ? "core-status-busy" : "core-status-idle"}">
          ${busy ? "RUNNING" : "IDLE"}
        </span>
      </div>
      <div class="core-body">
        ${
          busy && threadObj
            ? `<div class="core-thread-name">${threadObj.name}</div>`
            : `<div class="core-thread-name" style="color:var(--muted);">No thread</div>`
        }
      </div>
    `;
    coresGrid.appendChild(div);
  });

  // ---------------- SEMAPHORES PANEL ----------------
  const semList = document.getElementById("sem-list");
  semList.innerHTML = "";

  for (let [name, sem] of Object.entries(state.semaphores)) {
    const div = document.createElement("div");
    div.className = "sem-card";

    div.innerHTML = `
      <div class="sem-header">
        <span class="sem-name">${name}</span>
        <span class="sem-value ${sem.value > 0 ? "available" : "locked"}">
          <span class="value-icon">🔒</span> ${sem.value}
        </span>
      </div>

      <div class="sem-blocked">
        <div class="blocked-label">Blocked Threads:</div>
        <div class="blocked-value">${sem.blocked.join(", ") || "None"}</div>
      </div>

      <div class="sem-actions">
        <button class="btn-primary" onclick="semaphoreSignal('${name}')">SIGNAL (V)</button>
      </div>
    `;

    semList.appendChild(div);
  }

  // ---------------- MONITORS PANEL ----------------
  const monList = document.getElementById("mon-list");
  if (monList) {
    monList.innerHTML = "";

    for (let [name, mon] of Object.entries(state.monitors)) {
      const div = document.createElement("div");
      div.className = "sem-card";

      div.innerHTML = `
        <div class="sem-header">
          <span class="sem-name">${name}</span>
        </div>

        <div class="sem-blocked">
          <div class="blocked-label">Waiting:</div>
          <div class="blocked-value">${mon.waiting.join(", ") || "None"}</div>
        </div>

        <div class="sem-actions">
          <button class="btn-primary" onclick="monitorSignal('${name}')">SIGNAL</button>
          <button class="btn-primary" onclick="monitorBroadcast('${name}')">BROADCAST</button>
        </div>
      `;
      monList.appendChild(div);
    }
  }

  // ---------------- EVENT LOG ----------------
  if (state.tick !== lastTick) {
    const log = document.getElementById("event-log");
    const line = document.createElement("div");
    line.className = "event-line";

    const running = state.threads.filter((t) => t.state === "RUNNING").length;
    const ready = state.threads.filter((t) => t.state === "READY").length;
    const blocked = state.threads.filter((t) => t.state === "BLOCKED").length;

    line.innerHTML = `Tick <span>${state.tick}</span>: RUN ${running}, READY ${ready}, BLOCKED ${blocked}`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;

    lastTick = state.tick;
  }
}


// =======================================
//               POLLING
// =======================================
async function pollState() {
  try {
    const state = await apiGet(API.state);
    renderState(state);
  } catch (err) {
    console.error("Error fetching state", err);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(pollState, 500);
}


// =======================================
//              CONTROLS
// =======================================
function setupControls() {
  // Demo
  document.getElementById("btn-init-demo").addEventListener("click", async () => {
    await apiPost(API.initDemo);
    lastTick = 0;
    document.getElementById("event-log").innerHTML = "";
    pollState();
  });

  // Run controls
  document.getElementById("btn-start").addEventListener("click", async () => {
    await apiPost(API.start);
    document.body.classList.remove("no-animations");
  });

  document.getElementById("btn-pause").addEventListener("click", async () => {
    await apiPost(API.pause);
    document.body.classList.add("no-animations");
  });

  document.getElementById("btn-step").addEventListener("click", async () => {
    await apiPost(API.step);
    pollState();
  });

  document.getElementById("btn-reset").addEventListener("click", async () => {
    await apiPost(API.reset);
    lastTick = 0;
    document.getElementById("event-log").innerHTML = "";
    pollState();
  });

  // Scheduler / Model config
  document.getElementById("btn-apply-config").addEventListener("click", async () => {
    const model = document.getElementById("select-model").value;
    const scheduler = document.getElementById("select-scheduler").value;
    const quantum = parseInt(document.getElementById("input-quantum").value, 10);

    await apiPost(API.setConfig, { model, scheduler, quantum });

    document.getElementById("badge-scheduler").textContent = `Scheduler: ${scheduler}`;
    document.getElementById("badge-quantum").textContent = `Quantum: ${quantum}`;
  });

  // Add thread
  document.getElementById("form-add-thread").addEventListener("submit", async (e) => {
    e.preventDefault();

    const name = document.getElementById("thread-name").value.trim() || null;
    const burst = parseInt(document.getElementById("thread-burst").value, 10);
    const priority = parseInt(document.getElementById("thread-priority").value, 10);

    await apiPost(API.addThread, { name, burst, priority });

    document.getElementById("thread-name").value = "";
    pollState();
  });

  // TAB SWITCHING (semaphore / monitor)
  document.getElementById("btn-tab-semaphores").onclick = () => {
    currentSyncMode = "semaphore";
    document.getElementById("sync-panel-semaphores").style.display = "block";
    document.getElementById("sync-panel-monitors").style.display = "none";
  };

  document.getElementById("btn-tab-monitors").onclick = () => {
    currentSyncMode = "monitor";
    document.getElementById("sync-panel-semaphores").style.display = "none";
    document.getElementById("sync-panel-monitors").style.display = "block";
  };
}


// =======================================
//                  INIT
// =======================================
window.addEventListener("DOMContentLoaded", async () => {
  setupControls();
  try {
    await apiPost(API.initDemo);
  } catch (err) {
    console.error("Failed to init demo", err);
  }
  startPolling();
});
