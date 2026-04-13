import sys
import json
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None

MODULE_ID = "worker.python.system"
MAX_SEARCH_RESULTS = 10
IGNORE_DIRS = {".venv", "__pycache__", ".git", "node_modules"}


def generate_trace_id() -> str:
    return f"wsys_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def build_top_meta(meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = {
        "source": "internal",
        "timestamp": safe_iso_now(),
        "module": MODULE_ID
    }
    if isinstance(meta, dict):
        base.update(meta)
    return base


def merge_meta(top_meta: Optional[Dict[str, Any]], payload_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        **(top_meta or {}),
        **(payload_meta or {})
    }


def emit(port: str, payload: Optional[Dict[str, Any]] = None) -> None:
    payload = payload or {}
    trace_id = payload.get("trace_id") or generate_trace_id()
    meta = build_top_meta(payload.get("meta"))
    clean_payload = {k: v for k, v in payload.items() if k not in ("trace_id", "meta")}

    sys.stdout.write(json.dumps({
        "module": MODULE_ID,
        "port": port,
        "trace_id": trace_id,
        "meta": meta,
        "payload": clean_payload
    }, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def search_file(filename: str, base_path: str = ".") -> Dict[str, Any]:
    normalized_filename = (filename or "").strip()
    normalized_base_path = (base_path or ".").strip() or "."

    if not normalized_filename:
        return {
            "error": "Parámetro filename vacío o inválido"
        }

    if not os.path.exists(normalized_base_path):
        return {
            "error": f"El base_path no existe: {normalized_base_path}",
            "filename": normalized_filename,
            "base_path": normalized_base_path
        }

    if not os.path.isdir(normalized_base_path):
        return {
            "error": f"El base_path no es un directorio: {normalized_base_path}",
            "filename": normalized_filename,
            "base_path": normalized_base_path
        }

    matches = []

    for root, dirs, files in os.walk(normalized_base_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file_name in files:
            if normalized_filename.lower() in file_name.lower():
                matches.append(os.path.join(root, file_name))

            if len(matches) >= MAX_SEARCH_RESULTS:
                return {
                    "filename": normalized_filename,
                    "base_path": normalized_base_path,
                    "matches": matches
                }

    return {
        "filename": normalized_filename,
        "base_path": normalized_base_path,
        "matches": matches
    }


def monitor_resources() -> Dict[str, Any]:
    if psutil is None:
        return {
            "error": "psutil no está instalado. Ejecutá: pip3 install psutil"
        }

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent
    }


for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue

    payload: Dict[str, Any] = {}
    merged_meta: Dict[str, Any] = {}
    trace_id: Optional[str] = None

    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        emit("event.out", {
            "level": "error",
            "type": "system_worker_parse_error",
            "text": f"JSON inválido en stdin: {str(exc)}",
            "error": str(exc),
            "trace_id": generate_trace_id(),
            "meta": build_top_meta()
        })
        continue

    try:
        port = msg.get("port")
        payload = msg.get("payload", {}) or {}
        top_meta = msg.get("meta", {}) if isinstance(msg.get("meta", {}), dict) else {}
        payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        merged_meta = merge_meta(top_meta, payload_meta)

        if port != "action.in":
            continue

        task_id = payload.get("task_id") or merged_meta.get("task_id")
        action = payload.get("action") or merged_meta.get("action")
        params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}
        trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

        emit("event.out", {
            "level": "info",
            "type": "system_action_received",
            "text": f"Ejecutando acción system: {action}",
            "task_id": task_id,
            "action": action,
            "meta": build_top_meta(merged_meta),
            "trace_id": trace_id
        })

        try:
            if action == "search_file":
                result = search_file(
                    params.get("filename", ""),
                    params.get("base_path", ".")
                )
            elif action == "monitor_resources":
                result = monitor_resources()
            else:
                result = {"error": f"Acción system no soportada: {action}"}

            status = "success" if "error" not in result else "error"

        except Exception as exc:
            result = {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "action": action
            }
            status = "error"

            emit("event.out", {
                "level": "error",
                "type": "system_worker_action_error",
                "text": f"Error ejecutando acción system: {action}",
                "task_id": task_id,
                "action": action,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "meta": build_top_meta(merged_meta),
                "trace_id": trace_id
            })

        emit("result.out", {
            "task_id": task_id,
            "status": status,
            "result": result,
            "meta": build_top_meta(merged_meta),
            "trace_id": trace_id
        })

    except Exception as exc:
        emit("event.out", {
            "level": "error",
            "type": "system_worker_runtime_error",
            "text": f"Error general en {MODULE_ID}: {str(exc)}",
            "task_id": payload.get("task_id") or merged_meta.get("task_id"),
            "error": str(exc),
            "error_type": type(exc).__name__,
            "meta": build_top_meta(merged_meta),
            "trace_id": trace_id or generate_trace_id()
        })

        emit("result.out", {
            "task_id": payload.get("task_id") or merged_meta.get("task_id"),
            "status": "error",
            "result": {
                "error": str(exc),
                "error_type": type(exc).__name__,
                "action": payload.get("action") or merged_meta.get("action")
            },
            "meta": build_top_meta(merged_meta),
            "trace_id": trace_id or generate_trace_id()
        })