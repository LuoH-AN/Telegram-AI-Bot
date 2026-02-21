/* Gemen Dashboard — Frontend Logic */
(function () {
  "use strict";

  // ── Auth ──
  const params = new URLSearchParams(location.search);
  const urlToken = params.get("token");
  let token = localStorage.getItem("gemen_token");

  // If a short token is in the URL, exchange it for a JWT
  if (urlToken) {
    history.replaceState(null, "", location.pathname);
    fetch("/api/auth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: urlToken }),
    })
      .then((r) => r.ok ? r.json() : Promise.reject(new Error("Token exchange failed")))
      .then((data) => {
        localStorage.setItem("gemen_token", data.token);
        location.reload();
      })
      .catch(() => {
        // Short token invalid/expired — show login
        document.getElementById("loginOverlay").style.display = "flex";
        document.getElementById("mainContent").style.display = "none";
      });
    return; // stop — page will reload after exchange
  }

  const $login = document.getElementById("loginOverlay");
  const $main = document.getElementById("mainContent");

  if (!token) {
    $login.style.display = "flex";
    $main.style.display = "none";
    return; // stop here
  }
  $login.style.display = "none";
  $main.style.display = "block";

  // ── API Client ──
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
        ...(opts.headers || {}),
      },
    });
    if (res.status === 401) {
      localStorage.removeItem("gemen_token");
      location.reload();
      throw new Error("Unauthorized");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    return res.json();
  }

  // ── Toast ──
  let toastTimer;
  function toast(msg, type) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast show" + (type ? " " + type : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.className = "toast"), 3000);
  }

  // ── Theme ──
  const THEME_KEY = "theme";
  function applyTheme(t) {
    if (t === "system") {
      const sys = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", sys);
    } else {
      document.documentElement.setAttribute("data-theme", t);
    }
    document.querySelectorAll(".theme-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.theme === t);
    });
    localStorage.setItem(THEME_KEY, t);
  }
  document.querySelectorAll(".theme-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
  });
  applyTheme(localStorage.getItem(THEME_KEY) || "dark");

  // ── Main Tabs ──
  const $subTabRow = document.getElementById("settingsSubTabs");

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const panel = document.getElementById("tab-" + btn.dataset.tab);
      if (panel) panel.classList.add("active");

      // Show/hide sub-tab row
      if ($subTabRow) {
        $subTabRow.style.display = btn.dataset.tab === "settings" ? "flex" : "none";
      }

      // Lazy-load tab data
      if (btn.dataset.tab === "logs") loadLogs();
      if (btn.dataset.tab === "usage") loadUsage();
    });
  });

  // ── Sub-Tabs ──
  document.querySelectorAll(".sub-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sub-tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".sub-tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const panel = document.getElementById("subtab-" + btn.dataset.subtab);
      if (panel) panel.classList.add("active");

      // Lazy-load sub-tab data
      if (btn.dataset.subtab === "providers") loadProviders();
      if (btn.dataset.subtab === "conversations") loadConversationPersonas();
    });
  });

  // ═════════════════════════════
  //  SETTINGS — Save logic
  // ═════════════════════════════

  const SETTINGS_FIELDS = [
    "base_url", "model", "temperature", "token_limit", "title_model",
    "tts_voice", "tts_style", "tts_endpoint",
  ];
  const ALL_TOOLS = ["memory", "search", "fetch", "wikipedia", "tts"];

  async function loadSettings() {
    try {
      const data = await api("/api/settings");
      SETTINGS_FIELDS.forEach((key) => {
        const el = document.getElementById("cfg-" + key);
        if (el && data[key] !== undefined && data[key] !== null) {
          el.value = data[key];
        }
      });
      renderToolGrid(data.enabled_tools || "");
    } catch (e) {
      toast("Failed to load settings: " + e.message, "error");
    }
  }

  function renderToolGrid(enabledStr) {
    const enabled = new Set(enabledStr.split(",").map((s) => s.trim()).filter(Boolean));
    const grid = document.getElementById("toolGrid");
    grid.innerHTML = "";
    ALL_TOOLS.forEach((tool) => {
      const label = document.createElement("label");
      label.className = "tool-toggle";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = enabled.has(tool);
      cb.dataset.tool = tool;
      const span = document.createElement("span");
      span.textContent = tool;
      label.appendChild(cb);
      label.appendChild(span);
      grid.appendChild(label);
    });
  }

  function collectSettingsBody() {
    const body = {};
    SETTINGS_FIELDS.forEach((key) => {
      const el = document.getElementById("cfg-" + key);
      if (!el) return;
      let val = el.value.trim();
      if (key === "temperature") val = parseFloat(val) || 0;
      else if (key === "token_limit") val = parseInt(val, 10) || 0;
      body[key] = val;
    });
    // Collect enabled tools
    const tools = [];
    document.querySelectorAll("#toolGrid input[type=checkbox]").forEach((cb) => {
      if (cb.checked) tools.push(cb.dataset.tool);
    });
    body.enabled_tools = tools.join(",");
    return body;
  }

  async function saveSettings() {
    try {
      const body = collectSettingsBody();
      await api("/api/settings", { method: "PUT", body: JSON.stringify(body) });
      toast("Settings saved", "success");
    } catch (e) {
      toast("Save failed: " + e.message, "error");
    }
  }

  // Wire all save buttons to the same save function
  document.getElementById("btnSaveSettings").addEventListener("click", saveSettings);
  document.getElementById("btnSaveTools").addEventListener("click", saveSettings);
  document.getElementById("btnSaveTTS").addEventListener("click", saveSettings);

  // ═════════════════════════════
  //  PERSONAS
  // ═════════════════════════════

  async function loadPersonas() {
    try {
      const data = await api("/api/personas");
      const list = document.getElementById("personaList");
      list.innerHTML = "";
      const names = Object.keys(data.personas).sort((a, b) =>
        a === "default" ? -1 : b === "default" ? 1 : a.localeCompare(b)
      );
      names.forEach((name) => {
        const p = data.personas[name];
        const card = document.createElement("div");
        card.className = "persona-card";

        const header = document.createElement("div");
        header.className = "persona-card-header";

        const nameEl = document.createElement("div");
        nameEl.className = "persona-card-name";
        nameEl.textContent = name;
        if (name === data.current) {
          const badge = document.createElement("span");
          badge.className = "badge badge-green";
          badge.textContent = "active";
          badge.style.marginLeft = "8px";
          nameEl.appendChild(badge);
        }

        const actions = document.createElement("div");
        actions.className = "action-row";

        const saveBtn = document.createElement("button");
        saveBtn.className = "btn-sm outline";
        saveBtn.textContent = "Save";
        saveBtn.addEventListener("click", async () => {
          const ta = card.querySelector("textarea");
          try {
            await api("/api/personas/" + encodeURIComponent(name), {
              method: "PUT",
              body: JSON.stringify({ system_prompt: ta.value }),
            });
            toast("Persona updated", "success");
          } catch (e) {
            toast("Update failed: " + e.message, "error");
          }
        });
        actions.appendChild(saveBtn);

        if (name !== "default") {
          const delBtn = document.createElement("button");
          delBtn.className = "btn-sm danger";
          delBtn.textContent = "Delete";
          delBtn.addEventListener("click", async () => {
            if (!confirm("Delete persona '" + name + "'?")) return;
            try {
              await api("/api/personas/" + encodeURIComponent(name), { method: "DELETE" });
              toast("Persona deleted", "success");
              loadPersonas();
            } catch (e) {
              toast("Delete failed: " + e.message, "error");
            }
          });
          actions.appendChild(delBtn);
        }

        header.appendChild(nameEl);
        header.appendChild(actions);
        card.appendChild(header);

        const promptWrap = document.createElement("div");
        promptWrap.className = "persona-card-prompt";
        const ta = document.createElement("textarea");
        ta.className = "server-input";
        ta.rows = 3;
        ta.value = p.system_prompt || "";
        promptWrap.appendChild(ta);
        card.appendChild(promptWrap);

        list.appendChild(card);
      });
    } catch (e) {
      toast("Failed to load personas: " + e.message, "error");
    }
  }

  document.getElementById("btnCreatePersona").addEventListener("click", async () => {
    const nameInput = document.getElementById("newPersonaName");
    const name = nameInput.value.trim();
    if (!name) return toast("Enter a persona name", "error");
    try {
      await api("/api/personas", { method: "POST", body: JSON.stringify({ name }) });
      nameInput.value = "";
      toast("Persona created", "success");
      loadPersonas();
    } catch (e) {
      toast("Create failed: " + e.message, "error");
    }
  });

  // ═════════════════════════════
  //  PROVIDERS
  // ═════════════════════════════

  async function loadProviders() {
    try {
      const data = await api("/api/providers");
      const list = document.getElementById("providerList");
      const empty = document.getElementById("providerEmpty");
      list.innerHTML = "";
      const names = Object.keys(data.providers);
      if (!names.length) {
        empty.style.display = "block";
        return;
      }
      empty.style.display = "none";
      names.sort().forEach((name) => {
        const p = data.providers[name];
        const card = document.createElement("div");
        card.className = "provider-card";

        const header = document.createElement("div");
        header.className = "provider-card-header";

        const nameEl = document.createElement("div");
        nameEl.className = "provider-card-name";
        nameEl.textContent = name;

        const actions = document.createElement("div");
        actions.className = "action-row";

        // Load button
        const loadBtn = document.createElement("button");
        loadBtn.className = "btn-sm accent";
        loadBtn.textContent = "Load";
        loadBtn.addEventListener("click", async () => {
          try {
            await api("/api/providers/" + encodeURIComponent(name) + "/load", { method: "POST" });
            toast("Provider loaded — settings updated", "success");
            loadSettings();
          } catch (e) {
            toast("Load failed: " + e.message, "error");
          }
        });
        actions.appendChild(loadBtn);

        // Delete button
        const delBtn = document.createElement("button");
        delBtn.className = "btn-sm danger";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", async () => {
          if (!confirm("Delete provider '" + name + "'?")) return;
          try {
            await api("/api/providers/" + encodeURIComponent(name), { method: "DELETE" });
            toast("Provider deleted", "success");
            loadProviders();
          } catch (e) {
            toast("Delete failed: " + e.message, "error");
          }
        });
        actions.appendChild(delBtn);

        header.appendChild(nameEl);
        header.appendChild(actions);
        card.appendChild(header);

        // Details
        const details = [
          { label: "base_url", value: p.base_url },
          { label: "model", value: p.model },
          { label: "api_key", value: p.api_key },
        ];
        details.forEach((d) => {
          if (d.value) {
            const det = document.createElement("div");
            det.className = "provider-card-detail";
            det.textContent = d.label + ": " + d.value;
            card.appendChild(det);
          }
        });

        list.appendChild(card);
      });
    } catch (e) {
      toast("Failed to load providers: " + e.message, "error");
    }
  }

  document.getElementById("btnCreateProvider").addEventListener("click", async () => {
    const name = document.getElementById("prov-name").value.trim();
    const apiKey = document.getElementById("prov-api_key").value.trim();
    const baseUrl = document.getElementById("prov-base_url").value.trim();
    const model = document.getElementById("prov-model").value.trim();
    if (!name) return toast("Enter a provider name", "error");
    if (!apiKey) return toast("Enter an API key", "error");
    if (!baseUrl) return toast("Enter a base URL", "error");
    try {
      await api("/api/providers", {
        method: "POST",
        body: JSON.stringify({ name, api_key: apiKey, base_url: baseUrl, model }),
      });
      document.getElementById("prov-name").value = "";
      document.getElementById("prov-api_key").value = "";
      document.getElementById("prov-base_url").value = "";
      document.getElementById("prov-model").value = "";
      toast("Provider created", "success");
      loadProviders();
    } catch (e) {
      toast("Create failed: " + e.message, "error");
    }
  });

  // ═════════════════════════════
  //  CONVERSATIONS (Sessions)
  // ═════════════════════════════

  async function loadConversationPersonas() {
    try {
      const data = await api("/api/personas");
      const select = document.getElementById("convPersonaSelect");
      const current = select.value;
      select.innerHTML = '<option value="">Select persona...</option>';
      const names = Object.keys(data.personas).sort((a, b) =>
        a === "default" ? -1 : b === "default" ? 1 : a.localeCompare(b)
      );
      names.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
      });
      // Restore previous selection
      if (current && names.includes(current)) {
        select.value = current;
        loadSessions(current);
      }
    } catch (e) {
      toast("Failed to load personas: " + e.message, "error");
    }
  }

  document.getElementById("convPersonaSelect").addEventListener("change", (e) => {
    const persona = e.target.value;
    if (persona) {
      loadSessions(persona);
    } else {
      document.getElementById("sessionList").innerHTML = "";
      document.getElementById("sessionsEmpty").style.display = "none";
    }
  });

  async function loadSessions(persona) {
    try {
      const data = await api("/api/sessions?persona=" + encodeURIComponent(persona));
      const list = document.getElementById("sessionList");
      const empty = document.getElementById("sessionsEmpty");
      list.innerHTML = "";
      if (!data.sessions.length) {
        empty.style.display = "block";
        return;
      }
      empty.style.display = "none";
      // Show newest first
      const sessions = data.sessions.slice().reverse();
      sessions.forEach((s) => {
        const card = document.createElement("div");
        card.className = "session-card";

        const header = document.createElement("div");
        header.className = "session-card-header";

        const titleEl = document.createElement("div");
        titleEl.className = "session-card-title";
        titleEl.textContent = s.title || "Untitled";

        const metaRow = document.createElement("div");
        metaRow.style.display = "flex";
        metaRow.style.alignItems = "center";
        metaRow.style.gap = "8px";

        const meta = document.createElement("div");
        meta.className = "session-card-meta";
        const time = s.created_at ? new Date(s.created_at).toLocaleString() : "";
        meta.textContent = time + " · " + s.message_count + " msgs";

        const delBtn = document.createElement("button");
        delBtn.className = "btn-sm danger";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (!confirm("Delete this conversation?")) return;
          try {
            await api("/api/sessions/" + s.id, { method: "DELETE" });
            toast("Session deleted", "success");
            loadSessions(persona);
          } catch (err) {
            toast("Delete failed: " + err.message, "error");
          }
        });

        metaRow.appendChild(meta);
        metaRow.appendChild(delBtn);

        header.appendChild(titleEl);
        header.appendChild(metaRow);
        card.appendChild(header);

        // Messages area (lazy-loaded on click)
        const msgArea = document.createElement("div");
        msgArea.className = "session-messages";
        card.appendChild(msgArea);

        card.addEventListener("click", async () => {
          // Toggle
          if (msgArea.classList.contains("open")) {
            msgArea.classList.remove("open");
            return;
          }
          // Load messages
          try {
            const msgData = await api("/api/sessions/" + s.id + "/messages");
            msgArea.innerHTML = "";
            if (!msgData.messages.length) {
              msgArea.innerHTML = '<div class="empty-state" style="padding:12px">No messages.</div>';
            } else {
              msgData.messages.forEach((m) => {
                const msgEl = document.createElement("div");
                msgEl.className = "session-msg";
                const roleEl = document.createElement("div");
                roleEl.className = "session-msg-role " + m.role;
                roleEl.textContent = m.role;
                const contentEl = document.createElement("div");
                contentEl.className = "session-msg-content";
                contentEl.textContent = m.content;
                msgEl.appendChild(roleEl);
                msgEl.appendChild(contentEl);
                msgArea.appendChild(msgEl);
              });
            }
            msgArea.classList.add("open");
          } catch (err) {
            toast("Failed to load messages: " + err.message, "error");
          }
        });

        list.appendChild(card);
      });
    } catch (e) {
      toast("Failed to load sessions: " + e.message, "error");
    }
  }

  // ═════════════════════════════
  //  LOGS TAB
  // ═════════════════════════════

  let logsPage = 1;
  const LOGS_LIMIT = 50;

  document.getElementById("logTypeFilter").addEventListener("change", () => {
    logsPage = 1;
    loadLogs();
  });

  async function loadLogs() {
    const type = document.getElementById("logTypeFilter").value;
    const qs = new URLSearchParams({ page: logsPage, limit: LOGS_LIMIT });
    if (type) qs.set("type", type);
    try {
      const data = await api("/api/logs?" + qs);
      const body = document.getElementById("logsBody");
      const empty = document.getElementById("logsEmpty");
      const tableWrap = document.getElementById("logsTableWrap");
      body.innerHTML = "";
      if (!data.logs.length) {
        tableWrap.style.display = "none";
        empty.style.display = "block";
      } else {
        tableWrap.style.display = "";
        empty.style.display = "none";
        data.logs.forEach((log) => {
          const tr = document.createElement("tr");
          const time = log.created_at ? new Date(log.created_at).toLocaleString() : "";
          const typeBadge = log.log_type === "error"
            ? '<span class="badge badge-red">error</span>'
            : '<span class="badge badge-accent">ai</span>';
          const tools = log.tool_calls ? JSON.parse(log.tool_calls).join(", ") : "";
          const latency = log.latency_ms != null ? log.latency_ms + "ms" : "";
          const tokens = log.total_tokens != null ? log.total_tokens : "";
          const error = log.error_message
            ? (log.error_message.length > 60 ? log.error_message.slice(0, 60) + "..." : log.error_message)
            : "";
          tr.innerHTML =
            "<td>" + esc(time) + "</td>" +
            "<td>" + typeBadge + "</td>" +
            "<td>" + esc(log.model || "") + "</td>" +
            "<td>" + esc(String(tokens)) + "</td>" +
            "<td>" + esc(tools) + "</td>" +
            "<td>" + esc(latency) + "</td>" +
            "<td>" + esc(log.persona_name || "") + "</td>" +
            "<td>" + esc(error) + "</td>";
          body.appendChild(tr);
        });
      }
      renderLogsPagination(data.page, data.pages);
    } catch (e) {
      toast("Failed to load logs: " + e.message, "error");
    }
  }

  function renderLogsPagination(current, total) {
    const el = document.getElementById("logsPagination");
    el.innerHTML = "";
    if (total <= 1) return;
    const prev = document.createElement("button");
    prev.className = "btn-sm outline";
    prev.textContent = "Prev";
    prev.disabled = current <= 1;
    prev.addEventListener("click", () => { logsPage--; loadLogs(); });

    const info = document.createElement("span");
    info.className = "page-info";
    info.textContent = current + " / " + total;

    const next = document.createElement("button");
    next.className = "btn-sm outline";
    next.textContent = "Next";
    next.disabled = current >= total;
    next.addEventListener("click", () => { logsPage++; loadLogs(); });

    el.appendChild(prev);
    el.appendChild(info);
    el.appendChild(next);
  }

  // ═════════════════════════════
  //  USAGE TAB
  // ═════════════════════════════

  async function loadUsage() {
    try {
      const data = await api("/api/usage");
      const stats = document.getElementById("usageStats");
      const limit = data.token_limit || 0;
      const total = data.total_all_personas || 0;
      const remaining = data.remaining;
      const pct = data.usage_percentage;

      let html =
        '<div class="stat-card">' +
          '<div class="stat-label">Total Tokens Used</div>' +
          '<div class="stat-value accent">' + formatNum(total) + "</div>" +
        "</div>" +
        '<div class="stat-card">' +
          '<div class="stat-label">Token Limit</div>' +
          '<div class="stat-value">' + (limit ? formatNum(limit) : "Unlimited") + "</div>" +
        "</div>";

      if (limit) {
        html +=
          '<div class="stat-card">' +
            '<div class="stat-label">Remaining</div>' +
            '<div class="stat-value green">' + formatNum(remaining) + "</div>" +
          "</div>" +
          '<div class="stat-card">' +
            '<div class="stat-label">Usage</div>' +
            '<div class="stat-value">' + (pct != null ? pct.toFixed(1) + "%" : "N/A") + "</div>" +
            '<div class="progress-bar"><div class="progress-bar-fill" style="width:' + (pct || 0) + '%;background-color:' + usageColor(pct || 0) + '"></div></div>' +
          "</div>";
      }
      stats.innerHTML = html;

      // Per-persona table
      const body = document.getElementById("usageBody");
      body.innerHTML = "";
      (data.per_persona || []).forEach((p) => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" + esc(p.persona) + "</td>" +
          "<td>" + formatNum(p.prompt_tokens) + "</td>" +
          "<td>" + formatNum(p.completion_tokens) + "</td>" +
          "<td>" + formatNum(p.total_tokens) + "</td>";
        body.appendChild(tr);
      });
    } catch (e) {
      toast("Failed to load usage: " + e.message, "error");
    }
  }

  // ── Helpers ──
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  function formatNum(n) {
    if (n == null) return "0";
    return Number(n).toLocaleString();
  }
  function usageColor(pct) {
    // Light green (low) → dark red (high)
    const p = Math.min(100, Math.max(0, pct)) / 100;
    const r = Math.round(52 + (185 - 52) * p);   // 34→b9 (green→red)
    const g = Math.round(211 - (211 - 50) * p);   // d3→32
    const b = Math.round(153 - (153 - 50) * p);   // 99→32
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  // ── Init ──
  loadSettings();
  loadPersonas();
})();
