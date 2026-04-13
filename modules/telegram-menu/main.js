import readline from "readline";
import { getIdempotencyGuard } from "../../lib/idempotency.js";

const MODULE_ID = "telegram.menu.main";

// Guard de idempotencia
const idempotency = getIdempotencyGuard();

function generateTraceId() {
  return `tgm_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function safeIsoNow() {
  return new Date().toISOString();
}

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function emit(port, payload = {}) {
  const traceId = payload?.trace_id || generateTraceId();
  const meta = payload?.meta || {
    source: "telegram",
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

function buildTelegramMeta(payload = {}, extra = {}) {
  const merged = mergeMeta(payload?._envelope_meta || {}, payload?.meta || {});
  return {
    source: "telegram",
    chat_id: payload?.chat_id ?? merged?.chat_id ?? null,
    user_id: merged?.user_id ?? null,
    module: MODULE_ID,
    timestamp: safeIsoNow(),
    ...merged,
    ...extra
  };
}

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function hasValidChatId(payload) {
  return payload?.chat_id !== null && payload?.chat_id !== undefined;
}

function buildCommandId() {
  return `tgm_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function menuPayload(payload, text, inlineKeyboard, traceId = null) {
  return {
    chat_id: payload?.chat_id || null,
    message_id: payload?.message_id || null,
    mode: payload?.message_id ? "edit" : "send",
    text,
    inline_keyboard: inlineKeyboard,
    meta: buildTelegramMeta(payload),
    trace_id: traceId || generateTraceId()
  };
}

function commandPayload(payload, text, traceId = null) {
  return {
    command_id: buildCommandId(),
    text,
    source: "telegram",
    chat_id: payload?.chat_id || null,
    meta: buildTelegramMeta(payload, {
      ui_origin: "telegram_menu",
      callback_data: payload?.data || null
    }),
    trace_id: traceId || generateTraceId()
  };
}

function approvalRequestPayload(payload, action, traceId = null) {
  return {
    action,
    source: "telegram",
    chat_id: payload?.chat_id || null,
    message_id: payload?.message_id || null,
    trace_id: traceId || generateTraceId(),
    meta: buildTelegramMeta(payload, {
      ui_origin: "telegram_menu",
      callback_data: payload?.data || null
    })
  };
}

function approvalCallbackPayload(payload, action, planId = null, traceId = null) {
  return {
    action,
    plan_id: planId,
    source: "telegram",
    chat_id: payload?.chat_id || null,
    message_id: payload?.message_id || null,
    data: payload?.data || null,
    trace_id: traceId || generateTraceId(),
    meta: buildTelegramMeta(payload, {
      ui_origin: "telegram_menu",
      callback_data: payload?.data || null
    })
  };
}

const MENUS = {
  main: {
    text: "🏰 MENÚ PRINCIPAL 🏰\n━━━━━━━━━━━━━━━━\n🎮 Elige tu próxima aventura:",
    inline_keyboard: [
      [btn("⚔️ Apps", "menu:apps"), btn("🌐 Web", "menu:web")],
      [btn("⚙️ Sistema", "menu:system"), btn("💭 Memoria", "menu:memory")],
      [btn("🏆 Logros", "menu:achievements"), btn("📊 Estadísticas", "menu:stats")],
      [btn("⏳ Pendientes", "menu:pending"), btn("🔍 Auditoría", "menu:audit")],
      [btn("❓ Ayuda", "menu:help")]
    ]
  },
  web: {
    text: "🌐 ZONA WEB 🌐\n━━━━━━━━━━━━━━━━\n🗺️ Explorar sitios:",
    inline_keyboard: [
      [btn("🐙 GitHub", "web:github"), btn("📺 YouTube", "web:youtube")],
      [btn("🔍 Google", "web:google"), btn("🤖 ChatGPT", "web:chatgpt")],
      [btn("📧 Gmail", "web:gmail"), btn("🦊 GitLab", "web:gitlab")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  },
  pending: {
    text: "⏳ MISIÓN EN PAUSA ⏳\n━━━━━━━━━━━━━━━━\n⚔️ Gestiona tus pendientes:",
    inline_keyboard: [
      [btn("📋 Ver pendientes", "pending:list")],
      [btn("✅ Aprobar última", "pending:approve_last")],
      [btn("❌ Rechazar última", "pending:reject_last")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  },
  audit: {
    text: "🔍 TORRE DE AUDITORÍA 🔍\n━━━━━━━━━━━━━━━━\n📊 Analizar el reino:",
    inline_keyboard: [
      [btn("🏰 Auditar Proyecto", "audit:project")],
      [btn("🛡️ Auditar Seguridad", "audit:safety")],
      [btn("🔄 Auditar Router", "audit:router")],
      [btn("✅ Auditar Approval", "audit:approval")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  },
  achievements: {
    text: "🏆 SALÓN DE LOGROS 🏆\n━━━━━━━━━━━━━━━━\n⭐ Tus conquistas:",
    inline_keyboard: [
      [btn("🎯 Ver Logros", "achievements:list")],
      [btn("📈 Progreso", "achievements:progress")],
      [btn("🏅 Ranking", "achievements:rank")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  },
  stats: {
    text: "📊 TORRE DE ESTADÍSTICAS 📊\n━━━━━━━━━━━━━━━━\n📈 Tu rendimiento:",
    inline_keyboard: [
      [btn("👤 Mi Perfil", "stats:profile")],
      [btn("📋 Resumen", "stats:summary")],
      [btn("🏆 Leaderboard", "stats:leaderboard")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  },
  help: {
    text: "❓ GUÍA DEL JUGADOR ❓\n━━━━━━━━━━━━━━━━\n📖 Comandos disponibles:",
    inline_keyboard: [
      [btn("🎮 Cómo Jugar", "help:howto")],
      [btn("⚔️ Comandos", "help:commands")],
      [btn("💡 Tips", "help:tips")],
      [btn("⬅️ Volver al Menú", "menu:main")]
    ]
  }
};

const WEB_COMMANDS = {
  "web:github": ["⏳ Abriendo GitHub...", "abrir web github.com"],
  "web:youtube": ["⏳ Abriendo YouTube...", "youtube"],
  "web:google": ["⏳ Abriendo Google...", "abrir web google.com"],
  "web:chatgpt": ["⏳ Abriendo ChatGPT...", "abrir web chat.openai.com"],
  "web:gmail": ["⏳ Abriendo Gmail...", "abrir web gmail.com"],
  "web:gitlab": ["⏳ Abriendo GitLab...", "abrir web gitlab.com"]
};

const AUDIT_COMMANDS = {
  "audit:project": ["⏳ Auditando proyecto...", "auditar proyecto"],
  "audit:approval": ["⏳ Auditando approval.main...", "auditar modulo approval.main"],
  "audit:router": ["⏳ Auditando router.main...", "auditar modulo router.main"],
  "audit:safety": ["⏳ Auditando safety.guard.main...", "auditar modulo safety.guard.main"]
};

const ACHIEVEMENT_COMMANDS = {
  "achievements:list": ["🏆 Consultando logros...", "mis logros"],
  "achievements:progress": ["📈 Consultando progreso...", "mi progreso"],
  "achievements:rank": ["🏅 Consultando ranking...", "ranking"]
};

const STATS_COMMANDS = {
  "stats:profile": ["👤 Cargando perfil...", "mi perfil"],
  "stats:summary": ["📋 Cargando resumen...", "mis estadísticas"],
  "stats:leaderboard": ["🏆 Cargando leaderboard...", "leaderboard"]
};

function emitMenu(payload, key, traceId = null) {
  const menu = MENUS[key] || MENUS.main;
  emit("ui.response.out", menuPayload(payload, menu.text, menu.inline_keyboard, traceId));
}

function emitAckAndCommand(payload, text, commandText, traceId = null) {
  const mergedMeta = mergeMeta(payload?._envelope_meta || {}, payload?.meta || {});
  const check = idempotency.isDuplicate(
    "menu_command",
    {
      command: commandText,
      chat_id: payload?.chat_id,
      callback_data: payload?.data
    },
    {
      chat_id: payload?.chat_id,
      user_id: mergedMeta?.user_id
    }
  );

  const finalTraceId = traceId || generateTraceId();

  if (check.isDuplicate) {
    console.error(`[${MODULE_ID}] Comando duplicado ignorado: ${commandText}`);
    emit(
      "ui.response.out",
      menuPayload(payload, `${text} (ya procesado)`, [[btn("Menú", "menu:main")]], finalTraceId)
    );
    return;
  }

  emit(
    "ui.response.out",
    menuPayload(payload, text, [[btn("Menú", "menu:main")]], finalTraceId)
  );
  emit("command.out", commandPayload(payload, commandText, finalTraceId));
}

function mapSceneToMenu(data) {
  if (data === "scene:main") return "main";
  if (data === "scene:web_active") return "web";
  if (data === "scene:awaiting_approval") return "pending";
  if (data === "scene:app_active") return "main";
  if (data === "scene:task_result") return "main";
  if (data === "scene:task_running") return "main";
  return null;
}

function isOwnedElsewhere(data) {
  return (
    data === "menu:apps" ||
    data === "menu:system" ||
    data === "menu:memory" ||
    (typeof data === "string" && data.startsWith("memory:"))
  );
}

function emitHelpText(payload, text, traceId = null) {
  emit(
    "ui.response.out",
    menuPayload(payload, text, [[btn("⬅️ Volver", "menu:main")]], traceId)
  );
}

function handleCallback(payload = {}, traceId = null) {
  if (!hasValidChatId(payload)) {
    return;
  }

  const data = typeof payload?.data === "string" ? payload.data : "";
  const finalTraceId = traceId || generateTraceId();

  if (!data) {
    emitMenu(payload, "main", finalTraceId);
    return;
  }

  const mappedScene = mapSceneToMenu(data);
  if (mappedScene) {
    emitMenu(payload, mappedScene, finalTraceId);
    return;
  }

  if (isOwnedElsewhere(data)) {
    return;
  }

  if (data === "menu:main") return emitMenu(payload, "main", finalTraceId);
  if (data === "menu:web") return emitMenu(payload, "web", finalTraceId);
  if (data === "menu:pending") return emitMenu(payload, "pending", finalTraceId);
  if (data === "menu:audit") return emitMenu(payload, "audit", finalTraceId);
  if (data === "menu:achievements") return emitMenu(payload, "achievements", finalTraceId);
  if (data === "menu:stats") return emitMenu(payload, "stats", finalTraceId);
  if (data === "menu:help") return emitMenu(payload, "help", finalTraceId);

  if (ACHIEVEMENT_COMMANDS[data]) {
    const [ack, cmd] = ACHIEVEMENT_COMMANDS[data];
    emitAckAndCommand(payload, ack, cmd, finalTraceId);
    return;
  }

  if (STATS_COMMANDS[data]) {
    const [ack, cmd] = STATS_COMMANDS[data];
    emitAckAndCommand(payload, ack, cmd, finalTraceId);
    return;
  }

  if (WEB_COMMANDS[data]) {
    const [ack, cmd] = WEB_COMMANDS[data];
    emitAckAndCommand(payload, ack, cmd, finalTraceId);
    return;
  }

  if (AUDIT_COMMANDS[data]) {
    const [ack, cmd] = AUDIT_COMMANDS[data];
    emitAckAndCommand(payload, ack, cmd, finalTraceId);
    return;
  }

  if (data === "help:howto") {
    emitHelpText(
      payload,
      "🎮 CÓMO JUGAR 🎮\n━━━━━━━━━━━━━━━━\n" +
        "1️⃣ Gana XP ejecutando comandos\n" +
        "2️⃣ Sube de nivel para desbloquear rangos\n" +
        "3️⃣ Completa logros para bonus XP\n" +
        "4️⃣ Mantén rachas de acciones exitosas\n\n" +
        "💡 Tip: Usa el menú principal para navegar",
      finalTraceId
    );
    return;
  }

  if (data === "help:commands") {
    emitHelpText(
      payload,
      "⚔️ COMANDOS ⚔️\n━━━━━━━━━━━━━━━━\n" +
        "📱 Apps: Abrir [app]\n" +
        "🌐 Web: Ir a [url]\n" +
        "⌨️ Terminal: Ejecutar [comando]\n" +
        "🔍 Buscar: Buscar [archivo]\n" +
        "🤖 IA: Pregúntale a la IA\n\n" +
        "💡 Más en el menú principal",
      finalTraceId
    );
    return;
  }

  if (data === "help:tips") {
    emitHelpText(
      payload,
      "💡 TIPS 💡\n━━━━━━━━━━━━━━━━\n" +
        "🔥 Cada acción exitosa da +XP\n" +
        "⭐ Los logros dan bonus grandes\n" +
        "🎯 Mantén rachas para multiplicadores\n" +
        "🏆 Llega al nivel 10 para ser Wizard\n\n" +
        "⚡ ¡Juega cada día para subir rápido!",
      finalTraceId
    );
    return;
  }

  if (data === "pending:list") {
    emit("approval.request.out", approvalRequestPayload(payload, "list_pending", finalTraceId));
    return;
  }

  if (data === "pending:approve_last") {
    emit("approval.callback.out", approvalCallbackPayload(payload, "approve_last", null, finalTraceId));
    return;
  }

  if (data === "pending:reject_last") {
    emit("approval.callback.out", approvalCallbackPayload(payload, "reject_last", null, finalTraceId));
    return;
  }

  if (data.startsWith("approval:approve:")) {
    emit(
      "approval.callback.out",
      approvalCallbackPayload(
        payload,
        "approve_plan",
        data.slice("approval:approve:".length),
        finalTraceId
      )
    );
    return;
  }

  if (data.startsWith("approval:reject:")) {
    emit(
      "approval.callback.out",
      approvalCallbackPayload(
        payload,
        "reject_plan",
        data.slice("approval:reject:".length),
        finalTraceId
      )
    );
    return;
  }

  emitMenu(payload, "main", finalTraceId);
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  if (msg.port !== "callback.in") return;

  const payload = msg.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  const callbackCheck = idempotency.isDuplicate(
    "menu_callback",
    {
      data: payload?.data,
      chat_id: payload?.chat_id
    },
    {
      chat_id: payload?.chat_id,
      user_id: mergedMeta?.user_id,
      callback_id: payload?.callback_id
    }
  );

  if (callbackCheck.isDuplicate) {
    console.error(`[${MODULE_ID}] Callback duplicado ignorado: ${payload?.data}`);
    return;
  }

  handleCallback(
    {
      ...payload,
      meta: mergedMeta,
      _envelope_meta: topMeta
    },
    traceId
  );
});