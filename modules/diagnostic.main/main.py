#!/usr/bin/env python3
"""
Diagnostic Main Module - Módulo de Blueprint
Escucha todos los mensajes del sistema y genera reportes de diagnóstico
"""

import json
import sys
import os
import time
import threading
import signal
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from lib.logger import StructuredLogger
except ImportError:
    class StructuredLogger:
        def __init__(self, name): self.name = name
        def info(self, msg): emit_event("info", msg)
        def error(self, msg): emit_event("error", msg)
        def warn(self, msg): emit_event("warn", msg)

# Config
DURATION_MINUTES = int(os.environ.get("DIAGNOSTIC_DURATION", 50))
REPORT_INTERVAL = int(os.environ.get("DIAGNOSTIC_INTERVAL", 300))

# Estado
diagnostic = {
    "start_time": time.time(),
    "message_count": 0,
    "messages_by_module": defaultdict(int),
    "messages_by_port": defaultdict(int),
    "trace_ids": set(),
    "missing_trace_ids": 0,
    "missing_meta": 0,
    "errors": [],
    "last_report": 0,
    "port_types": defaultdict(int),
    "module_pairs": defaultdict(int),  # source -> target tracking
    "latencies": [],
    "active": True
}

def generate_trace_id():
    import random
    return f"diag_{int(time.time()*1000)}_{random.randint(1000,9999)}"

def emit(port, payload):
    """Emite mensaje al bus"""
    msg = {
        "module": "diagnostic.main",
        "port": port,
        "payload": payload,
        "trace_id": generate_trace_id(),
        "meta": {"source": "diagnostic", "timestamp": time.time()}
    }
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def emit_event(level, text, extra=None):
    """Emite evento al sistema"""
    payload = {
        "level": level,
        "type": "diagnostic_report",
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
    if extra:
        payload.update(extra)
    emit("event.out", payload)

def emit_result(status, data):
    """Emite resultado final"""
    emit("result.out", {
        "status": status,
        "result": data,
        "timestamp": datetime.now().isoformat()
    })

def analyze_message(msg):
    """Analiza un mensaje del bus"""
    module = msg.get("module", "unknown")
    port = msg.get("port", "unknown")
    trace_id = msg.get("trace_id")
    meta = msg.get("meta")
    payload = msg.get("payload", {})
    
    diagnostic["message_count"] += 1
    diagnostic["messages_by_module"][module] += 1
    diagnostic["messages_by_port"][port] += 1
    
    # Track port types
    port_type = "unknown"
    if ".out" in port:
        port_type = "output"
    elif ".in" in port:
        port_type = "input"
    elif "event" in port:
        port_type = "event"
    elif "command" in port:
        port_type = "command"
    elif "result" in port:
        port_type = "result"
    
    diagnostic["port_types"][port_type] += 1
    
    # Validate trace_id
    if trace_id:
        diagnostic["trace_ids"].add(trace_id)
    else:
        diagnostic["missing_trace_ids"] += 1
    
    # Validate meta
    if not meta:
        diagnostic["missing_meta"] += 1
    
    # Detect errors in payloads
    if isinstance(payload, dict):
        if payload.get("level") == "error" or payload.get("status") == "error":
            diagnostic["errors"].append({
                "module": module,
                "port": port,
                "error": payload.get("error") or payload.get("text", "unknown"),
                "timestamp": time.time()
            })

def calculate_benchmarks():
    """Calcula métricas de benchmark"""
    elapsed = time.time() - diagnostic["start_time"]
    msg_count = diagnostic["message_count"]
    
    # Message rate
    rate = msg_count / elapsed if elapsed > 0 else 0
    
    # Contract compliance
    trace_compliance = 1.0
    if msg_count > 0:
        trace_compliance = (msg_count - diagnostic["missing_trace_ids"]) / msg_count
    
    # Top modules
    top_modules = sorted(
        diagnostic["messages_by_module"].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    # Health score
    health_score = min(100, trace_compliance * 100)
    if rate < 1:  # Penalizar sistemas inactivos
        health_score *= 0.5
    
    # Grade
    if health_score >= 90:
        grade = "A"
    elif health_score >= 75:
        grade = "B"
    elif health_score >= 60:
        grade = "C"
    elif health_score >= 40:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "elapsed_seconds": round(elapsed, 1),
        "elapsed_formatted": str(timedelta(seconds=int(elapsed))),
        "total_messages": msg_count,
        "message_rate": round(rate, 2),
        "unique_trace_ids": len(diagnostic["trace_ids"]),
        "missing_trace_ids": diagnostic["missing_trace_ids"],
        "missing_meta": diagnostic["missing_meta"],
        "trace_compliance_pct": round(trace_compliance * 100, 1),
        "health_score": round(health_score, 1),
        "grade": grade,
        "port_distribution": dict(diagnostic["port_types"]),
        "top_modules": top_modules,
        "error_count": len(diagnostic["errors"]),
        "recent_errors": diagnostic["errors"][-5:] if diagnostic["errors"] else []
    }

def generate_report(is_final=False):
    """Genera reporte de diagnóstico"""
    benchmarks = calculate_benchmarks()
    
    report_type = "FINAL" if is_final else "INTERMEDIO"
    
    emit_event("info", f"📊 Reporte {report_type} de Diagnóstico", {
        "report_type": report_type,
        "benchmarks": benchmarks,
        "is_final": is_final
    })
    
    # Log a stdout también para debugging
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"📊 REPORTE {report_type} - {datetime.now().isoformat()}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"⏱️  Tiempo: {benchmarks['elapsed_formatted']}", file=sys.stderr)
    print(f"📨 Mensajes: {benchmarks['total_messages']:,} ({benchmarks['message_rate']:.2f}/s)", file=sys.stderr)
    print(f"🎯 Trace Compliance: {benchmarks['trace_compliance_pct']}%", file=sys.stderr)
    print(f"🏆 Health Score: {benchmarks['health_score']}/100 (Grade: {benchmarks['grade']})", file=sys.stderr)
    print(f"❌ Errores detectados: {benchmarks['error_count']}", file=sys.stderr)
    
    if benchmarks['top_modules']:
        print(f"\n📈 Top Módulos:", file=sys.stderr)
        for mod, count in benchmarks['top_modules'][:5]:
            print(f"   {mod}: {count:,}", file=sys.stderr)
    
    if benchmarks['recent_errors']:
        print(f"\n🚨 Errores recientes:", file=sys.stderr)
        for err in benchmarks['recent_errors']:
            print(f"   [{err['module']}] {err['error'][:50]}", file=sys.stderr)
    
    print(f"{'='*60}\n", file=sys.stderr)
    
    return benchmarks

def report_thread():
    """Thread que genera reportes periódicos"""
    while diagnostic["active"]:
        time.sleep(REPORT_INTERVAL)
        
        if not diagnostic["active"]:
            break
            
        elapsed = time.time() - diagnostic["start_time"]
        if elapsed - diagnostic["last_report"] >= REPORT_INTERVAL:
            generate_report(is_final=False)
            diagnostic["last_report"] = elapsed

def main_loop():
    """Loop principal de procesamiento de mensajes"""
    emit_event("info", f"🔬 Diagnóstico iniciado - Duración: {DURATION_MINUTES}min, Intervalo: {REPORT_INTERVAL}s")
    
    # Iniciar thread de reportes
    reporter = threading.Thread(target=report_thread, daemon=True)
    reporter.start()
    
    # Loop principal
    end_time = time.time() + (DURATION_MINUTES * 60)
    
    while time.time() < end_time and diagnostic["active"]:
        try:
            line = sys.stdin.readline()
            if not line:
                continue
                
            if not line.strip():
                continue
            
            try:
                msg = json.loads(line)
                analyze_message(msg)
            except json.JSONDecodeError as e:
                diagnostic["errors"].append({
                    "module": "parser",
                    "port": "stdin",
                    "error": f"JSON parse error: {e}",
                    "timestamp": time.time()
                })
                
        except KeyboardInterrupt:
            emit_event("warn", "Diagnóstico interrumpido por usuario")
            break
        except Exception as e:
            emit_event("error", f"Error en main_loop: {e}")
    
    # Finalizar
    diagnostic["active"] = False
    final_report = generate_report(is_final=True)
    
    # Emitir resultado final
    emit_result("success", {
        "diagnostic_complete": True,
        "final_grade": final_report["grade"],
        "health_score": final_report["health_score"],
        "total_messages_analyzed": final_report["total_messages"],
        "duration_seconds": final_report["elapsed_seconds"],
        "report": final_report
    })
    
    emit_event("info", f"✅ Diagnóstico completado - Grade: {final_report['grade']}, Score: {final_report['health_score']}/100")
    
    # Guardar reporte a archivo
    try:
        report_path = os.path.join(PROJECT_ROOT, "logs", f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(final_report, f, indent=2)
        emit_event("info", f"💾 Reporte guardado en: {report_path}")
    except Exception as e:
        emit_event("error", f"No se pudo guardar reporte: {e}")

def signal_handler(signum, frame):
    """Maneja señales de terminación"""
    emit_event("info", "Señal recibida, finalizando diagnóstico...")
    diagnostic["active"] = False

if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main_loop()
    except Exception as e:
        emit_event("error", f"Error fatal: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    
    sys.exit(0)
