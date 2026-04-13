"""
AI Learning Engine - Motor de aprendizaje continuo
Sistema que aprende de las interacciones y mejora sus respuestas y acciones.
"""

import json
import sys
import os
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter

MODULE_ID = "ai.learning.engine.main"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def generate_trace_id() -> str:
    return f"aile_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


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


def emit_result(task_id: str, status: str, result: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    emit("result.out", {
        "task_id": task_id,
        "status": status,
        "result": result,
        "meta": meta or {},
        "trace_id": trace_id or generate_trace_id()
    })


def emit_guaranteed_result(task_id: str, status: str, result: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    try:
        emit_result(task_id, status, result, meta, trace_id=trace_id)
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


class LearningEngine:
    """Motor de aprendizaje que mejora con cada interacción."""

    def __init__(self, learning_path: str = "logs/ai-learning.json"):
        self.learning_path = os.path.join(PROJECT_ROOT, learning_path)

        self.user_preferences: Dict = {}
        self.command_patterns: List[Dict] = []
        self.success_rates: Dict[str, Dict] = defaultdict(
            lambda: {"attempts": 0, "successes": 0}
        )
        self.time_patterns: Dict[str, List[int]] = defaultdict(list)
        self.corrections: List[Dict] = []
        self.learned_shortcuts: Dict[str, str] = {}

        self.load_learning()

    def load_learning(self):
        """Carga datos de aprendizaje previos."""
        if os.path.exists(self.learning_path):
            try:
                with open(self.learning_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.user_preferences = data.get("preferences", {})
                    self.command_patterns = data.get("patterns", [])

                    self.success_rates = defaultdict(
                        lambda: {"attempts": 0, "successes": 0}
                    )
                    self.success_rates.update(data.get("success_rates", {}))

                    self.corrections = data.get("corrections", [])
                    self.learned_shortcuts = data.get("shortcuts", {})

                    stored_time_patterns = data.get("time_patterns", {})
                    if isinstance(stored_time_patterns, dict):
                        self.time_patterns = defaultdict(list)
                        for k, v in stored_time_patterns.items():
                            self.time_patterns[k] = v if isinstance(v, list) else []

                logger.info(f"Aprendizaje cargado: {len(self.command_patterns)} patrones")
            except Exception as e:
                logger.error(f"Error cargando aprendizaje: {e}")

    def save_learning(self):
        """Guarda datos de aprendizaje."""
        try:
            os.makedirs(os.path.dirname(self.learning_path), exist_ok=True)
            with open(self.learning_path, "w", encoding="utf-8") as f:
                json.dump({
                    "preferences": self.user_preferences,
                    "patterns": self.command_patterns[-500:],
                    "success_rates": dict(self.success_rates),
                    "time_patterns": dict(self.time_patterns),
                    "corrections": self.corrections[-100:],
                    "shortcuts": self.learned_shortcuts,
                    "updated_at": safe_iso_now()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando aprendizaje: {e}")

    def learn_interaction(
        self,
        command: str,
        action: str,
        result: Dict,
        context: Optional[Dict] = None
    ):
        """Aprende de una interacción."""
        pattern = {
            "command": command,
            "action": action,
            "success": result.get("success", False),
            "timestamp": safe_iso_now(),
            "hour": datetime.now().hour,
            "context": context or {}
        }

        self.command_patterns.append(pattern)

        if action:
            self.success_rates[action]["attempts"] += 1
            if result.get("success", False):
                self.success_rates[action]["successes"] += 1

            self.time_patterns[action].append(datetime.now().hour)

        self._detect_shortcuts()
        self.save_learning()

    def _detect_shortcuts(self):
        """Detecta comandos frecuentes para crear atajos."""
        recent = [
            p for p in self.command_patterns
            if datetime.now() - datetime.fromisoformat(p["timestamp"]) < timedelta(days=30)
        ]

        command_counts = Counter(
            p["command"] for p in recent
            if p.get("command")
        )

        for command, count in command_counts.most_common(10):
            if count >= 5 and command not in self.learned_shortcuts:
                words = command.lower().split()
                shortcut = "".join(w[0] for w in words if w)[:3]
                if shortcut and shortcut not in self.learned_shortcuts.values():
                    self.learned_shortcuts[command] = shortcut
                    logger.info(f"Atajo aprendido: '{shortcut}' -> '{command}'")

    def learn_correction(
        self,
        original_command: str,
        corrected_command: str,
        reason: Optional[str] = None
    ):
        """Aprende de una corrección del usuario."""
        correction = {
            "original": original_command,
            "corrected": corrected_command,
            "reason": reason,
            "timestamp": safe_iso_now(),
            "learned": True
        }

        self.corrections.append(correction)

        if "abrir" in corrected_command.lower() and "abrir" not in original_command.lower():
            self.user_preferences["prefers_open_verb"] = True

        self.save_learning()

    def learn_preference(self, key: str, value: Any, confidence: float = 1.0):
        """Aprende una preferencia del usuario."""
        if not key:
            raise ValueError("Preference key vacía")

        if key not in self.user_preferences:
            self.user_preferences[key] = {
                "value": value,
                "confidence": confidence,
                "first_seen": safe_iso_now(),
                "updated_at": safe_iso_now()
            }
        else:
            pref = self.user_preferences[key]
            old_value = pref["value"]

            if old_value != value:
                pref["previous_values"] = pref.get("previous_values", [])
                pref["previous_values"].append({
                    "value": old_value,
                    "changed_at": pref["updated_at"]
                })

            pref["value"] = value
            pref["confidence"] = min(pref.get("confidence", 0.0) + confidence * 0.1, 1.0)
            pref["updated_at"] = safe_iso_now()

        self.save_learning()

    def predict_best_action(self, command: str, context: Optional[Dict] = None) -> Dict:
        """Predice la mejor acción basada en aprendizaje previo."""
        similar = self._find_similar_patterns(command)

        if not similar:
            return {
                "success": False,
                "message": "No hay datos suficientes para predecir",
                "confidence": 0
            }

        action_scores = defaultdict(lambda: {"success": 0, "total": 0})

        for pattern in similar:
            action = pattern["action"]
            if not action:
                continue
            action_scores[action]["total"] += 1
            if pattern["success"]:
                action_scores[action]["success"] += 1

        best_action = None
        best_score = 0.0

        for action, scores in action_scores.items():
            if scores["total"] > 0:
                success_rate = scores["success"] / scores["total"]
                confidence = min(scores["total"] / 5, 1.0)
                score = success_rate * confidence

                if score > best_score:
                    best_score = score
                    best_action = action

        if best_action and best_score > 0.3:
            return {
                "success": True,
                "predicted_action": best_action,
                "confidence": best_score,
                "based_on": len(similar),
                "suggested": best_score > 0.7
            }

        return {
            "success": False,
            "message": "Confianza insuficiente para sugerir",
            "confidence": best_score if best_action else 0
        }

    def _find_similar_patterns(self, command: str, limit: int = 20) -> List[Dict]:
        """Encuentra patrones similares al comando dado."""
        command_words = set((command or "").lower().split())
        scored = []

        for pattern in self.command_patterns:
            pattern_words = set((pattern.get("command") or "").lower().split())

            if command_words and pattern_words:
                intersection = len(command_words & pattern_words)
                union = len(command_words | pattern_words)
                similarity = intersection / union if union > 0 else 0
            else:
                similarity = 0

            if similarity > 0.3:
                scored.append((similarity, pattern))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def get_personalized_suggestions(self) -> List[str]:
        """Genera sugerencias personalizadas basadas en aprendizaje."""
        suggestions = []

        if self.learned_shortcuts:
            most_used = list(self.learned_shortcuts.items())[:3]
            for command, shortcut in most_used:
                suggestions.append(f"Atajo rápido: escribe '{shortcut}' para '{command}'")

        current_hour = datetime.now().hour
        for action, hours in self.time_patterns.items():
            if hours and abs(current_hour - max(set(hours), key=hours.count)) <= 2:
                suggestions.append(f"¿Quieres {action}? Es tu hora habitual")
                break

        if self.corrections:
            recent_correction = self.corrections[-1]
            suggestions.append(
                f"Recuerda: '{recent_correction['original']}' -> '{recent_correction['corrected']}'"
            )

        return suggestions

    def get_learning_stats(self) -> Dict:
        """Obtiene estadísticas de aprendizaje."""
        total_attempts = sum(v["attempts"] for v in self.success_rates.values())
        total_successes = sum(v["successes"] for v in self.success_rates.values())
        overall_success = (total_successes / total_attempts) if total_attempts > 0 else 0

        return {
            "total_patterns": len(self.command_patterns),
            "unique_actions": len(self.success_rates),
            "total_corrections": len(self.corrections),
            "shortcuts_learned": len(self.learned_shortcuts),
            "overall_success_rate": round(overall_success, 3),
            "preferences_count": len(self.user_preferences)
        }


engine = LearningEngine()


def derive_learning_from_runtime_result(payload: Dict, meta: Optional[Dict] = None) -> Optional[Dict]:
    """
    Convierte un result.out normal del sistema en una interacción aprendible.
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
        or result.get("action")
        or ""
    )

    command = (
        merged_meta.get("original_command")
        or merged_meta.get("user_command")
        or merged_meta.get("text")
        or merged_meta.get("callback_data")
        or ""
    )

    if not action and not result:
        return None

    success = payload.get("status") == "success"
    learned_result = dict(result)
    if "success" not in learned_result:
        learned_result["success"] = success

    return {
        "command": command,
        "executed_action": action,
        "result": learned_result,
        "context": {
            "source": merged_meta.get("source"),
            "chat_id": merged_meta.get("chat_id"),
            "worker": merged_meta.get("worker"),
            "ui_origin": merged_meta.get("ui_origin")
        }
    }


def handle_action(payload: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    meta = meta or {}
    action = payload.get("action")
    params = payload.get("params", {}) or {}
    task_id = payload.get("task_id") or meta.get("task_id") or f"learn_{int(datetime.now().timestamp())}"

    try:
        if not isinstance(action, str) or not action.startswith("learn."):
            derived = derive_learning_from_runtime_result(payload, meta)

            if derived:
                engine.learn_interaction(
                    command=derived.get("command", ""),
                    action=derived.get("executed_action", ""),
                    result=derived.get("result", {}),
                    context=derived.get("context", {})
                )

                emit("event.out", {
                    "task_id": task_id,
                    "type": "learning.observed",
                    "learned_implicitly": True,
                    "action": derived.get("executed_action", ""),
                    "meta": meta,
                    "trace_id": trace_id or generate_trace_id()
                })
                return

            return

        if action == "learn.interaction":
            engine.learn_interaction(
                command=params.get("command", ""),
                action=params.get("executed_action", ""),
                result=params.get("result", {}),
                context=params.get("context", {})
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "message": "Interacción aprendida"
            }, meta, trace_id=trace_id)

        elif action == "learn.correction":
            engine.learn_correction(
                original_command=params.get("original_command", ""),
                corrected_command=params.get("corrected_command", ""),
                reason=params.get("reason")
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "message": "Corrección aprendida"
            }, meta, trace_id=trace_id)

        elif action == "learn.preference":
            engine.learn_preference(
                key=params.get("key", ""),
                value=params.get("value"),
                confidence=float(params.get("confidence", 1.0))
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "message": "Preferencia aprendida"
            }, meta, trace_id=trace_id)

        elif action == "learn.predict":
            prediction = engine.predict_best_action(
                command=params.get("command", ""),
                context=params.get("context", {})
            )
            emit_guaranteed_result(task_id, "success", prediction, meta, trace_id=trace_id)

        elif action == "learn.suggestions":
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "suggestions": engine.get_personalized_suggestions()
            }, meta, trace_id=trace_id)

        elif action == "learn.stats":
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "stats": engine.get_learning_stats()
            }, meta, trace_id=trace_id)

        elif action == "learn.shortcuts":
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "shortcuts": engine.learned_shortcuts
            }, meta, trace_id=trace_id)

        else:
            emit_guaranteed_result(task_id, "error", {
                "success": False,
                "error": f"Acción no soportada: {action}"
            }, meta, trace_id=trace_id)

    except Exception as e:
        logger.error(f"Error procesando acción {action}: {e}")
        emit_guaranteed_result(task_id, "error", {
            "success": False,
            "error": str(e)
        }, meta, trace_id=trace_id)


def handle_query(payload: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    meta = meta or {}
    task_id = payload.get("task_id") or meta.get("task_id") or f"query_{int(datetime.now().timestamp())}"

    try:
        emit_guaranteed_result(task_id, "success", {
            "success": True,
            "stats": engine.get_learning_stats(),
            "suggestions": engine.get_personalized_suggestions(),
            "shortcuts": engine.learned_shortcuts
        }, meta, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Error procesando query: {e}")
        emit_guaranteed_result(task_id, "error", {
            "success": False,
            "error": str(e)
        }, meta, trace_id=trace_id)


def main():
    logger.info(f"AI Learning Engine iniciado - {MODULE_ID}")

    emit("event.out", {
        "level": "info",
        "type": "ai_learning_engine_ready",
        "module": MODULE_ID,
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

            if port == "action.in":
                handle_action(payload, meta=meta, trace_id=trace_id)
            elif port == "query.in":
                handle_query(payload, meta=meta, trace_id=trace_id)

        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido: {e}")
            emit("event.out", {
                "level": "error",
                "type": "ai_learning_engine_invalid_json",
                "error": str(e),
                "trace_id": generate_trace_id()
            })
        except Exception as e:
            logger.error(f"Error leyendo mensaje: {e}")
            emit("event.out", {
                "level": "error",
                "type": "ai_learning_engine_error",
                "error": str(e),
                "trace_id": generate_trace_id()
            })


if __name__ == "__main__":
    main()