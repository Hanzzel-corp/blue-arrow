import readline from "readline";

const MODULE_ID = "agent.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function generateTraceId() {
  return `agent_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function safeNowIso() {
  return new Date().toISOString();
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "internal",
    timestamp: safeNowIso(),
    module: MODULE_ID
  };

  const { trace_id: _traceId, meta: _meta, ...cleanPayload } = payload || {};

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

function emitSignal(signalType, payload, meta = {}, traceId = null) {
  const signal = {
    type: signalType,
    payload,
    meta: {
      source: MODULE_ID,
      timestamp: safeNowIso(),
      correlation_id: `sig_${Date.now()}`,
      ...meta
    },
    trace_id: traceId || generateTraceId()
  };

  emit("signal.out", signal);
  return signal;
}

function buildIntentSignal(cmd, traceId = null) {
  const text = cmd?.text || "";
  const source = cmd?.source || "cli";

  emitSignal(
    "user_command",
    {
      raw_text: text,
      chat_id: cmd?.chat_id || null,
      user_id: cmd?.meta?.user_id || null,
      source
    },
    {
      chat_id: cmd?.chat_id || null,
      session_id: cmd?.meta?.session_id || null
    },
    traceId
  );

  return text;
}

function normalizeText(text) {
  return (text || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildPlan(cmd, steps, extraMeta = {}) {
  const mergedMeta = {
    source: cmd?.source || "cli",
    chat_id: cmd?.chat_id || null,
    ...(cmd?.meta || {}),
    ...extraMeta
  };

  return {
    plan_id: `plan_${Date.now()}`,
    kind: steps.length > 1 ? "multi_step" : "single_step",
    original_command: cmd?.text || "",
    meta: mergedMeta,
    steps
  };
}

function buildOpenApplicationPlan(cmd, appName, extraMeta = {}) {
  return buildPlan(
    cmd,
    [
      {
        action: "open_application",
        params: { name: appName }
      }
    ],
    extraMeta
  );
}

function buildOfficePlan(cmd) {
  const text = cmd?.text || "";
  const normalized = normalizeText(text);

  const mentionsOffice =
    normalized.includes("writer") ||
    normalized.includes("libreoffice") ||
    normalized.includes("office") ||
    normalized.includes("documento");

  if (!mentionsOffice) {
    return null;
  }

  const wantsWriting =
    normalized.includes("redact") ||
    normalized.includes("escrib") ||
    normalized.includes("nota") ||
    normalized.includes("carta") ||
    normalized.includes("mejor") ||
    normalized.includes("texto") ||
    normalized.includes("contenido");

  if (wantsWriting) {
    return buildPlan(cmd, [
      {
        action: "office.writer.generate",
        params: {
          prompt: text,
          text
        }
      }
    ]);
  }

  return buildPlan(cmd, [
    {
      action: "office.open_writer",
      params: {}
    }
  ]);
}

function buildLockedResolvedPlan(payload) {
  const meta = payload?.meta || {};
  const resolvedAction = meta?.resolved_action || null;

  if (!meta?.locked || !resolvedAction?.action) {
    return null;
  }

  const activeApp = meta?.active_app || null;
  const resolvedApplication = meta?.resolved_application || null;

  const mergedParams = {
    ...(resolvedAction.params || {})
  };

  if (
    resolvedAction.action === "terminal.write_command" &&
    !mergedParams.window_id
  ) {
    mergedParams.window_id =
      resolvedAction?.params?.window_id ||
      resolvedApplication?.window_id ||
      activeApp?.window_id ||
      meta?.window_id ||
      null;
  }

  return {
    plan_id: `plan_${Date.now()}`,
    kind: "single_step",
    original_command: payload?.text || "",
    steps: [
      {
        step_id: meta?.step_id || "step_1",
        action: resolvedAction.action,
        params: mergedParams
      }
    ],
    meta: {
      ...meta,
      source: payload?.source || meta?.source || "unknown",
      chat_id: payload?.chat_id || meta?.chat_id || null,
      planner: {
        planned: true,
        mode: "single_step_plan"
      },
      resolved_application: {
        ...(resolvedApplication || {}),
        window_id:
          resolvedApplication?.window_id ||
          activeApp?.window_id ||
          meta?.window_id ||
          null
      }
    }
  };
}

function buildLockedPlanFromMeta(cmd) {
  const meta = cmd?.meta || {};

  if (meta?.target_application) {
    return buildOpenApplicationPlan(cmd, meta.target_application, {
      locked: true,
      resolved_by: "meta.target_application"
    });
  }

  if (meta?.ui_origin === "apps_menu" && (meta.app_command || meta.app_id)) {
    const appName = meta.app_command || cmd?.text || "unknown_app";

    return buildOpenApplicationPlan(cmd, appName, {
      locked: true,
      resolved_by: "apps_menu"
    });
  }

  return null;
}

function planFromCommand(cmd) {
  const lockedPlan = buildLockedPlanFromMeta(cmd);
  if (lockedPlan) {
    return lockedPlan;
  }

  const text = normalizeText(cmd?.text).trim();

  let m = text.match(/^(buscar archivo|busca archivo|search file)\s+(.+)$/i);
  if (m) {
    return buildPlan(cmd, [
      {
        action: "search_file",
        params: {
          filename: m[2].trim(),
          base_path: "."
        }
      }
    ]);
  }

  if (
    /^(recurso|recursos|estado sistema|estado del sistema|monitor resources)$/i.test(
      text
    )
  ) {
    return buildPlan(cmd, [
      {
        action: "monitor_resources",
        params: {}
      }
    ]);
  }

  const mGoogle = text.match(/^(buscar en google|googlear|google)\s+(.+)$/i);
  if (mGoogle) {
    return buildPlan(cmd, [
      {
        action: "search_google",
        params: {
          query: mGoogle[2].trim()
        }
      }
    ]);
  }

  const mUrl = text.match(
    /^(abrir web|abrir pagina|abrir pagina web|open url|ir a)\s+(.+)$/i
  );
  if (mUrl) {
    const raw = mUrl[2].trim();
    const url = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;

    return buildPlan(cmd, [
      {
        action: "open_url",
        params: { url }
      }
    ]);
  }

  const mClick = text.match(/^click web\s+(.+?)\s+\|\s+(.+)$/i);
  if (mClick) {
    const rawUrl = mClick[1].trim();
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;

    return buildPlan(cmd, [
      {
        action: "click_web",
        params: {
          url,
          selector: mClick[2].trim()
        }
      }
    ]);
  }

  const mForm = text.match(/^form web\s+(.+?)\s+\|\s+(.+?)(?:\s+\|\s+(.+))?$/i);
  if (mForm) {
    const rawUrl = mForm[1].trim();
    const url = /^https?:\/\//i.test(rawUrl) ? rawUrl : `https://${rawUrl}`;

    const fieldsRaw = mForm[2]
      .split(";")
      .map((x) => x.trim())
      .filter(Boolean);

    const fields = [];

    for (const item of fieldsRaw) {
      const idx = item.indexOf("=");
      if (idx === -1) continue;

      fields.push({
        selector: item.slice(0, idx).trim(),
        value: item.slice(idx + 1).trim()
      });
    }

    const submitSelector = mForm[3] ? mForm[3].trim() : null;

    return buildPlan(cmd, [
      {
        action: "fill_form",
        params: {
          url,
          fields,
          submit_selector: submitSelector
        }
      }
    ]);
  }

  if (text.includes("github")) {
    return buildPlan(cmd, [
      {
        action: "open_url",
        params: { url: "https://github.com" }
      }
    ]);
  }

  if (text.includes("google")) {
    return buildPlan(cmd, [
      {
        action: "open_url",
        params: { url: "https://www.google.com" }
      }
    ]);
  }

  if (text.includes("youtube")) {
    return buildPlan(cmd, [
      {
        action: "open_url",
        params: { url: "https://www.youtube.com" }
      }
    ]);
  }

  const mAI = text.match(/^(ia|ai|preguntale|pregunta)\s*[:\-]?\s*(.+)$/i);
  if (mAI) {
    const question = mAI[2].trim();
    return buildPlan(
      cmd,
      [
        {
          action: "ai.query",
          params: {
            prompt: question,
            system_prompt: "Eres un asistente útil y conciso. Responde en español."
          }
        }
      ],
      { target_module: "ai.assistant.main" }
    );
  }

  const officePlan = buildOfficePlan(cmd);
  if (officePlan) {
    return officePlan;
  }

  if (/^(abri|abrir|abre|open)\b/.test(text)) {
    let app = null;

    if (text.includes("chrome")) app = "Google Chrome";
    else if (text.includes("firefox")) app = "Firefox";
    else if (
      text.includes("vscode") ||
      text.includes("vs code") ||
      text.includes("visual studio code") ||
      /\bcode\b/.test(text)
    ) {
      app = "VS Code";
    } else {
      app = text
        .replace(/^(abri|abrir|abre|open)\s+/, "")
        .replace(/^(aplicacion|app)\s+/, "")
        .trim();
    }

    return buildOpenApplicationPlan(cmd, app);
  }

  return buildPlan(cmd, [
    {
      action: "echo_text",
      params: { text: cmd?.text || "" }
    }
  ]);
}

function isApprovalCommand(normalized) {
  return (
    /^aprobar\s+[a-z0-9._-]+$/i.test(normalized) ||
    /^rechazar\s+[a-z0-9._-]+$/i.test(normalized)
  );
}

function isMemoryQuery(normalized) {
  return (
    normalized.includes("ultimo comando") ||
    normalized.includes("ultima app") ||
    normalized.includes("ultimo archivo") ||
    normalized.includes("ultimo arcivo") ||
    normalized.includes("ultimo estado")
  );
}

function isAuditCommand(normalized) {
  return (
    normalized === "auditar proyecto" ||
    /^auditar modulo\s+.+$/i.test(normalized)
  );
}

function hasLockedMeta(payload = {}) {
  const meta = payload?.meta || {};
  return Boolean(
    meta?.target_application ||
      meta?.locked === true ||
      meta?.resolved_by ||
      meta?.resolved_action?.action
  );
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (err) {
    emit("event.out", {
      level: "error",
      type: "agent_invalid_json",
      text: "agent.main recibió una línea JSON inválida",
      error: String(err?.message || err),
      raw_line: String(line).slice(0, 500),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeNowIso()
      }
    });
    return;
  }

  if (msg.port !== "command.in") {
    return;
  }

  const payload = msg.payload || {};
  const normalized = normalizeText(payload?.text || "").trim();
  const traceId = payload?.trace_id || msg?.trace_id || generateTraceId();

  buildIntentSignal(payload, traceId);

  emit("event.out", {
    level: "info",
    text: "Comando recibido por agent.main",
    type: "agent_command_received",
    command_text: payload?.text || "",
    trace_id: traceId,
    meta: {
      source: payload?.source || "cli",
      chat_id: payload?.chat_id || null,
      module: MODULE_ID,
      timestamp: safeNowIso()
    }
  });

  const meta = {
    source: payload?.source || "cli",
    chat_id: payload?.chat_id || null,
    ...(payload?.meta || {})
  };

  const lockedPlan = buildLockedResolvedPlan(payload);

  if (lockedPlan) {
    emit("event.out", {
      level: "info",
      type: "agent_locked_command_respected",
      text: "Agent respetó una acción ya resuelta por metadata",
      plan_id: lockedPlan.plan_id,
      meta: lockedPlan.meta,
      trace_id: traceId
    });

    emit("plan.out", { ...lockedPlan, trace_id: traceId });
    return;
  }

  if (hasLockedMeta(payload)) {
    const lockedPlanFromMeta = buildLockedPlanFromMeta(payload);

    if (lockedPlanFromMeta) {
      emit("event.out", {
        level: "info",
        type: "agent_locked_command_respected",
        text: "Agent respetó un comando ya resuelto por metadata",
        plan_id: lockedPlanFromMeta.plan_id || null,
        meta: lockedPlanFromMeta.meta || {},
        trace_id: traceId
      });

      emit("plan.out", { ...lockedPlanFromMeta, trace_id: traceId });
      return;
    }
  }

  if (isMemoryQuery(normalized)) {
    emit("memory.query.out", {
      text: payload.text,
      meta,
      trace_id: traceId
    });
    return;
  }

  if (isAuditCommand(normalized)) {
    emit("audit.request.out", {
      text: payload.text,
      meta,
      trace_id: traceId
    });
    return;
  }

  if (isApprovalCommand(normalized)) {
    emit("approval.command.out", {
      text: payload.text,
      meta,
      trace_id: traceId
    });
    return;
  }

  const plan = planFromCommand(payload);

  if (plan && Array.isArray(plan.steps) && plan.steps.length > 1) {
    emit("event.out", {
      level: "info",
      type: "agent_multi_step_detected",
      text: "Plan detectado, delegando a runner",
      plan_id: plan.plan_id || null,
      step_count: plan.steps.length,
      trace_id: traceId,
      meta: {
        ...(plan.meta || {}),
        module: MODULE_ID,
        timestamp: safeNowIso()
      }
    });

    emit("plan.out", { ...plan, trace_id: traceId });
    return;
  }

  emit("plan.out", { ...plan, trace_id: traceId });
});