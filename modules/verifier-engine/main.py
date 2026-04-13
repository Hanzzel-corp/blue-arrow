"""
Execution Verifier Engine - Core Module

Procesa resultados de workers, calcula confidence scores,
y emite resultados verificados para el supervisor.
"""

import json
import sys
import traceback
import time
import random
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path


MODULE_ID = "verifier.engine.main"
MAX_PROCESSED_TASKS = 1000


def generate_trace_id() -> str:
    return f"ver_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


# Add project root for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.execution_verifier import VerificationBuilder


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
    """Emite mensaje JSON Lines a stdout."""
    payload = payload or {}
    trace_id = payload.get("trace_id") or generate_trace_id()
    meta = build_top_meta(payload.get("meta"))
    clean_payload = {k: v for k, v in payload.items() if k not in ("trace_id", "meta")}
    msg = {
        "module": MODULE_ID,
        "port": port,
        "trace_id": trace_id,
        "meta": meta,
        "payload": clean_payload
    }
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def emit_verified_result(payload: Dict[str, Any], trace_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> None:
    """Emite resultado verificado completo hacia supervisor."""
    final_payload = dict(payload)
    final_payload["trace_id"] = final_payload.get("trace_id") or trace_id or generate_trace_id()
    final_payload["meta"] = build_top_meta(merge_meta(meta, final_payload.get("meta")))
    emit("result.out", final_payload)


def emit_verification_event(
    task_id: str,
    event_type: str,
    data: Dict[str, Any],
    trace_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> None:
    """Emite evento de verificación detallado."""
    emit("verification.out", {
        "task_id": task_id,
        "event_type": event_type,
        "timestamp": safe_iso_now(),
        "trace_id": trace_id or generate_trace_id(),
        "data": data,
        "meta": build_top_meta(meta)
    })


def emit_event(
    level: str,
    text: str,
    trace_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> None:
    """Emite evento de log."""
    emit("event.out", {
        "level": level,
        "text": text,
        "trace_id": trace_id or generate_trace_id(),
        "meta": build_top_meta(meta),
        **kwargs
    })


class VerifierCore:
    """Núcleo del sistema de verificación."""

    def __init__(self, min_confidence: float = 0.75) -> None:
        self.min_confidence = min_confidence
        self.processed_tasks: Dict[str, Dict[str, Any]] = {}

    def process_result(self, task_id: str, action: str, result: Dict[str, Any], meta: Dict[str, Any], trace_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Procesa un resultado y enriquece con verificación si es necesario.
        """
        if not task_id or task_id == "unknown":
            raise ValueError("task_id inválido para verificación")

        safe_result = result if isinstance(result, dict) else {}
        safe_meta = meta if isinstance(meta, dict) else {}
        safe_action = action if isinstance(action, str) and action.strip() else "unknown"

        if "_verification" in safe_result and isinstance(safe_result["_verification"], dict):
            verification = safe_result["_verification"]

            emit_verification_event(
                task_id,
                "verification_received",
                {
                    "action": safe_action,
                    "confidence": verification.get("confidence", 0),
                    "executive_state": verification.get("executive_state", "unknown"),
                    "level": verification.get("level", "unknown")
                },
                trace_id=trace_id,
                meta=safe_meta
            )

            return self._build_verified_result(task_id, safe_result, verification, safe_meta)

        verification = self._calculate_verification(safe_action, safe_result)
        safe_result["_verification"] = verification

        emit_verification_event(
            task_id,
            "verification_calculated",
            {
                "action": safe_action,
                "confidence": verification["confidence"],
                "executive_state": verification["executive_state"],
                "level": verification["level"],
                "note": "calculated_from_legacy"
            },
            trace_id=trace_id,
            meta=safe_meta
        )

        return self._build_verified_result(task_id, safe_result, verification, safe_meta)

    def _calculate_verification(self, action: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula verificación desde resultado legacy."""
        builder = VerificationBuilder(action)

        if action == "open_application":
            builder.add_signal("process_detected", result.get("process_detected", False), 0.20)
            builder.add_signal("window_detected", result.get("window_detected", False), 0.30)
            builder.add_signal(
                "target_matched",
                result.get("target_matched", result.get("opened", False)),
                0.25
            )
            builder.add_signal(
                "focus_confirmed",
                result.get("focus_confirmed", result.get("focus_attempted", False)),
                0.15
            )
            builder.add_signal("window_raised", result.get("focus_attempted", False), 0.10)

            if result.get("window_id"):
                builder.add_evidence("window_id", result["window_id"])
            if result.get("pid"):
                builder.add_evidence("pid", result["pid"])

        elif action == "terminal.write_command":
            builder.add_signal("terminal_exists", result.get("window_id") is not None, 0.20)
            builder.add_signal("window_active", result.get("active_window") is not None, 0.25)
            builder.add_signal("command_typed", result.get("success", False), 0.20)
            builder.add_signal("command_executed", result.get("executed", False), 0.25)
            builder.add_signal("output_captured", bool(result.get("output")), 0.10)

            if result.get("window_id"):
                builder.add_evidence("window_id", result["window_id"])

        elif action in ["open_url", "search_google", "fill_form", "click_web"]:
            builder.add_signal("page_loaded", result.get("opened", result.get("searched", False)), 0.30)
            builder.add_signal("url_matches", result.get("url") is not None, 0.25)
            builder.add_signal("title_available", bool(result.get("title")), 0.15)
            builder.add_signal("dom_ready", result.get("opened", False), 0.10)
            builder.add_signal("browser_opened", True, 0.20)

            if result.get("url"):
                builder.add_evidence("final_url", result["url"])
            if result.get("title"):
                builder.add_evidence("page_title", result["title"])

        else:
            builder.add_signal("generic_success", result.get("success", False), 0.60)
            builder.add_signal("has_result_payload", bool(result), 0.20)
            builder.add_signal("has_error", not bool(result.get("error")), 0.20)

        success = result.get("success", result.get("opened", result.get("searched", False)))
        target = result.get("application") or result.get("resolved_name") or result.get("url")

        verification = builder.build(success=success, target=target)

        confidence = float(verification.get("confidence", 0))
        executive_state = verification.get("executive_state", "unknown")

        if executive_state.startswith("success") and confidence < self.min_confidence:
            verification["executive_state"] = "success_weak"

        return verification

    def _build_verified_result(self, task_id: str, result: Dict[str, Any], verification: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
        """Construye resultado final con metadatos de verificación."""
        confidence = float(verification.get("confidence", 0))
        executive_state = verification.get("executive_state", "unknown")

        if executive_state.startswith("success"):
            status = "success"
        elif executive_state.startswith("error"):
            status = "error"
        else:
            status = "unknown"

        self.processed_tasks[task_id] = {
            "result": result,
            "verification": verification,
            "processed_at": safe_iso_now()
        }
        self._cleanup_processed_tasks()

        return {
            "task_id": task_id,
            "status": status,
            "result": result,
            "verification": {
                "confidence": confidence,
                "executive_state": executive_state,
                "level": verification.get("level", "unknown"),
                "classification": verification.get("classification", {})
            },
            "meta": meta
        }

    def _cleanup_processed_tasks(self) -> None:
        """Evita crecimiento infinito de memoria."""
        if len(self.processed_tasks) <= MAX_PROCESSED_TASKS:
            return

        overflow = len(self.processed_tasks) - MAX_PROCESSED_TASKS
        keys = list(self.processed_tasks.keys())[:overflow]
        for key in keys:
            self.processed_tasks.pop(key, None)

    def get_task_verification(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene verificación de una tarea procesada."""
        return self.processed_tasks.get(task_id)


def main() -> None:
    """Punto de entrada principal del módulo."""
    verifier = VerifierCore(min_confidence=0.75)

    emit_event(
        "info",
        "Execution Verifier Engine iniciado",
        meta={"module_name": MODULE_ID, "version": "1.0.0"}
    )

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            port = msg.get("port")
            payload = msg.get("payload", {}) or {}
            top_meta = msg.get("meta", {}) or {}
            payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
            merged_meta = merge_meta(top_meta, payload_meta)
            trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

            if port != "result.in":
                continue

            task_id = payload.get("task_id") or merged_meta.get("task_id")
            if not task_id:
                emit_event(
                    "error",
                    "result.in sin task_id",
                    trace_id=trace_id,
                    meta=merged_meta,
                    payload=payload
                )
                continue

            action = (
                payload.get("action")
                or merged_meta.get("action")
                or "unknown"
            )
            result = payload.get("result", {})
            meta = merged_meta

            emit_event(
                "info",
                f"Procesando verificación para {action}",
                trace_id=trace_id,
                meta=meta,
                task_id=task_id,
                action=action
            )

            verified = verifier.process_result(task_id, action, result, meta, trace_id=trace_id)

            emit_verified_result(verified, trace_id=trace_id, meta=meta)

            emit_event(
                "info" if verified["status"] == "success" else "warn",
                (
                    "Verificación completada: "
                    f"{verified['verification']['executive_state']} "
                    f"(confidence: {verified['verification']['confidence']})"
                ),
                trace_id=trace_id,
                meta=meta,
                task_id=task_id,
                executive_state=verified["verification"]["executive_state"],
                confidence=verified["verification"]["confidence"]
            )

        except json.JSONDecodeError as exc:
            emit_event("error", f"JSON inválido: {exc}")
        except Exception as exc:
            emit_event("error", f"Error procesando resultado: {exc}")
            emit_event("error", traceback.format_exc())


if __name__ == "__main__":
    main()