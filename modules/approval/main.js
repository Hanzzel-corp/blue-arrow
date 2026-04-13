import readline from "readline";

const MODULE_ID = "approval.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const pendingByPlanId = new Map();
const pendingOrder = [];

function generateTraceId() {
  return `appr_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function safeIsoNow() {
  return new Date().toISOString();
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: safeIsoNow(),
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

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function buildMeta(base = {}, extra = {}) {
  return {
    source: base?.source || "internal",
    chat_id: base?.chat_id ?? null,
    module: MODULE_ID,
    timestamp: safeIsoNow(),
    ...base,
    ...extra
  };
}

function resolvePlanId(payload = {}, meta = {}) {
  return (
    payload?.plan_id ||
    payload?.task_id ||
    payload?.report?.plan_id ||
    meta?.plan_id ||
    meta?.task_id ||
    null
  );
}

function resolveChatId(payload = {}, meta = {}) {
  return (
    payload?.chat_id ??
    payload?.meta?.chat_id ??
    payload?.report?.meta?.chat_id ??
    meta?.chat_id ??
    null
  );
}

function normalizePendingItem(payload = {}, meta = {}, traceId = null) {
  const planId = resolvePlanId(payload, meta);
  const report = payload?.report || {};
  const chatId = resolveChatId(payload, meta);

  if (!planId) return null;

  return {
    plan_id: planId,
    task_id: payload?.task_id || planId,
    chat_id: chatId,
    source: meta?.source || payload?.source || "unknown",
    confirmable: Boolean(payload?.confirmable),
    reason: payload?.reason || report?.policy_summary || "confirm",
    report,
    original_plan: payload?.original_plan || null,
    created_at: safeIsoNow(),
    trace_id: traceId || generateTraceId(),
    meta: buildMeta(meta, {
      plan_id: planId,
      task_id: payload?.task_id || planId,
      chat_id: chatId
    })
  };
}

function rememberPending(item) {
  if (!item?.plan_id) return;
  pendingByPlanId.set(item.plan_id, item);

  const idx = pendingOrder.indexOf(item.plan_id);
  if (idx >= 0) pendingOrder.splice(idx, 1);
  pendingOrder.unshift(item.plan_id);

  while (pendingOrder.length > 100) {
    const removed = pendingOrder.pop();
    if (removed) pendingByPlanId.delete(removed);
  }
}

function removePending(planId) {
  if (!planId) return;
  pendingByPlanId.delete(planId);
  const idx = pendingOrder.indexOf(planId);
  if (idx >= 0) pendingOrder.splice(idx, 1);
}

function latestPendingForChat(chatId) {
  for (const planId of pendingOrder) {
    const item = pendingByPlanId.get(planId);
    if (item && item.chat_id === chatId) {
      return item;
    }
  }
  return null;
}

function approvalButtons(planId) {
  return [
    [
      btn("✅ Aprobar", `approval:approve:${planId}`),
      btn("❌ Rechazar", `approval:reject:${planId}`)
    ],
    [btn("📋 Ver pendientes", "pending:list")],
    [btn("🏰 Menú", "menu:main")]
  ];
}

function formatPendingMessage(item) {
  const stepReports = Array.isArray(item?.report?.step_reports)
    ? item.report.step_reports
    : [];

  const first = stepReports[0] || {};
  const action = first?.action || "acción";
  const risk = item?.report?.risk_summary || "unknown";

  return (
    "⏸️ Acción pendiente de aprobación\n\n" +
    `Plan: ${item.plan_id}\n` +
    `Acción: ${action}\n` +
    `Riesgo: ${risk}\n\n` +
    "Elegí qué querés hacer:"
  );
}

function emitApprovalRequested(item, traceId = null) {
  const meta = buildMeta(item?.meta || {}, {
    plan_id: item?.plan_id || null,
    task_id: item?.task_id || item?.plan_id || null,
    chat_id: item?.chat_id ?? null
  });
  const finalTraceId = traceId || item?.trace_id || generateTraceId();

  emit("event.out", {
    level: "warn",
    type: "approval_requested",
    plan_id: item.plan_id,
    task_id: item.task_id,
    status: "awaiting_approval",
    trace_id: finalTraceId,
    meta
  });

  if (item.chat_id != null) {
    emit("ui.response.out", {
      chat_id: item.chat_id,
      mode: "send",
      text: formatPendingMessage(item),
      inline_keyboard: approvalButtons(item.plan_id),
      trace_id: finalTraceId,
      meta
    });
  }
}

function emitPendingList(chatId, traceId = null, meta = {}) {
  const items = pendingOrder
    .map((planId) => pendingByPlanId.get(planId))
    .filter((item) => item && item.chat_id === chatId);

  const finalTraceId = traceId || generateTraceId();
  const finalMeta = buildMeta(meta, { chat_id: chatId });

  if (!items.length) {
    emit("ui.response.out", {
      chat_id: chatId,
      mode: "send",
      text: "No hay planes pendientes para aprobar.",
      inline_keyboard: [[btn("🏰 Menú", "menu:main")]],
      trace_id: finalTraceId,
      meta: finalMeta
    });
    return;
  }

  const lines = items.slice(0, 10).map((item, index) => {
    const step = item?.report?.step_reports?.[0];
    return `${index + 1}. ${item.plan_id} · ${step?.action || "acción"}`;
  });

  emit("ui.response.out", {
    chat_id: chatId,
    mode: "send",
    text: `Pendientes:\n\n${lines.join("\n")}`,
    inline_keyboard: [
      ...items.slice(0, 5).map((item) => [
        btn(`✅ ${item.plan_id.slice(-6)}`, `approval:approve:${item.plan_id}`),
        btn(`❌ ${item.plan_id.slice(-6)}`, `approval:reject:${item.plan_id}`)
      ]),
      [btn("🏰 Menú", "menu:main")]
    ],
    trace_id: finalTraceId,
    meta: finalMeta
  });
}

function emitApproved(item, traceId = null, meta = {}) {
  const finalTraceId = traceId || generateTraceId();
  const finalMeta = buildMeta(meta, {
    source: item?.source || meta?.source || "telegram",
    chat_id: item?.chat_id ?? null,
    plan_id: item?.plan_id || null,
    task_id: item?.task_id || item?.plan_id || null
  });

  emit("event.out", {
    level: "info",
    type: "approval_approved",
    plan_id: item.plan_id,
    task_id: item.task_id,
    status: "approved",
    trace_id: finalTraceId,
    meta: finalMeta
  });

  emit("approved.plan.out", {
    ...(item.original_plan || {}),
    plan_id: item.plan_id,
    task_id: item.task_id,
    trace_id: finalTraceId,
    meta: finalMeta
  });

  if (item.chat_id != null) {
    emit("ui.response.out", {
      chat_id: item.chat_id,
      mode: "send",
      text: `✅ Plan aprobado: ${item.plan_id}`,
      inline_keyboard: [[btn("🏰 Menú", "menu:main")]],
      trace_id: finalTraceId,
      meta: finalMeta
    });
  }
}

function emitRejected(item, traceId = null, meta = {}) {
  const finalTraceId = traceId || generateTraceId();
  const finalMeta = buildMeta(meta, {
    source: item?.source || meta?.source || "telegram",
    chat_id: item?.chat_id ?? null,
    plan_id: item?.plan_id || null,
    task_id: item?.task_id || item?.plan_id || null
  });

  emit("event.out", {
    level: "warn",
    type: "approval_rejected",
    plan_id: item.plan_id,
    task_id: item.task_id,
    status: "rejected",
    trace_id: finalTraceId,
    meta: finalMeta
  });

  emit("response.out", {
    task_id: item.task_id,
    plan_id: item.plan_id,
    status: "error",
    error: "Plan rechazado por el usuario",
    trace_id: finalTraceId,
    meta: finalMeta
  });

  if (item.chat_id != null) {
    emit("ui.response.out", {
      chat_id: item.chat_id,
      mode: "send",
      text: `❌ Plan rechazado: ${item.plan_id}`,
      inline_keyboard: [[btn("🏰 Menú", "menu:main")]],
      trace_id: finalTraceId,
      meta: finalMeta
    });
  }
}

function approveItem(item, payload = {}, meta = {}, traceId = null) {
  if (!item) return;
  removePending(item.plan_id);
  emitApproved(item, traceId, meta);
}

function rejectItem(item, payload = {}, meta = {}, traceId = null) {
  if (!item) return;
  removePending(item.plan_id);
  emitRejected(item, traceId, meta);
}

function resolveTarget(action, payload = {}, planId = null, meta = {}) {
  const explicitPlanId =
    planId ||
    payload?.plan_id ||
    resolvePlanId(payload, meta) ||
    null;

  if (explicitPlanId && pendingByPlanId.has(explicitPlanId)) {
    return pendingByPlanId.get(explicitPlanId);
  }

  const chatId = resolveChatId(payload, meta);
  if (chatId != null) {
    return latestPendingForChat(chatId);
  }

  return null;
}

function handleBlockedPlan(payload = {}, meta = {}, traceId = null) {
  const item = normalizePendingItem(payload, meta, traceId);
  if (!item) return;

  rememberPending(item);
  emitApprovalRequested(item, traceId);
}

function handleRequest(payload = {}, meta = {}, traceId = null) {
  const action = payload?.action || "";
  const chatId = resolveChatId(payload, meta);

  if (action === "list_pending" && chatId != null) {
    emitPendingList(chatId, traceId, meta);
  }
}

function handleCommand(payload = {}, meta = {}, traceId = null) {
  const rawText = String(payload?.text || "").trim();
  const text = rawText.toLowerCase();
  const chatId = resolveChatId(payload, meta);

  if (text === "aprobar" || text === "approve") {
    const item = latestPendingForChat(chatId);
    if (item) {
      approveItem(item, payload, meta, traceId);
    }
    return;
  }

  if (text === "rechazar" || text === "reject") {
    const item = latestPendingForChat(chatId);
    if (item) {
      rejectItem(item, payload, meta, traceId);
    }
    return;
  }

  if (text.startsWith("aprobar ") || text.startsWith("approve ")) {
    const planId = rawText.split(/\s+/).slice(1).join(" ").trim();
    const item = resolveTarget("approve", payload, planId, meta);
    if (item) {
      approveItem(item, payload, meta, traceId);
    }
    return;
  }

  if (text.startsWith("rechazar ") || text.startsWith("reject ")) {
    const planId = rawText.split(/\s+/).slice(1).join(" ").trim();
    const item = resolveTarget("reject", payload, planId, meta);
    if (item) {
      rejectItem(item, payload, meta, traceId);
    }
  }
}

function handleCallback(payload = {}, meta = {}, traceId = null) {
  const action = payload?.action || "";
  const data = payload?.data || "";

  if (action === "list_pending") {
    const chatId = resolveChatId(payload, meta);
    if (chatId != null) {
      emitPendingList(chatId, traceId, meta);
    }
    return;
  }

  if (action === "approve_last") {
    const item = resolveTarget("approve", payload, null, meta);
    if (item) approveItem(item, payload, meta, traceId);
    return;
  }

  if (action === "reject_last") {
    const item = resolveTarget("reject", payload, null, meta);
    if (item) rejectItem(item, payload, meta, traceId);
    return;
  }

  if (action === "approve_plan") {
    const item = resolveTarget("approve", payload, payload?.plan_id || null, meta);
    if (item) approveItem(item, payload, meta, traceId);
    return;
  }

  if (action === "reject_plan") {
    const item = resolveTarget("reject", payload, payload?.plan_id || null, meta);
    if (item) rejectItem(item, payload, meta, traceId);
    return;
  }

  if (typeof data === "string" && data.startsWith("approval:approve:")) {
    const planId = data.slice("approval:approve:".length);
    const item = resolveTarget("approve", payload, planId, meta);
    if (item) approveItem(item, payload, meta, traceId);
    return;
  }

  if (typeof data === "string" && data.startsWith("approval:reject:")) {
    const planId = data.slice("approval:reject:".length);
    const item = resolveTarget("reject", payload, planId, meta);
    if (item) rejectItem(item, payload, meta, traceId);
  }
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const payload = msg?.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (msg.port === "blocked.plan.in") {
    handleBlockedPlan(payload, mergedMeta, traceId);
    return;
  }

  if (msg.port === "command.in") {
    handleCommand(payload, mergedMeta, traceId);
    return;
  }

  if (msg.port === "request.in") {
    handleRequest(payload, mergedMeta, traceId);
    return;
  }

  if (msg.port === "callback.in") {
    handleCallback(payload, mergedMeta, traceId);
  }
});