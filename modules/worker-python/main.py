import sys
import os
import json
import subprocess
import platform
import shutil
import shlex
import re
import time
import random
from pathlib import Path
from configparser import ConfigParser
from difflib import get_close_matches
from datetime import datetime
from typing import Any, Dict, Optional, List

# Add project root for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Execution Verifier for enriched results
from lib.execution_verifier import enrich_success, enrich_error

MODULE_ID = "worker.python.desktop"
APP_CACHE_PATH = PROJECT_ROOT / "logs" / "desktop-apps.json"
COMMAND_TERMINAL_STATE_PATH = PROJECT_ROOT / "logs" / "command-terminal.json"

_command_terminal_window_id = None

APP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
]

MANUAL_FALLBACKS = {
    "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "google chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "firefox": ["firefox"],
    "vscode": ["code", "code-insiders"],
    "vs code": ["code", "code-insiders"],
    "visual studio code": ["code", "code-insiders"],
    "navegador": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "firefox"],
    "writer": ["libreoffice", "lowriter"],
    "libreoffice writer": ["libreoffice", "lowriter"],
    "office writer": ["libreoffice", "lowriter"],
}


def generate_trace_id() -> str:
    return f"wpy_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def build_top_meta(meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    incoming = dict(meta or {})
    incoming.pop("module", None)

    return {
        **incoming,
        "source": incoming.get("source", "internal"),
        "timestamp": safe_iso_now(),
        "module": MODULE_ID
    }


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


def clean_exec(exec_value: str) -> Optional[str]:
    if not exec_value:
        return None
    try:
        parts = shlex.split(exec_value)
    except Exception:
        parts = exec_value.split()

    cleaned = []
    for part in parts:
        if part.startswith("%"):
            continue
        cleaned.append(part)

    if not cleaned:
        return None

    return cleaned[0]


def safe_read_desktop_file(path: Path) -> Optional[Dict[str, Any]]:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    if "[Desktop Entry]" not in content:
        return None

    try:
        parser.read_string(content)
    except Exception:
        return None

    if not parser.has_section("Desktop Entry"):
        return None

    section = parser["Desktop Entry"]

    if section.get("Type", "").strip() != "Application":
        return None

    if section.get("NoDisplay", "").strip().lower() == "true":
        return None

    name = section.get("Name", "").strip()
    generic_name = section.get("GenericName", "").strip()
    exec_value = clean_exec(section.get("Exec", "").strip())
    keywords = section.get("Keywords", "").strip()

    if not name or not exec_value:
        return None

    return {
        "name": name,
        "generic_name": generic_name,
        "exec": exec_value,
        "keywords": [k.strip() for k in keywords.split(";") if k.strip()],
        "source": str(path)
    }


def build_app_registry():
    registry = {}
    canonical = {}

    for app_dir in APP_DIRS:
        if not app_dir.exists():
            continue

        for file in app_dir.glob("*.desktop"):
            app = safe_read_desktop_file(file)
            if not app:
                continue

            exec_cmd = app["exec"]
            if not shutil.which(exec_cmd):
                continue

            entry = {
                "display_name": app["name"],
                "generic_name": app["generic_name"],
                "command": exec_cmd,
                "source": app["source"],
                "keywords": app["keywords"],
            }

            keys = set()
            keys.add(normalize_text(app["name"]))
            if app["generic_name"]:
                keys.add(normalize_text(app["generic_name"]))
            for kw in app["keywords"]:
                keys.add(normalize_text(kw))
            keys.add(normalize_text(exec_cmd))

            for key in keys:
                if key:
                    registry[key] = entry

            canonical[normalize_text(app["name"])] = entry

    return registry, canonical


def app_cache_id(label: str, command: str) -> str:
    left = normalize_text(label).replace(" ", "-")
    right = normalize_text(command).replace(" ", "-")
    return f"{left}__{right}"


def list_installed_applications() -> List[Dict[str, Any]]:
    apps = []
    seen = set()

    for entry in APP_CANONICAL.values():
        label = (entry.get("display_name") or "").strip()
        command = (entry.get("command") or "").strip()
        if not label or not command:
            continue

        key = (label.lower(), command.lower())
        if key in seen:
            continue
        seen.add(key)

        apps.append({
            "id": app_cache_id(label, command),
            "label": label,
            "command": command,
            "source": entry.get("source", ""),
            "generic_name": entry.get("generic_name", ""),
            "keywords": entry.get("keywords", [])
        })

    apps.sort(key=lambda item: item["label"].lower())
    return apps


def save_app_registry_cache() -> None:
    try:
        APP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        apps = list_installed_applications()
        APP_CACHE_PATH.write_text(
            json.dumps(apps, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


APP_REGISTRY, APP_CANONICAL = build_app_registry()
save_app_registry_cache()


def refresh_app_registry() -> None:
    global APP_REGISTRY, APP_CANONICAL
    APP_REGISTRY, APP_CANONICAL = build_app_registry()
    save_app_registry_cache()


def resolve_app_command(app_name: str) -> Optional[Dict[str, Any]]:
    normalized = normalize_text(app_name)

    if normalized in APP_REGISTRY:
        return APP_REGISTRY[normalized]

    candidates = list(APP_CANONICAL.keys())
    close = get_close_matches(normalized, candidates, n=1, cutoff=0.72)
    if close:
        return APP_CANONICAL[close[0]]

    for cmd in MANUAL_FALLBACKS.get(normalized, []):
        if shutil.which(cmd):
            return {
                "display_name": app_name,
                "generic_name": "",
                "command": cmd,
                "source": "manual_fallback",
                "keywords": []
            }

    if shutil.which(normalized):
        return {
            "display_name": app_name,
            "generic_name": "",
            "command": normalized,
            "source": "direct_which",
            "keywords": []
        }

    return None


def detached_popen(command):
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "env": os.environ.copy(),
    }
    system = platform.system().lower()
    if system == "linux":
        kwargs["start_new_session"] = True
    elif system == "windows":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        kwargs["shell"] = True
    return subprocess.Popen(command, **kwargs)


def process_aliases_for(command_name: str, app_name: str = ""):
    values = {
        normalize_text(command_name),
        normalize_text(app_name),
    }

    browser_aliases = {
        "chromium",
        "chromium-browser",
        "chrome",
        "google-chrome",
        "google-chrome-stable",
    }

    if values & browser_aliases:
        values |= browser_aliases

    vscode_aliases = {
        "code",
        "code-insiders",
        "visual studio code",
        "vs code",
        "vscode",
    }

    if values & vscode_aliases:
        values |= vscode_aliases

    firefox_aliases = {"firefox"}
    if values & firefox_aliases:
        values |= firefox_aliases

    terminal_aliases = {
        "gnome-terminal",
        "gnome-terminal-server",
        "terminal",
    }

    if values & {"gnome-terminal", "terminal"}:
        values |= terminal_aliases

    calculator_aliases = {
        "gnome-calculator",
        "calculator",
    }

    if values & {"gnome-calculator", "calculator", "calculadora"}:
        values |= calculator_aliases

    writer_aliases = {
        "libreoffice",
        "lowriter",
        "writer",
        "libreoffice writer",
    }

    if values & writer_aliases:
        values |= writer_aliases

    return {v for v in values if v}


def is_process_running(command_name: str, app_name: str = "") -> bool:
    aliases = process_aliases_for(command_name, app_name)
    if not aliases:
        return False

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
            if (
                raw == alias or
                raw.startswith(alias) or
                f" {alias} " in f" {raw} " or
                alias in raw
            ):
                return True

    return False


def command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def list_windows():
    if not command_exists("wmctrl"):
        return []

    try:
        out = subprocess.check_output(
            ["wmctrl", "-lx"],
            text=True,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return []

    return [line for line in out.splitlines() if line.strip()]


def normalize_lines(lines):
    return [normalize_text(x) for x in lines if x and x.strip()]


def window_snapshot():
    return normalize_lines(list_windows())


def count_matching_windows(markers) -> int:
    markers = [normalize_text(m) for m in markers if m]
    if not markers:
        return 0

    count = 0
    for line in window_snapshot():
        for marker in markers:
            if marker in line:
                count += 1
                break
    return count


def list_matching_window_ids(markers):
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


def detect_new_window_id(before_ids, markers, checks: int = 20, delay: float = 0.25):
    before_set = set(before_ids or [])

    for _ in range(checks):
        time.sleep(delay)
        current_ids = list_matching_window_ids(markers)

        for wid in current_ids:
            if wid not in before_set:
                return wid

    return None


def app_window_markers(command_name: str, app_name: str = "", resolved_name: str = ""):
    values = {
        normalize_text(command_name),
        normalize_text(app_name),
        normalize_text(resolved_name),
    }

    markers = set()

    if "gnome-terminal" in values or "terminal" in values:
        markers |= {
            "gnome-terminal",
            "gnome-terminal-server",
            "org.gnome.terminal",
            "terminal"
        }

    if "gnome-calculator" in values or "calculator" in values or "calculadora" in values:
        markers |= {
            "gnome-calculator",
            "org.gnome.calculator",
            "calculator",
            "calculadora"
        }

    if "gnome-calendar" in values or "calendar" in values or "calendario" in values:
        markers |= {
            "gnome-calendar",
            "org.gnome.calendar",
            "calendar",
            "calendario"
        }

    if (
        "writer" in values or
        "libreoffice" in values or
        "lowriter" in values or
        "libreoffice writer" in values
    ):
        markers |= {
            "writer",
            "lowriter",
            "libreoffice",
            "libreoffice-writer"
        }

    if not markers:
        markers |= {v for v in values if v}

    return [m for m in markers if m]


def window_exists(window_id) -> bool:
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


def list_terminal_window_ids():
    try:
        out = subprocess.check_output(
            ["xdotool", "search", "--class", "gnome-terminal"],
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()
        if not out:
            return []
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []


def load_command_terminal_window_id():
    global _command_terminal_window_id
    if _command_terminal_window_id and window_exists(_command_terminal_window_id):
        return _command_terminal_window_id

    try:
        if COMMAND_TERMINAL_STATE_PATH.exists():
            data = json.loads(COMMAND_TERMINAL_STATE_PATH.read_text(encoding="utf-8"))
            wid = (data or {}).get("window_id")
            if window_exists(wid):
                _command_terminal_window_id = wid
                return wid
    except Exception:
        pass

    return None


def save_command_terminal_window_id(window_id) -> None:
    global _command_terminal_window_id
    _command_terminal_window_id = window_id

    try:
        COMMAND_TERMINAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMMAND_TERMINAL_STATE_PATH.write_text(
            json.dumps({"window_id": window_id, "updated_at": time.time()}),
            encoding="utf-8"
        )
    except Exception:
        pass


def get_or_create_command_terminal_window(visible: bool = True):
    existing = load_command_terminal_window_id()
    if window_exists(existing):
        return existing

    if not command_exists("xdotool"):
        return None

    terminal_markers = app_window_markers("gnome-terminal", "terminal", "terminal")
    before_terminal_ids = list_matching_window_ids(terminal_markers)

    proc, _launch_mode = launch_terminal_window()
    if proc is None:
        return None

    new_window_id = detect_new_window_id(before_terminal_ids, terminal_markers)
    if new_window_id:
        try:
            subprocess.run(
                ["xdotool", "windowraise", new_window_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", new_window_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except Exception:
            pass

        time.sleep(0.8 if visible else 0.2)
        save_command_terminal_window_id(new_window_id)
        return new_window_id

    return None


def get_preferred_terminal_window(meta=None):
    meta = meta or {}

    preferred = (
        meta.get("window_id")
        or (meta.get("resolved_application") or {}).get("window_id")
        or (meta.get("active_app") or {}).get("window_id")
    )

    if window_exists(preferred):
        return preferred

    cmd_wid = load_command_terminal_window_id()
    if window_exists(cmd_wid):
        return cmd_wid

    terminal_ids = list_terminal_window_ids()
    if terminal_ids:
        return terminal_ids[-1]

    return None


def bring_window_to_front(app_name: str) -> bool:
    if not command_exists("wmctrl"):
        return False

    candidates = [
        app_name,
        "Terminal",
        "terminal",
        "gnome-terminal",
        "org.gnome.Terminal",
        "LibreOffice Writer",
        "Writer",
        "writer",
        "LibreOffice",
        "libreoffice",
    ]

    for candidate in candidates:
        try:
            result = subprocess.run(
                ["wmctrl", "-a", candidate],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue

    return False


def is_terminal_window_active():
    info = get_active_window_info()
    if not info.get("ok"):
        return False, info

    haystack = normalize_text(
        f"{info.get('name', '')} {info.get('wm_class', '')}"
    )

    terminal_markers = [
        "gnome-terminal",
        "org.gnome.terminal",
        "terminal"
    ]

    for marker in terminal_markers:
        if marker in haystack:
            return True, info

    return False, info


def get_active_window_info() -> Dict[str, Any]:
    if not command_exists("xdotool"):
        return {
            "ok": False,
            "error": "xdotool no disponible"
        }

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
        return {
            "ok": False,
            "error": str(e)
        }


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


def find_writer_window():
    markers = app_window_markers("libreoffice", "writer", "LibreOffice Writer")
    ids = list_matching_window_ids(markers)
    if ids:
        return ids[-1]
    return None


def open_writer(command: str = "libreoffice --writer"):
    markers = app_window_markers("libreoffice", "writer", "LibreOffice Writer")
    before_ids = list_matching_window_ids(markers)

    try:
        detached_popen(shlex.split(command))
    except Exception as e:
        result = {
            "success": False,
            "opened": False,
            "error": f"no se pudo abrir writer: {e}"
        }
        return enrich_error(
            result,
            "office.open_writer",
            "launch_failed",
            target="writer",
            process_detected=False,
            window_detected=False
        )

    new_window_id = detect_new_window_id(before_ids, markers, checks=24, delay=0.35)
    process_detected = is_process_running("libreoffice", "writer")

    if new_window_id:
        try:
            subprocess.run(
                ["xdotool", "windowraise", str(new_window_id)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", str(new_window_id)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except Exception:
            pass

        result = {
            "success": True,
            "opened": True,
            "window_id": new_window_id,
            "application": "writer",
            "command": command
        }
        return enrich_success(
            result,
            "office.open_writer",
            target="writer",
            process_detected=process_detected,
            window_detected=True,
            window_id=new_window_id,
            target_matched=True,
            focus_confirmed=True,
            focus_attempted=True
        )

    existing_window_id = find_writer_window()
    if existing_window_id:
        bring_window_to_front("LibreOffice Writer")
        result = {
            "success": True,
            "opened": True,
            "window_id": existing_window_id,
            "application": "writer",
            "command": command,
            "reused_existing_window": True
        }
        return enrich_success(
            result,
            "office.open_writer",
            target="writer",
            process_detected=process_detected,
            window_detected=True,
            window_id=existing_window_id,
            target_matched=True,
            focus_confirmed=True,
            focus_attempted=True
        )

    result = {
        "success": False,
        "opened": False,
        "error": "Writer no mostró una ventana detectable",
        "application": "writer",
        "command": command
    }
    return enrich_error(
        result,
        "office.open_writer",
        "window_not_detected",
        target="writer",
        process_detected=process_detected,
        window_detected=False,
        focus_attempted=True
    )


def write_text_in_writer(text: str, window_id: Optional[str] = None):
    if not text:
        result = {
            "success": False,
            "wrote": False,
            "error": "text vacío"
        }
        return enrich_error(
            result,
            "office.write_text",
            "empty_text",
            target="writer"
        )

    def _resolve_writer_window(preferred: Optional[str] = None) -> Optional[str]:
        if preferred and window_exists(preferred):
            return preferred

        found = find_writer_window()
        if found and window_exists(found):
            return found

        return None

    wid = _resolve_writer_window(window_id)

    if not wid:
        result = {
            "success": False,
            "wrote": False,
            "error": "no hay ventana de Writer disponible"
        }
        return enrich_error(
            result,
            "office.write_text",
            "writer_window_not_found",
            target="writer",
            window_detected=False
        )

    focus_ok = False
    last_focus_error = None

    try:
        subprocess.run(
            ["xdotool", "windowraise", str(wid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(wid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        focus_ok = True
    except Exception as e:
        last_focus_error = str(e)

    if not focus_ok:
        wid2 = _resolve_writer_window(None)
        if wid2:
            wid = wid2
            try:
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", str(wid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                focus_ok = True
            except Exception as e:
                last_focus_error = str(e)

    if not focus_ok:
        try:
            subprocess.run(
                ["wmctrl", "-a", "LibreOffice Writer"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            time.sleep(0.4)
            wid3 = _resolve_writer_window(None)
            if wid3:
                wid = wid3
                focus_ok = True
        except Exception as e:
            last_focus_error = str(e)

    if not focus_ok:
        result = {
            "success": False,
            "wrote": False,
            "window_id": wid,
            "error": f"no se pudo enfocar Writer: {last_focus_error or 'focus_failed'}"
        }
        return enrich_error(
            result,
            "office.write_text",
            "writer_focus_failed",
            target="writer",
            window_detected=bool(wid),
            window_id=wid,
            error_message=last_focus_error or "focus_failed"
        )

    try:
        time.sleep(0.6)

        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "1", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        result = {
            "success": True,
            "wrote": True,
            "window_id": wid,
            "chars": len(text)
        }
        return enrich_success(
            result,
            "office.write_text",
            target="writer",
            window_detected=True,
            window_id=wid,
            focus_confirmed=True,
            focus_attempted=True
        )
    except Exception as e:
        result = {
            "success": False,
            "wrote": False,
            "window_id": wid,
            "error": f"no se pudo escribir en Writer: {e}"
        }
        return enrich_error(
            result,
            "office.write_text",
            "writer_type_failed",
            target="writer",
            window_detected=True,
            window_id=wid,
            error_message=str(e)
        )


def write_in_terminal(command: str, window_id=None, visible: bool = True, execute: bool = True):
    if not command:
        result = {
            "success": False,
            "error": "No command provided"
        }
        return enrich_error(
            result,
            "terminal.write_command",
            "missing_command",
            target="terminal"
        )

    if not window_id:
        result = {
            "success": False,
            "error": "No hay window_id de Terminal disponible"
        }
        return enrich_error(
            result,
            "terminal.write_command",
            "missing_window_id",
            target="terminal"
        )

    try:
        subprocess.run(
            ["xdotool", "windowraise", str(window_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        subprocess.run(
            ["xdotool", "windowactivate", "--sync", str(window_id)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        time.sleep(1.0 if visible else 0.2)

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
                window_id=window_id
            )

        if visible:
            subprocess.run(
                ["xdotool", "key", "--window", str(window_id), "ctrl+l"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            time.sleep(0.4)

            marker = f'echo ">>> EJECUTANDO: {command}"'
            subprocess.run(
                ["xdotool", "type", "--window", str(window_id), "--delay", "90", marker],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            time.sleep(0.8)
            subprocess.run(
                ["xdotool", "key", "--window", str(window_id), "Return"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            time.sleep(0.8)

        typing_delay = "90" if visible else "10"
        executed = False

        if execute:
            subprocess.run(
                ["xdotool", "type", "--window", str(window_id), "--delay", typing_delay, command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )

            time.sleep(1.0 if visible else 0.1)

            subprocess.run(
                ["xdotool", "key", "--window", str(window_id), "Return"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            executed = True

            time.sleep(1.5 if visible else 0.1)

        result = {
            "success": True,
            "command": command,
            "method": "xdotool",
            "window_id": window_id,
            "active_window": active_info,
            "visible": visible,
            "executed": executed,
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
            output_captured=False
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


def open_application(name, resolved_app=None, meta=None):
    try:
        meta = meta or {}

        incoming_name = name
        normalized_name = None
        resolved_from_name = None

        if isinstance(incoming_name, dict):
            resolved_from_name = incoming_name
            normalized_name = (
                incoming_name.get("label")
                or incoming_name.get("name")
                or incoming_name.get("command")
                or ""
            )
        else:
            normalized_name = str(incoming_name or "").strip()

        effective_resolved = (
            resolved_app
            or meta.get("target_application")
            or meta.get("resolved_application")
            or resolved_from_name
        )

        if not normalized_name and isinstance(effective_resolved, dict):
            normalized_name = (
                effective_resolved.get("label")
                or effective_resolved.get("name")
                or effective_resolved.get("command")
                or ""
            )

        if not normalized_name:
            result = {
                "opened": False,
                "error": "Nombre de aplicación vacío o inválido",
                "application": incoming_name
            }
            return enrich_error(
                result,
                "open_application",
                "invalid_application_name",
                target=None,
                process_detected=False,
                window_detected=False
            )

        if isinstance(effective_resolved, dict) and effective_resolved.get("command"):
            app = {
                "display_name": effective_resolved.get("label") or normalized_name,
                "generic_name": "",
                "command": effective_resolved.get("command"),
                "source": effective_resolved.get("source") or "planner_resolved",
                "keywords": []
            }
        else:
            refresh_app_registry()
            app = resolve_app_command(normalized_name)

        if not app:
            result = {
                "opened": False,
                "error": f"No encontré una aplicación compatible para '{normalized_name}'",
                "application": normalized_name
            }
            return enrich_error(
                result,
                "open_application",
                "application_not_found",
                target=normalized_name,
                process_detected=False,
                window_detected=False
            )

        command_name = app["command"]
        normalized_lookup = normalize_text(normalized_name)

        if command_name == "gnome-terminal" or normalized_lookup in {"terminal", "gnome-terminal"}:
            terminal_markers = app_window_markers(command_name, normalized_name, app["display_name"])
            before_terminal_ids = list_matching_window_ids(terminal_markers)

            proc, launch_mode = launch_terminal_window()

            if proc is None:
                result = {
                    "opened": False,
                    "error": "No pude lanzar GNOME Terminal",
                    "application": normalized_name,
                    "resolved_name": app["display_name"],
                    "command": app["command"],
                    "source": app["source"]
                }
                return enrich_error(
                    result,
                    "open_application",
                    "launch_failed",
                    target=normalized_name,
                    process_detected=False,
                    window_detected=False,
                    launch_mode=launch_mode
                )

            new_window_id = detect_new_window_id(before_terminal_ids, terminal_markers)

            if new_window_id:
                try:
                    subprocess.run(
                        ["xdotool", "windowraise", str(new_window_id)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True
                    )
                except Exception:
                    pass

                try:
                    subprocess.run(
                        ["xdotool", "windowactivate", "--sync", str(new_window_id)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True
                    )
                except Exception:
                    pass

                save_command_terminal_window_id(new_window_id)

                result = {
                    "opened": True,
                    "application": normalized_name,
                    "resolved_name": app["display_name"],
                    "command": app["command"],
                    "source": app["source"],
                    "launch_mode": launch_mode,
                    "window_id": new_window_id
                }
                return enrich_success(
                    result,
                    "open_application",
                    target=app["display_name"],
                    process_detected=is_process_running(command_name, normalized_name),
                    window_detected=True,
                    window_id=new_window_id,
                    target_matched=True,
                    focus_confirmed=True,
                    focus_attempted=True
                )

            after_terminal_ids = list_matching_window_ids(terminal_markers)
            existing_terminal_id = after_terminal_ids[-1] if after_terminal_ids else None
            process_detected = is_process_running(command_name, normalized_name)

            if existing_terminal_id:
                try:
                    subprocess.run(
                        ["xdotool", "windowraise", str(existing_terminal_id)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True
                    )
                except Exception:
                    pass

                try:
                    subprocess.run(
                        ["xdotool", "windowactivate", "--sync", str(existing_terminal_id)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True
                    )
                except Exception:
                    pass

                save_command_terminal_window_id(existing_terminal_id)

                result = {
                    "opened": True,
                    "application": normalized_name,
                    "resolved_name": app["display_name"],
                    "command": app["command"],
                    "source": app["source"],
                    "launch_mode": launch_mode,
                    "window_id": existing_terminal_id,
                    "reused_existing_window": True
                }
                return enrich_success(
                    result,
                    "open_application",
                    target=app["display_name"],
                    process_detected=process_detected,
                    window_detected=True,
                    window_id=existing_terminal_id,
                    target_matched=True,
                    focus_confirmed=True,
                    focus_attempted=True
                )

            if process_detected:
                result = {
                    "opened": True,
                    "application": normalized_name,
                    "resolved_name": app["display_name"],
                    "command": app["command"],
                    "source": app["source"],
                    "launch_mode": launch_mode,
                    "window_id": None,
                    "process_only_confirmation": True
                }
                return enrich_success(
                    result,
                    "open_application",
                    target=app["display_name"],
                    process_detected=True,
                    window_detected=False,
                    window_id=None,
                    target_matched=True,
                    focus_confirmed=False,
                    focus_attempted=True
                )

            result = {
                "opened": False,
                "error": "GNOME Terminal no mostró una ventana detectable",
                "application": normalized_name,
                "resolved_name": app["display_name"],
                "command": app["command"],
                "source": app["source"],
                "launch_mode": launch_mode
            }
            return enrich_error(
                result,
                "open_application",
                "window_not_detected",
                target=normalized_name,
                process_detected=False,
                window_detected=False,
                launch_mode=launch_mode,
                focus_attempted=True
            )

        window_markers = app_window_markers(command_name, normalized_name, app["display_name"])
        before_windows = count_matching_windows(window_markers)
        before_ids = list_matching_window_ids(window_markers)

        detached_popen([command_name])

        checks = 16
        for _ in range(checks):
            time.sleep(0.25)

            process_detected = is_process_running(command_name, normalized_name)
            after_windows = count_matching_windows(window_markers)
            window_detected = after_windows > before_windows
            new_window_id = detect_new_window_id(before_ids, window_markers, checks=1, delay=0.0)

            if window_detected or new_window_id:
                bring_window_to_front(app["display_name"])
                result = {
                    "opened": True,
                    "application": normalized_name,
                    "resolved_name": app["display_name"],
                    "command": app["command"],
                    "source": app["source"],
                    "window_id": new_window_id
                }
                return enrich_success(
                    result,
                    "open_application",
                    target=app["display_name"],
                    process_detected=process_detected,
                    window_detected=True,
                    window_id=new_window_id,
                    target_matched=True,
                    focus_confirmed=True,
                    focus_attempted=True
                )

        result = {
            "opened": False,
            "error": f"La aplicación '{normalized_name}' no mostró una ventana nueva visible",
            "application": normalized_name,
            "resolved_name": app["display_name"],
            "command": app["command"],
            "source": app["source"]
        }
        process_detected = is_process_running(command_name, normalized_name)
        return enrich_error(
            result,
            "open_application",
            "timeout_no_window",
            target=normalized_name,
            process_detected=process_detected,
            window_detected=False,
            focus_attempted=True
        )

    except Exception as e:
        result = {
            "opened": False,
            "error": str(e),
            "application": name
        }
        return enrich_error(
            result,
            "open_application",
            "exception",
            target=name if isinstance(name, str) else None,
            error_message=str(e)
        )


for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue

    payload: Dict[str, Any] = {}
    merged_meta: Dict[str, Any] = {}
    trace_id: Optional[str] = None

    try:
        msg = json.loads(line)
        port = msg.get("port")

        payload = msg.get("payload", {}) or {}
        top_meta = msg.get("meta", {}) if isinstance(msg.get("meta", {}), dict) else {}
        payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        merged_meta = merge_meta(top_meta, payload_meta)

        task_id = payload.get("task_id") or merged_meta.get("task_id")
        action = payload.get("action") or merged_meta.get("action")
        params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}
        trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

        if action and "action" not in merged_meta:
            merged_meta["action"] = action

        if port != "action.in":
            continue

        emit("event.out", {
            "level": "info",
            "text": f"Ejecutando acción: {action}",
            "task_id": task_id,
            "meta": build_top_meta(merged_meta),
            "trace_id": trace_id
        })

        if action == "open_application":
            resolved_app = (
                params.get("resolved_app")
                or merged_meta.get("target_application")
                or merged_meta.get("resolved_application")
            )

            raw_name = params.get("name", "")
            if not raw_name and isinstance(resolved_app, dict):
                raw_name = resolved_app

            result = open_application(
                raw_name,
                resolved_app,
                merged_meta
            )

            status = "success" if result.get("opened") else "error"
            emit_result(task_id, status, result, merged_meta, trace_id)

        elif action == "office.open_writer":
            result = open_writer(params.get("command", "libreoffice --writer"))
            status = "success" if result.get("success") else "error"
            emit_result(task_id, status, result, merged_meta, trace_id)

        elif action == "office.write_text":
            result = write_text_in_writer(
                params.get("text", ""),
                params.get("window_id")
            )
            status = "success" if result.get("success") else "error"
            emit_result(task_id, status, result, merged_meta, trace_id)

        elif action == "terminal.write_command":
            resolved_app = merged_meta.get("resolved_application", {}) or {}
            window_id = (
                params.get("window_id")
                or resolved_app.get("window_id")
                or merged_meta.get("window_id")
            )

            if not window_id:
                window_id = get_or_create_command_terminal_window(
                    visible=params.get("visible", True)
                )

            result = write_in_terminal(
                params.get("command", ""),
                window_id,
                params.get("visible", True),
                params.get("execute", True)
            )

            status = "success" if result.get("success") else "error"
            emit_result(task_id, status, result, merged_meta, trace_id)

        elif action == "echo_text":
            result = {"echo": params.get("text", "")}
            emit_result(task_id, "success", result, merged_meta, trace_id)

        else:
            emit_result(task_id, "error", {
                "success": False,
                "error": f"Acción no soportada: {action}"
            }, merged_meta, trace_id)

    except json.JSONDecodeError as e:
        emit("event.out", {
            "level": "error",
            "text": f"JSON inválido en {MODULE_ID}: {str(e)}",
            "error_type": type(e).__name__,
            "trace_id": trace_id or generate_trace_id(),
            "meta": build_top_meta(merged_meta)
        })

    except Exception as e:
        error_msg = str(e)
        helpful_hint = ""

        if "xdotool" in error_msg.lower():
            helpful_hint = " Sugerencia: Instala xdotool con 'sudo apt install xdotool'"
        elif "wmctrl" in error_msg.lower():
            helpful_hint = " Sugerencia: Instala wmctrl con 'sudo apt install wmctrl'"
        elif "no such file" in error_msg.lower() or "not found" in error_msg.lower():
            helpful_hint = " Sugerencia: Verifica que la aplicación esté instalada"
        elif "permission denied" in error_msg.lower():
            helpful_hint = " Sugerencia: Verifica los permisos del archivo o ejecutable"
        elif "window" in error_msg.lower() and "not found" in error_msg.lower():
            helpful_hint = " Sugerencia: La ventana puede haberse cerrado. Intenta reabrir la aplicación"

        full_error = f"{error_msg}\n{helpful_hint}" if helpful_hint else error_msg

        emit_result(
            payload.get("task_id") or merged_meta.get("task_id"),
            "error",
            {
                "success": False,
                "error": full_error,
                "error_type": type(e).__name__,
                "action": payload.get("action", "unknown")
            },
            merged_meta,
            trace_id or generate_trace_id()
        )

        emit("event.out", {
            "level": "error",
            "text": f"Error en worker-python.desktop: {error_msg}",
            "task_id": payload.get("task_id") or merged_meta.get("task_id"),
            "error_type": type(e).__name__,
            "trace_id": trace_id or generate_trace_id(),
            "meta": build_top_meta(merged_meta)
        })