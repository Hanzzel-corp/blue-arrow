import readline from "readline";

const MODULE_ID = "ui.state.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const stateByChat = new Map();
const taskContextById = new Map();

// Throttling to reduce UI spam
const lastUiStateEmission = new Map(); // chatId -> timestamp
const lastRenderRequestEmission = new Map(); // chatId -> timestamp
const UI_STATE_THROTTLE_MS = 100; // Min time between ui.state.out emissions
const RENDER_REQUEST_THROTTLE_MS = 200; // Min time between render.request.out emissions

function generateTraceId() {
  return `${MODULE_ID}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function safeIsoNow() {
  return new Date().toISOString();
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: safeIsoNow(),
    chat_id: getChatId(payload),
    module: MODULE_ID
  };
  const { trace_id: _trace, meta: _meta, ...cleanPayload } = payload || {};
  process.stdout.write(
    JSON.stringify({
      module: MODULE_ID,
      port,
      trace_id: traceId,
      meta,
      payload: cleanPayload
    }) + "\n"
  );
}

function mergeMeta(topMeta = {}, payloadMeta = {}) {
  return {
    ...(topMeta || {}),
    ...(payloadMeta || {})
  };
}

function getChatId(payload = {}, meta = {}) {
  return (
    payload?.chat_id ??
    payload?.meta?.chat_id ??
    meta?.chat_id ??
    payload?.report?.meta?.chat_id ??
    payload?.result?.meta?.chat_id ??
    payload?.state?.chat_id ??
    null
  );
}

function buildDefaultState(chatId = null) {
  return {
    chat_id: chatId,
    scene: "main",
    foreground_context: null,
    background_context: null,
    active_app: null,
    active_web: null,
    background_app: null,
    background_web: null,
    active_action: null,
    pending_plan_id: null,
    running_task_id: null,
    last_callback_data: null,
    last_result_type: null,
    breadcrumbs: ["main"]
  };
}

function getState(chatId) {
  const key = String(chatId);
  if (!stateByChat.has(key)) {
    stateByChat.set(key, buildDefaultState(chatId));
  }
  return stateByChat.get(key);
}

function saveState(chatId, state) {
  if (chatId == null || !state) return;
  const key = String(chatId);
  stateByChat.set(key, state);
}

function rememberTaskContext(taskId, payload = {}, fallbackChatId = null, meta = {}) {
  const id =
    taskId ||
    payload?.task_id ||
    payload?.plan_id ||
    payload?.report?.plan_id ||
    meta?.task_id ||
    meta?.plan_id ||
    null;

  const chatId = getChatId(payload, meta) ?? fallbackChatId ?? null;
  if (!id || chatId == null) return;

  const key = String(id);
  const prev = taskContextById.get(key) || {};

  taskContextById.set(key, {
    ...prev,
    chat_id: chatId,
    source:
      meta?.source ||
      payload?.meta?.source ||
      payload?.report?.meta?.source ||
      prev.source ||
      null
  });
}

function chatIdFromTask(taskId) {
  if (!taskId) return null;
  return taskContextById.get(String(taskId))?.chat_id ?? null;
}

function fallbackChatIdFromStates() {
  const values = Array.from(stateByChat.values()).filter(
    (s) => s && s.chat_id != null
  );

  if (!values.length) return null;
  return values[values.length - 1].chat_id;
}

function pushBreadcrumb(state, scene) {
  if (!scene) return;

  const current = Array.isArray(state?.breadcrumbs) ? state.breadcrumbs : ["main"];
  const last = current[current.length - 1];

  if (last !== scene) {
    state.breadcrumbs = [...current.slice(-4), scene];
  } else {
    state.breadcrumbs = current;
  }
}

function sceneFromCallbackData(data = "") {
  if (data === "menu:main") return "main";
  if (data === "menu:apps") return "apps";
  if (data === "menu:web") return "web";
  if (data === "menu:system") return "system";
  if (data === "menu:memory") return "memory";
  if (data === "menu:pending") return "pending";
  if (data === "menu:audit") return "audit";
  if (typeof data === "string" && data.startsWith("app:open:")) return "app_open_request";
  if (typeof data === "string" && data.startsWith("approval:")) return "awaiting_approval";
  if (typeof data === "string" && data.startsWith("action:")) return "action_menu";
  return null;
}

function effectiveSceneFromState(state) {
  if (state?.foreground_context === "web" && state?.active_web?.url) {
    return "web_active";
  }

  if (
    state?.foreground_context === "app" &&
    (state?.active_app?.id || state?.active_app?.label)
  ) {
    return "app_active";
  }

  if (state?.scene === "awaiting_approval") return "awaiting_approval";
  if (state?.scene === "task_running") return "task_running";
  if (state?.scene === "task_result") return "task_result";

  return state?.scene || "main";
}

function emitStateEvent(type, chatId, extra = {}, traceId = null) {
  emit("event.out", {
    level: "info",
    type,
    chat_id: chatId,
    trace_id: traceId || extra.trace_id || generateTraceId(),
    meta: {
      source: "ui.state.main",
      chat_id: chatId,
      module: MODULE_ID,
      timestamp: safeIsoNow(),
      ...extra.meta
    },
    ...extra
  });
}

function snapshotFromState(state) {
  return {
    chat_id: state.chat_id ?? null,
    scene: effectiveSceneFromState(state),
    foreground_context: state.foreground_context ?? null,
    background_context: state.background_context ?? null,
    active_app: state.active_app ?? null,
    active_web: state.active_web ?? null,
    background_app: state.background_app ?? null,
    background_web: state.background_web ?? null,
    active_action: state.active_action ?? null,
    pending_plan_id: state.pending_plan_id ?? null,
    running_task_id: state.running_task_id ?? null,
    last_callback_data: state.last_callback_data ?? null,
    last_result_type: state.last_result_type ?? null,
    breadcrumbs: Array.isArray(state.breadcrumbs) ? state.breadcrumbs : []
  };
}

function emitUiState(state, reason = "state_updated", meta = {}, traceId = null) {
  const chatId = state?.chat_id || null;
  const now = Date.now();
  const lastEmission = lastUiStateEmission.get(chatId) || 0;

  if (now - lastEmission < UI_STATE_THROTTLE_MS) {
    return;
  }
  lastUiStateEmission.set(chatId, now);

  emit("ui.state.out", {
    trace_id: traceId || generateTraceId(),
    reason,
    state: snapshotFromState(state),
    meta: {
      source: "ui.state.main",
      chat_id: chatId,
      module: MODULE_ID,
      timestamp: safeIsoNow(),
      ...meta
    }
  });
}

function emitRenderRequest(state, reason = "render", meta = {}, traceId = null) {
  const chatId = state?.chat_id || null;
  const now = Date.now();
  const lastEmission = lastRenderRequestEmission.get(chatId) || 0;

  if (now - lastEmission < RENDER_REQUEST_THROTTLE_MS) {
    return;
  }
  lastRenderRequestEmission.set(chatId, now);

  emit("ui.render.request.out", {
    trace_id: traceId || generateTraceId(),
    reason,
    state: snapshotFromState(state),
    meta: {
      source: "ui.state.main",
      chat_id: chatId,
      module: MODULE_ID,
      timestamp: safeIsoNow(),
      ...meta
    }
  });
}

function clearBackground(state) {
  state.background_context = null;
  state.background_app = null;
  state.background_web = null;
}

function moveForegroundToBackground(state) {
  const prevForeground = state.foreground_context;

  clearBackground(state);

  if (prevForeground === "app" && state.active_app) {
    state.background_context = "app";
    state.background_app = { ...state.active_app };
    return;
  }

  if (prevForeground === "web" && state.active_web) {
    state.background_context = "web";
    state.background_web = { ...state.active_web };
  }
}

function setForegroundApp(state, app) {
  moveForegroundToBackground(state);

  state.foreground_context = "app";
  state.active_app = app;
  state.active_web = null;
  state.scene = "app_active";
  pushBreadcrumb(state, "app_active");
}

function setForegroundWeb(state, web) {
  moveForegroundToBackground(state);

  state.foreground_context = "web";
  state.active_web = web;
  state.active_app = null;
  state.scene = "web_active";
  pushBreadcrumb(state, "web_active");
}

function sameApp(a, b) {
  if (!a || !b) return false;

  return (
    (a.id && b.id && a.id === b.id) ||
    (a.command && b.command && a.command === b.command) ||
    (a.label && b.label && a.label === b.label)
  );
}

function sameWeb(a, b) {
  if (!a || !b) return false;

  return (
    (a.url && b.url && a.url === b.url) ||
    (a.title && b.title && a.title === b.title)
  );
}

function comparableApp(app) {
  if (!app) return null;
  return {
    id: app.id || null,
    label: app.label || null,
    command: app.command || null,
    source: app.source || null,
    family: app.family || null,
    window_id: app.window_id || null
  };
}

function comparableWeb(web) {
  if (!web) return null;
  return {
    url: web.url || null,
    title: web.title || null
  };
}

function visibleContextSnapshot(state) {
  return JSON.stringify({
    foreground_context: state.foreground_context || null,
    background_context: state.background_context || null,
    active_app: comparableApp(state.active_app),
    active_web: comparableWeb(state.active_web),
    background_app: comparableApp(state.background_app),
    background_web: comparableWeb(state.background_web)
  });
}

function resolveChatIdOrAbort(payload = {}, label = "ui_state_unknown_chat", meta = {}, traceId = null) {
  const taskId = payload?.task_id || meta?.task_id || null;
  const planId = payload?.plan_id || payload?.report?.plan_id || meta?.plan_id || null;

  const resolvedChatId =
    getChatId(payload, meta) ??
    chatIdFromTask(taskId) ??
    chatIdFromTask(planId) ??
    payload?.report?.meta?.chat_id ??
    fallbackChatIdFromStates();

  if (resolvedChatId == null) {
    emit("event.out", {
      level: "warn",
      type: label,
      payload,
      trace_id: traceId || generateTraceId(),
      meta: {
        source: "ui.state.main",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return null;
  }

  return resolvedChatId;
}

function handleCallback(payload, meta = {}, traceId = null) {
  const chatId = resolveChatIdOrAbort(payload, "ui_callback_without_chat", meta, traceId);
  if (chatId == null) return;

  const state = getState(chatId);
  const data = typeof payload?.data === "string" ? payload.data : "";

  state.chat_id = chatId;
  state.last_callback_data = data;

  const nextScene = sceneFromCallbackData(data);
  if (nextScene) {
    state.scene = nextScene;
    pushBreadcrumb(state, nextScene);

    emitStateEvent("ui_scene_changed", chatId, {
      scene: state.scene,
      callback_data: data,
      breadcrumbs: state.breadcrumbs,
      meta
    }, traceId);
  }

  if (typeof data === "string" && data.startsWith("app:open:")) {
    emitStateEvent("ui_app_open_requested", chatId, {
      app_id: data.slice("app:open:".length),
      meta
    }, traceId);
  }

  emitUiState(state, "callback", meta, traceId);
  saveState(chatId, state);
}

function handleEvent(payload, meta = {}, traceId = null) {
  const type = payload?.type || "";
  const planId = payload?.plan_id || payload?.report?.plan_id || meta?.plan_id || null;
  const taskId = payload?.task_id || meta?.task_id || null;
  const directChatId = getChatId(payload, meta);

  if (planId && directChatId != null) {
    rememberTaskContext(planId, payload, directChatId, meta);
  }

  if (taskId && directChatId != null) {
    rememberTaskContext(taskId, payload, directChatId, meta);
  }

  const resolvedChatId = resolveChatIdOrAbort(payload, "ui_event_without_chat", meta, traceId);
  if (resolvedChatId == null) return;

  const state = getState(resolvedChatId);
  state.chat_id = resolvedChatId;

  if (type === "safety_guard_approved" || type === "safety_guard_blocked") {
    const safetyPlanId = payload?.report?.plan_id || payload?.plan_id || null;
    if (safetyPlanId) {
      rememberTaskContext(safetyPlanId, payload, resolvedChatId, meta);
    }
  }

  if (type === "approval_requested") {
    state.pending_plan_id = payload?.plan_id || meta?.plan_id || null;
    state.scene = "awaiting_approval";
    pushBreadcrumb(state, "awaiting_approval");

    if (payload?.plan_id || meta?.plan_id) {
      rememberTaskContext(payload?.plan_id || meta?.plan_id, payload, resolvedChatId, meta);
    }

    emitStateEvent("ui_pending_plan_changed", resolvedChatId, {
      plan_id: state.pending_plan_id,
      status: "awaiting_approval",
      meta
    }, traceId);
  }

  if (type === "approval_approved" || type === "approval_rejected") {
    if (state.pending_plan_id === payload?.plan_id) {
      state.pending_plan_id = null;
    }

    if (payload?.plan_id || meta?.plan_id) {
      rememberTaskContext(payload?.plan_id || meta?.plan_id, payload, resolvedChatId, meta);
    }

    emitStateEvent("ui_pending_plan_changed", resolvedChatId, {
      plan_id: payload?.plan_id || meta?.plan_id || null,
      status: type === "approval_approved" ? "approved" : "rejected",
      meta
    }, traceId);
  }

  if (type === "supervisor_task_started") {
    state.running_task_id = payload?.task_id || meta?.task_id || null;
    state.scene = "task_running";
    pushBreadcrumb(state, "task_running");

    if (payload?.task_id || meta?.task_id) {
      rememberTaskContext(payload?.task_id || meta?.task_id, payload, resolvedChatId, meta);
    }

    emitStateEvent("ui_running_task_changed", resolvedChatId, {
      task_id: state.running_task_id,
      status: "running",
      meta
    }, traceId);
  }

  if (type === "supervisor_task_status_changed") {
    state.running_task_id = payload?.task_id || meta?.task_id || state.running_task_id;

    if (payload?.task_id || meta?.task_id) {
      rememberTaskContext(payload?.task_id || meta?.task_id, payload, resolvedChatId, meta);
    }

    emitStateEvent("ui_running_task_changed", resolvedChatId, {
      task_id: state.running_task_id,
      status: payload?.status || null,
      previous_status: payload?.previous_status || null,
      meta
    }, traceId);
  }

  if (
    type === "supervisor_task_success" ||
    type === "supervisor_task_error" ||
    type === "supervisor_task_timeout"
  ) {
    state.running_task_id = null;
    state.scene = "task_result";
    pushBreadcrumb(state, "task_result");

    if (payload?.task_id || meta?.task_id) {
      rememberTaskContext(payload?.task_id || meta?.task_id, payload, resolvedChatId, meta);
    }

    emitStateEvent("ui_task_finished", resolvedChatId, {
      task_id: payload?.task_id || meta?.task_id || null,
      status: payload?.status || null,
      meta
    }, traceId);
  }

  emitUiState(state, `event:${type}`, meta, traceId);

  if (
    type === "approval_requested" ||
    type === "approval_approved" ||
    type === "approval_rejected" ||
    type === "supervisor_task_started" ||
    type === "supervisor_task_success" ||
    type === "supervisor_task_error" ||
    type === "supervisor_task_timeout"
  ) {
    emitRenderRequest(state, `event:${type}`, meta, traceId);
  }

  saveState(resolvedChatId, state);
}

function handleResult(payload, meta = {}, traceId = null) {
  const taskId = payload?.task_id || meta?.task_id || null;
  const directChatId = getChatId(payload, meta);

  if (taskId && directChatId != null) {
    rememberTaskContext(taskId, payload, directChatId, meta);
  }

  const resolvedChatId = resolveChatIdOrAbort(payload, "ui_result_without_chat", meta, traceId);
  if (resolvedChatId == null) return;

  const state = getState(resolvedChatId);
  state.chat_id = resolvedChatId;

  const result = payload?.result || {};

  const isDesktopOpen =
    result?.opened === true &&
    !result?.url &&
    (result?.resolved_name || result?.application || result?.command);

  const isWebOpen =
    result?.opened === true &&
    !!result?.url;

  if (isDesktopOpen) {
    const app = {
      id: result?.id || null,
      label: result?.resolved_name || result?.application || null,
      command: result?.command || null,
      source: result?.source || null,
      family: result?.family || null,
      capabilities: Array.isArray(result?.capabilities)
        ? result.capabilities
        : [],
      window_id: result?.window_id || null
    };

    setForegroundApp(state, app);
  }

  if (isWebOpen) {
    const web = {
      url: result?.url || null,
      title: result?.title || null
    };

    setForegroundWeb(state, web);
  }

  state.last_result_type = payload?.status || null;

  if (isDesktopOpen || isWebOpen) {
    const eventType = isDesktopOpen ? "ui_active_app_changed" : "ui_active_web_changed";
    const eventData = isDesktopOpen
      ? { app: state.active_app }
      : { web: state.active_web };

    emitStateEvent(eventType, resolvedChatId, {
      ...eventData,
      foreground_context: state.foreground_context,
      background_context: state.background_context,
      background_app: state.background_app,
      background_web: state.background_web,
      meta
    }, traceId);
  }

  emitStateEvent("ui_result_observed", resolvedChatId, {
    task_id: payload?.task_id || meta?.task_id || null,
    status: payload?.status || null,
    foreground_context: state.foreground_context,
    background_context: state.background_context,
    meta
  }, traceId);

  emitUiState(state, "result", meta, traceId);

  if (isDesktopOpen || isWebOpen) {
    emitRenderRequest(state, isDesktopOpen ? "app_opened" : "web_opened", meta, traceId);
  }

  saveState(resolvedChatId, state);
}

function handleAppContext(payload, meta = {}, traceId = null) {
  const chatId = resolveChatIdOrAbort(payload, "ui_app_context_without_chat", meta, traceId);
  if (chatId == null) return;

  const state = getState(chatId);
  const beforeSnapshot = visibleContextSnapshot(state);

  const app = payload?.app || null;
  const web = payload?.web || null;

  const capabilities = Array.isArray(payload?.capabilities)
    ? payload.capabilities
    : Array.isArray(app?.capabilities)
      ? app.capabilities
      : [];

  if (web) {
    const nextWeb = {
      url: web.url || null,
      title: web.title || null
    };

    const isSameForegroundWeb =
      state.foreground_context === "web" &&
      state.active_web &&
      sameWeb(state.active_web, nextWeb);

    if (isSameForegroundWeb) {
      state.active_web = {
        ...state.active_web,
        ...nextWeb
      };
      state.scene = "web_active";
      pushBreadcrumb(state, "web_active");
    } else {
      clearBackground(state);

      if (state.active_app) {
        state.background_context = "app";
        state.background_app = { ...state.active_app };
      } else if (state.foreground_context === "web" && state.active_web) {
        state.background_context = "web";
        state.background_web = { ...state.active_web };
      }

      state.foreground_context = "web";
      state.active_web = nextWeb;
      state.active_app = null;
      state.scene = "web_active";
      pushBreadcrumb(state, "web_active");
    }

    const afterSnapshot = visibleContextSnapshot(state);
    if (afterSnapshot !== beforeSnapshot) {
      emitStateEvent("ui_active_web_changed", chatId, {
        web: state.active_web,
        foreground_context: state.foreground_context,
        background_context: state.background_context,
        background_app: state.background_app,
        background_web: state.background_web,
        meta
      }, traceId);

      emitUiState(state, "web_context", meta, traceId);
      emitRenderRequest(state, "web_context", meta, traceId);
    }

    saveState(chatId, state);
    return;
  }

  if (!app) return;

  const nextApp = {
    id: app?.id || null,
    label: app?.label || null,
    command: app?.command || null,
    source: app?.source || null,
    family: app?.family || null,
    capabilities,
    window_id: app?.window_id || null
  };

  const isSameForegroundApp =
    state.foreground_context === "app" &&
    state.active_app &&
    sameApp(state.active_app, nextApp);

  if (isSameForegroundApp) {
    state.active_app = {
      ...state.active_app,
      ...nextApp,
      window_id: nextApp.window_id || state.active_app?.window_id || null
    };
    state.scene = "app_active";
    pushBreadcrumb(state, "app_active");
  } else {
    const previousApp =
      state.foreground_context === "app" && state.active_app
        ? { ...state.active_app }
        : null;

    const previousWeb =
      state.foreground_context === "web" && state.active_web
        ? { ...state.active_web }
        : null;

    clearBackground(state);

    if (previousApp && !sameApp(previousApp, nextApp)) {
      state.background_context = "app";
      state.background_app = previousApp;
    } else if (previousWeb) {
      state.background_context = "web";
      state.background_web = previousWeb;
    }

    state.foreground_context = "app";
    state.active_app = nextApp;
    state.active_web = null;
    state.scene = "app_active";
    pushBreadcrumb(state, "app_active");
  }

  const afterSnapshot = visibleContextSnapshot(state);
  if (afterSnapshot !== beforeSnapshot) {
    emitStateEvent("ui_active_app_changed", chatId, {
      app: state.active_app,
      foreground_context: state.foreground_context,
      background_context: state.background_context,
      background_app: state.background_app,
      background_web: state.background_web,
      meta
    }, traceId);

    emitUiState(state, "app_context", meta, traceId);
    emitRenderRequest(state, "app_context", meta, traceId);
  }

  saveState(chatId, state);
}

function handleStateIn(payload, meta = {}, traceId = null) {
  const incoming =
    payload?.state && typeof payload.state === "object"
      ? payload.state
      : payload && typeof payload === "object"
        ? payload
        : null;

  if (!incoming) return;

  const chatId = resolveChatIdOrAbort({ ...payload, state: incoming }, "ui_state_in_without_chat", meta, traceId);
  if (chatId == null) return;

  const prev = getState(chatId);
  const next = {
    ...buildDefaultState(chatId),
    ...prev,
    ...incoming,
    chat_id: chatId,
    breadcrumbs: Array.isArray(incoming?.breadcrumbs)
      ? incoming.breadcrumbs
      : Array.isArray(prev?.breadcrumbs)
        ? prev.breadcrumbs
        : ["main"]
  };

  saveState(chatId, next);
  emitUiState(next, "state_in", meta, traceId);
  emitRenderRequest(next, "state_in", meta, traceId);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  try {
    const msg = JSON.parse(line);
    const port = msg?.port;
    const payload = msg?.payload || {};
    const topMeta = msg?.meta || {};
    const payloadMeta =
      typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
    const mergedMeta = mergeMeta(topMeta, payloadMeta);
    const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

    if (port === "callback.in") {
      handleCallback(payload, mergedMeta, traceId);
      return;
    }

    if (port === "event.in") {
      handleEvent(payload, mergedMeta, traceId);
      return;
    }

    if (port === "result.in") {
      handleResult(payload, mergedMeta, traceId);
      return;
    }

    if (port === "app.context.in") {
      handleAppContext(payload, mergedMeta, traceId);
      return;
    }

    if (port === "state.in") {
      handleStateIn(payload, mergedMeta, traceId);
    }
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "ui_state_parse_error",
      error: String(err),
      trace_id: generateTraceId(),
      meta: {
        source: "ui.state.main",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
  }
});