#!/usr/bin/env python3
"""
Active Diagnostic & Safe Runtime Probe
- Analiza código fuente
- Detecta duplicados aproximados
- Identifica funciones stub/vacías
- Benchmark liviano de funciones reales
- Prueba módulos de forma segura según manifest
"""

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from lib.logger import StructuredLogger
except ImportError:
    class StructuredLogger:
        def __init__(self, name):
            self.name = name

        def info(self, msg):
            print(f"INFO [{self.name}]: {msg}", file=sys.stderr)

        def error(self, msg):
            print(f"ERROR [{self.name}]: {msg}", file=sys.stderr)

        def warn(self, msg):
            print(f"WARN [{self.name}]: {msg}", file=sys.stderr)

        def debug(self, msg):
            pass


logger = StructuredLogger("active.diagnostic")


class CodeAnalyzer:
    """Analiza código fuente para detectar problemas."""

    def __init__(self, root_path: Path):
        self.root = Path(root_path)
        self.duplicates: List[Dict[str, Any]] = []
        self.stub_functions: List[Dict[str, Any]] = []
        self.unused_imports: List[Dict[str, Any]] = []
        self.syntax_errors: List[Dict[str, Any]] = []

    def analyze_all(self) -> Dict[str, Any]:
        logger.info("Analizando código fuente...")

        js_files = list(self.root.rglob("*.js"))
        py_files = list(self.root.rglob("*.py"))

        self._find_duplicates(js_files, py_files)
        self._find_stub_functions(js_files, py_files)
        self._analyze_imports(py_files)
        self._check_syntax(py_files, js_files)

        return {
            "files_analyzed": len(js_files) + len(py_files),
            "js_files": len(js_files),
            "py_files": len(py_files),
            "duplicates": self.duplicates,
            "stub_functions": self.stub_functions,
            "unused_imports": self.unused_imports,
            "syntax_errors": self.syntax_errors,
            "summary": {
                "duplicate_blocks": len(self.duplicates),
                "stub_functions": len(self.stub_functions),
                "syntax_errors": len(self.syntax_errors),
                "unused_imports": len(self.unused_imports),
            },
        }

    def _find_duplicates(self, js_files: List[Path], py_files: List[Path]) -> None:
        content_hashes: Dict[str, List[Any]] = defaultdict(list)

        for f in js_files + py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for i in range(len(lines) - 4):
                    block = "\n".join(lines[i:i + 5]).strip()
                    if len(block) > 50 and not block.startswith("//") and not block.startswith("#"):
                        h = hashlib.md5(block.encode()).hexdigest()
                        content_hashes[h].append((str(f), i + 1, block[:100]))
            except Exception:
                continue

        for h, locations in content_hashes.items():
            files_involved = sorted(set(loc[0] for loc in locations))
            if len(files_involved) >= 2 and len(locations) >= 2:
                self.duplicates.append(
                    {
                        "hash": h[:8],
                        "occurrences": len(locations),
                        "files": files_involved[:5],
                        "sample": locations[0][2] if locations else "",
                    }
                )

    def _find_stub_functions(self, js_files: List[Path], py_files: List[Path]) -> None:
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        body = node.body
                        if len(body) == 1:
                            if isinstance(body[0], ast.Pass):
                                self.stub_functions.append(
                                    {
                                        "file": str(f),
                                        "function": node.name,
                                        "line": node.lineno,
                                        "type": "empty_pass",
                                        "language": "python",
                                    }
                                )
                            elif (
                                isinstance(body[0], ast.Expr)
                                and isinstance(body[0].value, ast.Constant)
                                and isinstance(body[0].value.value, str)
                                and "todo" in body[0].value.value.lower()
                            ):
                                self.stub_functions.append(
                                    {
                                        "file": str(f),
                                        "function": node.name,
                                        "line": node.lineno,
                                        "type": "todo_stub",
                                        "language": "python",
                                    }
                                )
                        elif len(body) == 2:
                            if (
                                isinstance(body[0], ast.Expr)
                                and isinstance(body[0].value, ast.Constant)
                                and isinstance(body[1], ast.Pass)
                            ):
                                self.stub_functions.append(
                                    {
                                        "file": str(f),
                                        "function": node.name,
                                        "line": node.lineno,
                                        "type": "docstring_only",
                                        "language": "python",
                                    }
                                )
            except SyntaxError as e:
                self.syntax_errors.append(
                    {
                        "file": str(f),
                        "error": str(e),
                        "language": "python",
                        "line": getattr(e, "lineno", None),
                    }
                )
            except Exception:
                continue

        for f in js_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                patterns = [
                    r"function\s+(\w+)\s*\([^)]*\)\s*\{\s*\}",
                    r"(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*\{\s*//\s*TODO",
                    r"const\s+(\w+)\s*=\s*\([^)]*\)\s*=>\s*\{\s*\}",
                ]

                for pattern in patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        self.stub_functions.append(
                            {
                                "file": str(f),
                                "function": match.group(1),
                                "line": content[:match.start()].count("\n") + 1,
                                "type": "empty_or_todo",
                                "language": "javascript",
                            }
                        )
            except Exception:
                continue

    def _analyze_imports(self, py_files: List[Path]) -> None:
        for f in py_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)

                imports: List[str] = []
                used_names = set()

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.asname or alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            imports.append(alias.asname or alias.name)
                    elif isinstance(node, ast.Name):
                        used_names.add(node.id)

                for imp in imports:
                    if imp not in used_names and not imp.startswith("_"):
                        self.unused_imports.append(
                            {
                                "file": str(f),
                                "import": imp,
                                "confidence": "low",
                            }
                        )
            except Exception:
                continue

    def _check_syntax(self, py_files: List[Path], js_files: List[Path]) -> None:
        for f in py_files:
            try:
                ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError as e:
                self.syntax_errors.append(
                    {
                        "file": str(f),
                        "line": e.lineno,
                        "error": str(e),
                        "language": "python",
                    }
                )

        for f in js_files:
            try:
                subprocess.run(
                    ["node", "--check", str(f)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=str(PROJECT_ROOT),
                )
            except Exception:
                # no agrego error duro si node/check falla por entorno
                continue


class ModuleProber:
    """Sonda módulos de forma segura usando manifest real."""

    SAFE_PORT_CANDIDATES = [
        "event.in",
        "command.in",
        "query.in",
        "context.in",
        "request.in",
        "callback.in",
    ]

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.results: Dict[str, Dict[str, Any]] = {}
        self.response_times: Dict[str, List[float]] = defaultdict(list)
        self.broken_modules: List[Dict[str, Any]] = []
        self.unresponsive_modules: List[str] = []

    def _load_manifest(self, module_dir: Path) -> Optional[Dict[str, Any]]:
        manifest_path = module_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _discover_modules(self) -> List[Dict[str, Any]]:
        modules_dir = self.project_root / "modules"
        discovered = []

        if not modules_dir.exists():
            return discovered

        for entry in sorted(modules_dir.iterdir()):
            if not entry.is_dir():
                continue

            manifest = self._load_manifest(entry)
            if not manifest:
                continue

            discovered.append(
                {
                    "dir": entry,
                    "manifest": manifest,
                    "id": manifest.get("id", entry.name),
                    "entry": manifest.get("entry"),
                    "language": manifest.get("language", "javascript"),
                    "inputs": manifest.get("inputs", []),
                }
            )

        return discovered

    def _build_safe_probe_message(self, module_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        inputs = module_info.get("inputs") or []
        acceptable = [p for p in self.SAFE_PORT_CANDIDATES if p in inputs]

        if not acceptable:
            return None

        port = acceptable[0]
        trace_id = f"probe_{int(time.time() * 1000)}"

        payload: Dict[str, Any] = {
            "trace_id": trace_id,
            "meta": {
                "source": "internal",
                "timestamp": datetime.now().isoformat(),
                "test": True,
                "target": module_info["id"],
            }
        }

        if port == "command.in":
            payload.update(
                {
                    "command_id": f"probe_cmd_{int(time.time() * 1000)}",
                    "text": "__probe__",
                    "source": "internal",
                }
            )
        elif port == "query.in":
            payload.update(
                {
                    "query_id": f"probe_query_{int(time.time() * 1000)}",
                    "query": "__probe__",
                }
            )
        elif port == "callback.in":
            payload.update(
                {
                    "chat_id": 0,
                    "data": "__probe__",
                    "action": "probe",
                }
            )
        elif port == "request.in":
            payload.update({"action": "probe"})
        elif port == "context.in":
            payload.update({"type": "probe", "text": "__probe__"})
        elif port == "event.in":
            payload.update({"type": "probe", "level": "debug"})

        return {
            "module": "active.diagnostic",
            "port": port,
            "payload": payload,
            "trace_id": trace_id,
            "meta": {
                "source": "internal",
                "timestamp": datetime.now().isoformat(),
            },
        }

    def probe_module(self, module_info: Dict[str, Any]) -> Dict[str, Any]:
        manifest = module_info["manifest"]
        entry = module_info.get("entry")
        language = module_info.get("language")
        module_id = module_info["id"]
        module_dir = module_info["dir"]

        if not entry:
            return {"status": "invalid_manifest", "error": "entry missing"}

        entry_path = module_dir / entry
        if not entry_path.exists():
            return {"status": "missing_entry", "error": f"Entry no encontrado: {entry}"}

        test_msg = self._build_safe_probe_message(module_info)
        if not test_msg:
            return {
                "status": "skipped",
                "reason": "no_safe_input_port",
            }

        start_time = time.time()

        try:
            if language == "python":
                cmd = [sys.executable, str(entry_path)]
            else:
                cmd = ["node", str(entry_path)]

            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.project_root),
            )

            assert proc.stdin is not None
            proc.stdin.write(json.dumps(test_msg) + "\n")
            proc.stdin.flush()

            try:
                stdout, stderr = proc.communicate(timeout=3)
                elapsed = time.time() - start_time

                responses = []
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        try:
                            responses.append(json.loads(line))
                        except Exception:
                            continue

                return {
                    "status": "responsive" if responses else "no_output",
                    "response_time_ms": round(elapsed * 1000, 2),
                    "responses": len(responses),
                    "has_error": bool(stderr.strip()),
                    "stderr_preview": stderr[:200] if stderr else None,
                    "probe_port": test_msg["port"],
                }
            except subprocess.TimeoutExpired:
                proc.kill()
                return {"status": "timeout", "response_time_ms": 3000}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def probe_all_modules(self) -> Dict[str, Any]:
        discovered = self._discover_modules()
        logger.info(f"Sondeando {len(discovered)} módulos...")

        results: Dict[str, Any] = {}

        for module_info in discovered:
            module_id = module_info["id"]
            logger.info(f"  Probando {module_id}...")
            result = self.probe_module(module_info)
            results[module_id] = result

            if result["status"] in ["timeout", "error", "missing_entry", "invalid_manifest"]:
                self.broken_modules.append(
                    {
                        "module": module_id,
                        "issue": result["status"],
                        "details": result.get("error", result.get("reason", "N/A")),
                    }
                )
            elif result["status"] == "no_output":
                self.unresponsive_modules.append(module_id)

            if result.get("response_time_ms"):
                self.response_times[module_id].append(result["response_time_ms"])

        return {
            "results": results,
            "broken_count": len(self.broken_modules),
            "unresponsive_count": len(self.unresponsive_modules),
            "broken_modules": self.broken_modules,
            "unresponsive_modules": self.unresponsive_modules,
            "avg_response_times": {
                m: sum(times) / len(times)
                for m, times in self.response_times.items()
                if times
            },
        }


class FunctionBenchmark:
    """Benchmark liviano de funciones reales."""

    def benchmark_function(self, func: Callable, *args: Any, iterations: int = 100) -> Dict[str, Any]:
        times: List[float] = []
        errors = 0

        for _ in range(iterations):
            start = time.perf_counter()
            try:
                func(*args)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
            except Exception:
                errors += 1

        if not times:
            return {
                "function": getattr(func, "__name__", "unknown"),
                "status": "failed",
                "error_rate": 1.0,
                "iterations": iterations,
            }

        sorted_times = sorted(times)
        p95_index = min(len(sorted_times) - 1, int(len(sorted_times) * 0.95))

        return {
            "function": getattr(func, "__name__", "unknown"),
            "status": "ok",
            "iterations": iterations,
            "errors": errors,
            "error_rate": errors / iterations,
            "avg_ms": round(sum(times) / len(times) * 1000, 3),
            "min_ms": round(min(times) * 1000, 3),
            "max_ms": round(max(times) * 1000, 3),
            "median_ms": round(sorted_times[len(sorted_times) // 2] * 1000, 3),
            "p95_ms": round(sorted_times[p95_index] * 1000, 3),
        }

    def benchmark_lib_functions(self) -> List[Dict[str, Any]]:
        benchmarks: List[Dict[str, Any]] = []

        try:
            from lib.config import config
            benchmarks.append(self.benchmark_function(config.get, "runtime.debug"))
        except Exception as e:
            benchmarks.append({"function": "config.get", "status": "import_error", "error": str(e)})

        try:
            from lib.logger import StructuredLogger
            logger_instance = StructuredLogger("bench")
            benchmarks.append(self.benchmark_function(logger_instance.debug, "test"))
        except Exception as e:
            benchmarks.append({"function": "StructuredLogger.debug", "status": "import_error", "error": str(e)})

        return benchmarks


class ActiveDiagnostic:
    """Diagnóstico activo completo."""

    def __init__(self, duration_seconds: int = 300):
        self.duration = duration_seconds
        self.running = False
        self.code_analyzer = CodeAnalyzer(PROJECT_ROOT)
        self.module_prober = ModuleProber(PROJECT_ROOT)
        self.function_benchmark = FunctionBenchmark()

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("Señal recibida, finalizando...")
        self.running = False

    def _get_blueprint_modules(self) -> List[str]:
        blueprint_path = PROJECT_ROOT / "blueprints" / "system.v0.json"
        if blueprint_path.exists():
            try:
                with open(blueprint_path, encoding="utf-8") as f:
                    blueprint = json.load(f)
                return blueprint.get("modules", [])
            except Exception:
                return []
        return []

    def _get_all_modules(self) -> List[str]:
        modules_dir = PROJECT_ROOT / "modules"
        modules = []

        if not modules_dir.exists():
            return modules

        for entry in modules_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    modules.append(manifest.get("id", entry.name))
                except Exception:
                    modules.append(entry.name)
            else:
                modules.append(entry.name)

        return sorted(modules)

    def run(self) -> Dict[str, Any]:
        logger.info(f"🔬 DIAGNÓSTICO ACTIVO - {self.duration:.0f} segundos")
        print("\n" + "=" * 80)
        print("🔬 ACTIVE SYSTEM DIAGNOSTIC - SAFE MODE")
        print("=" * 80)

        start_time = time.time()
        self.running = True

        results: Dict[str, Any] = {
            "start_time": datetime.now().isoformat(),
            "duration_configured_seconds": self.duration,
            "phases": {},
        }

        print("\n📋 FASE 1: ANÁLISIS ESTÁTICO DE CÓDIGO")
        print("-" * 40)
        code_analysis = self.code_analyzer.analyze_all()
        results["phases"]["code_analysis"] = code_analysis

        print(f"✅ Archivos analizados: {code_analysis['files_analyzed']}")
        print(f"   JS: {code_analysis['js_files']}, Python: {code_analysis['py_files']}")
        print(f"   Bloques duplicados: {code_analysis['summary']['duplicate_blocks']}")
        print(f"   Funciones stub: {code_analysis['summary']['stub_functions']}")
        print(f"   Errores de sintaxis: {code_analysis['summary']['syntax_errors']}")

        if code_analysis["syntax_errors"]:
            print("\n🚨 ERRORES DE SINTAXIS:")
            for err in code_analysis["syntax_errors"][:5]:
                print(f"   ❌ {err['file']}:{err.get('line', '?')} - {str(err['error'])[:60]}")

        print("\n📋 FASE 2: SONDEO SEGURO DE MÓDULOS")
        print("-" * 40)

        blueprint_modules = set(self._get_blueprint_modules())
        all_modules = set(self._get_all_modules())

        missing_from_disk = sorted(blueprint_modules - all_modules)
        unused_in_blueprint = sorted(all_modules - blueprint_modules)

        print(f"📦 Módulos en blueprint: {len(blueprint_modules)}")
        print(f"📦 Módulos disponibles: {len(all_modules)}")

        if missing_from_disk:
            print("\n❌ Módulos en blueprint pero NO en disco:")
            for m in missing_from_disk[:10]:
                print(f"   • {m}")

        if unused_in_blueprint:
            print("\n⚠️  Módulos en disco pero NO en blueprint:")
            for m in unused_in_blueprint[:10]:
                print(f"   • {m}")

        probe_results = self.module_prober.probe_all_modules()
        results["phases"]["module_probe"] = probe_results

        total_probed = len(probe_results["results"])
        responsive = total_probed - probe_results["broken_count"] - probe_results["unresponsive_count"]

        print(f"\n🔍 Sondeo completado sobre {total_probed} módulos")
        print(f"   ✅ Responsive/usable: {responsive}")
        print(f"   ❌ Rotos: {probe_results['broken_count']}")
        print(f"   ⚠️  No responden: {probe_results['unresponsive_count']}")

        if probe_results["broken_modules"]:
            print("\n🚨 MÓDULOS ROTOS:")
            for bm in probe_results["broken_modules"][:10]:
                print(f"   ❌ {bm['module']}: {bm['issue']} - {str(bm['details'])[:60]}")

        print("\n📋 FASE 3: BENCHMARK DE FUNCIONES")
        print("-" * 40)
        func_benchmarks = self.function_benchmark.benchmark_lib_functions()
        results["phases"]["function_benchmark"] = func_benchmarks

        for bench in func_benchmarks:
            if bench["status"] == "ok":
                print(f"   ✅ {bench['function']}: {bench['avg_ms']}ms avg")
            else:
                print(f"   ❌ {bench['function']}: {bench['status']} - {bench.get('error', 'N/A')}")

        print("\n📋 FASE 4: MONITOREO")
        print("-" * 40)

        last_report = time.time()
        report_interval = min(60, max(10, self.duration // 5))

        while self.running and (time.time() - start_time) < self.duration:
            elapsed = time.time() - start_time
            if time.time() - last_report >= report_interval:
                print(f"\n⏱️  Tiempo transcurrido: {timedelta(seconds=int(elapsed))}")
                last_report = time.time()
            time.sleep(1)

        total_elapsed = time.time() - start_time

        print("\n" + "=" * 80)
        print("🏁 REPORTE FINAL")
        print("=" * 80)

        results["end_time"] = datetime.now().isoformat()
        results["total_elapsed_seconds"] = round(total_elapsed, 1)

        score = 100
        score -= code_analysis["summary"]["syntax_errors"] * 10
        score -= code_analysis["summary"]["stub_functions"] * 2
        score -= len(probe_results["broken_modules"]) * 15
        score -= len(probe_results["unresponsive_modules"]) * 5
        score -= len(missing_from_disk) * 20
        score = max(0, min(100, score))

        results["overall_score"] = score
        results["grade"] = "A" if score > 80 else "B" if score > 60 else "C" if score > 40 else "D"

        print(f"\n🏆 SCORE GENERAL: {score}/100 (Grade: {results['grade']})")
        print("\n📊 RESUMEN:")
        print(f"   • Errores de sintaxis: {code_analysis['summary']['syntax_errors']}")
        print(f"   • Funciones stub: {code_analysis['summary']['stub_functions']}")
        print(f"   • Código duplicado: {code_analysis['summary']['duplicate_blocks']} bloques")
        print(f"   • Módulos rotos: {len(probe_results['broken_modules'])}")
        print(f"   • Módulos no responden: {len(probe_results['unresponsive_modules'])}")
        print(f"   • Módulos en blueprint sin disco: {len(missing_from_disk)}")

        report_path = PROJECT_ROOT / "logs" / f"active_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print(f"\n💾 Reporte guardado: {report_path}")
        print("=" * 80 + "\n")

        return results


def main():
    parser = argparse.ArgumentParser(description="Active Diagnostic - Safe Mode")
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Duración en segundos",
    )
    args = parser.parse_args()

    diagnostic = ActiveDiagnostic(duration_seconds=args.duration)

    try:
        results = diagnostic.run()
        sys.exit(0 if results["grade"] in ["A", "B"] else 1)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
