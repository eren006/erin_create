const projectGrid = document.getElementById("project-grid");
const emptyState = document.getElementById("empty-state");
const historyList = document.getElementById("history-list");
const historyEmpty = document.getElementById("history-empty");

const addModal = document.getElementById("add-modal");
const addForm = document.getElementById("add-form");
const formError = document.getElementById("form-error");

const outputModal = document.getElementById("output-modal");
const outputTitle = document.getElementById("output-title");
const outputStatus = document.getElementById("output-status");
const outputBody = document.getElementById("output-body");

let projectsCache = [];
const expandedHistory = new Set();

function timeAgo(isoString) {
  if (!isoString) return "从未";
  const then = new Date(isoString.replace(" ", "T"));
  const diffMs = Date.now() - then.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

function statusBadge(status) {
  if (status === "success") return `<span class="badge badge-success">成功</span>`;
  if (status === "failed") return `<span class="badge badge-failed">失败</span>`;
  return `<span class="badge badge-neutral">从未部署</span>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

async function loadProjects() {
  const res = await fetch("/api/projects");
  projectsCache = await res.json();
  renderProjects();
}

function renderProjects() {
  projectGrid.innerHTML = "";
  emptyState.hidden = projectsCache.length > 0;

  for (const p of projectsCache) {
    const card = document.createElement("div");
    card.className = "project-card";

    const lastRun = p.last_run;
    const status = lastRun ? lastRun.status : null;

    card.innerHTML = `
      <div class="project-card-head">
        <div>
          <div class="project-name">${escapeHtml(p.name)}</div>
          <div class="project-path">${escapeHtml(p.path)}</div>
        </div>
        <button class="btn-danger-text" data-action="delete" data-id="${p.id}" title="删除项目">删除</button>
      </div>
      <div class="status-row">
        ${statusBadge(status)}
        <span>${lastRun ? timeAgo(lastRun.finished_at || lastRun.started_at) : "从未"}</span>
      </div>
      ${lastRun && lastRun.commit_log ? `<div class="commit-preview">${escapeHtml(lastRun.commit_log)}</div>` : ""}
      <div class="card-actions">
        <div class="card-actions-left">
          <button class="btn btn-primary" data-action="deploy" data-id="${p.id}" ${p.is_running ? "disabled" : ""}>
            ${p.is_running ? "部署中…" : "Deploy"}
          </button>
        </div>
        <button class="history-toggle" data-action="toggle-history" data-id="${p.id}">
          ${expandedHistory.has(p.id) ? "收起历史 ▲" : "查看历史 ▼"}
        </button>
      </div>
      <div class="inline-history" data-history-for="${p.id}" ${expandedHistory.has(p.id) ? "" : "hidden"}></div>
    `;
    projectGrid.appendChild(card);

    if (expandedHistory.has(p.id)) {
      loadInlineHistory(p.id);
    }
  }
}

async function loadInlineHistory(projectId) {
  const container = document.querySelector(`[data-history-for="${projectId}"]`);
  if (!container) return;
  const res = await fetch(`/api/projects/${projectId}/history`);
  const runs = await res.json();
  if (runs.length === 0) {
    container.innerHTML = `<div class="inline-history-row">还没有部署记录</div>`;
    return;
  }
  container.innerHTML = runs.map(r => `
    <div class="inline-history-row">
      <span>${statusBadge(r.status)} ${escapeHtml((r.commit_log || "").split("\n")[0] || "(无提交记录)")}</span>
      <span>${timeAgo(r.finished_at || r.started_at)}</span>
    </div>
  `).join("");
}

async function loadGlobalHistory() {
  const res = await fetch("/api/history");
  const runs = await res.json();
  historyEmpty.hidden = runs.length > 0;
  historyList.innerHTML = runs.map(r => `
    <div class="history-item">
      <div class="history-item-head">
        <strong>${escapeHtml(r.project_name)}</strong>
        ${statusBadge(r.status)}
        <span class="history-item-time">${timeAgo(r.finished_at || r.started_at)}</span>
      </div>
      <div class="history-commits">${escapeHtml(r.commit_log || "(无提交记录)")}</div>
    </div>
  `).join("");
}

async function deploy(projectId) {
  renderProjects();
  const res = await fetch(`/api/projects/${projectId}/deploy`, { method: "POST" });
  const data = await res.json();

  if (!res.ok) {
    alert(data.error || "部署失败");
    await loadProjects();
    return;
  }

  await loadProjects();
  showOutput(data.name, data.last_status, data.last_output);
}

function showOutput(name, status, output) {
  outputTitle.textContent = `部署输出 · ${name}`;
  outputStatus.innerHTML = statusBadge(status);
  outputBody.textContent = output || "(无输出)";
  outputModal.hidden = false;
}

async function deleteProject(projectId) {
  if (!confirm("确定要删除这个项目吗?部署记录也会一起删掉。")) return;
  await fetch(`/api/projects/${projectId}`, { method: "DELETE" });
  await loadProjects();
}

projectGrid.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = Number(btn.dataset.id);
  const action = btn.dataset.action;

  if (action === "deploy") deploy(id);
  if (action === "delete") deleteProject(id);
  if (action === "toggle-history") {
    if (expandedHistory.has(id)) {
      expandedHistory.delete(id);
    } else {
      expandedHistory.add(id);
    }
    renderProjects();
  }
});

document.getElementById("add-project-btn").addEventListener("click", () => {
  addForm.reset();
  document.getElementById("f-script").value = "deploy.sh";
  formError.hidden = true;
  addModal.hidden = false;
});

document.getElementById("cancel-add").addEventListener("click", () => {
  addModal.hidden = true;
});

addForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;
  const payload = {
    name: document.getElementById("f-name").value,
    path: document.getElementById("f-path").value,
    deploy_script: document.getElementById("f-script").value || "deploy.sh",
  };
  const res = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    formError.textContent = data.error || "添加失败";
    formError.hidden = false;
    return;
  }
  addModal.hidden = true;
  await loadProjects();
});

document.getElementById("close-output").addEventListener("click", () => {
  outputModal.hidden = true;
});

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "history") loadGlobalHistory();
  });
});

loadProjects();
