import readline from "readline";
import { getIdempotencyGuard } from "../../lib/idempotency.js";

const MODULE_ID = "interface.telegram";
const TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const API = TOKEN ? `https://api.telegram.org/bot${TOKEN}` : null;

const idempotency = getIdempotencyGuard();

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

const stateByChat = new Map();

function generateTraceId() {
  return `tg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

function safeIsoNow() {
  return new Date().toISOString();
}

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "telegram",
    timestamp: safeIsoNow(),
    module: MODULE_ID,
    chat_id: payload?.chat_id || payload?.meta?.chat_id || null
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

function safeJsonParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function getChatState(chatId) {
  const key = String(chatId ?? "global");

  if (!stateByChat.has(key)) {
    stateByChat.set(key, {
      chat_id: chatId ?? null,
      active_app: null,
      resolved_application: null,
      window_id: null,
      updated_at: null
    });
  }

  return stateByChat.get(key);
}

function saveChatState(chatId, state) {
  const key = String(chatId ?? "global");
  stateByChat.set(key, state);
}

function normalizeApp(app) {
  if (!app) return null;

  return {
    id: app?.id || null,
    label: app?.label || null,
    command: app?.command || null,
    source: app?.source || null,
    family: app?.family || null,
    capabilities: Array.isArray(app?.capabilities) ? app.capabilities : [],
    window_id: app?.window_id || null
  };
}

function normalizeResolvedApplication(app) {
  if (!app) return null;

  return {
    id: app?.id || null,
    label: app?.label || null,
    command: app?.command || null,
    source: app?.source || null,
    window_id: app?.window_id || null
  };
}

function buildResolvedApplicationFromState(state) {
  return normalizeResolvedApplication(state?.active_app || null);
}

function enrichTelegramCommandPayload(payload, state) {
  const activeApp = state?.active_app || null;
  const resolvedApplication =
    state?.resolved_application || buildResolvedApplicationFromState(state);

  return {
    ...payload,
    meta: {
      ...(payload?.meta || {}),
      active_app: activeApp,
      resolved_application: resolvedApplication,
      window_id:
        activeApp?.window_id ||
        resolvedApplication?.window_id ||
        state?.window_id ||
        null
    }
  };
}

function updateStateFromAppContext(payload = {}, envelopeMeta = {}, incomingTraceId = null) {
  const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});
  const chatId =
    payload?.chat_id ??
    mergedMeta?.chat_id ??
    payload?.session?.chat_id ??
    null;

  if (chatId == null) return;

  const state = getChatState(chatId);

  const hasExplicitApp =
    Object.prototype.hasOwnProperty.call(payload, "app") ||
    Object.prototype.hasOwnProperty.call(payload, "active_app") ||
    Object.prototype.hasOwnProperty.call(payload, "session");

  const rawApp =
    payload?.app ??
    payload?.active_app ??
    payload?.session?.app ??
    mergedMeta?.active_app ??
    null;

  const rawResolved =
    payload?.resolved_application ??
    mergedMeta?.resolved_application ??
    payload?.session?.resolved_application ??
    null;

  const nextApp = hasExplicitApp ? normalizeApp(rawApp) : state.active_app;
  const nextResolved =
    rawResolved !== null
      ? normalizeResolvedApplication(rawResolved)
      : buildResolvedApplicationFromState({ active_app: nextApp });

  state.chat_id = chatId;
  state.active_app = nextApp;
  state.resolved_application = nextResolved;
  state.window_id =
    nextApp?.window_id ||
    nextResolved?.window_id ||
    payload?.window_id ||
    mergedMeta?.window_id ||
    null;
  state.updated_at = safeIsoNow();

  saveChatState(chatId, state);

  emit("event.out", {
    level: "info",
    type: "telegram_context_updated",
    text: "interface.telegram actualizó contexto de app activa",
    meta: {
      source: "telegram",
      chat_id: chatId,
      active_app: state.active_app,
      resolved_application: state.resolved_application,
      window_id: state.window_id,
      module: MODULE_ID,
      timestamp: safeIsoNow()
    },
    trace_id: incomingTraceId || generateTraceId()
  });
}

async function tg(method, body = {}) {
  if (!API) {
    throw new Error("TELEGRAM_BOT_TOKEN no configurado");
  }

  let res;
  try {
    res = await fetch(`${API}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  } catch (err) {
    const cause =
      err?.cause?.code ||
      err?.cause?.message ||
      err?.message ||
      String(err);

    throw new Error(`Fetch error en ${method}: ${cause}`);
  }

  let raw = "";
  try {
    raw = await res.text();
  } catch (err) {
    throw new Error(`No pude leer respuesta de Telegram en ${method}: ${err.message}`);
  }

  const data = safeJsonParse(raw);
  if (!data && raw) {
    throw new Error(
      `Respuesta no JSON de Telegram en ${method} (status ${res.status}): ${raw.slice(0, 300)}`
    );
  }

  if (!res.ok) {
    throw new Error(
      `HTTP ${res.status} en ${method}: ${data?.description || raw || "sin detalle"}`
    );
  }

  if (!data?.ok) {
    throw new Error(data?.description || `Telegram error en ${method}`);
  }

  return data.result;
}

function buildReplyMarkup(inlineKeyboard) {
  if (!Array.isArray(inlineKeyboard) || inlineKeyboard.length === 0) {
    return undefined;
  }

  return {
    inline_keyboard: inlineKeyboard
  };
}

async function sendTelegramMessage(chatId, text, extra = {}) {
  if (!chatId || !text) return;

  await tg("sendMessage", {
    chat_id: chatId,
    text,
    ...extra
  });
}

async function sendTelegramUI(payload, envelopeMeta = {}) {
  const mergedMeta = mergeMeta(envelopeMeta, payload?.meta || {});
  const chatId = payload?.chat_id ?? mergedMeta?.chat_id ?? null;
  const text = payload?.text || "";
  const messageId = payload?.message_id || null;
  const mode = payload?.mode || (messageId ? "edit" : "send");
  const reply_markup = buildReplyMarkup(payload?.inline_keyboard);
  const parse_mode = payload?.parse_mode || undefined;

  if (!chatId || !text) return;

  if (mode === "edit" && messageId) {
    try {
      await tg("editMessageText", {
        chat_id: chatId,
        message_id: messageId,
        text,
        reply_markup,
        parse_mode
      });
      return;
    } catch (err) {
      const msg = String(err);

      if (msg.includes("message is not modified")) {
        return;
      }

      if (
        msg.includes("message to edit not found") ||
        msg.includes("message can't be edited")
      ) {
        await sendTelegramMessage(chatId, text, {
          reply_markup,
          parse_mode
        });
        return;
      }

      throw err;
    }
  }

  await sendTelegramMessage(chatId, text, {
    reply_markup,
    parse_mode
  });
}

function formatSearchResults(result = {}) {
  const top = (result.results || [])
    .slice(0, 5)
    .map((r, i) => `${i + 1}. ${r.text}\n${r.href}`)
    .join("\n\n");

  return (
    `✅ Búsqueda: ${result.query}\n` +
    `${top || "Sin resultados legibles."}`
  );
}

function formatSystemMetrics(result = {}) {
  return (
    "✅ Estado del sistema\n" +
    `CPU: ${result.cpu_percent}%\n` +
    `RAM: ${result.memory_percent}%\n` +
    `Disco: ${result.disk_percent}%`
  );
}

function formatFileMatches(result = {}) {
  if (!Array.isArray(result.matches) || result.matches.length === 0) {
    return `✅ No encontré coincidencias para ${result.filename}`;
  }

  const top = result.matches.slice(0, 5).join("\n");
  return `✅ Coincidencias para ${result.filename}:\n${top}`;
}

function formatResponseText(payload = {}) {
  const result = payload?.result || {};

  if (payload.status === "pending_approval") {
    return `⏸️ ${result?.echo || "La acción requiere aprobación."}`;
  }

  if (payload.status === "approved") {
    return `✅ ${result?.echo || "Plan aprobado. Ejecutando..."}`;
  }

  if (payload.status === "success") {
    if (result?.response) return `${result.response}`;
    if (result?.echo) return `✅ ${result.echo}`;
    if (result?.opened && result?.application) return `✅ Abrí ${result.application}`;
    if (result?.opened && result?.url) return `✅ Abrí ${result.url}`;
    if (result?.searched && result?.query) return formatSearchResults(result);
    if (result?.filled && result?.url) {
      return (
        `✅ Formulario completado en ${result.url}\n` +
        `Campos: ${result.fields?.length || 0}\n` +
        `Submit: ${result.submitted ? "sí" : "no"}`
      );
    }
    if (result?.clicked && result?.selector) {
      return `✅ Click en ${result.selector}`;
    }
    if (
      result?.cpu_percent !== undefined &&
      result?.memory_percent !== undefined &&
      result?.disk_percent !== undefined
    ) {
      return formatSystemMetrics(result);
    }
    if (result?.filename && Array.isArray(result?.matches)) {
      return formatFileMatches(result);
    }
    if (result?.memory_answer) {
      return `✅ ${result.memory_answer}`;
    }
    if (
      result?.success === true &&
      result?.command &&
      (result?.method || "").startsWith("xdotool")
    ) {
      const executed =
        result?.executed === undefined ? true : Boolean(result.executed);

      if (!executed) {
        return (
          "⌨️ Listo, escribí el comando en la Terminal.\n" +
          "Presioná Enter para ejecutarlo.\n\n" +
          `Comando: ${result.command}\n` +
          `Ventana: ${result.window_id || "sin_id"}`
        );
      }

      return (
        `✅ Ejecuté en Terminal: ${result.command}\n` +
        `Ventana: ${result.window_id || "sin_id"}`
      );
    }

    return `✅ ${JSON.stringify(result)}`;
  }

  if (result?.error) return `❌ ${result.error}`;
  if (payload?.error) return `❌ ${payload.error}`;
  return null;
}

async function pollLoop() {
  if (!TOKEN) {
    process.stderr.write("[telegram] Falta TELEGRAM_BOT_TOKEN\n");
    return;
  }

  let offset = 0;

  while (true) {
    try {
      const updates = await tg("getUpdates", {
        offset,
        timeout: 20
      });

      for (const update of updates) {
        offset = update.update_id + 1;

        const cb = update.callback_query;
        if (cb) {
          const chatId = cb.message?.chat?.id || cb.from?.id || null;
          const messageId = cb.message?.message_id || null;

          try {
            await tg("answerCallbackQuery", {
              callback_query_id: cb.id
            });
          } catch (err) {
            process.stderr.write(`[telegram] answerCallbackQuery error: ${String(err)}\n`);
          }

          const callbackCheck = idempotency.isDuplicate("telegram_callback", {
            callback_id: cb.id,
            data: cb.data
          }, { chat_id: chatId, user_id: cb.from?.id });

          if (callbackCheck.isDuplicate) {
            process.stderr.write(`[telegram] Callback duplicado ignorado: ${cb.id} (hace ${callbackCheck.age}s)\n`);
            continue;
          }

          const traceId = generateTraceId();
          emit("callback.out", {
            callback_id: cb.id,
            data: cb.data || "",
            source: "telegram",
            chat_id: chatId,
            message_id: messageId,
            trace_id: traceId,
            meta: {
              source: "telegram",
              chat_id: chatId,
              user_id: cb.from?.id || null,
              idempotency_key: callbackCheck.fingerprint,
              module: MODULE_ID,
              timestamp: safeIsoNow()
            }
          });

          continue;
        }

        const message = update.message;
        if (!message?.text) continue;

        const text = message.text || "";
        const chatId = message.chat.id;

        if (/^\/?(start|menu|inicio)$/i.test(text.trim())) {
          const menuCheck = idempotency.isDuplicate("telegram_menu_command", {
            command: "menu:main"
          }, { chat_id: chatId, user_id: message.from?.id, message_id: message.message_id });

          if (menuCheck.isDuplicate) {
            process.stderr.write("[telegram] Comando de menú duplicado ignorado\n");
            continue;
          }

          const traceId = generateTraceId();
          emit("callback.out", {
            callback_id: null,
            data: "menu:main",
            source: "telegram",
            chat_id: chatId,
            message_id: null,
            trace_id: traceId,
            meta: {
              source: "telegram",
              chat_id: chatId,
              user_id: message.from?.id || null,
              idempotency_key: menuCheck.fingerprint,
              module: MODULE_ID,
              timestamp: safeIsoNow()
            }
          });
          continue;
        }

        const state = getChatState(chatId);

        const commandCheck = idempotency.isDuplicate("telegram_text_command", {
          text: text,
          chat_id: chatId
        }, { chat_id: chatId, user_id: message.from?.id, message_id: message.message_id });

        if (commandCheck.isDuplicate) {
          process.stderr.write(`[telegram] Comando duplicado ignorado: "${text.substring(0, 30)}..." (hace ${commandCheck.age}s)\n`);
          continue;
        }

        const traceId = generateTraceId();
        let commandPayload = {
          command_id: `tg_${update.update_id}`,
          text,
          source: "telegram",
          chat_id: chatId,
          trace_id: traceId,
          meta: {
            source: "telegram",
            chat_id: chatId,
            user_id: message.from?.id || null,
            idempotency_key: commandCheck.fingerprint,
            module: MODULE_ID,
            timestamp: safeIsoNow()
          }
        };

        commandPayload = enrichTelegramCommandPayload(commandPayload, state);
        emit("command.out", commandPayload);

        emit("action.out", {
          action: "game.track",
          params: {
            user_id: message.from?.id || chatId,
            command: text,
            action_type: "command",
            success: true,
            context: {
              source: "telegram",
              chat_id: chatId
            }
          },
          trace_id: traceId,
          meta: {
            source: "telegram",
            chat_id: chatId,
            idempotency_key: commandCheck.fingerprint,
            module: MODULE_ID,
            timestamp: safeIsoNow()
          }
        });
      }
    } catch (err) {
      process.stderr.write(`[telegram][pollLoop] ${err.message}\n`);
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

rl.on("line", async (line) => {
  if (!line.trim()) return;

  const msg = safeJsonParse(line);
  if (!msg) {
    process.stderr.write("[telegram] línea JSON inválida en stdin\n");
    return;
  }

  const payload = msg?.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (msg.port === "app.context.in" || msg.port === "app.session.in") {
    updateStateFromAppContext(payload, mergedMeta, traceId);
    return;
  }

  if (msg.port === "event.in") {
    if (payload?.type === "ui_active_app_changed") {
      updateStateFromAppContext({
        chat_id: payload?.chat_id,
        app: payload?.app ?? null,
        resolved_application: payload?.app
          ? {
              id: payload.app.id || null,
              label: payload.app.label || null,
              command: payload.app.command || null,
              source: payload.app.source || null,
              window_id: payload.app.window_id || null
            }
          : null,
        meta: {
          chat_id: payload?.chat_id,
          active_app: payload?.app || null,
          resolved_application: payload?.app
            ? {
                id: payload.app.id || null,
                label: payload.app.label || null,
                command: payload.app.command || null,
                source: payload.app.source || null,
                window_id: payload.app.window_id || null
              }
            : null,
          window_id: payload?.app?.window_id || null
        }
      }, mergedMeta, traceId);
    }

    return;
  }

  if (msg.port === "ui.response.in") {
    sendTelegramUI(payload, mergedMeta).catch((err) => {
      process.stderr.write(`[telegram] ui send error: ${String(err)}\n`);
    });
    return;
  }

  if (msg.port === "response.in") {
    emit("event.out", {
      level: "info",
      type: "telegram_response_in_received",
      text: "interface.telegram recibió response.in",
      meta: {
        ...mergedMeta,
        module: MODULE_ID,
        timestamp: safeIsoNow()
      },
      trace_id: traceId
    });

    if (mergedMeta.source === "telegram" && mergedMeta.chat_id) {
      if (payload.result?.response) {
        try {
          await sendTelegramMessage(mergedMeta.chat_id, payload.result.response);
        } catch (err) {
          process.stderr.write(`[telegram][sendMessage] ${err.message}\n`);
        }
        return;
      }

      if (payload.type === "ai_query_completed" && payload.status === "success") {
        emit("event.out", {
          level: "info",
          type: "ai_response_received",
          text: "AI query completed",
          task_id: payload.task_id,
          meta: {
            ...mergedMeta,
            module: MODULE_ID,
            timestamp: safeIsoNow()
          },
          trace_id: traceId
        });
        return;
      }

      if (payload.type?.startsWith("ai_") && payload.text) {
        if (payload.type === "ai_query_processing" || payload.type === "ai_query_received") {
          return;
        }
      }

      const text = formatResponseText(payload);

      if (!text) {
        return;
      }

      try {
        await sendTelegramMessage(mergedMeta.chat_id, text);
      } catch (err) {
        process.stderr.write(`[telegram][sendMessage] ${err.message}\n`);
      }
    }
  }
});

pollLoop();