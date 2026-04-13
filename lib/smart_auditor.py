#!/usr/bin/env python3
"""
Smart Auditor - Auditoría con priorización y sugerencias.

Categorías de violación:
- CRITICAL: Rompe el sistema o viola reglas fundamentales
- HIGH: Riesgo operativo significativo
- MEDIUM: Mejora recomendada
- LOW: Estilo o convención
- TOLERABLE: Aceptable en ciertos contextos
- JUSTIFIED: Excepción documentada
- TECH_DEBT: Deuda técnica aceptada temporalmente

Sugerencias automáticas para cada tipo de violación.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from decision_log import DecisionLogManager, Decision


class ViolationCategory(Enum):
    """Categorías de violación por impacto y acción recomendada."""
    CRITICAL = "critical"           # Rompe el sistema - corregir inmediatamente
    HIGH = "high"                   # Riesgo operativo - planear corrección
    MEDIUM = "medium"               # Mejora recomendada - backlog
    LOW = "low"                     # Estilo - nice to have
    TOLERABLE = "tolerable"         # Aceptable en contexto (documentar)
    JUSTIFIED = "justified"         # Excepción con razón documentada
    TECH_DEBT = "tech_debt"         # Deuda aceptada - trackear


@dataclass
class Violation:
    """Violación con contexto completo y sugerencia."""
    rule: str
    category: ViolationCategory
    type: str
    message: str
    location: str
    suggestion: str
    impact: str
    effort: str  # low/medium/high - esfuerzo para corregir
    auto_fixable: bool = False


@dataclass
class AuditContext:
    """Contexto para decisiones inteligentes."""
    module_tiers: Dict[str, str] = field(default_factory=dict)
    execution_critical: List[str] = field(default_factory=list)
    known_loops: List[Tuple[str, str]] = field(default_factory=list)
    justified_exceptions: List[str] = field(default_factory=list)


class SmartAuditor:
    """
    Auditor inteligente con priorización y sugerencias.
    """
    
    # Módulos core - sus violaciones son más graves
    CORE_MODULES = {
        'supervisor.main', 'router.main', 'agent.main', 'planner.main',
        'safety.guard.main', 'approval.main', 'worker.python.desktop',
        'worker.python.terminal', 'worker.python.system', 'worker.python.browser',
        'memory.log.main', 'interface.main'
    }
    
    # Satellites - sus violaciones son menos críticas
    SATELLITE_MODULES = {
        'gamification.main', 'ai.assistant.main', 'ai.learning.engine.main',
        'ai.memory.semantic.main', 'ai.self.audit.main', 'verifier.engine.main'
    }
    
    # Loops conocidos y aceptados (por diseño)
    KNOWN_LOOPS = [
        ('planner.main', 'phase.engine.main'),
        ('phase.engine.main', 'planner.main'),
        ('interface.telegram', 'telegram.menu.main'),
        ('telegram.menu.main', 'interface.telegram'),
    ]
    
    def __init__(self, blueprint_path: str):
        self.blueprint_path = Path(blueprint_path)
        self.blueprint = self._load_blueprint()
        self.connections = self._parse_connections()
        self.violations: List[Violation] = []
        self.decision_log = DecisionLogManager()
        self.context = AuditContext(
            module_tiers=self._classify_modules(),
            known_loops=self.KNOWN_LOOPS,
            justified_exceptions=[]  # Se carga desde decision log
        )

    def _load_blueprint(self) -> dict:
        with open(self.blueprint_path) as f:
            return json.load(f)

    def _parse_connections(self) -> dict:
        conns = {
            'by_source': defaultdict(list),
            'by_target': defaultdict(list),
            'execution_flow': [],
            'observation_flow': [],
        }
        
        for conn in self.blueprint.get('connections', []):
            from_mod, from_port = conn['from'].split(':')
            to_mod, to_port = conn['to'].split(':')
            
            conn_data = {
                'from': conn['from'],
                'to': conn['to'],
                'from_module': from_mod,
                'to_module': to_mod,
                'from_port': from_port,
                'to_port': to_port,
            }
            
            conns['by_source'][conn['from']].append(conn_data)
            conns['by_target'][conn['to']].append(conn_data)
            
            if self._is_execution_port(from_port) or self._is_execution_port(to_port):
                conns['execution_flow'].append(conn_data)
            elif self._is_observation_port(from_port) or self._is_observation_port(to_port):
                conns['observation_flow'].append(conn_data)
        
        return conns

    def _classify_modules(self) -> Dict[str, str]:
        tiers = {}
        for module in self.blueprint.get('modules', []):
            if module in self.CORE_MODULES:
                tiers[module] = 'core'
            elif module in self.SATELLITE_MODULES:
                tiers[module] = 'satellite'
            else:
                tiers[module] = 'unknown'
        return tiers

    def _is_execution_port(self, port: str) -> bool:
        return any(port.endswith(p) for p in ['action.in', 'plan.in', 'command.in', 'result.out'])

    def _is_observation_port(self, port: str) -> bool:
        return any(port.endswith(p) for p in ['event.in', 'event.out'])

    def _get_module_tier(self, module: str) -> str:
        return self.context.module_tiers.get(module, 'unknown')

    def _is_known_loop(self, mod1: str, mod2: str) -> bool:
        return (mod1, mod2) in self.context.known_loops or (mod2, mod1) in self.context.known_loops

    def _is_justified(self, from_conn: str, to_conn: str) -> Tuple[bool, str]:
        """Verifica si una conexión está justificada en el Decision Log."""
        exception_key = f"{from_conn} -> {to_conn}"
        
        # Buscar en decision log
        justified, decision = self.decision_log.is_exception_justified(exception_key)
        if justified and decision:
            return True, f"[{decision.id}] {decision.motivation}"
        
        # Fallback: verificar en loops conocidos
        from_mod = from_conn.split(":")[0]
        to_mod = to_conn.split(":")[0]
        if self._is_known_loop(from_mod, to_mod):
            return True, f"Loop conocido por diseño ({from_mod} <-> {to_mod})"
        
        return False, ""

    def audit_execution_broadcast(self):
        """Audita broadcast de ejecución con contexto."""
        for source, targets in self.connections['by_source'].items():
            if len(targets) <= 1:
                continue
            
            from_mod = targets[0]['from_module']
            from_port = targets[0]['from_port']
            
            if not self._is_execution_port(from_port):
                continue
            
            # Filtrar solo targets de ejecución
            exec_targets = [t for t in targets if self._is_execution_port(t['to_port'])]
            
            if len(exec_targets) <= 1:
                continue
            
            # Analizar severidad según contexto
            target_modules = [t['to_module'] for t in exec_targets]
            core_targets = [m for m in target_modules if self._get_module_tier(m) == 'core']
            
            # Verificar si es justificado
            for target in exec_targets:
                justified, reason = self._is_justified(source, target['to'])
                if justified:
                    self.violations.append(Violation(
                        rule="1",
                        category=ViolationCategory.JUSTIFIED,
                        type="execution_broadcast_justified",
                        message=f"{source} -> {target['to']} tiene paralelismo justificado",
                        location=f"blueprints/system.v0.json: {source} -> {target['to']}",
                        suggestion=f"Documentar en JUSTIFIED_EXCEPTIONS: {reason}",
                        impact="Aceptado por diseño",
                        effort="none",
                        auto_fixable=False
                    ))
                    continue
            
            # Si tiene múltiples targets core → CRÍTICO
            if len(core_targets) > 1:
                self.violations.append(Violation(
                    rule="1",
                    category=ViolationCategory.CRITICAL,
                    type="execution_broadcast_core",
                    message=f"{source} hace broadcast a {len(core_targets)} módulos core",
                    location=f"blueprints/system.v0.json: {source}",
                    suggestion="Reducir a ruta única: mantener solo el camino principal, mover observación a event.out",
                    impact="Riesgo de inconsistencia en estado core",
                    effort="high",
                    auto_fixable=False
                ))
            # Si tiene mix → HIGH
            elif len(exec_targets) > 2:
                self.violations.append(Violation(
                    rule="1",
                    category=ViolationCategory.HIGH,
                    type="execution_broadcast_mixed",
                    message=f"{source} hace broadcast a {len(exec_targets)} destinos",
                    location=f"blueprints/system.v0.json: {source}",
                    suggestion="Separar: ejecución a 1 destino, observación a los demás via event.out",
                    impact="Complejidad innecesaria, dificulta debugging",
                    effort="medium",
                    auto_fixable=False
                ))
            # Si solo satellites → MEDIUM (deuda técnica)
            else:
                self.violations.append(Violation(
                    rule="1",
                    category=ViolationCategory.TECH_DEBT,
                    type="execution_broadcast_satellite",
                    message=f"{source} hace broadcast a satellites",
                    location=f"blueprints/system.v0.json: {source}",
                    suggestion="Considerar si se puede mover a event.out para satellites",
                    impact="Bajo - solo afecta satellites",
                    effort="low",
                    auto_fixable=False
                ))

    def audit_loops(self):
        """Audita loops con conocimiento de diseño."""
        # Detectar ciclos simples (A->B y B->A)
        for conn in self.blueprint.get('connections', []):
            from_mod = conn['from'].split(':')[0]
            to_mod = conn['to'].split(':')[0]
            
            # Buscar conexión inversa
            inverse_exists = any(
                c['from'].startswith(to_mod) and c['to'].startswith(from_mod)
                for c in self.blueprint.get('connections', [])
            )
            
            if inverse_exists:
                # Verificar si es loop conocido
                if self._is_known_loop(from_mod, to_mod):
                    self.violations.append(Violation(
                        rule="loop",
                        category=ViolationCategory.JUSTIFIED,
                        type="known_loop",
                        message=f"Loop conocido entre {from_mod} <-> {to_mod}",
                        location=f"blueprints/system.v0.json",
                        suggestion="Loop aceptado por diseño (phase.engine <-> planner)",
                        impact="Controlado - conocido",
                        effort="none",
                        auto_fixable=False
                    ))
                else:
                    # Loop no conocido → posible problema
                    tier_from = self._get_module_tier(from_mod)
                    tier_to = self._get_module_tier(to_mod)
                    
                    if tier_from == 'core' and tier_to == 'core':
                        category = ViolationCategory.CRITICAL
                        impact = "Riesgo de loop infinito en core"
                        effort = "high"
                    else:
                        category = ViolationCategory.HIGH
                        impact = "Posible loop no controlado"
                        effort = "medium"
                    
                    self.violations.append(Violation(
                        rule="loop",
                        category=category,
                        type="uncontrolled_loop",
                        message=f"Posible loop no documentado: {from_mod} <-> {to_mod}",
                        location=f"blueprints/system.v0.json",
                        suggestion="Verificar si es intencional. Si sí, agregar a KNOWN_LOOPS",
                        impact=impact,
                        effort=effort,
                        auto_fixable=False
                    ))

    def audit_observation_to_execution(self):
        """Audita observación que intenta afectar ejecución."""
        for conn in self.blueprint.get('connections', []):
            from_port = conn['from'].split(':')[1]
            to_port = conn['to'].split(':')[1]
            to_mod = conn['to'].split(':')[0]
            
            if self._is_observation_port(from_port) and self._is_execution_port(to_port):
                tier = self._get_module_tier(to_mod)
                
                if tier == 'core':
                    self.violations.append(Violation(
                        rule="5",
                        category=ViolationCategory.CRITICAL,
                        type="observation_to_core_execution",
                        message=f"{conn['from']} (observación) conecta a ejecución core {conn['to']}",
                        location=f"blueprints/system.v0.json: {conn['from']} -> {conn['to']}",
                        suggestion="CRÍTICO: Mover a event.out o cambiar a puerto de control",
                        impact="Violación grave de separación de responsabilidades",
                        effort="high",
                        auto_fixable=False
                    ))
                elif tier == 'satellite':
                    # Acción derivada en satellite
                    self.violations.append(Violation(
                        rule="5",
                        category=ViolationCategory.TOLERABLE,
                        type="observation_to_satellite",
                        message=f"{conn['from']} dispara acción en satellite {conn['to']}",
                        location=f"blueprints/system.v0.json: {conn['from']} -> {conn['to']}",
                        suggestion="Aceptable si es acción derivada. Documentar en excepciones.",
                        impact="Controlado - satellite puede manejar triggers",
                        effort="low",
                        auto_fixable=False
                    ))

    def audit(self) -> List[Violation]:
        """Ejecuta auditoría inteligente completa."""
        self.audit_execution_broadcast()
        self.audit_loops()
        self.audit_observation_to_execution()
        
        return self.violations

    def print_report(self):
        """Imprime reporte priorizado con acciones."""
        print("=" * 80)
        print("SMART AUDITOR - Reporte Priorizado")
        print("=" * 80)
        print()
        
        # Agrupar por categoría
        by_category = defaultdict(list)
        for v in self.violations:
            by_category[v.category].append(v)
        
        # Orden de severidad
        severity_order = [
            ViolationCategory.CRITICAL,
            ViolationCategory.HIGH,
            ViolationCategory.MEDIUM,
            ViolationCategory.TECH_DEBT,
            ViolationCategory.TOLERABLE,
            ViolationCategory.JUSTIFIED,
        ]
        
        # Resumen ejecutivo
        print("RESUMEN EJECUTIVO:")
        print("-" * 80)
        total = len(self.violations)
        critical = len(by_category[ViolationCategory.CRITICAL])
        high = len(by_category[ViolationCategory.HIGH])
        justified = len(by_category[ViolationCategory.JUSTIFIED])
        
        print(f"Total violaciones analizadas: {total}")
        print(f"  🔴 CRÍTICAS (acción inmediata): {critical}")
        print(f"  🟠 ALTAS (planear corrección): {high}")
        print(f"  🟡 MEDIAS (backlog): {len(by_category[ViolationCategory.MEDIUM])}")
        print(f"  🔵 DEUDA TÉCNICA: {len(by_category[ViolationCategory.TECH_DEBT])}")
        print(f"  🟢 JUSTIFICADAS: {justified}")
        print()
        
        # Detalle por categoría
        for category in severity_order:
            if category not in by_category:
                continue
            
            violations = by_category[category]
            
            emoji = {
                ViolationCategory.CRITICAL: "🔴",
                ViolationCategory.HIGH: "🟠",
                ViolationCategory.MEDIUM: "🟡",
                ViolationCategory.TECH_DEBT: "🔵",
                ViolationCategory.TOLERABLE: "⚪",
                ViolationCategory.JUSTIFIED: "🟢",
            }.get(category, "⚪")
            
            print(f"{emoji} {category.value.upper()} ({len(violations)})")
            print("-" * 80)
            
            for v in violations[:5]:  # Max 5 por categoría
                print(f"\n  [{v.rule}] {v.type}")
                print(f"  {v.message}")
                print(f"  📍 {v.location}")
                print(f"  💡 {v.suggestion}")
                print(f"  ⚡ Impacto: {v.impact}")
                print(f"  🔧 Esfuerzo: {v.effort}")
            
            if len(violations) > 5:
                print(f"\n  ... y {len(violations) - 5} más")
            
            print()
        
        # Acciones recomendadas
        print("=" * 80)
        print("ACCIONES RECOMENDADAS:")
        print("-" * 80)
        
        if critical > 0:
            print("\n1. 🔴 URGENTE - Corregir antes del próximo deploy:")
            for v in by_category[ViolationCategory.CRITICAL][:3]:
                print(f"   - {v.type}: {v.suggestion}")
        
        if high > 0:
            print("\n2. 🟠 PLANEAR - Incluir en próximo sprint:")
            for v in by_category[ViolationCategory.HIGH][:3]:
                print(f"   - {v.type}: {v.suggestion}")
        
        if len(by_category[ViolationCategory.TECH_DEBT]) > 0:
            print("\n3. 🔵 REFACTORING TÉCNICO - Cuando haya tiempo:")
            for v in by_category[ViolationCategory.TECH_DEBT][:2]:
                print(f"   - {v.type}: {v.suggestion}")
        
        # Decision Log summary
        print()
        print("=" * 80)
        print("DECISION LOG:")
        print("-" * 80)
        
        # Obtener stats del decision log
        overdue = self.decision_log.check_overdue_reviews()
        all_decisions = self.decision_log.list_decisions()
        tech_debt_adr = [d for d in all_decisions if d.status == "tech_debt"]
        
        if all_decisions:
            print(f"Total ADRs: {len(all_decisions)} | Deuda técnica: {len(tech_debt_adr)} | Vencidas: {len(overdue)}")
            
            if overdue:
                print("\n⚠️  Decisiones pendientes de revisión:")
                for d in overdue[:3]:
                    print(f"   - [{d.id}] {d.title} (venció: {d.review_date})")
            
            if tech_debt_adr:
                print("\n🔵 Deuda técnica documentada:")
                for d in tech_debt_adr[:2]:
                    print(f"   - [{d.id}] {d.title}")
        else:
            print("No se encontró decision log")
        
        print()
        print("=" * 80)


def main():
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"
    
    auditor = SmartAuditor(str(blueprint_path))
    violations = auditor.audit()
    auditor.print_report()
    
    # Exit code basado en críticas
    critical = len([v for v in violations if v.category == ViolationCategory.CRITICAL])
    sys.exit(2 if critical > 0 else 0)


if __name__ == "__main__":
    main()
