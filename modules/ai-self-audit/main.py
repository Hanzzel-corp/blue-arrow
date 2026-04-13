"""
AI Self-Audit Module - Análisis automático y mejora continua del proyecto
Sistema de auto-análisis que revisa el código, arquitectura y sugiere mejoras.
"""

import json
import sys
import os
import ast
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

MODULE_ID = "ai.self.audit.main"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def generate_trace_id() -> str:
    return f"aisa_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


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


class CodeAnalyzer:
    """Analizador de código estático."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.issues: List[Dict] = []
        self.metrics: Dict[str, Any] = {}
        self._reset_metrics()

    def _reset_metrics(self):
        self.metrics = {
            "total_files": 0,
            "total_lines": 0,
            "python_files": 0,
            "js_files": 0,
            "issues_found": 0
        }

    def analyze_python_file(self, filepath: str) -> Dict:
        """Analiza un archivo Python."""
        issues = []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

                self.metrics["total_lines"] += len(lines)
                self.metrics["python_files"] += 1

                try:
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not ast.get_docstring(node):
                                issues.append({
                                    "type": "missing_docstring",
                                    "line": node.lineno,
                                    "message": f"Función '{node.name}' sin docstring",
                                    "filepath": filepath
                                })

                except SyntaxError as e:
                    issues.append({
                        "type": "syntax_error",
                        "line": e.lineno or 0,
                        "message": str(e),
                        "filepath": filepath
                    })

                for i, line in enumerate(lines, 1):
                    if len(line) > 100:
                        issues.append({
                            "type": "long_line",
                            "line": i,
                            "message": f"Línea muy larga ({len(line)} caracteres)",
                            "filepath": filepath
                        })

                    if "TODO" in line and not any(x in line for x in ["# TODO:", "TODO("]):
                        issues.append({
                            "type": "todo_format",
                            "line": i,
                            "message": "TODO sin formato estándar",
                            "filepath": filepath
                        })

        except Exception as e:
            issues.append({
                "type": "file_error",
                "line": 0,
                "message": str(e),
                "filepath": filepath
            })

        return {
            "filepath": filepath,
            "issues": issues,
            "issue_count": len(issues)
        }

    def analyze_js_file(self, filepath: str) -> Dict:
        """Analiza un archivo JavaScript básico."""
        issues = []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

                self.metrics["total_lines"] += len(lines)
                self.metrics["js_files"] += 1

                for i, line in enumerate(lines, 1):
                    if len(line) > 100:
                        issues.append({
                            "type": "long_line",
                            "line": i,
                            "message": f"Línea muy larga ({len(line)} caracteres)",
                            "filepath": filepath
                        })

                    if "console.log(" in line and "//" not in line:
                        issues.append({
                            "type": "console_log",
                            "line": i,
                            "message": "console.log encontrado (posible debug olvidado)",
                            "filepath": filepath
                        })

        except Exception as e:
            issues.append({
                "type": "file_error",
                "line": 0,
                "message": str(e),
                "filepath": filepath
            })

        return {
            "filepath": filepath,
            "issues": issues,
            "issue_count": len(issues)
        }

    def analyze_project(self) -> Dict:
        """Analiza todo el proyecto."""
        self._reset_metrics()
        all_issues = []

        py_files = list(Path(self.project_root).rglob("*.py"))
        for py_file in py_files:
            if "__pycache__" not in str(py_file) and ".venv" not in str(py_file):
                self.metrics["total_files"] += 1
                result = self.analyze_python_file(str(py_file))
                all_issues.extend(result["issues"])

        js_files = list(Path(self.project_root).rglob("*.js"))
        for js_file in js_files:
            if "node_modules" not in str(js_file):
                self.metrics["total_files"] += 1
                result = self.analyze_js_file(str(js_file))
                all_issues.extend(result["issues"])

        self.metrics["issues_found"] = len(all_issues)

        return {
            "success": True,
            "metrics": dict(self.metrics),
            "issues": all_issues[:50],
            "issue_count": len(all_issues),
            "timestamp": safe_iso_now()
        }


class ProjectArchitect:
    """Analiza la arquitectura del proyecto."""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def check_blueprint_consistency(self) -> Dict:
        """Verifica consistencia del blueprint."""
        blueprint_path = os.path.join(self.project_root, "blueprints", "system.v0.json")

        if not os.path.exists(blueprint_path):
            return {"success": False, "error": "Blueprint no encontrado"}

        try:
            with open(blueprint_path, "r", encoding="utf-8") as f:
                blueprint = json.load(f)

            declared_modules = set(blueprint.get("modules", []))

            modules_path = os.path.join(self.project_root, "modules")
            existing_modules = set()

            if os.path.exists(modules_path):
                for module_dir in os.listdir(modules_path):
                    manifest_path = os.path.join(modules_path, module_dir, "manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as mf:
                                manifest = json.load(mf)
                                existing_modules.add(manifest.get("id", module_dir))
                        except Exception:
                            pass

            missing_in_blueprint = existing_modules - declared_modules
            missing_in_modules = declared_modules - existing_modules

            return {
                "success": True,
                "declared_modules": len(declared_modules),
                "existing_modules": len(existing_modules),
                "missing_in_blueprint": sorted(list(missing_in_blueprint)),
                "missing_in_modules": sorted(list(missing_in_modules)),
                "consistent": len(missing_in_blueprint) == 0 and len(missing_in_modules) == 0
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def analyze_dependencies(self) -> Dict:
        """Analiza dependencias entre módulos."""
        dependencies = {}

        modules_path = os.path.join(self.project_root, "modules")
        if not os.path.exists(modules_path):
            return {"success": False, "error": "No modules directory"}

        for module_dir in os.listdir(modules_path):
            module_path = os.path.join(modules_path, module_dir)
            if os.path.isdir(module_path):
                main_files = [f for f in os.listdir(module_path) if f.startswith("main.")]
                if main_files:
                    deps = []
                    for main_file in main_files:
                        filepath = os.path.join(module_path, main_file)
                        try:
                            with open(filepath, "r", encoding="utf-8") as f:
                                content = f.read()
                                if "emit(" in content:
                                    deps.append("runtime_bus")
                        except Exception:
                            pass
                    dependencies[module_dir] = deps

        return {
            "success": True,
            "module_count": len(dependencies),
            "dependencies": dependencies
        }


class SelfAuditor:
    """Sistema principal de auto-auditoría."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.code_analyzer = CodeAnalyzer(project_root)
        self.architect = ProjectArchitect(project_root)
        self.audit_history: List[Dict] = []
        self._load_history()

    def _history_path(self) -> str:
        return os.path.join(self.project_root, "logs", "self-audit-history.json")

    def _load_history(self):
        try:
            path = self._history_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.audit_history = data.get("history", [])
        except Exception as e:
            logger.error(f"Error cargando historial de auditoría: {e}")
            self.audit_history = []

    def run_full_audit(self) -> Dict:
        """Ejecuta auditoría completa del proyecto."""
        logger.info("Iniciando auditoría completa...")

        code_analysis = self.code_analyzer.analyze_project()
        blueprint_check = self.architect.check_blueprint_consistency()
        deps_analysis = self.architect.analyze_dependencies()
        suggestions = self._generate_suggestions(code_analysis, blueprint_check, deps_analysis)

        audit_result = {
            "success": True,
            "timestamp": safe_iso_now(),
            "code_analysis": code_analysis,
            "architecture": {
                "blueprint": blueprint_check,
                "dependencies": deps_analysis
            },
            "suggestions": suggestions,
            "summary": {
                "total_issues": code_analysis.get("issue_count", 0),
                "critical_issues": len([
                    i for i in code_analysis.get("issues", [])
                    if i.get("type") == "syntax_error"
                ]),
                "architecture_consistent": blueprint_check.get("consistent", False)
            }
        }

        self.audit_history.append(audit_result)
        self._save_history()

        return audit_result

    def _generate_suggestions(self, code: Dict, blueprint: Dict, deps: Dict) -> List[str]:
        """Genera sugerencias basadas en el análisis."""
        suggestions = []

        if code.get("issue_count", 0) > 0:
            missing_docs = len([
                i for i in code.get("issues", [])
                if i.get("type") == "missing_docstring"
            ])
            if missing_docs > 0:
                suggestions.append(f"Agregar docstrings a {missing_docs} funciones sin documentar")

            long_lines = len([
                i for i in code.get("issues", [])
                if i.get("type") == "long_line"
            ])
            if long_lines > 0:
                suggestions.append(f"Reformatear {long_lines} líneas que exceden 100 caracteres")

        if blueprint.get("success") and not blueprint.get("consistent", True):
            if blueprint.get("missing_in_blueprint"):
                suggestions.append(
                    f"Actualizar blueprint: agregar {len(blueprint['missing_in_blueprint'])} módulos faltantes"
                )

            if blueprint.get("missing_in_modules"):
                suggestions.append(
                    f"Corregir blueprint: remover o crear {len(blueprint['missing_in_modules'])} módulos declarados sin implementación"
                )

        if deps.get("success") and deps.get("module_count", 0) > 20:
            suggestions.append("El proyecto tiene alta modularidad; conviene reforzar tracing y contratos entre módulos")

        if not suggestions:
            suggestions.append("No se detectaron mejoras críticas inmediatas")

        return suggestions

    def quick_audit(self) -> Dict:
        """Auditoría rápida."""
        blueprint_check = self.architect.check_blueprint_consistency()

        return {
            "success": True,
            "timestamp": safe_iso_now(),
            "summary": {
                "architecture_consistent": blueprint_check.get("consistent", False),
                "declared_modules": blueprint_check.get("declared_modules", 0),
                "existing_modules": blueprint_check.get("existing_modules", 0)
            },
            "details": blueprint_check
        }

    def code_only_audit(self) -> Dict:
        """Auditoría solo de código."""
        return self.code_analyzer.analyze_project()

    def architecture_only_audit(self) -> Dict:
        """Auditoría solo de arquitectura."""
        return {
            "success": True,
            "timestamp": safe_iso_now(),
            "blueprint": self.architect.check_blueprint_consistency(),
            "dependencies": self.architect.analyze_dependencies()
        }

    def health_audit(self) -> Dict:
        """Chequeo resumido de salud."""
        full = self.run_full_audit()
        issue_count = full.get("summary", {}).get("total_issues", 0)
        critical = full.get("summary", {}).get("critical_issues", 0)
        consistent = full.get("summary", {}).get("architecture_consistent", False)

        health_score = 100
        health_score -= min(issue_count, 40)
        health_score -= critical * 10
        if not consistent:
            health_score -= 20
        health_score = max(0, health_score)

        return {
            "success": True,
            "timestamp": safe_iso_now(),
            "health_score": health_score,
            "status": "healthy" if health_score >= 80 else "warning" if health_score >= 50 else "critical",
            "summary": full.get("summary", {}),
            "suggestions": full.get("suggestions", [])[:5]
        }

    def _save_history(self):
        """Guarda historial de auditoría."""
        try:
            path = self._history_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "history": self.audit_history[-20:],
                    "updated_at": safe_iso_now()
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando historial de auditoría: {e}")


auditor = SelfAuditor(PROJECT_ROOT)


def extract_task_id(payload: Dict, meta: Dict) -> str:
    return (
        payload.get("task_id")
        or payload.get("plan_id")
        or meta.get("task_id")
        or meta.get("plan_id")
        or f"audit_{int(datetime.now().timestamp())}"
    )


def handle_action(payload: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    action = payload.get("action")
    meta = meta or {}
    task_id = extract_task_id(payload, meta)

    try:
        if action == "audit.run":
            result = auditor.run_full_audit()
            emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

        elif action == "audit.quick":
            result = auditor.quick_audit()
            emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

        elif action == "audit.code":
            result = auditor.code_only_audit()
            emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

        elif action == "audit.architecture":
            result = auditor.architecture_only_audit()
            emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

        elif action == "audit.health":
            result = auditor.health_audit()
            emit_guaranteed_result(task_id, "success", result, meta, trace_id=trace_id)

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
    task_id = extract_task_id(payload, meta)

    try:
        emit_guaranteed_result(task_id, "success", {
            "success": True,
            "history_count": len(auditor.audit_history),
            "last_audit": auditor.audit_history[-1] if auditor.audit_history else None
        }, meta, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Error procesando query: {e}")
        emit_guaranteed_result(task_id, "error", {
            "success": False,
            "error": str(e)
        }, meta, trace_id=trace_id)


def main():
    logger.info(f"AI Self-Audit Module iniciado - {MODULE_ID}")

    emit("event.out", {
        "level": "info",
        "type": "ai_self_audit_ready",
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
                "type": "ai_self_audit_invalid_json",
                "error": str(e),
                "trace_id": generate_trace_id()
            })
        except Exception as e:
            logger.error(f"Error leyendo mensaje: {e}")
            emit("event.out", {
                "level": "error",
                "type": "ai_self_audit_error",
                "error": str(e),
                "trace_id": generate_trace_id()
            })


if __name__ == "__main__":
    main()
