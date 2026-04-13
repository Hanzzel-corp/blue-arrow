import sys
import json
import os
import time
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

MODULE_ID = "worker.python.browser"
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
NAVIGATION_TIMEOUT_MS = 30000


def generate_trace_id() -> str:
    return f"wbr_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


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


def ensure_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://{raw}"


class BrowserWorker:
    def __init__(self) -> None:
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.current_trace_id: Optional[str] = None
        self.current_meta: Dict[str, Any] = {}

    def set_execution_context(self, trace_id: Optional[str], meta: Optional[Dict[str, Any]]) -> None:
        self.current_trace_id = trace_id or generate_trace_id()
        self.current_meta = dict(meta or {})

    def emit_event(self, level: str, event_type: str, text: str, **kwargs: Any) -> None:
        emit("event.out", {
            "level": level,
            "type": event_type,
            "text": text,
            "trace_id": self.current_trace_id or generate_trace_id(),
            "meta": build_top_meta(self.current_meta),
            **kwargs
        })

    def reset_page(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                self.page.close()
        except Exception:
            pass
        self.page = None

        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        self.context = None

    def find_browser_executable(self) -> Optional[str]:
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/usr/local/bin/google-chrome"
        ]

        for browser_path in chrome_paths:
            if os.path.exists(browser_path):
                return browser_path
        return None

    def ensure_page(self) -> None:
        if self.pw is None:
            self.pw = sync_playwright().start()

        if self.browser is None or not self.browser.is_connected():
            executable_path = self.find_browser_executable()

            try:
                if executable_path:
                    self.emit_event(
                        "info",
                        "browser_runtime_selected",
                        f"Usando Chrome del sistema: {executable_path}",
                        executable_path=executable_path
                    )
                    self.browser = self.pw.chromium.launch(
                        headless=False,
                        executable_path=executable_path,
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
                else:
                    self.emit_event(
                        "warn",
                        "browser_runtime_fallback",
                        "No se encontró Chrome en rutas estándar, intentando canal 'chrome'"
                    )
                    self.browser = self.pw.chromium.launch(
                        headless=False,
                        channel="chrome",
                        args=["--no-sandbox", "--disable-dev-shm-usage"]
                    )
            except Exception as exc:
                self.emit_event(
                    "error",
                    "browser_launch_error",
                    f"Error lanzando navegador: {str(exc)}",
                    error=str(exc)
                )
                raise

        if self.context is None:
            self.context = self.browser.new_context(viewport=DEFAULT_VIEWPORT)

        if self.page is None or self.page.is_closed():
            self.page = self.context.new_page()

    def with_page_retry(self, fn, retryable: bool = True):
        self.ensure_page()

        try:
            return fn()
        except Exception as exc:
            if not retryable:
                raise

            self.emit_event(
                "warn",
                "browser_retry_after_failure",
                "Fallo de página/contexto, reiniciando sesión browser y reintentando una vez",
                error=str(exc)
            )

            self.reset_page()
            self.ensure_page()
            return fn()

    def close(self) -> None:
        self.reset_page()

        try:
            if self.browser and self.browser.is_connected():
                self.browser.close()
        except Exception:
            pass
        self.browser = None

        try:
            if self.pw:
                self.pw.stop()
        except Exception:
            pass
        self.pw = None

    def open_url(self, url: str) -> Dict[str, Any]:
        normalized_url = ensure_url(url)
        if not isinstance(normalized_url, str) or not normalized_url.strip():
            return {"error": "Parámetro url inválido o vacío"}

        def run():
            self.page.goto(normalized_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            return {
                "opened": True,
                "url": self.page.url,
                "title": self.page.title()
            }

        return self.with_page_retry(run, retryable=True)

    def search_google(self, query: str) -> Dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return {"error": "Parámetro query inválido o vacío"}

        def run():
            self.page.goto(
                "https://www.google.com",
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT_MS
            )

            search_box = self.page.locator('textarea[name="q"], input[name="q"]').first
            search_box.fill(query)
            search_box.press("Enter")
            self.page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

            results: List[Dict[str, str]] = []

            candidates = self.page.locator("a[href]").all()
            for link in candidates[:30]:
                try:
                    href = link.get_attribute("href")
                    text = (link.inner_text() or "").strip()

                    if not href or not text:
                        continue

                    if href.startswith("/search") or href.startswith("#"):
                        continue

                    if len(text) < 8:
                        continue

                    results.append({
                        "text": text[:120],
                        "href": href
                    })

                    if len(results) >= 5:
                        break
                except Exception:
                    continue

            return {
                "searched": True,
                "query": query,
                "url": self.page.url,
                "title": self.page.title(),
                "results": results
            }

        return self.with_page_retry(run, retryable=True)

    def fill_form(self, url: str, fields: List[Dict[str, Any]], submit_selector: Optional[str] = None) -> Dict[str, Any]:
        normalized_url = ensure_url(url)
        if not isinstance(normalized_url, str) or not normalized_url.strip():
            return {"error": "Parámetro url inválido o vacío"}

        if not isinstance(fields, list):
            return {"error": "Parámetro fields inválido; se esperaba una lista"}

        def run():
            self.page.goto(normalized_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)

            filled = []
            for field in fields:
                if not isinstance(field, dict):
                    continue

                selector = field.get("selector")
                value = field.get("value", "")

                if not selector or not isinstance(selector, str):
                    continue

                locator = self.page.locator(selector).first
                locator.fill("" if value is None else str(value))

                filled.append({
                    "selector": selector,
                    "value": value
                })

            if submit_selector:
                self.page.locator(submit_selector).first.click()

            return {
                "filled": True,
                "url": self.page.url,
                "title": self.page.title(),
                "fields": filled,
                "submitted": bool(submit_selector)
            }

        return self.with_page_retry(run, retryable=False)

    def click_element(self, url: str, selector: str) -> Dict[str, Any]:
        normalized_url = ensure_url(url)
        if not isinstance(normalized_url, str) or not normalized_url.strip():
            return {"error": "Parámetro url inválido o vacío"}

        if not isinstance(selector, str) or not selector.strip():
            return {"error": "Parámetro selector inválido o vacío"}

        def run():
            self.page.goto(normalized_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
            self.page.locator(selector).first.click()

            return {
                "clicked": True,
                "url": self.page.url,
                "title": self.page.title(),
                "selector": selector
            }

        return self.with_page_retry(run, retryable=False)


worker = BrowserWorker()

try:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            emit("event.out", {
                "level": "error",
                "type": "browser_worker_parse_error",
                "text": f"JSON inválido en stdin: {str(exc)}",
                "error": str(exc),
                "trace_id": generate_trace_id(),
                "meta": build_top_meta()
            })
            continue

        port = msg.get("port")
        payload = msg.get("payload", {}) or {}
        top_meta = msg.get("meta", {}) if isinstance(msg.get("meta", {}), dict) else {}
        payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
        merged_meta = merge_meta(top_meta, payload_meta)
        incoming_trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

        if port != "action.in":
            continue

        action = payload.get("action") or merged_meta.get("action")
        params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}
        task_id = payload.get("task_id") or merged_meta.get("task_id")

        worker.set_execution_context(incoming_trace_id, merged_meta)

        emit("event.out", {
            "level": "info",
            "type": "browser_action_received",
            "text": f"Ejecutando acción browser: {action}",
            "task_id": task_id,
            "action": action,
            "meta": build_top_meta(merged_meta),
            "trace_id": incoming_trace_id
        })

        try:
            if action == "open_url":
                result = worker.open_url(params.get("url", ""))
            elif action == "search_google":
                result = worker.search_google(params.get("query", ""))
            elif action == "fill_form":
                result = worker.fill_form(
                    params.get("url", ""),
                    params.get("fields", []),
                    params.get("submit_selector")
                )
            elif action == "click_web":
                result = worker.click_element(
                    params.get("url", ""),
                    params.get("selector", "")
                )
            else:
                result = {
                    "error": f"Acción browser no soportada: {action}"
                }

            status = "success" if "error" not in result else "error"

        except PlaywrightTimeoutError as exc:
            result = {"error": f"Timeout en browser: {str(exc)}"}
            status = "error"

        except Exception as exc:
            result = {"error": str(exc)}
            status = "error"

        emit("result.out", {
            "task_id": task_id,
            "action": action,
            "status": status,
            "result": result,
            "meta": build_top_meta(merged_meta),
            "trace_id": incoming_trace_id
        })

finally:
    worker.close()