import sys
import os
import json
import subprocess
import shutil
import time
import re
import random
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


MODULE_ID = "worker.python.terminal"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TERMINAL_STATE_PATH = PROJECT_ROOT / "logs" / "command-terminal.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.execution_verifier import enrich_success, enrich_error

_terminal_window_id = None


def generate_trace_id() -> str:
    return f"wpt_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


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


def emit_result(
    task_id: Optional[str],
    status: str,
    result: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> None:
    emit("result.out", {
        "task_id": task_id,
        "status": status,
        "result": result,
        "trace_id": trace_id or generate_trace_id(),
        "meta": build_top_meta(meta)
    })


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\s\-.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def build_result_meta(meta: Optional[Dict[str, Any]] = None, window_id: Optional[str] = None) -> Dict[str, Any]:
    base = dict(meta or {})
    if window_id:
        base["window_id"] = window_id

        resolved = dict(base.get("resolved_application") or {})
        resolved["window_id"] = window_id
        if resolved:
            base["resolved_application"] = resolved

        active = dict(base.get("active_app") or {})
        if active:
            active["window_id"] = window_id
            base["active_app"] = active

    return base


def window_exists(window_id: Optional[str]) -> bool:
    if not window_id:
        return False
    try:
        subprocess.run(
            ["xdotool", "getwindowname", str(window_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except Exception:
        return False


def save_terminal_window_id(window_id: str) -> None:
    global _terminal_window_id
    _terminal_window_id = window_id
    try:
        TERMINAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TERMINAL_STATE_PATH.write_text(
            json.dumps({"window_id": window_id, "updated_at": time.time()}),
            encoding="utf-8"
        )
    except Exception:
        pass


def load_terminal_window_id() -> Optional[str]:
    global _terminal_window_id

    if _terminal_window_id and window_exists(_terminal_window_id):
        return _terminal_window_id

    try:
        if TERMINAL_STATE_PATH.exists():
            data = json.loads(TERMINAL_STATE_PATH.read_text(encoding="utf-8"))
            wid = (data or {}).get("window_id")
            if window_exists(wid):
                _terminal_window_id = wid
                return wid
    except Exception:
        pass

    return None


def list_matching_window_ids(markers) -> list[str]:
    markers = [normalize_text(m) for m in markers if m]
    if not markers or not command_exists("wmctrl"):
        return []

    try:
        out = subprocess.check_output(
            ["wmctrl", "-lx"],
            text=True,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return []

    found = []
    for line in out.splitlines():
        raw = normalize_text(line)
        if not raw:
            continue

        for marker in markers:
            if marker in raw:
                parts = line.split(None, 1)
                if parts:
                    found.append(parts[0])
                break

    return found


def detect_new_window_id(before_ids, markers, checks: int = 20, delay: float = 0.25) -> Optional[str]:
    before_set = set(before_ids or [])

    for _ in range(checks):
        time.sleep(delay)
        current_ids = list_matching_window_ids(markers)
        for wid in current_ids:
            if wid not in before_set:
                return wid

    return None


def terminal_markers() -> list[str]:
    return [
        "gnome-terminal",
        "gnome-terminal-server",
        "org.gnome.terminal",
        "terminal"
    ]


def detached_popen(command):
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ.copy(),
        start_new_session=True
    )


def is_process_running() -> bool:
    aliases = {"gnome-terminal", "gnome-terminal-server", "terminal"}
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "comm=,args="],
            text=True,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return False

    for line in out.splitlines():
        raw = normalize_text(line)
        if not raw:
            continue
        for alias in aliases:
            if raw == alias or raw.startswith(alias) or alias in raw:
                return True

    return False


def launch_terminal_window():
    attempts = []

    if command_exists("gnome-terminal"):
        attempts.append((["gnome-terminal", "--window"], "gnome-terminal --window"))
        attempts.append((["gnome-terminal"], "gnome-terminal"))

    if command_exists("gtk-launch"):
        attempts.append((["gtk-launch", "org.gnome.Terminal.desktop"], "gtk-launch"))

    if command_exists("gio"):
        attempts.append((
            ["gio", "launch", "/usr/share/applications/org.gnome.Terminal.desktop"],
            "gio-launch"
        ))

    for cmd, mode in attempts:
        try:
            proc = detached_popen(cmd)
            return proc, mode
        except Exception:
            continue

    return None, None


def bring_window_to_front(window_id: Optional[str]) -> bool:
    if not window_id:
        return False

    ok = False
    try:
        subprocess.run(
            ["xdotool", "windowraise", str(window_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        ok = True
    except Exception:
        pass

    try:
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(window_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        ok = True
    except Exception:
        pass

    return ok


def get_active_window_info() -> Dict[str, Any]:
    if not command_exists("xdotool"):
        return {"ok": False, "error": "xdotool no disponible"}

    try:
        win_id = subprocess.check_output(
            ["xdotool", "getactivewindow"],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()

        win_name = subprocess.check_output(
            ["xdotool", "getwindowname", win_id],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()

        wm_class = subprocess.check_output(
            ["xprop", "-id", win_id, "WM_CLASS"],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()

        return {
            "ok": True,
            "id": win_id,
            "name": win_name,
            "wm_class": wm_class
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def is_terminal_window_active():
    info = get_active_window_info()
    if not info.get("ok"):
        return False, info

    haystack = normalize_text(f"{info.get('name', '')} {info.get('wm_class', '')}")
    for marker in terminal_markers():
        if marker in haystack:
            return True, info

    return False, info


def ensure_terminal_window(visible: bool = True) -> Dict[str, Any]:
    existing = load_terminal_window_id()
    if window_exists(existing):
        bring_window_to_front(existing)
        return {
            "success": True,
            "window_id": existing,
            "created": False,
            "reused_existing_window": True
        }

    before_ids = list_matching_window_ids(terminal_markers())
    proc, launch_mode = launch_terminal_window()

    if proc is None:
        return {
            "success": False,
            "error": "No pude lanzar GNOME Terminal",
            "launch_mode": None
        }

    new_window_id = detect_new_window_id(before_ids, terminal_markers())

    if new_window_id:
        bring_window_to_front(new_window_id)
        time.sleep(0.8 if visible else 0.2)
        save_terminal_window_id(new_window_id)
        return {
            "success": True,
            "window_id": new_window_id,
            "created": True,
            "launch_mode": launch_mode
        }

    after_ids = list_matching_window_ids(terminal_markers())
    existing_after = after_ids[-1] if after_ids else None

    if existing_after:
        bring_window_to_front(existing_after)
        save_terminal_window_id(existing_after)
        return {
            "success": True,
            "window_id": existing_after,
            "created": False,
            "reused_existing_window": True,
            "launch_mode": launch_mode
        }

    process_detected = is_process_running()
    if process_detected:
        return {
            "success": False,
            "error": "GNOME Terminal quedó en proceso pero sin window_id detectable",
            "launch_mode": launch_mode,
            "process_only_confirmation": True
        }

    return {
        "success": False,
        "error": "GNOME Terminal no mostró una ventana detectable",
        "launch_mode": launch_mode
    }


def write_in_terminal(command: str, window_id: Optional[str] = None, visible: bool = True, execute: bool = True) -> Dict[str, Any]:
    if not command:
        result = {"success": False, "error": "No command provided"}
        return enrich_error(
            result,
            "terminal.write_command",
            "missing_command",
            target="terminal"
        )

    if not window_id:
        result = {"success": False, "error": "No hay window_id de Terminal disponible"}
        return enrich_error(
            result,
            "terminal.write_command",
            "missing_window_id",
            target="terminal"
        )

    try:
        activated = bring_window_to_front(window_id)
        time.sleep(1.2 if visible else 0.3)

        terminal_active, active_info = is_terminal_window_active()
        if not terminal_active:
            result = {
                "success": False,
                "error": "La ventana activa no es Terminal. No escribo por seguridad.",
                "command": command,
                "window_id": window_id,
                "active_window": active_info
            }
            return enrich_error(
                result,
                "terminal.write_command",
                "terminal_not_active",
                target="terminal",
                window_id=window_id,
                focus_attempted=True,
                focus_confirmed=False
            )

        if visible:
            try:
                subprocess.run(
                    ["xdotool", "key", "ctrl+l"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                time.sleep(0.5)
            except Exception:
                pass

        marker = f'echo ">>> EJECUTANDO: {command}"'
        typing_delay = "120" if visible else "20"

        if visible:
            subprocess.run(
                ["xdotool", "type", "--delay", typing_delay, marker],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            time.sleep(0.6)

            subprocess.run(
                ["xdotool", "key", "Return"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            time.sleep(0.8)

        subprocess.run(
            ["xdotool", "type", "--delay", typing_delay, command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        time.sleep(0.8 if visible else 0.2)

        executed = False
        if execute:
            subprocess.run(
                ["xdotool", "key", "Return"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            executed = True
            time.sleep(2.5 if visible else 0.2)

        result = {
            "success": True,
            "command": command,
            "method": "xdotool_active_window",
            "window_id": window_id,
            "active_window": active_info,
            "visible": visible,
            "executed": executed,
            "activation_ok": activated,
            "output": None,
            "error": "",
            "output_lines": 0
        }

        return enrich_success(
            result,
            "terminal.write_command",
            target="terminal",
            window_id=window_id,
            window_active=terminal_active,
            command_typed=True,
            command_executed=executed,
            output_captured=False,
            focus_attempted=True,
            focus_confirmed=True
        )

    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
            "command": command,
            "window_id": window_id
        }
        return enrich_error(
            result,
            "terminal.write_command",
            "exception",
            target="terminal",
            window_id=window_id,
            error_message=str(e)
        )


emit("event.out", {
    "level": "info",
    "type": "terminal_worker_ready",
    "module": MODULE_ID,
    "capabilities": {
        "xdotool_available": command_exists("xdotool"),
        "wmctrl_available": command_exists("wmctrl"),
        "gnome_terminal_available": command_exists("gnome-terminal"),
        "gtk_launch_available": command_exists("gtk-launch"),
        "gio_available": command_exists("gio"),
        "session_type": os.environ.get("XDG_SESSION_TYPE", "unknown")
    },
    "trace_id": generate_trace_id(),
    "meta": build_top_meta()
})

for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue

    payload: Dict[str, Any] = {}
    merged_meta: Dict[str, Any] = {}
    action_trace_id: Optional[str] = None

    try:
        msg = json.loads(line)
        port = msg.get("port")

        payload = msg.get("payload", {}) or {}
        top_meta = msg.get("meta", {}) or {}
        payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        merged_meta = merge_meta(top_meta, payload_meta)

        task_id = payload.get("task_id") or merged_meta.get("task_id")
        action = payload.get("action") or merged_meta.get("action")
        params = payload.get("params", {}) or {}
        action_trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

        if action and "action" not in merged_meta:
            merged_meta["action"] = action

        if port != "action.in":
            continue

        emit("event.out", {
            "level": "info",
            "text": f"Ejecutando acción: {action}",
            "task_id": task_id,
            "meta": build_top_meta(merged_meta),
            "trace_id": action_trace_id
        })

        if action == "terminal.ensure":
            result = ensure_terminal_window(
                visible=params.get("visible", True)
            )
            status = "success" if result.get("success") else "error"
            result_meta = build_result_meta(merged_meta, result.get("window_id"))
            emit_result(task_id, status, result, result_meta, trace_id=action_trace_id)

        elif action == "terminal.write_command":
            window_id = (
                params.get("window_id")
                or (merged_meta.get("resolved_application") or {}).get("window_id")
                or merged_meta.get("window_id")
            )

            if not window_id:
                ensure_result = ensure_terminal_window(
                    visible=params.get("visible", True)
                )
                if not ensure_result.get("success"):
                    result_meta = build_result_meta(merged_meta, ensure_result.get("window_id"))
                    emit_result(task_id, "error", ensure_result, result_meta, trace_id=action_trace_id)
                    continue
                window_id = ensure_result.get("window_id")
                merged_meta = build_result_meta(merged_meta, window_id)

            result = write_in_terminal(
                params.get("command", ""),
                window_id,
                params.get("visible", True),
                params.get("execute", True)
            )

            status = "success" if result.get("success") else "error"
            result_meta = build_result_meta(merged_meta, window_id)
            emit_result(task_id, status, result, result_meta, trace_id=action_trace_id)

        else:
            emit_result(task_id, "error", {
                "success": False,
                "error": f"Acción no soportada: {action}"
            }, merged_meta, trace_id=action_trace_id)

    except json.JSONDecodeError as e:
        emit("event.out", {
            "level": "error",
            "text": f"JSON inválido en {MODULE_ID}: {str(e)}",
            "error_type": type(e).__name__,
            "trace_id": action_trace_id or generate_trace_id(),
            "meta": build_top_meta(merged_meta)
        })

    except Exception as e:
        emit_result(
            payload.get("task_id") or merged_meta.get("task_id"),
            "error",
            {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "action": payload.get("action", "unknown")
            },
            merged_meta,
            trace_id=action_trace_id
        )

        emit("event.out", {
            "level": "error",
            "text": f"Error en worker.python.terminal: {str(e)}",
            "task_id": payload.get("task_id") or merged_meta.get("task_id"),
            "error_type": type(e).__name__,
            "trace_id": action_trace_id or generate_trace_id(),
            "meta": build_top_meta(merged_meta)
        })