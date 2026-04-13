#!/usr/bin/env python3
"""
System Diagnostic & Benchmark Module
Analiza conexiones, detecta problemas, benchmark de performance
Ejecutar: python3 lib/system_diagnostic.py --duration 3000
"""

import json
import sys
import os
import time
import threading
import statistics
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any, Set
import argparse
import signal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from lib.logger import StructuredLogger
except ImportError:
    class StructuredLogger:
        def __init__(self, name): self.name = name
        def info(self, msg): print(f"INFO [{self.name}]: {msg}", file=sys.stderr)
        def error(self, msg): print(f"ERROR [{self.name}]: {msg}", file=sys.stderr)
        def warn(self, msg): print(f"WARN [{self.name}]: {msg}", file=sys.stderr)
        def debug(self, msg): pass

logger = StructuredLogger("system.diagnostic")


class ConnectionAnalyzer:
    """Analiza todas las conexiones del blueprint"""
    
    def __init__(self, blueprint_path: str):
        self.blueprint = self._load_blueprint(blueprint_path)
        self.registry = self._load_registry()
        self.connections: List[Dict] = self.blueprint.get("connections", [])
        self.modules: Set[str] = set(self.blueprint.get("modules", []))
        
    def _load_blueprint(self, path: str) -> Dict:
        with open(path, 'r') as f:
            return json.load(f)
    
    def _load_registry(self) -> Dict[str, Any]:
        """Carga manifests de todos los módulos"""
        registry = {}
        modules_dir = os.path.join(PROJECT_ROOT, "modules")
        for entry in os.listdir(modules_dir):
            module_dir = os.path.join(modules_dir, entry)
            if os.path.isdir(module_dir):
                manifest_path = os.path.join(module_dir, "manifest.json")
                if os.path.exists(manifest_path):
                    with open(manifest_path, 'r') as f:
                        registry[entry] = json.load(f)
        return registry
    
    def analyze_connections(self) -> Dict:
        """Analiza todas las conexiones y detecta problemas"""
        issues = []
        stats = {
            "total_connections": len(self.connections),
            "unique_sources": set(),
            "unique_targets": set(),
            "orphan_ports": [],
            "missing_modules": [],
            "duplicate_connections": [],
            "unused_modules": set(self.modules)
        }
        
        seen_connections = set()
        
        for conn in self.connections:
            from_key = conn.get("from", "")
            to_key = conn.get("to", "")
            
            stats["unique_sources"].add(from_key)
            stats["unique_targets"].add(to_key)
            
            # Check duplicados
            conn_key = f"{from_key}->{to_key}"
            if conn_key in seen_connections:
                stats["duplicate_connections"].append(conn_key)
            seen_connections.add(conn_key)
            
            # Verificar módulos existen
            from_module = from_key.split(":")[0] if ":" in from_key else from_key
            to_module = to_key.split(":")[0] if ":" in to_key else to_key
            
            if from_module not in self.modules:
                stats["missing_modules"].append(from_module)
                issues.append({
                    "type": "missing_source_module",
                    "connection": conn,
                    "severity": "high"
                })
            else:
                stats["unused_modules"].discard(from_module)
                
            if to_module not in self.modules:
                stats["missing_modules"].append(to_module)
                issues.append({
                    "type": "missing_target_module", 
                    "connection": conn,
                    "severity": "high"
                })
            else:
                stats["unused_modules"].discard(to_module)
        
        # Detectar puertos huérfanos (outputs sin connections)
        for module_id in self.modules:
            manifest = self.registry.get(module_id.replace(".", "-"), {})
            outputs = manifest.get("outputs", [])
            for output in outputs:
                port_key = f"{module_id}:{output}"
                if port_key not in stats["unique_sources"]:
                    stats["orphan_ports"].append(port_key)
        
        return {
            "stats": {
                "total_connections": stats["total_connections"],
                "unique_sources": len(stats["unique_sources"]),
                "unique_targets": len(stats["unique_targets"]),
                "orphan_ports": len(stats["orphan_ports"]),
                "missing_modules": list(set(stats["missing_modules"])),
                "duplicate_connections": stats["duplicate_connections"],
                "unused_modules": list(stats["unused_modules"]),
                "orphan_ports_list": stats["orphan_ports"][:10]  # Top 10
            },
            "issues": issues,
            "healthy": len(issues) == 0 and len(stats["missing_modules"]) == 0
        }


class MessageTracer:
    """Traza mensajes y mide latencias"""
    
    def __init__(self):
        self.message_counts = defaultdict(int)
        self.message_latencies = defaultdict(list)
        self.errors = []
        self.warnings = []
        self.start_time = time.time()
        self.trace_ids = set()
        self.missing_trace_ids = []
        self.missing_meta = []
        self.port_usage = defaultdict(int)
        self.module_activity = defaultdict(lambda: {"in": 0, "out": 0, "last_seen": None})
        
    def trace_message(self, msg: Dict) -> Dict:
        """Procesa un mensaje y extrae métricas"""
        module = msg.get("module", "unknown")
        port = msg.get("port", "unknown")
        trace_id = msg.get("trace_id")
        meta = msg.get("meta")
        
        # Contadores
        self.message_counts[f"{module}:{port}"] += 1
        self.port_usage[port] += 1
        
        if port.endswith(".out"):
            self.module_activity[module]["out"] += 1
        elif port.endswith(".in"):
            self.module_activity[module]["in"] += 1
        self.module_activity[module]["last_seen"] = time.time()
        
        issues = []
        
        # Validar trace_id
        if not trace_id:
            self.missing_trace_ids.append(f"{module}:{port}")
            issues.append({"type": "missing_trace_id", "module": module, "port": port})
        else:
            self.trace_ids.add(trace_id)
        
        # Validar meta
        if not meta:
            self.missing_meta.append(f"{module}:{port}")
            issues.append({"type": "missing_meta", "module": module, "port": port})
        
        return {
            "module": module,
            "port": port,
            "trace_id": trace_id,
            "has_meta": meta is not None,
            "issues": issues
        }
    
    def get_stats(self) -> Dict:
        elapsed = time.time() - self.start_time
        
        # Top puertos más usados
        top_ports = sorted(self.port_usage.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Módulos más activos
        top_modules = sorted(
            [(m, a["out"] + a["in"]) for m, a in self.module_activity.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Módulos inactivos (>30s sin mensajes)
        now = time.time()
        inactive = [m for m, a in self.module_activity.items() 
                   if a["last_seen"] and (now - a["last_seen"]) > 30]
        
        return {
            "elapsed_seconds": round(elapsed, 1),
            "total_messages": sum(self.message_counts.values()),
            "unique_trace_ids": len(self.trace_ids),
            "missing_trace_ids_count": len(self.missing_trace_ids),
            "missing_meta_count": len(self.missing_meta),
            "top_ports": top_ports,
            "top_modules": top_modules,
            "inactive_modules": inactive,
            "message_rate": round(sum(self.message_counts.values()) / elapsed, 2) if elapsed > 0 else 0
        }


class BenchmarkSuite:
    """Suite de benchmarks del sistema"""
    
    def __init__(self):
        self.results = {}
        
    def benchmark_connection_density(self, analyzer: ConnectionAnalyzer) -> Dict:
        """Mide densidad de conexiones"""
        analysis = analyzer.analyze_connections()
        stats = analysis["stats"]
        
        # Score: más conexiones = más integrado
        connection_score = min(stats["total_connections"] / 50, 1.0) * 100
        
        # Penalización por puertos huérfanos
        orphan_penalty = min(stats["orphan_ports"] / 20, 1.0) * 50
        
        # Penalización por módulos sin usar
        unused_penalty = len(stats["unused_modules"]) * 10
        
        final_score = max(0, connection_score - orphan_penalty - unused_penalty)
        
        return {
            "score": round(final_score, 1),
            "connection_score": round(connection_score, 1),
            "orphan_penalty": round(orphan_penalty, 1),
            "unused_penalty": unused_penalty,
            "grade": "A" if final_score > 80 else "B" if final_score > 60 else "C" if final_score > 40 else "D"
        }
    
    def benchmark_message_health(self, tracer: MessageTracer) -> Dict:
        """Evalúa salud de mensajes"""
        stats = tracer.get_stats()
        
        # Score base por volumen
        volume_score = min(stats["total_messages"] / 1000, 1.0) * 100
        
        # Penalización por trace_id faltantes
        total = stats["total_messages"]
        if total > 0:
            trace_penalty = (stats["missing_trace_ids_count"] / total) * 100
            meta_penalty = (stats["missing_meta_count"] / total) * 50
        else:
            trace_penalty = 0
            meta_penalty = 0
        
        # Bonus por rate sostenido
        rate_bonus = min(stats["message_rate"] / 50, 1.0) * 20
        
        final_score = max(0, volume_score - trace_penalty - meta_penalty + rate_bonus)
        
        return {
            "score": round(final_score, 1),
            "volume_score": round(volume_score, 1),
            "trace_penalty": round(trace_penalty, 1),
            "meta_penalty": round(meta_penalty, 1),
            "rate_bonus": round(rate_bonus, 1),
            "grade": "A" if final_score > 80 else "B" if final_score > 60 else "C" if final_score > 40 else "D"
        }
    
    def run_all(self, analyzer: ConnectionAnalyzer, tracer: MessageTracer) -> Dict:
        self.results = {
            "connection_density": self.benchmark_connection_density(analyzer),
            "message_health": self.benchmark_message_health(tracer),
            "timestamp": datetime.now().isoformat()
        }
        
        # Overall grade
        scores = [r["score"] for r in self.results.values() if isinstance(r, dict) and "score" in r]
        avg_score = statistics.mean(scores) if scores else 0
        
        self.results["overall_score"] = round(avg_score, 1)
        self.results["overall_grade"] = "A" if avg_score > 80 else "B" if avg_score > 60 else "C" if avg_score > 40 else "D"
        
        return self.results


class SystemDiagnostic:
    """Diagnóstico completo del sistema"""
    
    def __init__(self, duration_minutes: int = 50):
        self.duration = duration_minutes * 60  # Convertir a segundos
        self.running = False
        self.tracer = MessageTracer()
        self.analyzer = None
        self.benchmark = BenchmarkSuite()
        self.report_interval = 300  # Reporte cada 5 minutos
        self.last_report = 0
        
        # Señales
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        logger.info("Señal recibida, terminando diagnóstico...")
        self.running = False
        
    def _load_blueprint(self) -> str:
        """Encuentra el blueprint por defecto"""
        blueprint_path = os.path.join(PROJECT_ROOT, "blueprints", "system.v0.json")
        if not os.path.exists(blueprint_path):
            # Buscar cualquier .json en blueprints
            blueprints_dir = os.path.join(PROJECT_ROOT, "blueprints")
            for f in os.listdir(blueprints_dir):
                if f.endswith(".json"):
                    return os.path.join(blueprints_dir, f)
        return blueprint_path
    
    def _generate_report(self, final: bool = False) -> Dict:
        """Genera reporte de estado"""
        tracer_stats = self.tracer.get_stats()
        analysis = self.analyzer.analyze_connections() if self.analyzer else {"stats": {}, "issues": []}
        benchmarks = self.benchmark.run_all(self.analyzer, self.tracer) if self.analyzer else {}
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "is_final": final,
            "uptime_seconds": tracer_stats["elapsed_seconds"],
            "message_stats": tracer_stats,
            "connection_analysis": analysis,
            "benchmarks": benchmarks,
            "issues_found": len(analysis.get("issues", [])),
            "recommendations": self._generate_recommendations(analysis, tracer_stats)
        }
        return report
    
    def _generate_recommendations(self, analysis: Dict, tracer_stats: Dict) -> List[str]:
        """Genera recomendaciones basadas en hallazgos"""
        recommendations = []
        stats = analysis.get("stats", {})
        
        if stats.get("orphan_ports", 0) > 5:
            recommendations.append(f"🔧 {stats['orphan_ports']} puertos sin conexiones - revisar si son necesarios")
        
        if stats.get("unused_modules"):
            recommendations.append(f"🔧 Módulos sin usar: {', '.join(stats['unused_modules'][:3])}")
        
        if tracer_stats["missing_trace_ids_count"] > 0:
            pct = (tracer_stats["missing_trace_ids_count"] / max(tracer_stats["total_messages"], 1)) * 100
            recommendations.append(f"⚠️ {pct:.1f}% de mensajes sin trace_id - revisar contract compliance")
        
        if tracer_stats.get("inactive_modules"):
            recommendations.append(f"⚠️ Módulos inactivos: {', '.join(tracer_stats['inactive_modules'][:3])}")
        
        if not recommendations:
            recommendations.append("✅ Sistema saludable - no se detectaron problemas mayores")
        
        return recommendations
    
    def _print_report(self, report: Dict):
        """Imprime reporte formateado"""
        print("\n" + "="*80)
        print(f"📊 SYSTEM DIAGNOSTIC REPORT - {report['timestamp']}")
        print("="*80)
        
        if report["is_final"]:
            print("🏁 REPORTE FINAL\n")
        
        # Uptime
        uptime = report["uptime_seconds"]
        print(f"⏱️  Uptime: {timedelta(seconds=int(uptime))}")
        
        # Mensajes
        msg_stats = report["message_stats"]
        print(f"\n📨 MENSAJES:")
        print(f"   Total: {msg_stats['total_messages']:,}")
        print(f"   Rate: {msg_stats['message_rate']:.2f} msg/s")
        print(f"   Trace IDs únicos: {msg_stats['unique_trace_ids']:,}")
        print(f"   Sin trace_id: {msg_stats['missing_trace_ids_count']}")
        
        # Benchmarks
        benchmarks = report.get("benchmarks", {})
        if benchmarks:
            print(f"\n🏆 BENCHMARKS:")
            print(f"   Overall Score: {benchmarks.get('overall_score', 0)}/100 (Grade: {benchmarks.get('overall_grade', 'N/A')})")
            
            conn = benchmarks.get("connection_density", {})
            print(f"   Connection Density: {conn.get('score', 0)}/100 (Grade: {conn.get('grade', 'N/A')})")
            
            msg = benchmarks.get("message_health", {})
            print(f"   Message Health: {msg.get('score', 0)}/100 (Grade: {msg.get('grade', 'N/A')})")
        
        # Problemas
        analysis = report.get("connection_analysis", {})
        issues = analysis.get("issues", [])
        if issues:
            print(f"\n🚨 PROBLEMAS DETECTADOS ({len(issues)}):")
            for issue in issues[:5]:
                print(f"   • [{issue['severity'].upper()}] {issue['type']}: {issue.get('connection', {})}")
        
        # Recomendaciones
        print(f"\n💡 RECOMENDACIONES:")
        for rec in report["recommendations"]:
            print(f"   {rec}")
        
        # Top módulos
        top = msg_stats.get("top_modules", [])
        if top:
            print(f"\n📈 TOP MÓDULOS (por volumen):")
            for module, count in top[:5]:
                print(f"   {module}: {count:,} mensajes")
        
        print("="*80 + "\n")
    
    def run(self):
        """Ejecuta el loop de diagnóstico"""
        logger.info(f"Iniciando diagnóstico por {self.duration/60:.1f} minutos...")
        
        # Cargar blueprint
        blueprint_path = self._load_blueprint()
        logger.info(f"Blueprint cargado: {blueprint_path}")
        
        self.analyzer = ConnectionAnalyzer(blueprint_path)
        
        # Análisis inicial
        initial_analysis = self.analyzer.analyze_connections()
        print("\n📋 ANÁLISIS INICIAL DE CONEXIONES:")
        stats = initial_analysis["stats"]
        print(f"   Total conexiones: {stats['total_connections']}")
        print(f"   Módulos en blueprint: {len(self.analyzer.modules)}")
        print(f"   Puertos huérfanos: {stats['orphan_ports']}")
        print(f"   Módulos sin usar: {len(stats['unused_modules'])}")
        
        if initial_analysis["issues"]:
            print(f"\n⚠️  Problemas encontrados: {len(initial_analysis['issues'])}")
        
        # Loop principal - escuchar mensajes por stdin
        print(f"\n🔄 Iniciando monitoreo de mensajes (Ctrl+C para detener)...\n")
        self.running = True
        start_time = time.time()
        
        while self.running:
            elapsed = time.time() - start_time
            
            if elapsed >= self.duration:
                logger.info("Duración completada, generando reporte final...")
                break
            
            try:
                # Leer línea de stdin (con timeout para poder verificar duración)
                import select
                if select.select([sys.stdin], [], [], 1.0)[0]:
                    line = sys.stdin.readline()
                    if line.strip():
                        try:
                            msg = json.loads(line)
                            self.tracer.trace_message(msg)
                        except json.JSONDecodeError:
                            pass
                
                # Reporte periódico
                if elapsed - self.last_report >= self.report_interval:
                    report = self._generate_report(final=False)
                    self._print_report(report)
                    self.last_report = elapsed
                    
            except Exception as e:
                logger.error(f"Error en loop: {e}")
                continue
        
        # Reporte final
        final_report = self._generate_report(final=True)
        self._print_report(final_report)
        
        # Guardar reporte a archivo
        report_path = os.path.join(PROJECT_ROOT, "logs", f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(final_report, f, indent=2)
        logger.info(f"Reporte guardado en: {report_path}")
        
        return final_report


def main():
    parser = argparse.ArgumentParser(description="System Diagnostic & Benchmark")
    parser.add_argument("--duration", type=int, default=3000, help="Duración en segundos (default: 3000 = 50min)")
    parser.add_argument("--report-interval", type=int, default=300, help="Intervalo de reporte en segundos (default: 300 = 5min)")
    args = parser.parse_args()
    
    diagnostic = SystemDiagnostic(duration_minutes=args.duration/60)
    diagnostic.report_interval = args.report_interval
    
    try:
        report = diagnostic.run()
        sys.exit(0 if report["benchmarks"].get("overall_grade", "F") in ["A", "B"] else 1)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
