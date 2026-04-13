import readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const MODULE_ID = "safety.guard.main";

function generateTraceId() {
  return `sg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

const POLICY = {
  allow: new Set([
    "echo_text",
    "search_file",
    "monitor_resources",
    "open_url",
    "search_google",
    "click_web",
    "fill_form",
    "ai.query",
    "ai.generate_text",
    "ai.analyze_intent",
    "ai.generate_code",
    "ai.explain_error",
    "ai.analyze_project",
    "ai.get_preferences",
    "ai.predict",
    "ai.clear_history"
  ]),
  confirm: new Set([
    "open_application",
    "terminal.write_command",
    "delete_file",
    "move_many_files",
    "terminate_process",
    "run_shell",
    "run_command",
    "move_file",
    "copy_file",
    "ai.learn",
    "office.open_writer",
    "office.write_text",
    "office.writer.generate"
  ]),
  block: new Set([
    "disable_antivirus",
    "extract_passwords",
    "hidden_persistence",
    "credential_dumping"
  ])
};

function buildMeta(plan = {}, envelopeMeta = {}) {
  const merged = mergeMeta(envelopeMeta, plan?.meta || {});
  return {
    ...merged,
    source: merged?.source || "unknown",
    chat_id: merged?.chat_id || null,
    module: MODULE_ID,
    timestamp: safeIsoNow()
  };
}

function resolvePlanId(plan = {}, meta = {}) {
  return (
    plan?.plan_id ||
    plan?.task_id ||
    meta?.plan_id ||
    meta?.task_id ||
    null
  );
}

function classifyAction(action) {
  if (typeof action !== "string" || !action.trim()) {
    return {
      policy: "invalid",
      risk: "high",
      can_pass: false,
      reason: "invalid_action"
    };
  }

  if (POLICY.block.has(action)) {
    return {
      policy: "block",
      risk: "high",
      can_pass: false,
      reason: "blocked_action"
    };
  }

  if (POLICY.confirm.has(action)) {
    return {
      policy: "confirm",
      risk: action === "office.writer.generate" ? "high" : "medium",
      can_pass: false,
      reason: "confirmation_required"
    };
  }

  if (POLICY.allow.has(action)) {
    return {
      policy: "allow",
      risk: "low",
      can_pass: true,
      reason: "allowed_action"
    };
  }

  return {
    policy: "unknown",
    risk: "high",
    can_pass: false,
    reason: "unknown_action"
  };
}

function summarizeRisk(stepReports) {
  if (stepReports.some((x) => x.risk === "high")) return "high";
  if (stepReports.some((x) => x.risk === "medium")) return "medium";
  return "low";
}

function summarizePolicy(stepReports) {
  if (stepReports.some((x) => x.policy === "block")) return "block";
  if (stepReports.some((x) => x.policy === "invalid")) return "invalid";
  if (stepReports.some((x) => x.policy === "unknown")) return "unknown";
  if (stepReports.some((x) => x.policy === "confirm")) return "confirm";
  return "allow";
}

function previewParams(step) {
  const action = step?.action || null;
  const params =
    step?.params && typeof step.params === "object" ? step.params : {};
  const meta = step?.meta && typeof step.meta === "object" ? step.meta : {};
  const entities =
    step?.entities && typeof step.entities === "object" ? step.entities : {};

  if (action === "open_application") {
    const name =
      meta?.target_application ||
      params?.name ||
      entities?.application ||
      null;

    return {
      ...params,
      name
    };
  }

  if (
    action === "office.open_writer" ||
    action === "office.write_text" ||
    action === "office.writer.generate"
  ) {
    return {
      ...params,
      prompt: typeof params?.prompt === "string" ? params.prompt.slice(0, 120) : params?.prompt,
      text: typeof params?.text === "string" ? params.text.slice(0, 120) : params?.text
    };
  }

  return params;
}

function inspectStep(step, index) {
  const isValidObject = step && typeof step === "object" && !Array.isArray(step);
  const action = isValidObject ? step?.action || null : null;
  const verdict = classifyAction(action);

  return {
    index,
    action,
    params_preview: isValidObject ? previewParams(step) : {},
    policy: verdict.policy,
    risk: verdict.risk,
    can_pass: verdict.can_pass,
    reason: verdict.reason
  };
}

function inspectPlan(plan, envelopeMeta = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const step_reports = steps.map((step, index) => inspectStep(step, index));
  const meta = buildMeta(plan, envelopeMeta);

  return {
    plan_id: resolvePlanId(plan, meta),
    meta,
    total_steps: steps.length,
    risk_summary: summarizeRisk(step_reports),
    policy_summary: summarizePolicy(step_reports),
    step_reports
  };
}

function emitSignal(type, plan, report, extra = {}, traceId = null, envelopeMeta = {}) {
  const meta = buildMeta(plan, envelopeMeta);
  const planId = resolvePlanId(plan, meta);

  emit("signal.out", {
    type,
    task_id: planId,
    plan_id: planId,
    report,
    ...extra,
    trace_id: traceId || generateTraceId(),
    meta
  });
}

function blockInvalidPlan(plan, baseReport, traceId = null, envelopeMeta = {}) {
  const meta = buildMeta(plan, envelopeMeta);
  const planId = resolvePlanId(plan, meta);

  const report = {
    ...baseReport,
    plan_id: planId,
    meta,
    policy_summary: "invalid_plan",
    risk_summary: "high"
  };

  const finalTraceId = traceId || generateTraceId();

  emit("event.out", {
    level: "error",
    type: "safety_guard_blocked",
    text: "Safety bloqueó un plan vacío o inválido",
    report,
    trace_id: finalTraceId,
    meta
  });

  emit("blocked.plan.out", {
    task_id: planId,
    plan_id: planId,
    reason: "invalid_plan",
    confirmable: false,
    report,
    original_plan: plan,
    trace_id: finalTraceId,
    meta
  });

  emitSignal(
    "invalid_plan",
    plan,
    report,
    { reason: "invalid_plan" },
    finalTraceId,
    envelopeMeta
  );
}

function approvePlan(plan, report, traceId = null, envelopeMeta = {}) {
  const meta = buildMeta(plan, envelopeMeta);
  const planId = resolvePlanId(plan, meta);
  const finalTraceId = traceId || generateTraceId();

  emit("event.out", {
    level: "info",
    type: "safety_guard_approved",
    text: `Safety aprobó ${report.total_steps} paso(s) con riesgo ${report.risk_summary}`,
    report,
    trace_id: finalTraceId,
    meta
  });

  emit("approved.plan.out", {
    ...plan,
    task_id: planId,
    plan_id: planId,
    trace_id: finalTraceId,
    meta
  });

  emitSignal(
    "approved",
    plan,
    report,
    { reason: "allow" },
    finalTraceId,
    envelopeMeta
  );
}

function blockOrConfirmPlan(plan, report, traceId = null, envelopeMeta = {}) {
  const isConfirm = report.policy_summary === "confirm";
  const reason = report.policy_summary;
  const finalTraceId = traceId || generateTraceId();
  const meta = buildMeta(plan, envelopeMeta);
  const planId = resolvePlanId(plan, meta);

  emit("event.out", {
    level: isConfirm ? "warn" : "error",
    type: "safety_guard_blocked",
    text: isConfirm
      ? `Safety requiere aprobación manual para ${report.total_steps} paso(s)`
      : `Safety bloqueó plan con política ${report.policy_summary} y riesgo ${report.risk_summary}`,
    report,
    trace_id: finalTraceId,
    meta
  });

  emit("blocked.plan.out", {
    task_id: planId,
    plan_id: planId,
    reason,
    confirmable: isConfirm,
    report,
    original_plan: plan,
    trace_id: finalTraceId,
    meta
  });

  emitSignal(
    isConfirm ? "confirm_required" : "blocked",
    plan,
    report,
    {
      reason,
      confirmable: isConfirm
    },
    finalTraceId,
    envelopeMeta
  );
}

function handlePlan(plan = {}, envelopeMeta = {}, incomingTraceId = null) {
  const report = inspectPlan(plan, envelopeMeta);
  const traceId = incomingTraceId || generateTraceId();

  if (!Array.isArray(plan?.steps) || plan.steps.length === 0) {
    blockInvalidPlan(plan, report, traceId, envelopeMeta);
    return;
  }

  if (report.policy_summary === "allow") {
    approvePlan(plan, report, traceId, envelopeMeta);
    return;
  }

  blockOrConfirmPlan(plan, report, traceId, envelopeMeta);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (error) {
    emit("event.out", {
      level: "error",
      type: "safety_guard_parse_error",
      text: "Safety recibió una línea JSON inválida",
      error: String(error),
      trace_id: generateTraceId(),
      meta: {
        source: "internal",
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
    return;
  }

  if (msg.port !== "plan.in") return;

  try {
    const payload = msg?.payload || {};
    const envelopeMeta = msg?.meta || {};
    const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();
    handlePlan(payload, envelopeMeta, traceId);
  } catch (error) {
    emit("event.out", {
      level: "error",
      type: "safety_guard_runtime_error",
      text: "Safety falló procesando plan.in",
      error: String(error),
      trace_id: generateTraceId(),
      meta: {
        ...(msg?.meta || {}),
        module: MODULE_ID,
        timestamp: safeIsoNow()
      }
    });
  }
});