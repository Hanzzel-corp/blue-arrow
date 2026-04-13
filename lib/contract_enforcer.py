#!/usr/bin/env python3
"""
Contract Enforcer - Validación progresiva de contratos (3 fases).

Fase A: Warning solamente (compatibilidad)
Fase B: Warning + métricas por módulo (transparencia)
Fase C: Rechazo estricto para core (gobernanza)

Configuración en config/contract_phase.json
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ContractPhase(Enum):
    """Fases de enforcement de contratos."""
    PHASE_A = "A"
    PHASE_B = "B"
    PHASE_C = "C"


@dataclass
class ContractViolation:
    """Violación de contrato detectada."""
    module: str
    violation_type: str
    field: str
    expected: str
    actual: str
    message: str
    severity: str  # critical, high, medium, low
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModuleMetrics:
    """Métricas de cumplimiento por módulo (Fase B)."""
    module: str
    tier: str  # core, satellite
    total_messages: int = 0
    messages_with_violations: int = 0
    total_violations: int = 0
    missing_trace_id: int = 0
    missing_meta: int = 0
    invalid_meta_source: int = 0
    compliance_rate: float = 100.0
    last_violation: Optional[float] = None


class ContractEnforcer:
    """
    Enfoca contratos según fase configurada.

    Contrato mínimo:
    - trace_id: obligatorio (string)
    - meta: obligatorio (object)
    - meta.source: obligatorio (cli|telegram|internal|system)
    - meta.timestamp: auto-generado si falta
    """

    CORE_MODULES = {
        "supervisor.main",
        "router.main",
        "agent.main",
        "planner.main",
        "safety.guard.main",
        "approval.main",
        "worker.python.desktop",
        "worker.python.terminal",
        "worker.python.system",
        "worker.python.browser",
        "memory.log.main",
        "ui.state.main",
        "interface.main",
        "interface.telegram",
    }

    VALID_SOURCES = {"cli", "telegram", "internal", "system"}

    def __init__(self, phase: Optional[ContractPhase] = None, config_path: Optional[str] = None):
        self.phase = phase or self._load_phase(config_path)
        self.violations: List[ContractViolation] = []
        self.metrics: Dict[str, ModuleMetrics] = {}
        self.rejected_messages: List[Dict] = []

    def _load_phase(self, config_path: Optional[str]) -> ContractPhase:
        """Carga fase desde configuración."""
        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "contract_phase.json"
        else:
            config_path = Path(config_path)

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                phase_str = config.get("phase", "A")
                return ContractPhase(phase_str)
            except Exception:
                pass

        return ContractPhase.PHASE_A

    def validate_message(self, message: Dict, module_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Valida un mensaje contra el contrato.

        Returns:
            (is_valid, enriched_message_or_none)
            Fase A/B: siempre retorna True, puede enriquecer
            Fase C: retorna False para core si viola crítico
        """
        violations = self._check_contract(message, module_id)

        if violations:
            self.violations.extend(violations)

        if self.phase in (ContractPhase.PHASE_B, ContractPhase.PHASE_C):
            self._update_metrics(module_id, violations)

        if self.phase == ContractPhase.PHASE_C:
            is_core = module_id in self.CORE_MODULES
            critical_violations = [v for v in violations if v.severity == "critical"]

            if is_core and critical_violations:
                self.rejected_messages.append({
                    "message": message,
                    "module": module_id,
                    "violations": [v.__dict__ for v in critical_violations],
                    "timestamp": time.time(),
                })
                return False, None

        enriched = self._enrich_message(message, module_id)
        return True, enriched

    def _check_contract(self, message: Dict, module_id: str) -> List[ContractViolation]:
        """Verifica cumplimiento de contrato."""
        violations: List[ContractViolation] = []

        trace_id = message.get("trace_id")
        if not trace_id:
            violations.append(ContractViolation(
                module=module_id,
                violation_type="missing_field",
                field="trace_id",
                expected="string",
                actual="None",
                message="trace_id es obligatorio para trazabilidad",
                severity="critical",
            ))
        elif not isinstance(trace_id, str):
            violations.append(ContractViolation(
                module=module_id,
                violation_type="invalid_type",
                field="trace_id",
                expected="string",
                actual=type(trace_id).__name__,
                message=f"trace_id debe ser string, es {type(trace_id).__name__}",
                severity="high",
            ))

        meta = message.get("meta")
        if not meta or not isinstance(meta, dict):
            violations.append(ContractViolation(
                module=module_id,
                violation_type="missing_field",
                field="meta",
                expected="object",
                actual=type(meta).__name__ if meta is not None else "None",
                message="meta es obligatorio para contexto",
                severity="critical",
            ))
        else:
            source = meta.get("source")
            if not source:
                violations.append(ContractViolation(
                    module=module_id,
                    violation_type="missing_field",
                    field="meta.source",
                    expected="cli|telegram|internal|system",
                    actual="None",
                    message="meta.source es obligatorio",
                    severity="high",
                ))
            elif source not in self.VALID_SOURCES:
                violations.append(ContractViolation(
                    module=module_id,
                    violation_type="invalid_value",
                    field="meta.source",
                    expected="cli|telegram|internal|system",
                    actual=source,
                    message=f"meta.source='{source}' no es válido",
                    severity="medium",
                ))

        return violations

    def _enrich_message(self, message: Dict, module_id: str) -> Dict:
        """Enriquece mensaje con campos faltantes (modo compatibilidad)."""
        enriched = dict(message)

        if not enriched.get("trace_id"):
            enriched["trace_id"] = f"{module_id}-{int(time.time() * 1000)}-{id(message) % 10000}"

        if not enriched.get("meta") or not isinstance(enriched.get("meta"), dict):
            enriched["meta"] = {}

        if not enriched["meta"].get("source"):
            enriched["meta"]["source"] = "internal"

        if not enriched["meta"].get("timestamp"):
            enriched["meta"]["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        return enriched

    def _update_metrics(self, module_id: str, violations: List[ContractViolation]):
        """Actualiza métricas por módulo (Fase B/C)."""
        if module_id not in self.metrics:
            tier = "core" if module_id in self.CORE_MODULES else "satellite"
            self.metrics[module_id] = ModuleMetrics(module=module_id, tier=tier)

        metrics = self.metrics[module_id]
        metrics.total_messages += 1

        if violations:
            metrics.messages_with_violations += 1
            metrics.total_violations += len(violations)
            metrics.last_violation = time.time()

            for v in violations:
                if v.field == "trace_id":
                    metrics.missing_trace_id += 1
                elif v.field == "meta":
                    metrics.missing_meta += 1
                elif v.field == "meta.source":
                    metrics.invalid_meta_source += 1

        if metrics.total_messages > 0:
            metrics.compliance_rate = round(
                ((metrics.total_messages - metrics.messages_with_violations) / metrics.total_messages) * 100,
                2,
            )

    def get_warnings(self) -> List[str]:
        """Genera warnings de todas las violaciones (Fase A/B)."""
        return [f"[{v.severity.upper()}] {v.module}: {v.message}" for v in self.violations]

    def get_metrics_report(self) -> Dict:
        """Genera reporte de métricas (Fase B/C)."""
        if not self.metrics:
            return {"status": "no_data"}

        core_modules = [m for m in self.metrics.values() if m.tier == "core"]
        satellite_modules = [m for m in self.metrics.values() if m.tier == "satellite"]

        return {
            "status": "ok",
            "phase": self.phase.value,
            "summary": {
                "total_modules": len(self.metrics),
                "core_modules": len(core_modules),
                "satellite_modules": len(satellite_modules),
                "total_violations": sum(m.total_violations for m in self.metrics.values()),
                "messages_with_violations": sum(m.messages_with_violations for m in self.metrics.values()),
                "rejected_messages": len(self.rejected_messages) if self.phase == ContractPhase.PHASE_C else 0,
            },
            "core_compliance": {
                "avg_compliance_rate": round(
                    sum(m.compliance_rate for m in core_modules) / len(core_modules), 2
                ) if core_modules else 0,
                "modules_with_violations": len([m for m in core_modules if m.total_violations > 0]),
            },
            "satellite_compliance": {
                "avg_compliance_rate": round(
                    sum(m.compliance_rate for m in satellite_modules) / len(satellite_modules), 2
                ) if satellite_modules else 0,
                "modules_with_violations": len([m for m in satellite_modules if m.total_violations > 0]),
            },
            "modules": {
                m.module: {
                    "tier": m.tier,
                    "total_messages": m.total_messages,
                    "messages_with_violations": m.messages_with_violations,
                    "total_violations": m.total_violations,
                    "compliance_rate": m.compliance_rate,
                    "missing_trace_id": m.missing_trace_id,
                    "missing_meta": m.missing_meta,
                    "invalid_meta_source": m.invalid_meta_source,
                }
                for m in self.metrics.values()
            },
            "rejected_messages_sample": [
                {
                    "module": r["module"],
                    "violations_count": len(r["violations"]),
                    "timestamp": r["timestamp"],
                }
                for r in self.rejected_messages[:5]
            ] if self.phase == ContractPhase.PHASE_C else [],
        }

    def print_report(self):
        """Imprime reporte según fase."""
        print("=" * 70)
        print(f"CONTRACT ENFORCER - Fase {self.phase.value}")
        print("=" * 70)
        print()

        if self.phase == ContractPhase.PHASE_A:
            print("Modo: Warning solamente (compatibilidad)")
            print()
            warnings = self.get_warnings()
            if warnings:
                print(f"Warnings ({len(warnings)}):")
                for w in warnings[:10]:
                    print(f"  {w}")
                if len(warnings) > 10:
                    print(f"  ... y {len(warnings) - 10} más")
            else:
                print("✓ No hay violaciones de contrato")

        elif self.phase in (ContractPhase.PHASE_B, ContractPhase.PHASE_C):
            report = self.get_metrics_report()

            print(f"Modo: {'Métricas' if self.phase == ContractPhase.PHASE_B else 'Rechazo estricto'}")
            print()
            print("Resumen:")
            print(f"  Módulos monitoreados: {report['summary']['total_modules']}")
            print(f"  Core: {report['summary']['core_modules']}, Satellite: {report['summary']['satellite_modules']}")
            print(f"  Total violaciones: {report['summary']['total_violations']}")
            print(f"  Mensajes con violaciones: {report['summary']['messages_with_violations']}")

            if self.phase == ContractPhase.PHASE_C:
                print(f"  Mensajes rechazados: {report['summary']['rejected_messages']}")

            print()
            print("Cumplimiento Core:")
            print(f"  Promedio: {report['core_compliance']['avg_compliance_rate']}%")
            print(f"  Módulos con violaciones: {report['core_compliance']['modules_with_violations']}")

            print()
            print("Cumplimiento Satellite:")
            print(f"  Promedio: {report['satellite_compliance']['avg_compliance_rate']}%")

            if report["modules"]:
                print()
                print("Módulos con menor cumplimiento:")
                sorted_modules = sorted(
                    report["modules"].items(),
                    key=lambda x: x[1]["compliance_rate"],
                )
                for module, data in sorted_modules[:5]:
                    if data["total_violations"] > 0:
                        print(
                            f"  {module} ({data['tier']}): {data['compliance_rate']}% "
                            f"({data['total_violations']} violaciones)"
                        )

        print()
        print("=" * 70)


def create_phase_config(phase: ContractPhase):
    """Crea archivo de configuración de fase."""
    config_path = PROJECT_ROOT / "config" / "contract_phase.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "phase": phase.value,
        "description": {
            "A": "Warning solamente - modo compatibilidad",
            "B": "Warning + métricas - transparencia",
            "C": "Rechazo estricto para core - gobernanza",
        },
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"✓ Configuración guardada: {config_path}")
    print(f"  Fase: {phase.value} - {config['description'][phase.value]}")


def main():
    if len(sys.argv) > 1:
        phase_arg = sys.argv[1].upper()
        if phase_arg in ("A", "B", "C"):
            phase = ContractPhase(phase_arg)
            create_phase_config(phase)
            return

    print("DEMO: Contract Enforcer")
    print()

    for test_phase in [ContractPhase.PHASE_A, ContractPhase.PHASE_B, ContractPhase.PHASE_C]:
        enforcer = ContractEnforcer(phase=test_phase)

        test_messages = [
            {"module": "agent.main", "payload": {}},
            {"module": "agent.main", "trace_id": "abc", "payload": {}},
            {"module": "router.main", "trace_id": "xyz", "meta": {"source": "internal"}, "payload": {}},
            {"module": "gamification.main", "trace_id": "123", "meta": {"source": "invalid"}, "payload": {}},
        ]

        for msg in test_messages:
            module = msg["module"]
            payload = {k: v for k, v in msg.items() if k != "module"}

            is_valid, enriched = enforcer.validate_message(payload, module)

            if not is_valid:
                print(f"  [RECHAZADO] {module}: mensaje rechazado (Fase C)")

        enforcer.print_report()
        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
