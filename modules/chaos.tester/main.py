#!/usr/bin/env python3
"""
Chaos Tester Module - Módulo de Blueprint
Ejecuta acciones reales, testea módulos, detecta problemas activamente
"""

import json
import sys
import os
import time
import subprocess
import ast
import hashlib
import re
import threading
import signal
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Set
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Config
TEST_DURATION = int(os.environ.get("CHAOS_DURATION", 3000))  # 50 min default
REPORT_INTERVAL = int(os.environ.get("CHAOS_INTERVAL", 300))

# Estado
tester_state = {
    "active": False,
    "start_time": None,
    "tests_run": 0,
    "tests_passed": 0,
    "tests_failed": 0,
    "broken_modules": [],
    "duplicates_found": [],
    "stub_functions": [],
    "syntax_errors": [],
    "response_times": defaultdict(list),
    "last_report": 0
}

def generate_trace_id():
    import random
    return f"chaos_{int(time.time()*1000)}_{random.randint(1000,9999)}"

def emit(port, payload):
    msg = {
        "module": "chaos.tester",
        "port": port,
        "payload": payload,
        "trace_id": generate_trace_id(),
        "meta": {"source": "chaos_tester", "timestamp": time.time()}
    }
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def emit_event(level, text, extra=None):
    payload = {
        "level": level,
        "type": "chaos_report",
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
    if extra:
        payload.update(extra)
    emit("event.out", payload)
    
    # También a stderr
    print(f"[{level.upper()}] {text}", file=sys.stderr)

def emit_command(target_module, action, data):
    """Envía comando real a un módulo"""
    emit("command.out", {
        "target": target_module,
        "action": action,
        "data": data,
        "test_id": f"test_{tester_state['tests_run']}"
    })

class CodeAnalyzer:
    """Analiza código fuente"""
    
    def __init__(self):
        self.root = PROJECT_ROOT
        
    def analyze(self) -> Dict:
        """Análisis completo"""
        js_files = list(Path(self.root).rglob("modules/**/*.js"))
        py_files = list(Path(self.root).rglob("modules/**/*.py"))
        
        return {
            "duplicates": self._find_duplicates(js_files + py_files),
            "stub_functions": self._find_stubs(js_files, py_files),
            "syntax_errors": self._check_syntax(py_files, js_files),
            "files_analyzed": len(js_files) + len(py_files)
        }
    
    def _find_duplicates(self, files: List[Path]) -> List[Dict]:
        """Busca código duplicado"""
        hashes = defaultdict(list)
        
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    lines = content.split('\n')
                    
                    for i in range(len(lines) - 4):
                        block = '\n'.join(lines[i:i+5]).strip()
                        if len(block) > 50:
                            h = hashlib.md5(block.encode()).hexdigest()
                            hashes[h].append((str(f), i+1))
            except:
                continue
        
        duplicates = []
        for h, locs in hashes.items():
            files_involved = set(l[0] for l in locs)
            if len(files_involved) >= 2:
                duplicates.append({
                    "hash": h[:8],
                    "files": list(files_involved)[:3],
                    "occurrences": len(locs)
                })
        
        return duplicates
    
    def _find_stubs(self, js_files: List[Path], py_files: List[Path]) -> List[Dict]:
        """Busca funciones stub/vacías"""
        stubs = []
        
        for f in py_files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    tree = ast.parse(content)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                                stubs.append({
                                    "file": str(f).replace(PROJECT_ROOT, ""),
                                    "function": node.name,
                                    "line": node.lineno,
                                    "type": "empty_pass"
                                })
            except:
                continue
        
        # JS básico
        for f in js_files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    # Funciones vacías
                    matches = re.finditer(r'function\s+(\w+)\s*\([^)]*\)\s*\{\s*\}', content)
                    for match in matches:
                        stubs.append({
                            "file": str(f).replace(PROJECT_ROOT, ""),
                            "function": match.group(1),
                            "line": content[:match.start()].count('\n') + 1,
                            "type": "empty_js"
                        })
            except:
                continue
        
        return stubs
    
    def _check_syntax(self, py_files: List[Path], js_files: List[Path]) -> List[Dict]:
        """Verifica sintaxis"""
        errors = []
        
        for f in py_files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    ast.parse(file.read())
            except SyntaxError as e:
                errors.append({
                    "file": str(f).replace(PROJECT_ROOT, ""),
                    "line": e.lineno,
                    "error": str(e)[:100]
                })
        
        return errors

class ModuleTester:
    """Testea módulos activamente"""
    
    def __init__(self):
        self.test_results = []
        
    def test_module_ping(self, module_id: str) -> Dict:
        """Envía ping a módulo y espera respuesta"""
        
        module_dir = os.path.join(PROJECT_ROOT, "modules", module_id.replace(".", "-"))
        manifest_path = os.path.join(module_dir, "manifest.json")
        
        if not os.path.exists(manifest_path):
            return {"status": "missing", "error": "No manifest"}
        
        with open(manifest_path) as f:
            manifest = json.load(f)
        
        entry = manifest.get("entry", "main.js")
        language = manifest.get("language", "javascript")
        
        start = time.time()
        
        try:
            # Preparar mensaje de test
            test_msg = {
                "module": "test.harness",
                "port": "command.out",
                "payload": {"type": "ping", "test": True},
                "trace_id": generate_trace_id(),
                "meta": {"test": True, "timestamp": time.time()}
            }
            
            if language == "python":
                cmd = [sys.executable, os.path.join(module_dir, entry)]
            else:
                cmd = ["node", os.path.join(module_dir, entry)]
            
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_ROOT
            )
            
            proc.stdin.write(json.dumps(test_msg) + '\n')
            proc.stdin.flush()
            
            try:
                stdout, stderr = proc.communicate(timeout=3)
                elapsed = (time.time() - start) * 1000
                
                has_output = bool(stdout.strip())
                has_error = bool(stderr.strip())
                
                return {
                    "status": "ok" if has_output else "no_response",
                    "response_time_ms": round(elapsed, 2),
                    "has_output": has_output,
                    "has_stderr": has_error,
                    "stderr_preview": stderr[:100] if has_error else None
                }
                
            except subprocess.TimeoutExpired:
                proc.kill()
                return {"status": "timeout", "response_time_ms": 3000}
                
        except Exception as e:
            return {"status": "error", "error": str(e)[:100]}
    
    def test_all_modules(self) -> Dict:
        """Testea todos los módulos"""
        
        modules_dir = os.path.join(PROJECT_ROOT, "modules")
        modules = []
        
        for entry in os.listdir(modules_dir):
            if os.path.isdir(os.path.join(modules_dir, entry)):
                modules.append(entry.replace("-", "."))
        
        results = {}
        broken = []
        
        for module_id in modules[:15]:  # Limitar a 15 para no sobrecargar
            emit_event("info", f"Testing {module_id}...")
            
            result = self.test_module_ping(module_id)
            results[module_id] = result
            
            if result["status"] in ["timeout", "error", "missing"]:
                broken.append({
                    "module": module_id,
                    "issue": result["status"]
                })
            
            tester_state["tests_run"] += 1
            if result["status"] == "ok":
                tester_state["tests_passed"] += 1
            else:
                tester_state["tests_failed"] += 1
            
            # Guardar tiempo de respuesta
            if "response_time_ms" in result:
                tester_state["response_times"][module_id].append(result["response_time_ms"])
        
        return {
            "results": results,
            "broken_modules": broken,
            "total_tested": len(modules[:15])
        }

class ActionExecutor:
    """Ejecuta acciones reales en el sistema"""
    
    def __init__(self):
        self.actions_executed = []
        
    def execute_action(self, action_type: str, params: Dict) -> Dict:
        """Ejecuta una acción real"""
        
        result = {"action": action_type, "status": "unknown"}
        
        if action_type == "ping_router":
            # Enviar ping al router
            emit_command("router.main", "ping", {"timestamp": time.time()})
            result["status"] = "sent"
            
        elif action_type == "check_health":
            # Verificar health de runtime
            emit_command("runtime.main", "health_check", {})
            result["status"] = "sent"
            
        elif action_type == "test_event_emit":
            # Emitir evento de test
            emit_event("info", "Test event from chaos tester", {"test": True})
            result["status"] = "emitted"
            
        elif action_type == "memory_stress":
            # Crear carga de memoria (simulada)
            data = ["x" * 1000 for _ in range(1000)]  # ~1MB
            result["status"] = "executed"
            result["data_size"] = len(data)
            del data
            
        elif action_type == "disk_check":
            # Verificar espacio en disco
            stat = os.statvfs(PROJECT_ROOT)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            result["status"] = "ok"
            result["free_gb"] = round(free_gb, 2)
            
        tester_state["tests_run"] += 1
        if result["status"] in ["sent", "emitted", "executed", "ok"]:
            tester_state["tests_passed"] += 1
        else:
            tester_state["tests_failed"] += 1
        
        return result
    
    def run_chaos_suite(self) -> List[Dict]:
        """Ejecuta suite de acciones de caos"""
        
        actions = [
            ("ping_router", {}),
            ("test_event_emit", {}),
            ("disk_check", {}),
            ("memory_stress", {}),
            ("check_health", {})
        ]
        
        results = []
        for action_type, params in actions:
            emit_event("info", f"Executing chaos action: {action_type}")
            result = self.execute_action(action_type, params)
            results.append(result)
            time.sleep(0.5)  # Pequeña pausa entre acciones
        
        return results

def generate_report(is_final=False) -> Dict:
    """Genera reporte de estado"""
    
    elapsed = 0
    if tester_state["start_time"]:
        elapsed = time.time() - tester_state["start_time"]
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "is_final": is_final,
        "elapsed_seconds": round(elapsed, 1),
        "tests": {
            "run": tester_state["tests_run"],
            "passed": tester_state["tests_passed"],
            "failed": tester_state["tests_failed"],
            "success_rate": round(tester_state["tests_passed"] / max(tester_state["tests_run"], 1) * 100, 1)
        },
        "broken_modules": tester_state["broken_modules"],
        "duplicates_found": len(tester_state["duplicates_found"]),
        "stub_functions": len(tester_state["stub_functions"]),
        "syntax_errors": len(tester_state["syntax_errors"]),
        "avg_response_times": {
            m: round(sum(times)/len(times), 2)
            for m, times in tester_state["response_times"].items()
            if times
        }
    }
    
    # Calcular score
    score = 100
    score -= len(tester_state["broken_modules"]) * 10
    score -= len(tester_state["syntax_errors"]) * 15
    score -= len(tester_state["stub_functions"]) * 2
    score -= report["tests"]["failed"] * 5
    
    report["score"] = max(0, score)
    report["grade"] = "A" if score > 80 else "B" if score > 60 else "C" if score > 40 else "D"
    
    return report

def print_report(report: Dict):
    """Imprime reporte formateado"""
    
    print("\n" + "="*70, file=sys.stderr)
    if report["is_final"]:
        print("🏁 REPORTE FINAL - CHAOS TESTER", file=sys.stderr)
    else:
        print("📊 REPORTE INTERMEDIO", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    print(f"\n⏱️  Tiempo: {timedelta(seconds=int(report['elapsed_seconds']))}", file=sys.stderr)
    
    print(f"\n🧪 TESTS:", file=sys.stderr)
    print(f"   Ejecutados: {report['tests']['run']}", file=sys.stderr)
    print(f"   Exitosos: {report['tests']['passed']} ✅", file=sys.stderr)
    print(f"   Fallidos: {report['tests']['failed']} ❌", file=sys.stderr)
    print(f"   Tasa éxito: {report['tests']['success_rate']}%", file=sys.stderr)
    
    print(f"\n🔍 PROBLEMAS ENCONTRADOS:", file=sys.stderr)
    print(f"   Módulos rotos: {len(report['broken_modules'])}", file=sys.stderr)
    print(f"   Errores de sintaxis: {report['syntax_errors']}", file=sys.stderr)
    print(f"   Funciones stub: {report['stub_functions']}", file=sys.stderr)
    print(f"   Código duplicado: {report['duplicates_found']}", file=sys.stderr)
    
    print(f"\n🏆 SCORE: {report['score']}/100 (Grade: {report['grade']})", file=sys.stderr)
    
    if report['broken_modules']:
        print(f"\n🚨 MÓDULOS ROTOS:", file=sys.stderr)
        for bm in report['broken_modules'][:5]:
            print(f"   ❌ {bm.get('module', 'unknown')}: {bm.get('issue', 'N/A')}", file=sys.stderr)
    
    print("="*70 + "\n", file=sys.stderr)

def main_loop():
    """Loop principal"""
    
    emit_event("info", f"🔥 CHAOS TESTER iniciado - {TEST_DURATION/60:.0f}min de testing activo")
    
    tester_state["active"] = True
    tester_state["start_time"] = time.time()
    
    # FASE 1: Análisis estático
    emit_event("info", "📋 FASE 1: Análisis estático de código...")
    analyzer = CodeAnalyzer()
    analysis = analyzer.analyze()
    
    tester_state["duplicates_found"] = analysis["duplicates"]
    tester_state["stub_functions"] = analysis["stub_functions"]
    tester_state["syntax_errors"] = analysis["syntax_errors"]
    
    emit_event("info", f"   Archivos analizados: {analysis['files_analyzed']}")
    emit_event("info", f"   Duplicados: {len(analysis['duplicates'])}")
    emit_event("info", f"   Stubs: {len(analysis['stub_functions'])}")
    emit_event("info", f"   Errores sintaxis: {len(analysis['syntax_errors'])}")
    
    if analysis['syntax_errors']:
        for err in analysis['syntax_errors'][:3]:
            emit_event("error", f"Sintaxis error: {err['file']}:{err['line']}")
    
    if analysis['stub_functions']:
        for stub in analysis['stub_functions'][:3]:
            emit_event("warn", f"Stub: {stub['file']}:{stub['line']} - {stub['function']}")
    
    # FASE 2: Testing de módulos
    emit_event("info", "🔬 FASE 2: Testing activo de módulos...")
    tester = ModuleTester()
    test_results = tester.test_all_modules()
    
    tester_state["broken_modules"] = test_results["broken_modules"]
    
    if test_results["broken_modules"]:
        emit_event("error", f"🚨 {len(test_results['broken_modules'])} módulos rotos detectados")
        for bm in test_results["broken_modules"][:3]:
            emit_event("error", f"   ❌ {bm['module']}: {bm['issue']}")
    
    # FASE 3: Chaos actions
    emit_event("info", "🔥 FASE 3: Ejecutando acciones de caos...")
    executor = ActionExecutor()
    chaos_results = executor.run_chaos_suite()
    
    emit_event("info", f"   Acciones ejecutadas: {len(chaos_results)}")
    
    # FASE 4: Loop continuo
    end_time = time.time() + TEST_DURATION
    last_report = time.time()
    
    emit_event("info", f"🔄 FASE 4: Monitoreo continuo...")
    
    while time.time() < end_time and tester_state["active"]:
        try:
            line = sys.stdin.readline()
            if not line:
                continue
            
            # Procesar mensajes entrantes
            try:
                msg = json.loads(line)
                # Podríamos analizar mensajes aquí
            except:
                pass
            
            # Reporte periódico
            if time.time() - last_report >= REPORT_INTERVAL:
                report = generate_report(is_final=False)
                print_report(report)
                emit("result.out", {"type": "status_report", "report": report})
                last_report = time.time()
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            emit_event("error", f"Error en loop: {e}")
    
    # Finalizar
    tester_state["active"] = False
    
    final_report = generate_report(is_final=True)
    print_report(final_report)
    
    emit("result.out", {
        "status": "complete",
        "final_report": final_report
    })
    
    emit_event("info", f"✅ CHAOS TESTER completado - Grade: {final_report['grade']}")
    
    # Guardar reporte
    try:
        report_path = os.path.join(PROJECT_ROOT, "logs", f"chaos_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(final_report, f, indent=2)
        emit_event("info", f"💾 Reporte guardado: {report_path}")
    except Exception as e:
        emit_event("error", f"No se pudo guardar: {e}")

def signal_handler(signum, frame):
    tester_state["active"] = False
    emit_event("info", "Señal recibida, finalizando...")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main_loop()
    except Exception as e:
        emit_event("error", f"Fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    sys.exit(0)
