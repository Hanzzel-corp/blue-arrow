#!/usr/bin/env python3
"""
Coherence Analyzer Module - Módulo de Blueprint
Analiza coherencia entre los 3 planos del sistema
"""

import json
import sys
import os
import time
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from lib.ontology import get_ontology, Plane, CanonicalEntity
    from lib.coherence_diagnostic import PhysicalPlane, LogicalPlane, OperationalPlane, CoherenceDiagnostic
except ImportError as e:
    print(f"ERROR: Cannot import coherence modules: {e}", file=sys.stderr)
    sys.exit(1)

def generate_trace_id():
    import random
    return f"coh_{int(time.time()*1000)}_{random.randint(1000,9999)}"

def emit(port, payload):
    msg = {
        "module": "coherence.analyzer",
        "port": port,
        "payload": payload,
        "trace_id": generate_trace_id(),
        "meta": {"source": "coherence_analyzer", "timestamp": time.time()}
    }
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def emit_event(level, text, extra=None):
    payload = {
        "level": level,
        "type": "coherence_report",
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
    if extra:
        payload.update(extra)
    emit("event.out", payload)
    print(f"[{level.upper()}] {text}", file=sys.stderr)

def emit_result(status, data):
    emit("result.out", {
        "status": status,
        "result": data,
        "timestamp": datetime.now().isoformat()
    })

def emit_report(report_type, data):
    emit("report.out", {
        "report_type": report_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    })

class CoherenceModule:
    """Módulo de análisis de coherencia integrado"""
    
    def __init__(self):
        self.ontology = get_ontology()
        self.physical = PhysicalPlane(PROJECT_ROOT)
        self.logical = LogicalPlane(PROJECT_ROOT)
        self.operational = OperationalPlane(PROJECT_ROOT)
        self.running = False
        
    def analyze_all(self) -> Dict:
        """Ejecuta análisis completo de coherencia"""
        
        emit_event("info", "🔬 Iniciando análisis de coherencia entre planos")
        
        # Cargar blueprint
        blueprint = self.logical.load_blueprint()
        canonical_entities = self.ontology.get_all_canonical_ids()
        
        emit_event("info", f"📋 Blueprint: {len(blueprint.get('modules', []))} módulos")
        emit_event("info", f"📋 Ontología: {len(canonical_entities)} entidades")
        
        reports = []
        coherence_scores = []
        
        # Analizar cada entidad
        for entity_id in canonical_entities:
            entity = self.ontology.entities[entity_id]
            
            # Revisar 3 planos
            physical = self.physical.check_entity(entity)
            logical = self.logical.check_entity(entity, blueprint)
            operational = self.operational.check_entity(entity)
            
            # Calcular score
            score = 100
            cross_issues = []
            
            for plane in [physical, logical, operational]:
                if plane.status.value == "absent":
                    score -= 40
                elif plane.status.value == "mismatch":
                    score -= 25
                elif plane.status.value == "degraded":
                    score -= 15
            
            # Cross-plane issues
            if physical.status.value == "present" and logical.status.value == "absent":
                cross_issues.append("orphan_physical")
                score -= 20
            
            if logical.status.value == "present" and physical.status.value == "absent":
                cross_issues.append("ghost_logical")
                score -= 20
            
            if entity.tier == "core" and operational.status.value != "present":
                score -= 30
                cross_issues.append("core_not_operational")
            
            score = max(0, score)
            coherence_scores.append(score)
            
            reports.append({
                "canonical_id": entity_id,
                "coherence_score": score,
                "physical_status": physical.status.value,
                "logical_status": logical.status.value,
                "operational_status": operational.status.value,
                "cross_issues": cross_issues,
                "tier": entity.tier
            })
        
        # Calcular métricas globales
        high = len([s for s in coherence_scores if s >= 80])
        medium = len([s for s in coherence_scores if 60 <= s < 80])
        low = len([s for s in coherence_scores if s < 60])
        avg = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0
        
        # Encontrar huérfanos
        physical_orphans = self.physical.find_orphans(canonical_entities)
        logical_orphans = self.logical.find_logical_orphans(canonical_entities, blueprint)
        
        # Determinar grado
        if avg >= 90:
            grade, status = "A", "EXCELENTE"
        elif avg >= 80:
            grade, status = "B", "BUENO"
        elif avg >= 60:
            grade, status = "C", "REGULAR"
        elif avg >= 40:
            grade, status = "D", "DÉBIL"
        else:
            grade, status = "F", "CRÍTICO"
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_entities": len(reports),
                "avg_coherence": round(avg, 1),
                "grade": grade,
                "status": status,
                "distribution": {"high": high, "medium": medium, "low": low},
                "orphans": {
                    "physical": len(physical_orphans),
                    "logical": len(logical_orphans)
                }
            },
            "entities": reports,
            "physical_orphans": physical_orphans,
            "logical_orphans": logical_orphans
        }
        
        # Emitir evento resumen
        emit_event("info", f"🏆 Análisis completo - Grade: {grade}, Coherencia: {avg:.1f}/100")
        
        if physical_orphans:
            emit_event("warn", f"⚠️ {len(physical_orphans)} huérfanos físicos detectados")
        
        if logical_orphans:
            emit_event("warn", f"⚠️ {len(logical_orphans)} huérfanos lógicos detectados")
        
        # Emitir reporte detallado
        emit_report("coherence_analysis", result)
        
        return result
    
    def handle_command(self, payload: Dict):
        """Maneja comandos entrantes"""
        action = payload.get("action", "")
        
        if action == "analyze":
            result = self.analyze_all()
            emit_result("success", result)
            
        elif action == "check_entity":
            entity_id = payload.get("entity_id", "")
            entity = self.ontology.resolve(entity_id)
            
            if entity:
                blueprint = self.logical.load_blueprint()
                physical = self.physical.check_entity(entity)
                logical = self.logical.check_entity(entity, blueprint)
                operational = self.operational.check_entity(entity)
                
                emit_result("success", {
                    "entity_id": entity_id,
                    "canonical_id": entity.canonical_id,
                    "physical": physical.status.value,
                    "logical": logical.status.value,
                    "operational": operational.status.value
                })
            else:
                emit_result("error", {"message": f"Entity not found: {entity_id}"})
        
        elif action == "list_entities":
            entities = []
            for eid, entity in self.ontology.entities.items():
                entities.append({
                    "canonical_id": eid,
                    "name": entity.name,
                    "tier": entity.tier,
                    "role": entity.role
                })
            emit_result("success", {"entities": entities})
            
        else:
            emit_result("error", {"message": f"Unknown action: {action}"})
    
    def run(self):
        """Loop principal"""
        emit_event("info", "🚀 Coherence Analyzer iniciado")
        emit_event("info", "   Esperando comandos (analyze, check_entity, list_entities)")
        
        self.running = True
        
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    continue
                
                if not line.strip():
                    continue
                
                try:
                    msg = json.loads(line)
                    port = msg.get("port", "")
                    payload = msg.get("payload", {})
                    
                    if port == "command.in":
                        self.handle_command(payload)
                    elif port == "signal.in":
                        signal_type = payload.get("type", "")
                        if signal_type == "shutdown":
                            self.running = False
                            emit_event("info", "Apagando Coherence Analyzer...")
                            
                except json.JSONDecodeError:
                    emit_event("error", "Invalid JSON received")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                emit_event("error", f"Error en loop: {e}")
        
        emit_event("info", "👋 Coherence Analyzer finalizado")

def main():
    import signal
    
    module = CoherenceModule()
    
    def signal_handler(signum, frame):
        module.running = False
        emit_event("info", "Señal recibida, finalizando...")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        module.run()
    except Exception as e:
        emit_event("error", f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
