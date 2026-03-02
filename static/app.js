(function () {
  "use strict";

  const DEFAULT_TOOLS = ["memory", "search", "fetch", "wikipedia", "tts", "shell", "cron", "playwright", "crawl4ai", "browser_agent"];
  const SETTINGS_TEXT_FIELDS = [
    "base_url",
    "model",
    "reasoning_effort",
    "global_prompt",
    "title_model",
    "cron_model",
    "tts_voice",
    "tts_style",
    "tts_endpoint",
  ];

  const state = {
    token: null,
    activePane: "general",
    personas: null,
    providers: null,
    usage: null,
    logsPage: 1,
    logsPages: 1,
    selectedModel: "",
    availableTools: DEFAULT_TOOLS.slice(),
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function formatNum(n) {
    if (n == null || Number.isNaN(Number(n))) {
      return "0";
    }
    return Number(n).toLocaleString();
  }

  function formatDate(value) {
    if (!value) {
      return "-";
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) {
      return String(value);
    }
    return d.toLocaleString();
  }

  function toIsoFromDatetimeLocal(value) {
    if (!value) {
      return null;
    }
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) {
      return null;
    }
    return d.toISOString();
  }

  let toastTimer = null;
  function toast(message, type) {
    const node = $("toast");
    node.textContent = message;
    node.className = "toast show" + (type ? " " + type : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      node.className = "toast";
    }, 2600);
  }

  function logout() {
    localStorage.removeItem("gemen_token");
    location.reload();
  }

  async function request(path, options = {}, responseType = "json") {
    const headers = {
      Authorization: "Bearer " + state.token,
      ...(options.headers || {}),
    };

    const hasBody = options.body !== undefined && options.body !== null;
    const isFormData = hasBody && options.body instanceof FormData;
    if (!headers["Content-Type"] && hasBody && !isFormData) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch(path, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      logout();
      throw new Error("Unauthorized");
    }

    if (!res.ok) {
      let detail = "Request failed";
      try {
        const body = await res.json();
        detail = body.detail || body.error || JSON.stringify(body);
      } catch {
        try {
          detail = await res.text();
        } catch {
          detail = res.statusText || detail;
        }
      }
      throw new Error(detail);
    }

    if (responseType === "blob") {
      return res.blob();
    }
    if (responseType === "text") {
      return res.text();
    }
    if (res.status === 204) {
      return null;
    }
    return res.json();
  }

  async function apiGet(path) {
    return request(path, { method: "GET" });
  }

  async function apiPost(path, payload) {
    return request(path, { method: "POST", body: JSON.stringify(payload || {}) });
  }

  async function apiPut(path, payload) {
    return request(path, { method: "PUT", body: JSON.stringify(payload || {}) });
  }

  async function apiDelete(path) {
    return request(path, { method: "DELETE" });
  }

  function parseIncomingShortToken() {
    const queryToken = new URLSearchParams(location.search).get("token");
    const hashToken = new URLSearchParams((location.hash || "").replace(/^#/, "")).get("token");
    return queryToken || hashToken;
  }

  async function exchangeShortToken(shortToken) {
    const response = await fetch("/api/auth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: shortToken }),
    });
    if (!response.ok) {
      throw new Error("Token exchange failed");
    }
    const data = await response.json();
    return data.token;
  }

  async function setupAuth() {
    const shortToken = parseIncomingShortToken();
    if (shortToken) {
      history.replaceState(null, "", location.pathname);
      try {
        const jwtToken = await exchangeShortToken(shortToken);
        localStorage.setItem("gemen_token", jwtToken);
        location.reload();
        return false;
      } catch {
        localStorage.removeItem("gemen_token");
      }
    }

    state.token = localStorage.getItem("gemen_token");
    if (!state.token) {
      $("loginOverlay").style.display = "flex";
      $("mainApp").hidden = true;
      return false;
    }

    $("loginOverlay").style.display = "none";
    $("mainApp").hidden = false;
    return true;
  }

  function getAvailableTools() {
    if (!Array.isArray(state.availableTools) || !state.availableTools.length) {
      return DEFAULT_TOOLS.slice();
    }

    const seen = new Set();
    const tools = [];
    state.availableTools.forEach((tool) => {
      const name = String(tool || "").trim().toLowerCase();
      if (!name || seen.has(name)) {
        return;
      }
      seen.add(name);
      tools.push(name);
    });
    return tools.length ? tools : DEFAULT_TOOLS.slice();
  }

  function normalizeToolsCsv(csv) {
    const available = getAvailableTools();
    const seen = new Set();
    const list = [];
    String(csv || "")
      .split(",")
      .map((x) => x.trim().toLowerCase())
      .forEach((tool) => {
        if (!tool || !available.includes(tool) || seen.has(tool)) {
          return;
        }
        seen.add(tool);
        list.push(tool);
      });
    return list.join(",");
  }

  function renderToolGrid(containerId, toolsCsv) {
    const selected = new Set(normalizeToolsCsv(toolsCsv).split(",").filter(Boolean));
    const node = $(containerId);
    node.innerHTML = "";

    getAvailableTools().forEach((tool) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tool-item";
      button.dataset.tool = tool;
      button.textContent = tool;

      const active = selected.has(tool);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");

      button.addEventListener("click", () => {
        const next = !button.classList.contains("is-active");
        button.classList.toggle("is-active", next);
        button.setAttribute("aria-pressed", next ? "true" : "false");
      });

      node.appendChild(button);
    });
  }

  function collectToolCsv(containerId) {
    const values = [];
    document.querySelectorAll("#" + containerId + " .tool-item.is-active").forEach((button) => {
      values.push(button.dataset.tool || "");
    });
    return normalizeToolsCsv(values.join(","));
  }

  async function loadSettings() {
    const settings = await apiGet("/api/settings");
    if (Array.isArray(settings.available_tools) && settings.available_tools.length) {
      state.availableTools = settings.available_tools;
    }

    SETTINGS_TEXT_FIELDS.forEach((field) => {
      const input = $("cfg-" + field);
      if (input) {
        input.value = settings[field] == null ? "" : String(settings[field]);
      }
    });

    $("cfg-temperature").value = settings.temperature == null ? "" : String(settings.temperature);
    $("cfg-stream_mode").value = settings.stream_mode || "";
    $("cfg-api_key").value = "";
    $("cfg-api_key-mask").textContent = settings.has_api_key
      ? "Current key: " + (settings.api_key_masked || "***")
      : "Not set";

    renderToolGrid("toolGrid", settings.enabled_tools || "");
    renderToolGrid("cronToolGrid", settings.cron_enabled_tools || "");
  }

  async function saveSettings() {
    const body = {
      temperature: Number($("cfg-temperature").value || 0.7),
      stream_mode: $("cfg-stream_mode").value.trim(),
      enabled_tools: collectToolCsv("toolGrid"),
      cron_enabled_tools: collectToolCsv("cronToolGrid"),
    };

    SETTINGS_TEXT_FIELDS.forEach((field) => {
      body[field] = $("cfg-" + field).value.trim();
    });

    const apiKey = $("cfg-api_key").value.trim();
    if (apiKey) {
      body.api_key = apiKey;
    }

    await apiPut("/api/settings", body);
    $("cfg-api_key").value = "";
    toast("Settings saved", "success");
    await loadSettings();
  }

  function sortedPersonaNames() {
    if (!state.personas) {
      return [];
    }
    return Object.keys(state.personas.personas || {}).sort((a, b) => {
      if (a === "default") return -1;
      if (b === "default") return 1;
      return a.localeCompare(b);
    });
  }

  function refreshPersonaSelectors() {
    const names = sortedPersonaNames();

    const sessionSelect = $("sessionPersonaSelect");
    const prevSession = sessionSelect.value;
    sessionSelect.innerHTML = "";
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      sessionSelect.appendChild(option);
    });
    if (names.includes(prevSession)) {
      sessionSelect.value = prevSession;
    } else if (state.personas && names.includes(state.personas.current)) {
      sessionSelect.value = state.personas.current;
    }

    const usageSelect = $("usagePersonaSelect");
    const prevUsage = usageSelect.value;
    usageSelect.innerHTML = "";
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      usageSelect.appendChild(option);
    });
    if (names.includes(prevUsage)) {
      usageSelect.value = prevUsage;
    } else if (state.usage && names.includes(state.usage.current_persona)) {
      usageSelect.value = state.usage.current_persona;
    }
  }

  async function loadPersonas() {
    const data = await apiGet("/api/personas");
    state.personas = data;

    const tbody = $("personaTableBody");
    tbody.innerHTML = "";

    sortedPersonaNames().forEach((name) => {
      const persona = data.personas[name];
      const row = document.createElement("tr");

      const currentCell = document.createElement("td");
      currentCell.className = "row-current";
      currentCell.textContent = data.current === name ? "*" : "";

      const nameCell = document.createElement("td");
      nameCell.textContent = name;

      const promptCell = document.createElement("td");
      const textarea = document.createElement("textarea");
      textarea.rows = 3;
      textarea.value = persona.system_prompt || "";
      promptCell.appendChild(textarea);

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const switchBtn = document.createElement("button");
      switchBtn.className = "btn";
      switchBtn.type = "button";
      switchBtn.textContent = "Switch";
      switchBtn.addEventListener("click", async () => {
        try {
          await apiPost("/api/personas/" + encodeURIComponent(name) + "/switch", {});
          toast("Switched persona: " + name, "success");
          await loadPersonas();
          await loadUsage();
          $("sessionPersonaSelect").value = name;
          await loadSessions(name);
        } catch (err) {
          toast("Switch failed: " + err.message, "error");
        }
      });

      const saveBtn = document.createElement("button");
      saveBtn.className = "btn";
      saveBtn.type = "button";
      saveBtn.textContent = "Save Prompt";
      saveBtn.addEventListener("click", async () => {
        try {
          await apiPut("/api/personas/" + encodeURIComponent(name), {
            system_prompt: textarea.value,
          });
          toast("Prompt updated: " + name, "success");
          await loadPersonas();
        } catch (err) {
          toast("Update failed: " + err.message, "error");
        }
      });

      actions.appendChild(switchBtn);
      actions.appendChild(saveBtn);

      if (name !== "default") {
        const delBtn = document.createElement("button");
        delBtn.className = "btn danger";
        delBtn.type = "button";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", async () => {
          if (!confirm("Delete persona '" + name + "'?")) {
            return;
          }
          try {
            await apiDelete("/api/personas/" + encodeURIComponent(name));
            toast("Persona deleted", "success");
            await loadPersonas();
            await loadUsage();
            await loadSessions($("sessionPersonaSelect").value);
          } catch (err) {
            toast("Delete failed: " + err.message, "error");
          }
        });
        actions.appendChild(delBtn);
      }

      actionCell.appendChild(actions);

      row.appendChild(currentCell);
      row.appendChild(nameCell);
      row.appendChild(promptCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    refreshPersonaSelectors();
    refreshModelProviderSelect();
  }

  async function createPersona() {
    const name = $("persona-create-name").value.trim();
    const prompt = $("persona-create-prompt").value.trim();

    if (!name) {
      toast("Persona name required", "error");
      return;
    }

    await apiPost("/api/personas", {
      name,
      system_prompt: prompt || undefined,
    });

    $("persona-create-name").value = "";
    $("persona-create-prompt").value = "";
    toast("Persona created", "success");
    await loadPersonas();
  }

  async function loadSessions(personaName) {
    const persona = personaName || $("sessionPersonaSelect").value;
    if (!persona) {
      $("sessionTableBody").innerHTML = "";
      $("sessionMessages").textContent = "No persona selected.";
      return;
    }

    const data = await apiGet("/api/sessions?persona=" + encodeURIComponent(persona));
    const tbody = $("sessionTableBody");
    tbody.innerHTML = "";

    const sessions = (data.sessions || []).slice().reverse();
    sessions.forEach((session) => {
      const row = document.createElement("tr");

      const currentCell = document.createElement("td");
      currentCell.className = "row-current";
      currentCell.textContent = session.is_current ? "*" : "";

      const titleCell = document.createElement("td");
      const titleInput = document.createElement("input");
      titleInput.type = "text";
      titleInput.value = session.title || "New Chat";
      titleCell.appendChild(titleInput);

      const msgCell = document.createElement("td");
      msgCell.textContent = formatNum(session.message_count);

      const createdCell = document.createElement("td");
      createdCell.textContent = formatDate(session.created_at);

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const viewBtn = document.createElement("button");
      viewBtn.className = "btn";
      viewBtn.type = "button";
      viewBtn.textContent = "View";
      viewBtn.addEventListener("click", async () => {
        await loadSessionMessages(session.id);
      });

      const switchBtn = document.createElement("button");
      switchBtn.className = "btn";
      switchBtn.type = "button";
      switchBtn.textContent = "Switch";
      switchBtn.addEventListener("click", async () => {
        try {
          await apiPost("/api/sessions/" + session.id + "/switch", {});
          toast("Session switched", "success");
          await loadSessions(persona);
          await loadUsage();
        } catch (err) {
          toast("Switch failed: " + err.message, "error");
        }
      });

      const saveBtn = document.createElement("button");
      saveBtn.className = "btn";
      saveBtn.type = "button";
      saveBtn.textContent = "Rename";
      saveBtn.addEventListener("click", async () => {
        const title = titleInput.value.trim();
        if (!title) {
          toast("Title cannot be empty", "error");
          return;
        }
        try {
          await apiPut("/api/sessions/" + session.id + "/title", { title });
          toast("Session renamed", "success");
          await loadSessions(persona);
        } catch (err) {
          toast("Rename failed: " + err.message, "error");
        }
      });

      const exportBtn = document.createElement("button");
      exportBtn.className = "btn";
      exportBtn.type = "button";
      exportBtn.textContent = "Export";
      exportBtn.addEventListener("click", async () => {
        try {
          await exportSessionMarkdown(session.id, session.title || "session");
        } catch (err) {
          toast("Export failed: " + err.message, "error");
        }
      });

      const clearBtn = document.createElement("button");
      clearBtn.className = "btn";
      clearBtn.type = "button";
      clearBtn.textContent = "Clear";
      clearBtn.addEventListener("click", async () => {
        if (!confirm("Clear this session messages?")) {
          return;
        }
        try {
          await apiPost("/api/sessions/" + session.id + "/clear", { reset_usage: false });
          toast("Session cleared", "success");
          await loadSessions(persona);
          await loadSessionMessages(session.id);
        } catch (err) {
          toast("Clear failed: " + err.message, "error");
        }
      });

      const clearResetBtn = document.createElement("button");
      clearResetBtn.className = "btn";
      clearResetBtn.type = "button";
      clearResetBtn.textContent = "Clear+Reset";
      clearResetBtn.addEventListener("click", async () => {
        if (!confirm("Clear this session and reset persona usage?")) {
          return;
        }
        try {
          await apiPost("/api/sessions/" + session.id + "/clear", { reset_usage: true });
          toast("Session cleared, usage reset", "success");
          await loadSessions(persona);
          await loadUsage();
          await loadSessionMessages(session.id);
        } catch (err) {
          toast("Clear+reset failed: " + err.message, "error");
        }
      });

      const delBtn = document.createElement("button");
      delBtn.className = "btn danger";
      delBtn.type = "button";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", async () => {
        if (!confirm("Delete this session?")) {
          return;
        }
        try {
          await apiDelete("/api/sessions/" + session.id);
          toast("Session deleted", "success");
          await loadSessions(persona);
          $("sessionMessages").textContent = "Select a session to view messages.";
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      });

      actions.appendChild(viewBtn);
      actions.appendChild(switchBtn);
      actions.appendChild(saveBtn);
      actions.appendChild(exportBtn);
      actions.appendChild(clearBtn);
      actions.appendChild(clearResetBtn);
      actions.appendChild(delBtn);
      actionCell.appendChild(actions);

      row.appendChild(currentCell);
      row.appendChild(titleCell);
      row.appendChild(msgCell);
      row.appendChild(createdCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!sessions.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='5'>No sessions yet.</td>";
      tbody.appendChild(row);
    }
  }

  async function loadSessionMessages(sessionId) {
    try {
      const data = await apiGet("/api/sessions/" + sessionId + "/messages");
      const lines = [];
      (data.messages || []).forEach((message, idx) => {
        lines.push("[" + (idx + 1) + "] " + (message.role || "unknown"));
        lines.push(String(message.content || ""));
        lines.push("");
      });
      $("sessionMessages").textContent = lines.length ? lines.join("\n") : "No messages in this session.";
    } catch (err) {
      $("sessionMessages").textContent = "Failed to load messages: " + err.message;
    }
  }

  async function exportSessionMarkdown(sessionId, title) {
    const blob = await request("/api/sessions/" + sessionId + "/export", { method: "GET" }, "blob");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const safe = String(title || "session").replace(/[^a-zA-Z0-9._-]+/g, "_");
    anchor.href = url;
    anchor.download = safe + ".md";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    toast("Session exported", "success");
  }

  async function createSession() {
    const persona = $("sessionPersonaSelect").value;
    if (!persona) {
      toast("Select a persona first", "error");
      return;
    }
    const title = $("sessionNewTitle").value.trim();
    await apiPost("/api/sessions", {
      persona,
      title,
      switch_to_new: true,
    });
    $("sessionNewTitle").value = "";
    toast("Session created", "success");
    await loadSessions(persona);
  }

  async function loadMemories() {
    const data = await apiGet("/api/memories");
    const tbody = $("memoryTableBody");
    tbody.innerHTML = "";

    (data.memories || []).forEach((memory) => {
      const row = document.createElement("tr");

      const indexCell = document.createElement("td");
      indexCell.textContent = String(memory.index);

      const contentCell = document.createElement("td");
      const textarea = document.createElement("textarea");
      textarea.rows = 2;
      textarea.value = memory.content || "";
      contentCell.appendChild(textarea);

      const sourceCell = document.createElement("td");
      sourceCell.textContent = memory.source || "user";

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const saveBtn = document.createElement("button");
      saveBtn.className = "btn";
      saveBtn.type = "button";
      saveBtn.textContent = "Save";
      saveBtn.addEventListener("click", async () => {
        try {
          await apiPut("/api/memories/" + memory.index, { content: textarea.value.trim() });
          toast("Memory updated", "success");
          await loadMemories();
        } catch (err) {
          toast("Update failed: " + err.message, "error");
        }
      });

      const delBtn = document.createElement("button");
      delBtn.className = "btn danger";
      delBtn.type = "button";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", async () => {
        if (!confirm("Delete this memory?")) {
          return;
        }
        try {
          await apiDelete("/api/memories/" + memory.index);
          toast("Memory deleted", "success");
          await loadMemories();
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      });

      actions.appendChild(saveBtn);
      actions.appendChild(delBtn);
      actionCell.appendChild(actions);

      row.appendChild(indexCell);
      row.appendChild(contentCell);
      row.appendChild(sourceCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!data.memories || !data.memories.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='4'>No memories.</td>";
      tbody.appendChild(row);
    }
  }

  async function addMemory() {
    const content = $("memoryNewContent").value.trim();
    if (!content) {
      toast("Memory content required", "error");
      return;
    }
    await apiPost("/api/memories", { content });
    $("memoryNewContent").value = "";
    toast("Memory added", "success");
    await loadMemories();
  }

  async function clearAllMemories() {
    if (!confirm("Clear all memories?")) {
      return;
    }
    await apiDelete("/api/memories");
    toast("All memories cleared", "success");
    await loadMemories();
  }

  async function loadProviders() {
    const data = await apiGet("/api/providers");
    state.providers = data.providers || {};

    const tbody = $("providerTableBody");
    tbody.innerHTML = "";

    const names = Object.keys(state.providers).sort((a, b) => a.localeCompare(b));
    names.forEach((name) => {
      const provider = state.providers[name];
      const row = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = name;

      const keyCell = document.createElement("td");
      keyCell.textContent = provider.api_key || "";

      const baseCell = document.createElement("td");
      baseCell.textContent = provider.base_url || "";

      const modelCell = document.createElement("td");
      modelCell.textContent = provider.model || "";

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const loadBtn = document.createElement("button");
      loadBtn.className = "btn";
      loadBtn.type = "button";
      loadBtn.textContent = "Load";
      loadBtn.addEventListener("click", async () => {
        try {
          await apiPost("/api/providers/" + encodeURIComponent(name) + "/load", {});
          toast("Provider loaded", "success");
          await loadSettings();
          await loadUsage();
        } catch (err) {
          toast("Load failed: " + err.message, "error");
        }
      });

      const editBtn = document.createElement("button");
      editBtn.className = "btn";
      editBtn.type = "button";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => {
        $("providerName").value = name;
        $("providerApiKey").value = "";
        $("providerBaseUrl").value = provider.base_url || "";
        $("providerModel").value = provider.model || "";
        toast("Editing provider: " + name);
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "btn danger";
      deleteBtn.type = "button";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", async () => {
        if (!confirm("Delete provider '" + name + "'?")) {
          return;
        }
        try {
          await apiDelete("/api/providers/" + encodeURIComponent(name));
          toast("Provider deleted", "success");
          await loadProviders();
          refreshModelProviderSelect();
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      });

      actions.appendChild(loadBtn);
      actions.appendChild(editBtn);
      actions.appendChild(deleteBtn);
      actionCell.appendChild(actions);

      row.appendChild(nameCell);
      row.appendChild(keyCell);
      row.appendChild(baseCell);
      row.appendChild(modelCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!names.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='5'>No providers configured.</td>";
      tbody.appendChild(row);
    }

    refreshModelProviderSelect();
  }

  function providerFormValues() {
    return {
      name: $("providerName").value.trim(),
      api_key: $("providerApiKey").value.trim(),
      base_url: $("providerBaseUrl").value.trim(),
      model: $("providerModel").value.trim(),
    };
  }

  function clearProviderForm() {
    $("providerName").value = "";
    $("providerApiKey").value = "";
    $("providerBaseUrl").value = "";
    $("providerModel").value = "";
  }

  async function createProvider() {
    const values = providerFormValues();
    if (!values.name || !values.api_key || !values.base_url) {
      toast("Name, api_key, base_url are required", "error");
      return;
    }
    await apiPost("/api/providers", values);
    clearProviderForm();
    toast("Provider created", "success");
    await loadProviders();
  }

  async function updateProvider() {
    const values = providerFormValues();
    if (!values.name) {
      toast("Provider name required", "error");
      return;
    }

    const body = {};
    if (values.api_key) body.api_key = values.api_key;
    if (values.base_url) body.base_url = values.base_url;
    if (values.model) body.model = values.model;

    if (!Object.keys(body).length) {
      toast("Provide at least one field to update", "error");
      return;
    }

    await apiPut("/api/providers/" + encodeURIComponent(values.name), body);
    clearProviderForm();
    toast("Provider updated", "success");
    await loadProviders();
  }

  async function saveCurrentProvider() {
    const name = $("providerSaveName").value.trim();
    if (!name) {
      toast("Provider name required", "error");
      return;
    }
    await apiPost("/api/providers/save-current", { name });
    $("providerSaveName").value = "";
    toast("Current config saved as provider", "success");
    await loadProviders();
  }

  function refreshModelProviderSelect() {
    const select = $("modelProviderSelect");
    const prev = select.value;
    select.innerHTML = "";

    const currentOption = document.createElement("option");
    currentOption.value = "current";
    currentOption.textContent = "current";
    select.appendChild(currentOption);

    const names = Object.keys(state.providers || {}).sort((a, b) => a.localeCompare(b));
    names.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    });

    if (["current", ...names].includes(prev)) {
      select.value = prev;
    } else {
      select.value = "current";
    }
  }

  async function fetchModels() {
    const source = $("modelProviderSelect").value;
    const query = source && source !== "current" ? "?provider=" + encodeURIComponent(source) : "";
    const data = await apiGet("/api/models" + query);

    $("modelsCurrentModel").value = data.current_model || "";

    const list = $("modelsList");
    list.innerHTML = "";
    state.selectedModel = "";
    $("modelsSelectedModel").value = "";

    (data.models || []).forEach((modelName) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "model-item" + (modelName === data.current_model ? " active" : "");
      btn.textContent = modelName;
      btn.addEventListener("click", () => {
        state.selectedModel = modelName;
        $("modelsSelectedModel").value = modelName;
        document.querySelectorAll(".model-item").forEach((node) => {
          node.classList.toggle("active", node.textContent === modelName);
        });
      });
      list.appendChild(btn);
    });

    if (!data.models || !data.models.length) {
      list.textContent = "No models returned.";
    }

    toast("Models fetched: " + formatNum(data.count || 0), "success");
  }

  async function applySelectedModel() {
    if (!state.selectedModel) {
      toast("Select a model first", "error");
      return;
    }
    await apiPut("/api/settings", { model: state.selectedModel });
    toast("Model updated: " + state.selectedModel, "success");
    await loadSettings();
  }

  async function loadCronTasks() {
    const data = await apiGet("/api/cron");
    const tbody = $("cronTableBody");
    tbody.innerHTML = "";

    (data.tasks || []).forEach((task) => {
      const row = document.createElement("tr");

      const nameCell = document.createElement("td");
      nameCell.textContent = task.name || "";

      const cronCell = document.createElement("td");
      const cronInput = document.createElement("input");
      cronInput.type = "text";
      cronInput.value = task.cron_expression || "";
      cronCell.appendChild(cronInput);

      const promptCell = document.createElement("td");
      const promptInput = document.createElement("textarea");
      promptInput.rows = 2;
      promptInput.value = task.prompt || "";
      promptCell.appendChild(promptInput);

      const enabledCell = document.createElement("td");
      enabledCell.textContent = task.enabled ? "on" : "off";

      const lastRunCell = document.createElement("td");
      lastRunCell.textContent = formatDate(task.last_run_at);

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const saveBtn = document.createElement("button");
      saveBtn.className = "btn";
      saveBtn.type = "button";
      saveBtn.textContent = "Save";
      saveBtn.addEventListener("click", async () => {
        try {
          await apiPut("/api/cron/" + encodeURIComponent(task.name), {
            cron_expression: cronInput.value.trim(),
            prompt: promptInput.value,
            enabled: task.enabled,
          });
          toast("Cron task updated", "success");
          await loadCronTasks();
        } catch (err) {
          toast("Update failed: " + err.message, "error");
        }
      });

      const toggleBtn = document.createElement("button");
      toggleBtn.className = "btn";
      toggleBtn.type = "button";
      toggleBtn.textContent = task.enabled ? "Disable" : "Enable";
      toggleBtn.addEventListener("click", async () => {
        try {
          await apiPut("/api/cron/" + encodeURIComponent(task.name), {
            enabled: !task.enabled,
          });
          toast("Cron task toggled", "success");
          await loadCronTasks();
        } catch (err) {
          toast("Toggle failed: " + err.message, "error");
        }
      });

      const runBtn = document.createElement("button");
      runBtn.className = "btn";
      runBtn.type = "button";
      runBtn.textContent = "Run";
      runBtn.addEventListener("click", async () => {
        try {
          const res = await apiPost("/api/cron/" + encodeURIComponent(task.name) + "/run", {});
          toast(res.message || "Task executed", "success");
          await loadCronTasks();
        } catch (err) {
          toast("Run failed: " + err.message, "error");
        }
      });

      const delBtn = document.createElement("button");
      delBtn.className = "btn danger";
      delBtn.type = "button";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", async () => {
        if (!confirm("Delete cron task '" + task.name + "'?")) {
          return;
        }
        try {
          await apiDelete("/api/cron/" + encodeURIComponent(task.name));
          toast("Cron task deleted", "success");
          await loadCronTasks();
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      });

      actions.appendChild(saveBtn);
      actions.appendChild(toggleBtn);
      actions.appendChild(runBtn);
      actions.appendChild(delBtn);
      actionCell.appendChild(actions);

      row.appendChild(nameCell);
      row.appendChild(cronCell);
      row.appendChild(promptCell);
      row.appendChild(enabledCell);
      row.appendChild(lastRunCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!data.tasks || !data.tasks.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='6'>No cron tasks.</td>";
      tbody.appendChild(row);
    }
  }

  async function createCronTask() {
    const name = $("cronName").value.trim();
    const cron = $("cronExpression").value.trim();
    const prompt = $("cronPrompt").value.trim();

    if (!name || !cron || !prompt) {
      toast("name, cron_expression, prompt are required", "error");
      return;
    }

    await apiPost("/api/cron", {
      name,
      cron_expression: cron,
      prompt,
    });

    $("cronName").value = "";
    $("cronExpression").value = "";
    $("cronPrompt").value = "";
    toast("Cron task created", "success");
    await loadCronTasks();
  }

  function syncUsageControlFromState() {
    if (!state.usage) {
      return;
    }

    const usageSelect = $("usagePersonaSelect");
    const persona = usageSelect.value || state.usage.current_persona;
    const perPersona = state.usage.per_persona || [];
    const row = perPersona.find((item) => item.persona === persona);
    $("usageTokenLimit").value = row ? String(row.token_limit || 0) : "0";
  }

  async function loadUsage() {
    const data = await apiGet("/api/usage");
    state.usage = data;

    const summary = [];
    summary.push("Current Persona: " + (data.current_persona || "default"));
    summary.push("Total Tokens (All Personas): " + formatNum(data.total_all_personas || 0));
    summary.push("Current Token Limit: " + (data.token_limit ? formatNum(data.token_limit) : "unlimited"));
    summary.push("Remaining: " + (data.remaining == null ? "unlimited" : formatNum(data.remaining)));
    summary.push("Usage Percentage: " + (data.usage_percentage == null ? "n/a" : data.usage_percentage.toFixed(1) + "%"));
    $("usageSummary").textContent = summary.join("\n");

    refreshPersonaSelectors();
    $("usagePersonaSelect").value = data.current_persona || "default";
    syncUsageControlFromState();

    const tbody = $("usageTableBody");
    tbody.innerHTML = "";

    (data.per_persona || []).forEach((item) => {
      const row = document.createElement("tr");

      const personaCell = document.createElement("td");
      personaCell.textContent = item.persona;

      const promptCell = document.createElement("td");
      promptCell.textContent = formatNum(item.prompt_tokens);

      const completionCell = document.createElement("td");
      completionCell.textContent = formatNum(item.completion_tokens);

      const totalCell = document.createElement("td");
      totalCell.textContent = formatNum(item.total_tokens);

      const limitCell = document.createElement("td");
      const limitInput = document.createElement("input");
      limitInput.type = "number";
      limitInput.min = "0";
      limitInput.step = "1";
      limitInput.value = String(item.token_limit || 0);
      limitCell.appendChild(limitInput);

      const actionCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const setBtn = document.createElement("button");
      setBtn.className = "btn";
      setBtn.type = "button";
      setBtn.textContent = "Set Limit";
      setBtn.addEventListener("click", async () => {
        try {
          await apiPut("/api/usage/token-limit", {
            persona: item.persona,
            token_limit: Number(limitInput.value || 0),
          });
          toast("Token limit updated", "success");
          await loadUsage();
        } catch (err) {
          toast("Set limit failed: " + err.message, "error");
        }
      });

      const resetBtn = document.createElement("button");
      resetBtn.className = "btn";
      resetBtn.type = "button";
      resetBtn.textContent = "Reset";
      resetBtn.addEventListener("click", async () => {
        if (!confirm("Reset usage for persona '" + item.persona + "'?")) {
          return;
        }
        try {
          await apiPost("/api/usage/reset", { persona: item.persona });
          toast("Usage reset", "success");
          await loadUsage();
        } catch (err) {
          toast("Reset failed: " + err.message, "error");
        }
      });

      actions.appendChild(setBtn);
      actions.appendChild(resetBtn);
      actionCell.appendChild(actions);

      row.appendChild(personaCell);
      row.appendChild(promptCell);
      row.appendChild(completionCell);
      row.appendChild(totalCell);
      row.appendChild(limitCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!data.per_persona || !data.per_persona.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='6'>No usage rows.</td>";
      tbody.appendChild(row);
    }
  }

  async function setUsageLimitFromControls() {
    const persona = $("usagePersonaSelect").value;
    const tokenLimit = Number($("usageTokenLimit").value || 0);
    await apiPut("/api/usage/token-limit", {
      persona,
      token_limit: tokenLimit,
    });
    toast("Token limit updated", "success");
    await loadUsage();
  }

  async function resetUsageFromControls() {
    const persona = $("usagePersonaSelect").value;
    if (!confirm("Reset usage for persona '" + persona + "'?")) {
      return;
    }
    await apiPost("/api/usage/reset", { persona });
    toast("Usage reset", "success");
    await loadUsage();
  }

  function buildLogsFilterPayload() {
    const type = $("logTypeFilter").value || null;
    const before = toIsoFromDatetimeLocal($("logBefore").value);
    const after = toIsoFromDatetimeLocal($("logAfter").value);
    return {
      type,
      before,
      after,
    };
  }

  async function loadLogs() {
    const type = $("logTypeFilter").value;
    const params = new URLSearchParams();
    params.set("page", String(state.logsPage));
    params.set("limit", "50");
    if (type) {
      params.set("type", type);
    }

    const data = await apiGet("/api/logs?" + params.toString());
    state.logsPage = data.page || 1;
    state.logsPages = data.pages || 1;

    const tbody = $("logsTableBody");
    tbody.innerHTML = "";

    (data.logs || []).forEach((log) => {
      const row = document.createElement("tr");

      const checkCell = document.createElement("td");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "log-select";
      checkbox.dataset.logId = String(log.id);
      checkCell.appendChild(checkbox);

      const createdCell = document.createElement("td");
      createdCell.textContent = formatDate(log.created_at);

      const typeCell = document.createElement("td");
      typeCell.textContent = log.log_type || "";

      const modelCell = document.createElement("td");
      modelCell.textContent = log.model || "";

      const tokenCell = document.createElement("td");
      tokenCell.textContent = formatNum(log.total_tokens || 0);

      const latencyCell = document.createElement("td");
      latencyCell.textContent = log.latency_ms != null ? String(log.latency_ms) + "ms" : "-";

      const personaCell = document.createElement("td");
      personaCell.textContent = log.persona_name || "";

      const msgCell = document.createElement("td");
      msgCell.textContent = log.error_message || "";

      const actionCell = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "btn danger";
      btn.type = "button";
      btn.textContent = "Delete";
      btn.addEventListener("click", async () => {
        try {
          await apiDelete("/api/logs/" + log.id);
          toast("Log deleted", "success");
          await loadLogs();
        } catch (err) {
          toast("Delete failed: " + err.message, "error");
        }
      });
      actionCell.appendChild(btn);

      row.appendChild(checkCell);
      row.appendChild(createdCell);
      row.appendChild(typeCell);
      row.appendChild(modelCell);
      row.appendChild(tokenCell);
      row.appendChild(latencyCell);
      row.appendChild(personaCell);
      row.appendChild(msgCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    });

    if (!data.logs || !data.logs.length) {
      const row = document.createElement("tr");
      row.innerHTML = "<td colspan='9'>No logs.</td>";
      tbody.appendChild(row);
    }

    $("logsPageInfo").textContent = String(data.page || 1) + " / " + String(data.pages || 1);
    $("btnLogsPrev").disabled = (data.page || 1) <= 1;
    $("btnLogsNext").disabled = (data.page || 1) >= (data.pages || 1);
    $("logCheckAll").checked = false;
  }

  async function deleteSelectedLogs() {
    const selected = Array.from(document.querySelectorAll(".log-select:checked"));
    if (!selected.length) {
      toast("No logs selected", "error");
      return;
    }

    if (!confirm("Delete " + selected.length + " selected logs?")) {
      return;
    }

    for (const node of selected) {
      const id = Number(node.dataset.logId);
      if (!id) {
        continue;
      }
      await apiDelete("/api/logs/" + id);
    }

    toast("Selected logs deleted", "success");
    await loadLogs();
  }

  async function deleteFilteredLogs() {
    const payload = buildLogsFilterPayload();
    if (!payload.before && !payload.after) {
      toast("Set before/after filter first", "error");
      return;
    }

    if (!confirm("Delete logs by current filters?")) {
      return;
    }

    const res = await apiPost("/api/logs/delete", payload);
    toast("Deleted " + formatNum(res.deleted || 0) + " logs", "success");
    await loadLogs();
  }

  async function keepLatestLogs() {
    const keep = Number($("logKeepLatest").value || "");
    if (Number.isNaN(keep) || keep < 0) {
      toast("Enter a valid Keep Latest number", "error");
      return;
    }

    const payload = {
      type: $("logTypeFilter").value || null,
      keep_latest: keep,
    };

    if (!confirm("Keep latest " + keep + " logs and delete older ones?")) {
      return;
    }

    const res = await apiPost("/api/logs/delete", payload);
    toast("Deleted " + formatNum(res.deleted || 0) + " logs", "success");
    await loadLogs();
  }

  async function clearLogsByType() {
    const type = $("logTypeFilter").value || null;
    const label = type ? "type '" + type + "'" : "all types";
    if (!confirm("Clear logs for " + label + "?")) {
      return;
    }

    const res = await apiPost("/api/logs/delete", {
      type,
      clear_all: true,
    });
    toast("Deleted " + formatNum(res.deleted || 0) + " logs", "success");
    await loadLogs();
  }

  async function exportBackup() {
    const payload = await apiGet("/api/backup/export");
    const data = JSON.stringify(payload, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "gemen-backup-" + new Date().toISOString().replace(/[:.]/g, "-") + ".json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);

    $("backupResult").textContent = "Backup exported at " + new Date().toLocaleString();
    toast("Backup exported", "success");
  }

  async function importBackup() {
    const file = $("backupFileInput").files && $("backupFileInput").files[0];
    if (!file) {
      toast("Choose a backup file first", "error");
      return;
    }

    const mode = $("backupImportMode").value || "replace";
    const text = await file.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      toast("Invalid JSON file", "error");
      return;
    }

    if (!confirm("Import backup in '" + mode + "' mode?")) {
      return;
    }

    const result = await apiPost("/api/backup/import", {
      mode,
      payload,
    });

    $("backupResult").textContent = JSON.stringify(result, null, 2);
    toast("Backup imported", "success");
    await reloadAll();
  }

  function setActivePane(name) {
    state.activePane = name;
    document.querySelectorAll(".nav-btn").forEach((button) => {
      button.classList.toggle("active", button.dataset.pane === name);
    });
    document.querySelectorAll(".pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === "pane-" + name);
    });
    loadPaneData(name).catch((err) => {
      toast("Load failed: " + err.message, "error");
    });
  }

  async function loadPaneData(name) {
    if (name === "general") {
      await loadSettings();
      return;
    }
    if (name === "personas") {
      await loadPersonas();
      return;
    }
    if (name === "sessions") {
      await loadPersonas();
      await loadSessions($("sessionPersonaSelect").value);
      return;
    }
    if (name === "memories") {
      await loadMemories();
      return;
    }
    if (name === "providers") {
      await loadProviders();
      return;
    }
    if (name === "models") {
      await loadProviders();
      refreshModelProviderSelect();
      return;
    }
    if (name === "cron") {
      await loadCronTasks();
      return;
    }
    if (name === "usage") {
      await loadUsage();
      return;
    }
    if (name === "logs") {
      await loadLogs();
    }
  }

  async function reloadAll() {
    await loadSettings();
    await loadPersonas();
    await loadProviders();
    await loadUsage();
    await loadMemories();
    await loadCronTasks();
    await loadSessions($("sessionPersonaSelect").value || (state.personas ? state.personas.current : ""));
    if (state.activePane === "logs") {
      await loadLogs();
    }
  }

  function wireEvents() {
    document.querySelectorAll(".nav-btn").forEach((button) => {
      button.addEventListener("click", () => setActivePane(button.dataset.pane));
    });

    const logoutButton = $("btnLogout");
    if (logoutButton) {
      logoutButton.addEventListener("click", logout);
    }

    const refreshAllButton = $("btnRefreshAll");
    if (refreshAllButton) {
      refreshAllButton.addEventListener("click", async () => {
        try {
          await reloadAll();
          toast("Refreshed", "success");
        } catch (err) {
          toast("Refresh failed: " + err.message, "error");
        }
      });
    }

    $("btnSaveGeneral").addEventListener("click", async () => {
      try {
        await saveSettings();
      } catch (err) {
        toast("Save failed: " + err.message, "error");
      }
    });

    $("btnPersonaCreate").addEventListener("click", async () => {
      try {
        await createPersona();
      } catch (err) {
        toast("Create failed: " + err.message, "error");
      }
    });

    $("btnSessionCreate").addEventListener("click", async () => {
      try {
        await createSession();
      } catch (err) {
        toast("Create failed: " + err.message, "error");
      }
    });

    $("btnSessionRefresh").addEventListener("click", async () => {
      try {
        await loadSessions($("sessionPersonaSelect").value);
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("sessionPersonaSelect").addEventListener("change", async () => {
      try {
        await loadSessions($("sessionPersonaSelect").value);
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("btnAddMemory").addEventListener("click", async () => {
      try {
        await addMemory();
      } catch (err) {
        toast("Add failed: " + err.message, "error");
      }
    });

    $("btnClearMemories").addEventListener("click", async () => {
      try {
        await clearAllMemories();
      } catch (err) {
        toast("Clear failed: " + err.message, "error");
      }
    });

    $("btnProviderCreate").addEventListener("click", async () => {
      try {
        await createProvider();
      } catch (err) {
        toast("Create failed: " + err.message, "error");
      }
    });

    $("btnProviderUpdate").addEventListener("click", async () => {
      try {
        await updateProvider();
      } catch (err) {
        toast("Update failed: " + err.message, "error");
      }
    });

    $("btnProviderSaveCurrent").addEventListener("click", async () => {
      try {
        await saveCurrentProvider();
      } catch (err) {
        toast("Save failed: " + err.message, "error");
      }
    });

    $("btnModelFetch").addEventListener("click", async () => {
      try {
        await fetchModels();
      } catch (err) {
        toast("Fetch models failed: " + err.message, "error");
      }
    });

    $("btnModelUseSelected").addEventListener("click", async () => {
      try {
        await applySelectedModel();
      } catch (err) {
        toast("Apply failed: " + err.message, "error");
      }
    });

    $("btnCronCreate").addEventListener("click", async () => {
      try {
        await createCronTask();
      } catch (err) {
        toast("Create failed: " + err.message, "error");
      }
    });

    $("btnUsageRefresh").addEventListener("click", async () => {
      try {
        await loadUsage();
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("usagePersonaSelect").addEventListener("change", () => {
      syncUsageControlFromState();
    });

    $("btnUsageSetLimit").addEventListener("click", async () => {
      try {
        await setUsageLimitFromControls();
      } catch (err) {
        toast("Set limit failed: " + err.message, "error");
      }
    });

    $("btnUsageReset").addEventListener("click", async () => {
      try {
        await resetUsageFromControls();
      } catch (err) {
        toast("Reset failed: " + err.message, "error");
      }
    });

    $("btnLogsRefresh").addEventListener("click", async () => {
      try {
        await loadLogs();
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("btnLogsPrev").addEventListener("click", async () => {
      if (state.logsPage <= 1) {
        return;
      }
      state.logsPage -= 1;
      try {
        await loadLogs();
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("btnLogsNext").addEventListener("click", async () => {
      if (state.logsPage >= state.logsPages) {
        return;
      }
      state.logsPage += 1;
      try {
        await loadLogs();
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("logTypeFilter").addEventListener("change", async () => {
      state.logsPage = 1;
      try {
        await loadLogs();
      } catch (err) {
        toast("Load failed: " + err.message, "error");
      }
    });

    $("logCheckAll").addEventListener("change", (event) => {
      const checked = event.target.checked;
      document.querySelectorAll(".log-select").forEach((node) => {
        node.checked = checked;
      });
    });

    $("btnLogsDeleteSelected").addEventListener("click", async () => {
      try {
        await deleteSelectedLogs();
      } catch (err) {
        toast("Delete failed: " + err.message, "error");
      }
    });

    $("btnLogsDeleteFiltered").addEventListener("click", async () => {
      try {
        await deleteFilteredLogs();
      } catch (err) {
        toast("Delete failed: " + err.message, "error");
      }
    });

    $("btnLogsKeepLatest").addEventListener("click", async () => {
      try {
        await keepLatestLogs();
      } catch (err) {
        toast("Operation failed: " + err.message, "error");
      }
    });

    $("btnLogsClearAll").addEventListener("click", async () => {
      try {
        await clearLogsByType();
      } catch (err) {
        toast("Clear failed: " + err.message, "error");
      }
    });

    $("btnBackupExport").addEventListener("click", async () => {
      try {
        await exportBackup();
      } catch (err) {
        toast("Export failed: " + err.message, "error");
      }
    });

    $("btnBackupImport").addEventListener("click", async () => {
      try {
        await importBackup();
      } catch (err) {
        toast("Import failed: " + err.message, "error");
      }
    });
  }

  async function init() {
    const ok = await setupAuth();
    if (!ok) {
      return;
    }

    wireEvents();

    try {
      await loadSettings();
      await loadPersonas();
      await loadProviders();
      await loadUsage();
      await loadSessions($("sessionPersonaSelect").value || (state.personas ? state.personas.current : ""));
      await loadMemories();
      await loadCronTasks();
      setActivePane("general");
    } catch (err) {
      toast("Initialization failed: " + err.message, "error");
    }
  }

  init();
})();
