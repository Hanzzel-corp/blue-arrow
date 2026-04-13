import readline from "readline";

const MODULE_ID = "interface.main";

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function generateTraceId() {
  return `intf_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function extractMeta(msg = {}) {
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof msg?.payload?.meta === "object" && msg?.payload?.meta !== null
      ? msg.payload.meta
      : {};

  return {
    ...topMeta,
    ...payloadMeta
  };
}

function renderResponse(payload = {}) {
  const result = payload?.result || {};

  if (typeof result?.response === "string" && result.response.trim()) {
    return result.response;
  }

  if (typeof result?.echo === "string" && result.echo.trim()) {
    return result.echo;
  }

  if (typeof result?.error === "string" && result.error.trim()) {
    return `ERROR: ${result.error}`;
  }

  if (typeof payload?.error === "string" && payload.error.trim()) {
    return `ERROR: ${payload.error}`;
  }

  return JSON.stringify(payload, null, 2);
}

function showResponse(payload) {
  process.stderr.write(`\n[RESPUESTA]\n${renderResponse(payload)}\n`);
}

function showUi(payload) {
  const text = payload?.text;
  if (typeof text === "string" && text.trim()) {
    process.stderr.write(`\n[UI]\n${text}\n`);
    return;
  }

  process.stderr.write(`\n[UI]\n${JSON.stringify(payload, null, 2)}\n`);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch (error) {
    process.stderr.write(
      `\n[ERROR ${MODULE_ID}]\nJSON inválido: ${String(error)}\n`
    );
    return;
  }

  if (msg.port === "command.in") {
    const traceId = msg?.trace_id || msg?.payload?.trace_id || generateTraceId();
    const mergedMeta = extractMeta(msg);

    emit("command.out", {
      ...(msg.payload || {}),
      trace_id: traceId,
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: mergedMeta?.timestamp || safeIsoNow()
      }
    });
    return;
  }

  if (msg.port === "response.in") {
    const meta = extractMeta(msg);
    if (meta.source !== "telegram") {
      showResponse(msg.payload || {});
    }
    return;
  }

  if (msg.port === "ui.response.in") {
    const meta = extractMeta(msg);
    if (meta.source === "telegram") return;
    showUi(msg.payload || {});
  }
});