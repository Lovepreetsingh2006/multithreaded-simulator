const API = {
  state: "/api/state",
  start: "/api/start",
  pause: "/api/pause",
  step: "/api/step",
  reset: "/api/reset",
  initDemo: "/api/init_demo",
  addThread: "/api/add_thread",
  setConfig: "/api/set",
};

let pollTimer = null;
let lastTick = 0;

// =============================
//   SEMAPHORE FUNCTIONS
// =============================

function createSemaphore() {
  const name = document.getElementById("sem-name").value.trim();
  const init = parseInt(document.getElementById("sem-init").value, 10);

  if (!name) return alert("Enter semaphore name.");

  fetch("/api/semaphore/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name, initial: init }),
  }).then(() => refreshState());
}

function semaphoreWait(semName, threadId) {
  fetch("/api/semaphore/wait", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: semName, thread_id: threadId }),
  }).then(() => refreshState());
}

function semaphoreSignal(semName) {
  fetch("/api/semaphore/signal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: semName }),
  }).then(() => refreshState());
}

function refreshState() {
  pollState();
}

// =============================
//   API HELPERS
// =============================
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

// =============================
//  Build Thread Action Buttons
// =============================
function makeThreadActions(thread, semaphores) {
  if (thread.state === "TERMINATED") return "-";
  if (thread.state === "BLOCKED") return "<em>BLOCKED</em>";

  let html = "";

  for (let name of Object.keys(semaphores)) {
    html += `
      <button class="btn-primary" onclick="semaphoreWait('${name}', ${thread.id})">
        WAIT ${name}
      </button>
    `;
  }

  if (html.trim() === "") return "<em>No semaphores</em>";

  return html;
}

// =============================
//   UI UPDATE
// =============================
function renderState(state) {
  // Stats
  document.getElementById("stat-tick").textContent = state.tick;
  document.getElementById("stat-threads").textContent = state.threads.length;
  document.getElementById("stat-completed").textContent =
    state.stats.completed;
  document.getElementById("stat-context-switches").textContent =
    state.stats.context_switches;

  // Badges
  document.getElementById("badge-model").textContent = `Model: ${state.model}`;
  document.getElementById("badge-quantum").textContent = `Quantum: ${state.quantum}`;

  // Threads table
  const tbody = document.getElementById("threads-tbody");
  tbody.innerHTML = "";

  state.threads.forEach((t) => {
    const tr = document.createElement("tr");

    const isRunning = state.kernels.some((k) => k.current_thread === t.id);
    if (isRunning) {
      tr.classList.add("thread-row-running");
    }

    const stateClass = (() => {
      switch (t.state) {
        case "RUNNING": return "state-running";
        case "READY": return "state-ready";
        case "BLOCKED": return "state-blocked";
        case "TERMINATED": return "state-terminated";
      }
      return "state-ready";
    })();

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
      <td>${t.mapped_kernel === null ? "-" : t.mapped_kernel}</td>
      <td>${makeThreadActions(t, state.semaphores)}</td>
    `;

    tbody.appendChild(tr);
  });

  // CPU cores
  const coresGrid = document.getElementById("cores-grid");
  coresGrid.innerHTML = "";

  state.kernels.forEach((k) => {
    const busy = k.current_thread !== null;
    const threadObj = state.threads.find((t) => t.id === k.current_thread);

    const div = document.createElement("div");
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
            ? `<div class="core-thread-name">${threadObj.name}</div>
               <div class="thread-state-pill state-running" style="margin-top:4px;">
                 <span class="thread-state-dot"></span>
                 <span>RUNNING</span>
               </div>`
            : `<div class="core-thread-name" style="color:var(--muted);">No thread</div>`
        }
      </div>
    `;

    coresGrid.appendChild(div);
  });

  // =============================
  //   SEMAPHORES UI
  // =============================
  const semList = document.getElementById("sem-list");
  semList.innerHTML = "";

  for (let [name, sem] of Object.entries(state.semaphores)) {
    const div = document.createElement("div");
    div.className = "sem-card";

    const blocked = sem.blocked.length ? sem.blocked.join(", ") : "None";

    div.innerHTML = `
      <div class="sem-header">
        <span class="sem-name">${name}</span>
        <span class="sem-value ${sem.value > 0 ? "available" : "locked"}">
          <span class="value-icon">🔒</span>
          <span class="value-text">${sem.value}</span>
        </span>
      </div>

      <div class="sem-details">
        <div class="sem-blocked">
          <div class="blocked-label">Blocked Threads:</div>
          <div class="blocked-value">${blocked}</div>
        </div>
      </div>

      <div class="sem-actions">
        <button class="btn-primary" onclick="semaphoreSignal('${name}')">SIGNAL (V)</button>
      </div>
    `;

    semList.appendChild(div);
  }

  // =============================
  //   EVENT LOG
  // =============================
  if (state.tick !== lastTick) {
    const log = document.getElementById("event-log");
    const line = document.createElement("div");
    line.className = "event-line";

    const runningCount = state.threads.filter((t) => t.state === "RUNNING").length;
    const readyCount = state.threads.filter((t) => t.state === "READY").length;
    const blockedCount = state.threads.filter((t) => t.state === "BLOCKED").length;

    line.innerHTML = `Tick <span>${state.tick}</span>: RUN ${runningCount}, READY ${readyCount}, BLOCKED ${blockedCount}`;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;

    lastTick = state.tick;
  }
}

// =============================
//   POLLING LOOP
// =============================
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

// =============================
//   CONTROLS
// =============================
function setupControls() {
  document.getElementById("btn-init-demo").addEventListener("click", async () => {
    await apiPost(API.initDemo);
    lastTick = 0;
    document.getElementById("event-log").innerHTML = "";
    pollState();
  });

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

  document.getElementById("btn-apply-config").addEventListener("click", async () => {
    const model = document.getElementById("select-model").value;
    const scheduler = document.getElementById("select-scheduler").value;
    const quantum = parseInt(document.getElementById("input-quantum").value, 10);

    await apiPost(API.setConfig, { model, scheduler, quantum });

    document.getElementById("badge-scheduler").textContent = `Scheduler: ${scheduler}`;
    document.getElementById("badge-quantum").textContent = `Quantum: ${quantum}`;
  });

  document.getElementById("form-add-thread").addEventListener("submit", async (e) => {
    e.preventDefault();

    const name = document.getElementById("thread-name").value.trim() || null;
    const burst = parseInt(document.getElementById("thread-burst").value, 10);
    const priority = parseInt(document.getElementById("thread-priority").value, 10);

    await apiPost(API.addThread, { name, burst, priority });

    document.getElementById("thread-name").value = "";
    pollState();
  });
}

// =============================
//   INIT
// =============================
window.addEventListener("DOMContentLoaded", async () => {
  setupControls();
  try {
    await apiPost(API.initDemo);
  } catch (err) {
    console.error("Failed to init demo", err);
  }
  startPolling();
});
