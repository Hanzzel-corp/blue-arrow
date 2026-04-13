"""
AI Assistant Module - Integración con LLaMA para asistencia inteligente
Módulo de Python para blueprint-v0 que proporciona capacidades de IA local
"""

import json
import sys
import os
import subprocess
import re
import time
import threading
import random
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any

MODULE_ID = "ai.assistant.main"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def generate_trace_id() -> str:
    return f"ai_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


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

        def debug(self, msg):
            print(f"DEBUG: {msg}", file=sys.stderr)


logger = StructuredLogger(MODULE_ID)


def build_top_meta(meta: Optional[Dict] = None) -> Dict:
    incoming = dict(meta or {})
    incoming.pop("module", None)

    return {
        **incoming,
        "source": incoming.get("source", "internal"),
        "timestamp": safe_iso_now(),
        "module": MODULE_ID
    }


def emit(port: str, payload: Optional[Dict] = None):
    """Emite mensaje JSON Lines a stdout respetando contrato top-level."""
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
    """Emite resultado estandarizado."""
    emit("result.out", {
        "task_id": task_id,
        "status": status,
        "result": result,
        "meta": build_top_meta(meta),
        "trace_id": trace_id or generate_trace_id()
    })


ACTION_TIMEOUTS = {
    "ai.query": 40,
    "ai.generate_text": 40,
    "ai.analyze_intent": 20,
    "ai.generate_code": 40,
    "ai.explain_error": 25,
    "ai.analyze_project": 45,
    "default": 20
}


class Watchdog:
    """Watchdog para emitir heartbeats durante operaciones largas."""

    def __init__(
        self,
        task_id: str,
        interval: float = 3.0,
        trace_id: Optional[str] = None,
        meta: Optional[Dict] = None
    ):
        self.task_id = task_id
        self.interval = interval
        self.trace_id = trace_id or generate_trace_id()
        self.meta = meta or {}
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = None

    def _heartbeat(self):
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start_time
            emit("event.out", {
                "level": "info",
                "type": "ai_processing",
                "task_id": self.task_id,
                "status": "processing",
                "elapsed_seconds": round(elapsed, 1),
                "trace_id": self.trace_id,
                "meta": self.meta
            })
            self._stop_event.wait(self.interval)

    def start(self):
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=0.5)


class LLaMAInterface:
    """Interfaz para comunicación con LLaMA local vía ollama CLI."""

    def __init__(self, model: str = "llama3.2"):
        self.model = model
        self.logger = StructuredLogger("LLaMAInterface")
        self.conversation_history: List[Dict] = []
        self.max_history = 20

    def check_ollama_available(self) -> bool:
        """Verifica si ollama CLI está disponible y responde."""
        try:
            which_result = subprocess.run(
                ["which", "ollama"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=2
            )
            if which_result.returncode != 0:
                return False

            version_result = subprocess.run(
                ["ollama", "--version"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=4
            )
            return version_result.returncode == 0
        except Exception:
            return False

    def query(self, prompt: str, timeout: int = 40) -> Dict:
        """
        Consulta a LLaMA vía ollama CLI.
        Para ai.query se usa exactamente el prompt limpio,
        para replicar el comportamiento manual que sí funciona en terminal.
        """
        try:
            effective_prompt = (prompt or "").strip()

            if not effective_prompt:
                return {
                    "success": False,
                    "error": "Prompt vacío",
                    "error_type": "empty_prompt",
                    "model": self.model,
                    "timestamp": safe_iso_now()
                }

            cmd = ["ollama", "run", self.model, effective_prompt]

            logger.info(f"Llamando a ollama con prompt limpio: {effective_prompt[:80]}...")

            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8"
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Ollama error: {result.stderr.strip() or 'unknown error'}",
                    "stderr": result.stderr.strip(),
                    "stdout": result.stdout.strip(),
                    "model": self.model,
                    "timestamp": safe_iso_now()
                }

            content = (result.stdout or "").strip()

            if not content:
                return {
                    "success": False,
                    "error": "Ollama devolvió una respuesta vacía",
                    "model": self.model,
                    "timestamp": safe_iso_now()
                }

            self.conversation_history.append({"role": "user", "content": effective_prompt})
            self.conversation_history.append({"role": "assistant", "content": content})

            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history * 2:]

            return {
                "success": True,
                "response": content,
                "model": self.model,
                "timestamp": safe_iso_now()
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Timeout - LLaMA tardó demasiado en responder ({timeout}s)",
                "error_type": "timeout",
                "model": self.model,
                "timestamp": safe_iso_now()
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "model": self.model,
                "timestamp": safe_iso_now()
            }

    def analyze_intent(self, text: str) -> Dict:
        prompt = f"""Analiza el siguiente comando del usuario y responde SOLO JSON válido:

{{
  "intent": "intención_principal",
  "confidence": 0.0,
  "entities": {{
    "app": null,
    "file": null,
    "url": null,
    "command": null
  }},
  "context": "contexto implícito",
  "suggested_action": "acción recomendada",
  "requires_approval": false,
  "risk_level": "low"
}}

Comando:
{text}
"""
        result = self.query(prompt, timeout=ACTION_TIMEOUTS["ai.analyze_intent"])

        if result.get("success"):
            try:
                response_text = result["response"]

                if "```json" in response_text:
                    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(1)
                elif "```" in response_text:
                    json_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
                    if json_match:
                        response_text = json_match.group(1)

                parsed = json.loads(response_text)
                return {
                    "success": True,
                    "analysis": parsed,
                    "raw_response": result["response"]
                }
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "error": f"No se pudo parsear JSON: {e}",
                    "raw_response": result["response"]
                }

        return result

    def generate_code(self, description: str, language: str = "python") -> Dict:
        prompt = f"""Genera código {language} de alta calidad, bien documentado y con manejo de errores para:

{description}

Responde con el código directamente."""
        return self.query(prompt, timeout=ACTION_TIMEOUTS["ai.generate_code"])

    def explain_error(self, error_message: str, context: str = "") -> Dict:
        prompt = f"""Explica este error y sugiere soluciones:

Error: {error_message}

Contexto: {context if context else 'No disponible'}

Proporciona:
1. Explicación del error
2. Posibles causas
3. Soluciones sugeridas
4. Código de ejemplo si aplica
"""
        return self.query(prompt, timeout=ACTION_TIMEOUTS["ai.explain_error"])

    def get_conversation_context(self, limit: int = 10) -> List[Dict]:
        return self.conversation_history[-limit:]

    def clear_history(self):
        self.conversation_history = []


class SelfAnalyzer:
    """Sistema de auto-análisis del proyecto."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.llama = LLaMAInterface()

    def analyze_project_structure(self) -> Dict:
        structure = {
            "modules": [],
            "blueprints": [],
            "docs": [],
            "tests": []
        }

        modules_path = os.path.join(self.project_root, "modules")
        if os.path.exists(modules_path):
            structure["modules"] = [
                d for d in os.listdir(modules_path)
                if os.path.isdir(os.path.join(modules_path, d))
            ]

        blueprints_path = os.path.join(self.project_root, "blueprints")
        if os.path.exists(blueprints_path):
            structure["blueprints"] = [
                f for f in os.listdir(blueprints_path)
                if f.endswith(".json")
            ]

        docs_path = os.path.join(self.project_root, "docs")
        if os.path.exists(docs_path):
            structure["docs"] = [
                f for f in os.listdir(docs_path)
                if f.endswith(".md")
            ]

        tests_path = os.path.join(self.project_root, "tests")
        if os.path.exists(tests_path):
            structure["tests"] = [
                f for f in os.listdir(tests_path)
                if f.endswith(".py") or f.endswith(".js")
            ]

        return {
            "success": True,
            "structure": structure,
            "stats": {
                "module_count": len(structure["modules"]),
                "blueprint_count": len(structure["blueprints"]),
                "doc_count": len(structure["docs"]),
                "test_count": len(structure["tests"])
            }
        }

    def suggest_improvements(self) -> Dict:
        analysis = self.analyze_project_structure()

        if not analysis["success"]:
            return analysis

        prompt = f"""Analiza este proyecto con {analysis['stats']['module_count']} módulos y sugiere mejoras:

Módulos: {', '.join(analysis['structure']['modules'][:10])}

Proporciona sugerencias en estas categorías:
1. Arquitectura
2. Código y calidad
3. Documentación
4. Testing
5. Performance
6. Seguridad
"""

        result = self.llama.query(
            prompt,
            timeout=ACTION_TIMEOUTS["ai.analyze_project"]
        )

        if result.get("success"):
            return {
                "success": True,
                "analysis": analysis["stats"],
                "suggestions": result["response"],
                "timestamp": safe_iso_now()
            }

        return result


class UserLearningSystem:
    """Sistema de aprendizaje del usuario."""

    def __init__(self, memory_path: str = "logs/user-learning.json"):
        self.memory_path = os.path.join(PROJECT_ROOT, memory_path)
        self.preferences: Dict = {}
        self.patterns: List[Dict] = []
        self.load_memory()

    def load_memory(self):
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.preferences = data.get("preferences", {})
                    self.patterns = data.get("patterns", [])
            except Exception:
                pass

    def save_memory(self):
        os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump({
                "preferences": self.preferences,
                "patterns": self.patterns,
                "updated_at": safe_iso_now()
            }, f, indent=2, ensure_ascii=False)

    def learn_from_command(self, command: str, action: str, result: Dict):
        pattern = {
            "command": command,
            "action": action,
            "timestamp": safe_iso_now(),
            "success": result.get("success", False)
        }

        self.patterns.append(pattern)

        if len(self.patterns) > 1000:
            self.patterns = self.patterns[-500:]

        self.save_memory()

    def get_user_preferences(self) -> Dict:
        return self.preferences

    def update_preference(self, key: str, value: Any):
        self.preferences[key] = {
            "value": value,
            "updated_at": safe_iso_now()
        }
        self.save_memory()

    def predict_next_action(self, context: str) -> Optional[str]:
        similar = [p for p in self.patterns if context.lower() in p.get("command", "").lower()]

        if similar:
            actions = {}
            for p in similar:
                action = p.get("action", "unknown")
                actions[action] = actions.get(action, 0) + 1

            if actions:
                return max(actions.items(), key=lambda x: x[1])[0]

        return None


def query_with_timeout(prompt: str, timeout_sec: int = 40) -> Dict:
    """Usa el timeout interno de la interfaz LLaMA."""
    return llama_interface.query(prompt, timeout=timeout_sec)


def normalize_generate_text_result(result: Dict) -> Dict:
    response_text = (
        result.get("response")
        or result.get("text")
        or result.get("content")
        or ""
    )
    return {
        "success": True,
        "text": response_text,
        "response": response_text,
        "model": result.get("model"),
        "timestamp": result.get("timestamp", safe_iso_now())
    }


llama_interface = LLaMAInterface()
self_analyzer = SelfAnalyzer(PROJECT_ROOT)
learning_system = UserLearningSystem()

aiState = {
    "phase": "idle",
    "context": {
        "task_id": None,
        "chat_id": None,
        "input": None,
        "intent": None,
        "start_time": None
    },
    "metrics": {
        "queries_total": 0,
        "queries_success": 0,
        "queries_error": 0,
        "queries_timeout": 0
    }
}


def transition_to(new_phase, context_update=None, trace_id: Optional[str] = None, meta: Optional[Dict] = None):
    old_phase = aiState["phase"]
    aiState["phase"] = new_phase
    if context_update:
        aiState["context"].update(context_update)

    logger.info(f"Phase transition: {old_phase} -> {new_phase}")
    emit("event.out", {
        "level": "info",
        "type": "ai_phase_transition",
        "from": old_phase,
        "to": new_phase,
        "task_id": aiState["context"].get("task_id"),
        "trace_id": trace_id or generate_trace_id(),
        "meta": meta or {}
    })


def reset_state():
    aiState["phase"] = "idle"
    aiState["context"] = {
        "task_id": None,
        "chat_id": None,
        "input": None,
        "intent": None,
        "start_time": None
    }


def emit_guaranteed_result(task_id, status, result, meta, trace_id: Optional[str] = None):
    try:
        emit_result(task_id, status, result, meta, trace_id=trace_id)
        logger.info(f"Result emitted: {status} for task {task_id}")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to emit result: {e}")
        fallback_trace = trace_id or generate_trace_id()
        fallback = {
            "module": MODULE_ID,
            "port": "result.out",
            "trace_id": fallback_trace,
            "meta": build_top_meta(meta),
            "payload": {
                "task_id": task_id,
                "status": "error",
                "result": {
                    "error": "Failed to emit result",
                    "original_status": status,
                    "original_emit_error": str(e)
                }
            }
        }
        print(json.dumps(fallback, ensure_ascii=False), flush=True)


def extract_task_id(msg: Dict, payload: Dict, meta: Dict) -> Optional[str]:
    return (
        payload.get("task_id")
        or msg.get("task_id")
        or meta.get("task_id")
        or payload.get("plan_id")
        or msg.get("plan_id")
    )


def handle_ai_query(task_id: str, params: Dict, meta: Dict, input_trace_id: str):
    query_trace_id = input_trace_id
    prompt = params.get("prompt", "")
    timeout = ACTION_TIMEOUTS.get("ai.query", 40)

    emit("event.out", {
        "level": "info",
        "type": "ai_query_received",
        "task_id": task_id,
        "chat_id": meta.get("chat_id"),
        "prompt": prompt[:80],
        "meta": meta,
        "trace_id": query_trace_id
    })

    aiState["metrics"]["queries_total"] += 1
    transition_to("processing", {
        "task_id": task_id,
        "chat_id": meta.get("chat_id"),
        "input": prompt,
        "start_time": safe_iso_now()
    }, trace_id=query_trace_id, meta=meta)

    emit("event.out", {
        "level": "info",
        "type": "ai_query_processing",
        "task_id": task_id,
        "phase": "processing",
        "meta": meta,
        "trace_id": query_trace_id
    })

    watchdog = Watchdog(
        task_id,
        interval=3.0,
        trace_id=query_trace_id,
        meta=meta
    )

    try:
        if not llama_interface.check_ollama_available():
            transition_to("error", {"intent": "ollama_unavailable"}, trace_id=query_trace_id, meta=meta)
            result = {
                "success": False,
                "error": "Ollama no está disponible",
                "response": "Lo siento, el servicio de IA no está disponible.",
                "phase": "error"
            }
            emit_guaranteed_result(task_id, "error", result, meta, trace_id=query_trace_id)
            aiState["metrics"]["queries_error"] += 1
            reset_state()
            return

        emit("event.out", {
            "level": "info",
            "text": f"Consultando a LLaMA: {prompt[:80]}...",
            "task_id": task_id,
            "meta": meta,
            "trace_id": query_trace_id
        })

        watchdog.start()
        result = query_with_timeout(prompt, timeout_sec=timeout)

        status = "success" if result.get("success") else "error"
        if status == "success":
            aiState["metrics"]["queries_success"] += 1
            transition_to("responding", {"intent": "query_complete"}, trace_id=query_trace_id, meta=meta)
        else:
            if result.get("error_type") == "timeout":
                aiState["metrics"]["queries_timeout"] += 1
            else:
                aiState["metrics"]["queries_error"] += 1
            transition_to("error", {"intent": result.get("error_type", "query_failed")}, trace_id=query_trace_id, meta=meta)

        emit("event.out", {
            "level": "info",
            "text": f"Respuesta recibida: {result.get('success', False)}",
            "task_id": task_id,
            "meta": meta,
            "trace_id": query_trace_id
        })

        emit_guaranteed_result(task_id, status, result, meta, trace_id=query_trace_id)

        emit("event.out", {
            "level": "info",
            "type": "ai_query_completed",
            "task_id": task_id,
            "status": status,
            "phase": "completed" if status == "success" else "error",
            "meta": meta,
            "trace_id": query_trace_id
        })

        transition_to(
            "completed" if status == "success" else "idle",
            {"intent": "query_success" if status == "success" else "query_failed"},
            trace_id=query_trace_id,
            meta=meta
        )
        reset_state()

    except Exception as e:
        logger.error(f"Error en ai.query: {e}")
        aiState["metrics"]["queries_error"] += 1
        transition_to("error", {"intent": "exception", "error": str(e)}, trace_id=query_trace_id, meta=meta)

        emit("event.out", {
            "level": "error",
            "type": "ai_query_completed",
            "task_id": task_id,
            "status": "error",
            "phase": "exception",
            "trace_id": query_trace_id,
            "meta": meta
        })

        result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "response": "Error procesando la consulta",
            "partial_result": {
                "query_received": True,
                "ollama_available": llama_interface.check_ollama_available(),
                "error_at": safe_iso_now()
            },
            "phase": "error"
        }

        emit_guaranteed_result(task_id, "error", result, meta, trace_id=query_trace_id)
        reset_state()

    finally:
        watchdog.stop()


def main():
    logger.info(f"AI Assistant Module iniciado - {MODULE_ID}")

    ollama_available = llama_interface.check_ollama_available()
    logger.info(f"Ollama disponible: {ollama_available}")

    emit("event.out", {
        "level": "info",
        "type": "ai_assistant_ready",
        "ollama_available": ollama_available,
        "model": llama_interface.model,
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

            action = payload.get("action", "")
            params = payload.get("params", {}) or {}
            task_id = extract_task_id(msg, payload, meta)
            input_trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

            emit("event.out", {
                "level": "info",
                "type": "ai_input_received",
                "port": port,
                "task_id": task_id,
                "action": action,
                "has_params": isinstance(params, dict),
                "meta": {
                    "chat_id": meta.get("chat_id"),
                    "source": meta.get("source")
                },
                "trace_id": input_trace_id
            })

            if port == "ai.action.in":
                if not task_id:
                    emit("event.out", {
                        "level": "error",
                        "type": "ai_missing_task_id",
                        "message": "ai.assistant.main recibió ai.action.in sin task_id",
                        "payload_keys": list(payload.keys()),
                        "meta_keys": list(meta.keys()) if isinstance(meta, dict) else [],
                        "trace_id": input_trace_id,
                        "meta": meta
                    })
                    continue

                logger.info(f"Acción recibida: {action} | task_id={task_id}")

                emit("event.out", {
                    "level": "info",
                    "text": f"Procesando acción de IA: {action}",
                    "task_id": task_id,
                    "trace_id": input_trace_id,
                    "meta": meta
                })

                if action == "ai.query":
                    handle_ai_query(task_id, params, meta, input_trace_id)

                elif action == "ai.generate_text":
                    prompt = (
                        params.get("prompt")
                        or params.get("instruction")
                        or params.get("text")
                        or ""
                    )

                    if not prompt.strip():
                        emit_guaranteed_result(
                            task_id,
                            "error",
                            {
                                "success": False,
                                "error": "Prompt vacío",
                                "error_type": "empty_prompt"
                            },
                            meta,
                            trace_id=input_trace_id
                        )
                        continue

                    result = llama_interface.query(
                        prompt,
                        timeout=ACTION_TIMEOUTS.get("ai.generate_text", 40)
                    )

                    if result.get("success"):
                        normalized_result = normalize_generate_text_result(result)
                        emit_guaranteed_result(
                            task_id,
                            "success",
                            normalized_result,
                            meta,
                            trace_id=input_trace_id
                        )
                    else:
                        emit_guaranteed_result(
                            task_id,
                            "error",
                            result,
                            meta,
                            trace_id=input_trace_id
                        )

                elif action == "ai.analyze_intent":
                    text = params.get("text", "")
                    result = llama_interface.analyze_intent(text)
                    emit_guaranteed_result(
                        task_id,
                        "success" if result.get("success") else "error",
                        result,
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.generate_code":
                    description = params.get("description", "")
                    language = params.get("language", "python")
                    result = llama_interface.generate_code(description, language)
                    emit_guaranteed_result(
                        task_id,
                        "success" if result.get("success") else "error",
                        result,
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.explain_error":
                    error_msg = params.get("error", "")
                    context = params.get("context", "")
                    result = llama_interface.explain_error(error_msg, context)
                    emit_guaranteed_result(
                        task_id,
                        "success" if result.get("success") else "error",
                        result,
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.analyze_project":
                    result = self_analyzer.suggest_improvements()
                    emit_guaranteed_result(
                        task_id,
                        "success" if result.get("success") else "error",
                        result,
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.learn":
                    command = params.get("command", "")
                    action_name = params.get("action_name", "")
                    result_data = params.get("result", {})
                    learning_system.learn_from_command(command, action_name, result_data)
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"learned": True},
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.get_preferences":
                    prefs = learning_system.get_user_preferences()
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"preferences": prefs},
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.predict":
                    context = params.get("context", "")
                    prediction = learning_system.predict_next_action(context)
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"prediction": prediction},
                        meta,
                        trace_id=input_trace_id
                    )

                elif action == "ai.clear_history":
                    llama_interface.clear_history()
                    emit_guaranteed_result(
                        task_id,
                        "success",
                        {"cleared": True},
                        meta,
                        trace_id=input_trace_id
                    )

                else:
                    emit_guaranteed_result(
                        task_id,
                        "error",
                        {"error": f"Acción desconocida: {action}"},
                        meta,
                        trace_id=input_trace_id
                    )

            elif port == "query.in":
                query_type = payload.get("query_type", "")
                if not task_id:
                    task_id = f"query_{int(time.time() * 1000)}"

                if query_type == "ai_status":
                    emit_guaranteed_result(task_id, "success", {
                        "ollama_available": llama_interface.check_ollama_available(),
                        "model": llama_interface.model,
                        "conversation_history_size": len(llama_interface.conversation_history),
                        "learned_patterns": len(learning_system.patterns),
                        "metrics": aiState["metrics"]
                    }, meta, trace_id=input_trace_id)
                else:
                    emit_guaranteed_result(task_id, "error", {
                        "error": f"query_type desconocido: {query_type or 'empty'}"
                    }, meta, trace_id=input_trace_id)

        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido: {e}")
            emit("event.out", {
                "level": "error",
                "type": "ai_invalid_json",
                "error": str(e),
                "trace_id": generate_trace_id()
            })
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            logger.error(traceback.format_exc())
            emit("event.out", {
                "level": "error",
                "type": "ai_module_exception",
                "error": str(e),
                "trace_id": generate_trace_id()
            })


if __name__ == "__main__":
    main()