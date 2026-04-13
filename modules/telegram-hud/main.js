import fs from "fs";
import path from "path";
import readline from "readline";
import { fileURLToPath } from "url";

const MODULE_ID = "telegram.hud.main";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const STORE_PATH = path.resolve(__dirname, "../../logs/telegram-hud-state.json");
const GAME_DATA_PATH = path.resolve(__dirname, "../../logs/gamification.json");

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
  crlfDelay: Infinity
});

function safeIsoNow() {
  return new Date().toISOString();
}

function generateTraceId() {
  return `hud_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
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

function buildMeta(base = {}, extra = {}) {
  return {
    source: base?.source || "internal",
    chat_id: base?.chat_id ?? null,
    module: MODULE_ID,
    timestamp: safeIsoNow(),
    ...extra
  };
}

function btn(text, callbackData) {
  return { text, callback_data: callbackData };
}

function safeReadJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf8");
    if (!raw.trim()) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function loadStore() {
  const parsed = safeReadJson(STORE_PATH, {});
  return new Map(Object.entries(parsed));
}

const stateByChat = loadStore();
let gameDataCache = {
  mtimeMs: 0,
  data: {}
};

const lastRenderByChat = new Map();
const RENDER_DEBOUNCE_MS = 500;

function saveStore() {
  try {
    fs.mkdirSync(path.dirname(STORE_PATH), { recursive: true });
    const tempPath = `${STORE_PATH}.tmp`;
    fs.writeFileSync(
      tempPath,
      JSON.stringify(Object.fromEntries(stateByChat), null, 2),
      "utf8"
    );
    fs.renameSync(tempPath, STORE_PATH);
  } catch {
    // No emitimos UI ni eventos acá: HUD no debe contaminar el carril visual por errores internos.
  }
}

function getState(chatId) {
  return stateByChat.get(String(chatId)) || null;
}

function stateHash(state) {
  return JSON.stringify(state || {});
}

function saveState(state) {
  if (state?.chat_id === null || state?.chat_id === undefined) return;

  const key = String(state.chat_id);
  const prev = getState(state.chat_id) || {};
  const next = {
    ...prev,
    ...state,
    updated_at: safeIsoNow()
  };

  if (stateHash(prev) === stateHash(next)) {
    return;
  }

  stateByChat.set(key, next);
  saveStore();
}

function saveHudMeta(chatId, patch) {
  if (chatId === null || chatId === undefined) return;

  const prev = getState(chatId) || { chat_id: chatId };
  const next = {
    ...prev,
    ...patch,
    updated_at: safeIsoNow()
  };

  if (stateHash(prev) === stateHash(next)) {
    return;
  }

  stateByChat.set(String(chatId), next);
  saveStore();
}

function normalizeScene(state) {
  const raw = state?.scene || "main";
  const foreground = state?.foreground_context || null;

  if (foreground === "web" && state?.active_web?.url) {
    return "web_active";
  }

  if (
    foreground === "app" &&
    (state?.active_app?.id || state?.active_app?.label)
  ) {
    return "app_active";
  }

  if (raw === "awaiting_approval") return "awaiting_approval";
  if (raw === "task_running") return "task_running";
  if (raw === "task_result") return "task_result";

  return raw;
}

function preferredMode(state) {
  const messageId =
    state?.last_callback_message_id ||
    state?.callback_message_id ||
    null;

  return {
    mode: messageId ? "edit" : "send",
    message_id: messageId
  };
}

function hudHash(hud) {
  return JSON.stringify({
    text: hud?.text || "",
    inline_keyboard: hud?.inline_keyboard || []
  });
}

function backgroundText(state) {
  if (state?.background_context === "web" && state?.background_web?.title) {
    return `Segundo plano: ${state.background_web.title}`;
  }

  if (state?.background_context === "app" && state?.background_app?.label) {
    return `Segundo plano: ${state.background_app.label}`;
  }

  return null;
}

function getCachedGameData() {
  try {
    if (!fs.existsSync(GAME_DATA_PATH)) {
      gameDataCache = { mtimeMs: 0, data: {} };
      return gameDataCache.data;
    }

    const stat = fs.statSync(GAME_DATA_PATH);
    if (stat.mtimeMs === gameDataCache.mtimeMs) {
      return gameDataCache.data;
    }

    const parsed = safeReadJson(GAME_DATA_PATH, {});
    gameDataCache = {
      mtimeMs: stat.mtimeMs,
      data: parsed
    };
    return gameDataCache.data;
  } catch {
    return {};
  }
}

function loadGameData(chatId) {
  const allData = getCachedGameData();
  return allData[String(chatId)] || null;
}

function formatProgressBar(progress, length = 10) {
  const safeProgress = Math.max(0, Math.min(100, Number(progress) || 0));
  const filled = Math.floor((safeProgress / 100) * length);
  const empty = Math.max(0, length - filled);
  return "█".repeat(filled) + "░".repeat(empty);
}

function getRankIcon(level) {
  if (level >= 20) return "🏆";
  if (level >= 15) return "👑";
  if (level >= 10) return "⭐";
  if (level >= 7) return "🥇";
  if (level >= 5) return "🥈";
  if (level >= 3) return "🥉";
  return "🎮";
}

function getSceneEmoji(scene) {
  const emojis = {
    awaiting_approval: "⏸️",
    task_running: "⚔️",
    web_active: "🌐",
    app_active: "🎮",
    task_result: "✨",
    main: "🏰"
  };
  return emojis[scene] || "🎯";
}

function buildGameHeader(gameData) {
  if (!gameData) {
    return "🎮 JARVIS RPG v1.0\n";
  }

  const level = Math.max(1, Number(gameData.level) || 1);
  const xp = Math.max(0, Number(gameData.total_xp) || 0);
  const rank = getRankIcon(level);

  const nextLevelXp = (level ** 2) * 100;
  const currentLevelBase = ((level - 1) ** 2) * 100;
  const xpInLevel = Math.max(0, xp - currentLevelBase);
  const xpNeeded = Math.max(1, nextLevelXp - currentLevelBase);
  const progress = Math.min((xpInLevel / xpNeeded) * 100, 100);

  const stats = gameData.stats || {};
  const success = Math.max(0, Number(stats.successful_actions) || 0);
  const failed = Math.max(0, Number(stats.failed_actions) || 0);
  const total = success + failed;
  const health = total > 0 ? Math.round((success / total) * 100) : 100;

  const achievements = Array.isArray(gameData.achievements)
    ? gameData.achievements
    : [];
  const achievementStars = "⭐".repeat(Math.min(achievements.length, 5));

  return (
    "╔══════════════════════════════════════╗\n" +
    "║  🎮 JARVIS RPG v1.0               ║\n" +
    "╠══════════════════════════════════════╣\n" +
    `║ ${rank} Nivel ${level} ${achievementStars.padEnd(5)}     ║\n` +
    `║ XP: [${formatProgressBar(progress)}] ${Math.round(progress)}%      ║\n` +
    `║ HP: [${formatProgressBar(health)}] ${health}%      ║\n` +
    "╚══════════════════════════════════════╝\n"
  );
}

function buildHud(state) {
  const chatId = state?.chat_id;
  if (chatId === null || chatId === undefined) return null;

  const scene = normalizeScene(state);
  const { mode, message_id } = preferredMode(state);
  const foreground = state?.foreground_context || null;
  const bgText = backgroundText(state);
  const gameData = loadGameData(chatId);
  const gameHeader = buildGameHeader(gameData);
  const sceneEmoji = getSceneEmoji(scene);

  const rpgButtons = {
    main: [
      [btn("⚔️ Apps", "menu:apps"), btn("🌐 Web", "menu:web")],
      [btn("⚙️ Sistema", "menu:system"), btn("💭 Memoria", "menu:memory")],
      [btn("🏆 Logros", "menu:achievements"), btn("📊 Stats", "menu:stats")],
      [btn("⏳ Pendientes", "menu:pending")]
    ],
    awaiting_approval: [
      [btn("✅ Aprobar", "approval:approve"), btn("❌ Rechazar", "approval:reject")],
      [btn("⏳ Ver pendientes", "menu:pending")],
      [btn("🏰 Menú principal", "menu:main")]
    ],
    task_running: [
      [btn("🛑 Cancelar", "task:cancel")],
      [btn("⚙️ Sistema", "menu:system"), btn("💭 Memoria", "menu:memory")],
      [btn("🏰 Menú principal", "menu:main")]
    ],
    app_active: [
      [btn("📱 Apps", "menu:apps"), btn("🌐 Web", "menu:web")],
      [btn("⚙️ Sistema", "menu:system"), btn("💭 Memoria", "menu:memory")],
      [btn("🏰 Menú principal", "menu:main")]
    ],
    web_active: [
      [btn("🌐 Web", "menu:web"), btn("📱 Apps", "menu:apps")],
      [btn("⚙️ Sistema", "menu:system"), btn("💭 Memoria", "menu:memory")],
      [btn("🏰 Menú principal", "menu:main")]
    ],
    task_result: [
      [btn("🔁 Repetir", "task:repeat"), btn("📝 Detalles", "task:details")],
      [btn("📱 Apps", "menu:apps"), btn("🌐 Web", "menu:web")],
      [btn("🏰 Menú principal", "menu:main")]
    ]
  };

  const buttons = rpgButtons[scene] || rpgButtons.main;

  let sceneText = "";

  if (scene === "awaiting_approval") {
    sceneText =
      `${sceneEmoji} BATALLA EN PAUSA ${sceneEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      "⏸️ Esperando tu decisión...\n" +
      `🎯 Plan: ${state?.pending_plan_id || "???"}\n` +
      "💡 Tip: Revisa antes de aprobar";
  } else if (scene === "task_running") {
    const taskName = state?.running_task_id || "???";
    sceneText =
      `${sceneEmoji} EN COMBATE ${sceneEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      `🗡️ Misión: ${taskName}\n` +
      `🎯 Foco: ${foreground || "Ninguno"}\n` +
      "⚡ Estado: Ejecutando..." +
      (bgText ? `\n${bgText}` : "");
  } else if (scene === "web_active") {
    const webTitle = state?.active_web?.title || "Web";
    sceneText =
      `${sceneEmoji} EXPLORANDO ${sceneEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      `🗺️ Zona: ${webTitle}\n` +
      "🎯 Foco: Web\n" +
      "⚡ Estado: Navegando" +
      (bgText ? `\n${bgText}` : "");
  } else if (scene === "app_active") {
    const appLabel = state?.active_app?.label || "App";
    sceneText =
      `${sceneEmoji} APP ACTIVA ${sceneEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      `🎯 Aplicación: ${appLabel}\n` +
      "⚡ Estado: En uso" +
      (bgText ? `\n${bgText}` : "");
  } else if (scene === "task_result") {
    const resultType = state?.last_result_type || "???";
    const resultEmoji =
      resultType === "success" ? "✨" :
      resultType === "error" ? "💥" :
      "🎲";

    sceneText =
      `${resultEmoji} RESULTADO ${resultEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      `🎯 Tipo: ${resultType}\n` +
      "💰 Recompensa: +10 XP";
  } else {
    const stats = gameData?.stats || {};
    const commands = stats.commands_executed || 0;
    const apps = stats.apps_opened || 0;
    const urls = stats.urls_visited || 0;

    sceneText =
      `${sceneEmoji} BASE PRINCIPAL ${sceneEmoji}\n` +
      "━━━━━━━━━━━━━━━━━━━━\n" +
      "📊 Estadísticas de Hoy:\n" +
      `   ⌨️ Comandos: ${commands}\n` +
      `   📱 Apps: ${apps}\n` +
      `   🌐 URLs: ${urls}\n` +
      "⚡ Listo para la aventura!";
  }

  return {
    chat_id: chatId,
    mode,
    message_id,
    text: gameHeader + sceneText,
    inline_keyboard: buttons
  };
}

function handleUiState(payload, meta = {}) {
  const incomingState =
    payload?.state && typeof payload.state === "object"
      ? payload.state
      : (payload && typeof payload === "object" ? payload : null);

  if (!incomingState?.chat_id) return;

  saveState({
    ...incomingState,
    _meta: mergeMeta(meta, incomingState?._meta || {})
  });
}

function handleRenderRequest(payload, meta = {}, traceId = null) {
  const incomingState =
    payload?.state && typeof payload.state === "object" ? payload.state : null;
  const reason = payload?.reason || "render";

  const chatId =
    incomingState?.chat_id ||
    payload?.chat_id ||
    null;

  if (!chatId) return;

  const nowTs = Date.now();
  const lastRender = lastRenderByChat.get(chatId) || 0;
  if (nowTs - lastRender < RENDER_DEBOUNCE_MS) {
    return;
  }
  lastRenderByChat.set(chatId, nowTs);

  if (incomingState) {
    saveState({
      ...incomingState,
      _meta: mergeMeta(meta, incomingState?._meta || {})
    });
  }

  const latest = getState(chatId);
  if (!latest) return;

  const normalized = normalizeScene(latest);
  const effectiveState = {
    ...latest,
    scene: normalized
  };

  const hud = buildHud(effectiveState);
  if (!hud) return;

  const hash = hudHash(hud);
  if (
    latest?.last_hud_hash === hash &&
    latest?.last_hud_scene === normalized
  ) {
    return;
  }

  emit("ui.response.out", {
    ...hud,
    trace_id: traceId || generateTraceId(),
    meta: buildMeta(
      {
        source: meta?.source || "internal",
        chat_id: chatId
      },
      {
        reason
      }
    )
  });

  saveHudMeta(chatId, {
    scene: normalized,
    last_hud_hash: hash,
    last_hud_scene: normalized,
    last_hud_reason: reason
  });
}

rl.on("line", (line) => {
  if (!line.trim()) return;

  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const port = msg?.port;
  const payload = msg?.payload || {};
  const topMeta = msg?.meta || {};
  const payloadMeta =
    typeof payload?.meta === "object" && payload?.meta !== null ? payload.meta : {};
  const mergedMeta = mergeMeta(topMeta, payloadMeta);
  const traceId = msg?.trace_id || payload?.trace_id || generateTraceId();

  if (port === "ui.state.in") {
    handleUiState(payload, mergedMeta);
    return;
  }

  if (port === "render.request.in") {
    handleRenderRequest(payload, mergedMeta, traceId);
  }
});