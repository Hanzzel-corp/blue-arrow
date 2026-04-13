import json
import sys
import os
import time
import random
from datetime import datetime
from typing import Dict, List, Optional, Any

MODULE_ID = "gamification.main"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def generate_trace_id() -> str:
    return f"game_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = CURRENT_DIR
MODULES_DIR = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from logger import StructuredLogger  # type: ignore[reportMissingImports]
except ModuleNotFoundError:
    class StructuredLogger:
        def __init__(self, name):
            self.name = name

        def info(self, msg):
            print(f"INFO: {msg}", file=sys.stderr)

        def error(self, msg):
            print(f"ERROR: {msg}", file=sys.stderr)


logger = StructuredLogger(MODULE_ID)


def build_top_meta(meta: Optional[Dict] = None) -> Dict:
    base = {
        "source": "internal",
        "timestamp": safe_iso_now(),
        "module": MODULE_ID
    }
    if isinstance(meta, dict):
        base.update(meta)
    return base


def emit(port: str, payload: Optional[Dict] = None):
    payload = payload or {}
    trace_id = payload.get("trace_id") or generate_trace_id()
    meta = build_top_meta(payload.get("meta"))

    clean_payload = {
        k: v for k, v in payload.items()
        if k not in ("trace_id", "meta")
    }

    msg = {
        "module": MODULE_ID,
        "port": port,
        "trace_id": trace_id,
        "meta": meta,
        "payload": clean_payload
    }
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def emit_result(
    task_id: str,
    status: str,
    result: Dict,
    meta: Optional[Dict] = None,
    trace_id: Optional[str] = None
):
    emit("result.out", {
        "task_id": task_id,
        "status": status,
        "result": result,
        "meta": meta or {},
        "trace_id": trace_id or generate_trace_id()
    })


def emit_guaranteed_result(
    task_id: str,
    status: str,
    result: Dict,
    meta: Optional[Dict] = None,
    trace_id: Optional[str] = None
):
    try:
        emit_result(task_id, status, result, meta or {}, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Error emitiendo result.out: {e}")
        fallback = {
            "module": MODULE_ID,
            "port": "result.out",
            "trace_id": trace_id or generate_trace_id(),
            "meta": build_top_meta(meta),
            "payload": {
                "task_id": task_id,
                "status": "error",
                "result": {
                    "success": False,
                    "error": "emit_result_failed",
                    "detail": str(e),
                    "original_status": status
                }
            }
        }
        print(json.dumps(fallback, ensure_ascii=False), flush=True)


class GamificationSystem:
    """Sistema de gamificación para experiencia tipo videojuego."""

    def __init__(self, data_path: str = "logs/gamification.json"):
        self.data_path = os.path.join(PROJECT_ROOT, data_path)
        self.users: Dict = {}
        self.achievements_db = self._load_achievements_db()
        self.load_data()

    def _load_achievements_db(self) -> Dict:
        return {
            "first_command": {
                "id": "first_command",
                "name": "🎮 Primer Pasos",
                "description": "Ejecuta tu primer comando",
                "emoji": "🎯",
                "xp": 50,
                "rarity": "common"
            },
            "terminal_master": {
                "id": "terminal_master",
                "name": "⌨️ Maestro Terminal",
                "description": "Ejecuta 10 comandos en terminal",
                "emoji": "💻",
                "xp": 150,
                "rarity": "rare"
            },
            "app_opener": {
                "id": "app_opener",
                "name": "📱 Abreapp",
                "description": "Abre 5 aplicaciones diferentes",
                "emoji": "🚀",
                "xp": 100,
                "rarity": "common"
            },
            "browser_surfer": {
                "id": "browser_surfer",
                "name": "🌐 Surfer Web",
                "description": "Navega a 5 URLs diferentes",
                "emoji": "🏄",
                "xp": 120,
                "rarity": "common"
            },
            "file_hunter": {
                "id": "file_hunter",
                "name": "🔍 Cazador de Archivos",
                "description": "Busca archivos 3 veces",
                "emoji": "📂",
                "xp": 80,
                "rarity": "common"
            },
            "ai_explorer": {
                "id": "ai_explorer",
                "name": "🤖 Explorador IA",
                "description": "Usa el asistente de IA 5 veces",
                "emoji": "🧠",
                "xp": 200,
                "rarity": "rare"
            },
            "power_user": {
                "id": "power_user",
                "name": "⚡ Usuario Power",
                "description": "Completa 50 acciones exitosas",
                "emoji": "🔥",
                "xp": 500,
                "rarity": "epic"
            },
            "wizard": {
                "id": "wizard",
                "name": "🧙‍♂️ Mago del Sistema",
                "description": "Alcanza el nivel 10",
                "emoji": "⭐",
                "xp": 1000,
                "rarity": "legendary"
            },
            "auditor": {
                "id": "auditor",
                "name": "🔍 Auditor",
                "description": "Ejecuta una auditoría del proyecto",
                "emoji": "📊",
                "xp": 150,
                "rarity": "rare"
            },
            "memory_master": {
                "id": "memory_master",
                "name": "🧠 Maestro de la Memoria",
                "description": "Usa la memoria semántica 10 veces",
                "emoji": "💭",
                "xp": 200,
                "rarity": "rare"
            }
        }

    def load_data(self):
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
            except Exception as e:
                logger.error(f"Error cargando gamification.json: {e}")
                self.users = {}

    def save_data(self):
        try:
            os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando gamification.json: {e}")

    def get_or_create_user(self, user_id: str, username: Optional[str] = None) -> Dict:
        if user_id not in self.users:
            safe_suffix = user_id[-4:] if user_id else "0000"
            self.users[user_id] = {
                "user_id": user_id,
                "username": username or f"Player_{safe_suffix}",
                "level": 1,
                "total_xp": 0,
                "achievements": [],
                "stats": {
                    "commands_executed": 0,
                    "apps_opened": 0,
                    "urls_visited": 0,
                    "files_searched": 0,
                    "ai_queries": 0,
                    "successful_actions": 0,
                    "failed_actions": 0,
                    "login_streak": 0,
                    "last_login": None,
                    "audits_run": 0,
                    "memory_uses": 0
                },
                "created_at": safe_iso_now(),
                "last_action": None
            }
            self.save_data()
        return self.users[user_id]

    def calculate_level(self, total_xp: int) -> int:
        import math
        if total_xp < 100:
            return 1
        return int(math.sqrt(total_xp / 100)) + 1

    def get_level_floor_xp(self, level: int) -> int:
        if level <= 1:
            return 0
        return ((level - 1) ** 2) * 100

    def get_xp_for_next_level(self, level: int) -> int:
        return (level ** 2) * 100

    def add_xp(self, user_id: str, amount: int, reason: Optional[str] = None) -> Dict:
        user = self.get_or_create_user(user_id)
        old_level = user["level"]

        amount = int(amount)
        user["total_xp"] += amount
        new_level = self.calculate_level(user["total_xp"])

        leveled_up = False
        if new_level > old_level:
            user["level"] = new_level
            leveled_up = True

        user["last_action"] = {
            "type": "xp_gain",
            "amount": amount,
            "reason": reason,
            "timestamp": safe_iso_now()
        }

        self.save_data()

        return {
            "success": True,
            "xp_gained": amount,
            "total_xp": user["total_xp"],
            "old_level": old_level,
            "new_level": user["level"],
            "leveled_up": leveled_up,
            "next_level_xp": self.get_xp_for_next_level(user["level"])
        }

    def track_action(self, user_id: str, action_type: str, success: bool = True) -> Dict:
        user = self.get_or_create_user(user_id)

        if action_type == "command":
            user["stats"]["commands_executed"] += 1
        elif action_type == "open_app":
            user["stats"]["apps_opened"] += 1
        elif action_type == "browser_navigate":
            user["stats"]["urls_visited"] += 1
        elif action_type == "search_file":
            user["stats"]["files_searched"] += 1
        elif action_type == "ai_query":
            user["stats"]["ai_queries"] += 1
        elif action_type == "audit":
            user["stats"]["audits_run"] += 1
        elif action_type == "memory_use":
            user["stats"]["memory_uses"] += 1

        if success:
            user["stats"]["successful_actions"] += 1
        else:
            user["stats"]["failed_actions"] += 1

        xp_amount = 10
        if success:
            xp_amount += 5

        last_action = user.get("last_action") or {}
        if last_action.get("type") == "action" and last_action.get("success"):
            streak = last_action.get("streak", 0) + 1
            if streak > 3:
                xp_amount += min(streak * 2, 20)
        else:
            streak = 1

        user["last_action"] = {
            "type": "action",
            "action_type": action_type,
            "success": success,
            "streak": streak,
            "timestamp": safe_iso_now()
        }

        self.save_data()

        xp_result = self.add_xp(user_id, xp_amount, f"Acción: {action_type}")
        new_achievements = self._check_achievements(user_id)

        return {
            "success": True,
            "xp_result": xp_result,
            "new_achievements": new_achievements,
            "streak": streak
        }

    def _check_achievements(self, user_id: str) -> List[Dict]:
        user = self.get_or_create_user(user_id)
        new_achievements = []

        unlocked = set(user["achievements"])
        stats = user["stats"]

        checks = [
            ("first_command", stats["commands_executed"] >= 1),
            ("terminal_master", stats["commands_executed"] >= 10),
            ("app_opener", stats["apps_opened"] >= 5),
            ("browser_surfer", stats["urls_visited"] >= 5),
            ("file_hunter", stats["files_searched"] >= 3),
            ("ai_explorer", stats["ai_queries"] >= 5),
            ("power_user", stats["successful_actions"] >= 50),
            ("wizard", user["level"] >= 10),
            ("auditor", stats.get("audits_run", 0) >= 1),
            ("memory_master", stats.get("memory_uses", 0) >= 10)
        ]

        for achievement_id, condition in checks:
            if condition and achievement_id not in unlocked:
                achievement_data = self.achievements_db.get(achievement_id)
                if achievement_data:
                    user["achievements"].append(achievement_id)
                    new_achievements.append(achievement_data)
                    self.add_xp(
                        user_id,
                        achievement_data["xp"],
                        f"Logro: {achievement_data['name']}"
                    )

        if new_achievements:
            self.save_data()

        return new_achievements

    def get_user_profile(self, user_id: str) -> Dict:
        user = self.get_or_create_user(user_id)

        current_level = user["level"]
        current_floor = self.get_level_floor_xp(current_level)
        next_level_xp = self.get_xp_for_next_level(current_level)
        xp_in_current_level = user["total_xp"] - current_floor
        xp_needed = next_level_xp - current_floor
        progress = (xp_in_current_level / xp_needed * 100) if xp_needed > 0 else 100

        achievements_details = []
        for ach_id in user["achievements"]:
            if ach_id in self.achievements_db:
                achievements_details.append(self.achievements_db[ach_id])

        return {
            "user_id": user_id,
            "username": user["username"],
            "level": user["level"],
            "total_xp": user["total_xp"],
            "xp_to_next_level": max(next_level_xp - user["total_xp"], 0),
            "next_level_progress": min(max(progress, 0), 100),
            "achievements": achievements_details,
            "achievements_count": len(user["achievements"]),
            "stats": user["stats"],
            "rank": self._calculate_rank(user["level"])
        }

    def _calculate_rank(self, level: int) -> str:
        ranks = [
            (1, "Novato"),
            (3, "Aprendiz"),
            (5, "Usuario"),
            (7, "Avanzado"),
            (10, "Experto"),
            (15, "Maestro"),
            (20, "Legendario")
        ]

        current_rank = "Novato"
        for min_level, rank in ranks:
            if level >= min_level:
                current_rank = rank

        return current_rank

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        users_list = []
        for user_id, user_data in self.users.items():
            users_list.append({
                "user_id": user_id,
                "username": user_data["username"],
                "level": user_data["level"],
                "total_xp": user_data["total_xp"],
                "achievements_count": len(user_data["achievements"]),
                "rank": self._calculate_rank(user_data["level"])
            })

        users_list.sort(key=lambda x: (x["level"], x["total_xp"]), reverse=True)
        return users_list[:limit]

    def format_progress_bar(self, progress: float, length: int = 20) -> str:
        filled = int((progress / 100) * length)
        empty = length - filled
        return "█" * filled + "░" * empty


gamification = GamificationSystem()


def derive_game_track_from_runtime_payload(
    payload: Dict,
    meta: Optional[Dict] = None
) -> Optional[Dict]:
    """
    Convierte un result.out/runtime payload en un game.track implícito.
    """
    if not isinstance(payload, dict):
        return None

    meta = meta or {}
    payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    merged_meta = {**meta, **payload_meta}

    result = payload.get("result", {}) or {}

    action = (
        payload.get("action")
        or merged_meta.get("action")
        or ""
    )

    status = payload.get("status")
    success = status == "success"

    if not action and not result:
        return None

    if action == "open_application":
        action_type = "open_app"
    elif action in {"open_url", "search_google", "fill_form", "click_web"}:
        action_type = "browser_navigate"
    elif action == "search_file":
        action_type = "search_file"
    elif isinstance(action, str) and action.startswith("ai."):
        action_type = "ai_query"
    elif isinstance(action, str) and action.startswith("audit"):
        action_type = "audit"
    elif isinstance(action, str) and action.startswith("memory"):
        action_type = "memory_use"
    else:
        action_type = "command"

    user_id = str(merged_meta.get("chat_id", "default"))

    return {
        "user_id": user_id,
        "action_type": action_type,
        "success": success,
        "context": {
            "action": action,
            "worker": merged_meta.get("worker"),
            "source": merged_meta.get("source"),
            "ui_origin": merged_meta.get("ui_origin")
        }
    }


def extract_task_id(payload: Dict, meta: Dict) -> str:
    return (
        payload.get("task_id")
        or payload.get("plan_id")
        or meta.get("task_id")
        or meta.get("plan_id")
        or f"game_{int(datetime.now().timestamp())}"
    )


def main():
    logger.info(f"Gamification Module iniciado - {MODULE_ID}")

    emit("event.out", {
        "level": "info",
        "type": "gamification_ready",
        "users_count": len(gamification.users),
        "trace_id": generate_trace_id()
    })

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            port = msg.get("port")
            payload = msg.get("payload", {}) or {}
            top_meta = msg.get("meta", {}) or {}
            payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
            meta = {**top_meta, **payload_meta}
            trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

            task_id = extract_task_id(payload, meta)
            action = payload.get("action", "")
            params = payload.get("params", {}) or {}

            if port == "action.in":
                if not isinstance(action, str) or not action.startswith("game."):
                    derived = derive_game_track_from_runtime_payload(payload, meta)

                    if derived:
                        result = gamification.track_action(
                            derived["user_id"],
                            derived["action_type"],
                            derived["success"]
                        )

                        emit("event.out", {
                            "task_id": task_id,
                            "type": "gamification.tracked",
                            "tracked_implicitly": True,
                            "action_type": derived["action_type"],
                            "xp_result": result.get("xp_result"),
                            "new_achievements": result.get("new_achievements", []),
                            "streak": result.get("streak", 1),
                            "meta": {
                                **meta,
                                "context": derived.get("context", {})
                            },
                            "trace_id": trace_id
                        })
                        continue

                    continue

                logger.info(f"Acción: {action}")
                user_id = str(params.get("user_id", meta.get("chat_id", "default")))

                if action == "game.track":
                    result = gamification.track_action(
                        user_id,
                        params.get("action_type", "unknown"),
                        params.get("success", True)
                    )
                    emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

                    if result["xp_result"].get("leveled_up"):
                        emit("event.out", {
                            "level": "info",
                            "type": "gamification_level_up",
                            "user_id": user_id,
                            "new_level": result["xp_result"]["new_level"],
                            "old_level": result["xp_result"]["old_level"],
                            "trace_id": trace_id,
                            "meta": meta
                        })

                    for achievement in result.get("new_achievements", []):
                        emit("event.out", {
                            "level": "info",
                            "type": "gamification_achievement_unlocked",
                            "user_id": user_id,
                            "achievement": achievement,
                            "trace_id": trace_id,
                            "meta": meta
                        })

                elif action == "game.profile":
                    profile = gamification.get_user_profile(user_id)
                    emit_guaranteed_result(task_id, "success", profile, meta, trace_id=trace_id)

                elif action == "game.xp":
                    result = gamification.add_xp(
                        user_id,
                        int(params.get("amount", 0)),
                        params.get("reason")
                    )
                    emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

                    if result.get("leveled_up"):
                        emit("event.out", {
                            "level": "info",
                            "type": "gamification_level_up",
                            "user_id": user_id,
                            "new_level": result["new_level"],
                            "old_level": result["old_level"],
                            "trace_id": trace_id,
                            "meta": meta
                        })

                elif action == "game.leaderboard":
                    leaderboard = gamification.get_leaderboard(int(params.get("limit", 10)))
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"leaderboard": leaderboard},
                        meta,
                        trace_id=trace_id
                    )

                elif action == "game.achievements":
                    available = list(gamification.achievements_db.values())
                    unlocked = gamification.get_or_create_user(user_id)["achievements"]
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {
                            "available": available,
                            "unlocked": unlocked,
                            "progress": f"{len(unlocked)}/{len(available)}"
                        },
                        meta,
                        trace_id=trace_id
                    )

                elif action == "game.stats":
                    total_users = len(gamification.users)
                    total_achievements = sum(
                        len(u["achievements"]) for u in gamification.users.values()
                    )
                    avg_level = (
                        sum(u["level"] for u in gamification.users.values()) / total_users
                        if total_users else 0
                    )

                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {
                            "total_users": total_users,
                            "total_achievements_unlocked": total_achievements,
                            "average_level": round(avg_level, 2),
                            "achievements_available": len(gamification.achievements_db)
                        },
                        meta,
                        trace_id=trace_id
                    )

                elif action == "game.update_username":
                    user = gamification.get_or_create_user(user_id)
                    user["username"] = params.get("username", user["username"])
                    gamification.save_data()
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"updated": True},
                        meta,
                        trace_id=trace_id
                    )

                else:
                    emit_guaranteed_result(
                        task_id,
                        "error",
                        {
                            "success": False,
                            "error": f"Acción desconocida: {action}"
                        },
                        meta,
                        trace_id=trace_id
                    )

            elif port == "query.in":
                query_type = payload.get("query_type", "")
                user_id = str(payload.get("user_id", meta.get("chat_id", "default")))

                if query_type == "gamification_status":
                    profile = gamification.get_user_profile(user_id)
                    emit_guaranteed_result(task_id, "success", profile, meta, trace_id=trace_id)
                else:
                    emit_guaranteed_result(
                        task_id,
                        "error",
                        {
                            "success": False,
                            "error": f"query_type desconocido: {query_type or 'empty'}"
                        },
                        meta,
                        trace_id=trace_id
                    )

        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido: {e}")
            emit("event.out", {
                "level": "error",
                "type": "gamification_invalid_json",
                "error": str(e),
                "trace_id": generate_trace_id()
            })
        except Exception as e:
            logger.error(f"Error: {e}")
            emit("event.out", {
                "level": "error",
                "type": "gamification_exception",
                "error": str(e),
                "trace_id": generate_trace_id()
            })


if __name__ == "__main__":
    main()