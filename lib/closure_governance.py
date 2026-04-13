#!/usr/bin/env python3
"""
Closure Governance - Validación de gobierno de cierre de tareas.

Implementa:
- supervisor.main = único closer principal
- workers = informers (reportan resultado, no cierran)
- verifier = enriquecedor (verifica, no cierra)
- observers = solo escuchan (ui, memory, etc.)
- control = aprobación/señales/cancelación
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum


class ClosureRole(Enum):
    """Roles en el flujo de cierre de tareas."""
    CLOSER = "closer"
    INFORMER = "informer"
    VERIFIER = "verifier"
    OBSERVER = "observer"
    CONTROL = "control"
    UNKNOWN = "unknown"


@dataclass
class ClosureViolation:
    """Violación del gobierno de cierre."""
    module: str
    role_expected: ClosureRole
    role_violation: str
    severity: str
    message: str
    location: str


class ClosureGovernance:
    """
    Valida que el blueprint respete el gobierno de cierre.

    Regla #9:
    - supervisor.main es el closer principal
    - verifier.engine.main solo enruta/valida hacia supervisor
    - workers reportan, no cierran
    - observers no deben cerrar ni ejecutar
    """

    ROLE_DEFINITIONS = {
        "supervisor.main": ClosureRole.CLOSER,

        "worker.python.desktop": ClosureRole.INFORMER,
        "worker.python.terminal": ClosureRole.INFORMER,
        "worker.python.system": ClosureRole.INFORMER,
        "worker.python.browser": ClosureRole.INFORMER,
        "ai.assistant.main": ClosureRole.INFORMER,

        "verifier.engine.main": ClosureRole.VERIFIER,

        "approval.main": ClosureRole.CONTROL,
        "safety.guard.main": ClosureRole.CONTROL,
        "phase.engine.main": ClosureRole.CONTROL,

        "memory.log.main": ClosureRole.OBSERVER,
        "ui.state.main": ClosureRole.OBSERVER,
        "interface.main": ClosureRole.OBSERVER,
        "interface.telegram": ClosureRole.OBSERVER,
        "guide.main": ClosureRole.OBSERVER,
        "gamification.main": ClosureRole.OBSERVER,
        "ai.learning.engine.main": ClosureRole.OBSERVER,
        "ai.self.audit.main": ClosureRole.OBSERVER,
        "ai.memory.semantic.main": ClosureRole.OBSERVER,
        "apps.session.main": ClosureRole.OBSERVER,
        "telegram.hud.main": ClosureRole.OBSERVER,
        "telegram.menu.main": ClosureRole.OBSERVER,
        "system.menu.main": ClosureRole.OBSERVER,
        "memory.menu.main": ClosureRole.OBSERVER,
        "apps.menu.main": ClosureRole.OBSERVER,
        "project.audit.main": ClosureRole.OBSERVER,
    }

    VALID_CLOSURE_PATHS = {
        "supervisor.main:result.in": {
            "verifier.engine.main:result.out",
            "worker.python.desktop:result.out",
            "worker.python.terminal:result.out",
            "worker.python.system:result.out",
            "worker.python.browser:result.out",
            "ai.assistant.main:result.out",
        },
        "verifier.engine.main:result.in": {
            "worker.python.desktop:result.out",
            "worker.python.terminal:result.out",
            "worker.python.system:result.out",
            "worker.python.browser:result.out",
        },
    }

    SAFE_OBSERVER_INPUT_PORTS = {
        "event.in",
        "context.in",
        "memory.in",
        "query.in",
        "ui.response.in",
        "ui.state.in",
        "response.in",
    }

    def __init__(self, blueprint_path: str):
        self.blueprint_path = Path(blueprint_path)
        self.blueprint = self._load_blueprint()
        self.violations: List[ClosureViolation] = []

    def _load_blueprint(self) -> Dict:
        with open(self.blueprint_path, encoding="utf-8") as f:
            return json.load(f)

    def _split_endpoint(self, endpoint: str) -> Tuple[str, str]:
        if ":" not in endpoint:
            return endpoint, ""
        return endpoint.split(":", 1)

    def _role_of(self, module_id: str) -> ClosureRole:
        return self.ROLE_DEFINITIONS.get(module_id, ClosureRole.UNKNOWN)

    def validate(self) -> List[ClosureViolation]:
        """Valida todo el gobierno de cierre."""
        self.violations = []

        self._validate_unique_closer()
        self._validate_informer_paths()
        self._validate_verifier_chain()
        self._validate_observer_isolation()
        self._validate_no_closure_broadcast()

        return self.violations

    def _validate_unique_closer(self):
        """
        Solo supervisor.main y verifier.engine.main deberían recibir result.in.
        Además, si existe regla explícita en VALID_CLOSURE_PATHS, debe cumplirse.
        """
        for conn in self.blueprint.get("connections", []):
            from_ep = conn.get("from", "")
            to_ep = conn.get("to", "")

            from_mod, _ = self._split_endpoint(from_ep)
            to_mod, to_port = self._split_endpoint(to_ep)

            if to_port != "result.in":
                continue

            if to_mod not in {"supervisor.main", "verifier.engine.main"}:
                self.violations.append(
                    ClosureViolation(
                        module=from_mod,
                        role_expected=self._role_of(from_mod),
                        role_violation="closure_to_non_closer",
                        severity="CRITICAL",
                        message=f"{from_mod} envía resultado a {to_mod}:result.in (solo supervisor/verifier deberían recibir result.in)",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )
                continue

            allowed_sources = self.VALID_CLOSURE_PATHS.get(to_ep)
            if allowed_sources is not None and from_ep not in allowed_sources:
                self.violations.append(
                    ClosureViolation(
                        module=from_mod,
                        role_expected=self._role_of(from_mod),
                        role_violation="invalid_closure_path",
                        severity="HIGH",
                        message=f"{from_ep} no es una fuente permitida para {to_ep}",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )

    def _validate_informer_paths(self):
        """
        Informers pueden emitir result.out solo hacia verifier o supervisor.
        """
        informers = {m for m, r in self.ROLE_DEFINITIONS.items() if r == ClosureRole.INFORMER}

        for conn in self.blueprint.get("connections", []):
            from_ep = conn.get("from", "")
            to_ep = conn.get("to", "")
            from_mod, from_port = self._split_endpoint(from_ep)
            to_mod, _ = self._split_endpoint(to_ep)

            if from_mod not in informers:
                continue

            if from_port == "result.out":
                if to_mod not in {"verifier.engine.main", "supervisor.main"}:
                    self.violations.append(
                        ClosureViolation(
                            module=from_mod,
                            role_expected=ClosureRole.INFORMER,
                            role_violation="informer_closure_broadcast",
                            severity="HIGH",
                            message=f"{from_mod} (informer) envía result.out a {to_mod} (debería ser solo supervisor/verifier)",
                            location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                        )
                    )

    def _validate_verifier_chain(self):
        """
        verifier.engine.main:result.out debe terminar solo en supervisor.main:result.in.
        """
        verifier_outputs = [
            c for c in self.blueprint.get("connections", [])
            if c.get("from", "").startswith("verifier.engine.main:result.out")
        ]

        for conn in verifier_outputs:
            from_ep = conn["from"]
            to_ep = conn["to"]
            to_mod, to_port = self._split_endpoint(to_ep)

            if not (to_mod == "supervisor.main" and to_port == "result.in"):
                self.violations.append(
                    ClosureViolation(
                        module="verifier.engine.main",
                        role_expected=ClosureRole.VERIFIER,
                        role_violation="verifier_does_not_close_to_supervisor",
                        severity="CRITICAL",
                        message=f"verifier.engine.main envía resultado a {to_ep} (DEBE ir a supervisor.main:result.in)",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )

    def _validate_observer_isolation(self):
        """
        Observers no deben participar del flujo de ejecución/cierre.
        Solo se permiten rutas observacionales seguras.
        """
        observers = {m for m, r in self.ROLE_DEFINITIONS.items() if r == ClosureRole.OBSERVER}

        for conn in self.blueprint.get("connections", []):
            from_ep = conn.get("from", "")
            to_ep = conn.get("to", "")

            from_mod, from_port = self._split_endpoint(from_ep)
            _, to_port = self._split_endpoint(to_ep)

            if from_mod not in observers:
                continue

            if from_port == "result.out":
                self.violations.append(
                    ClosureViolation(
                        module=from_mod,
                        role_expected=ClosureRole.OBSERVER,
                        role_violation="observer_emits_result_out",
                        severity="HIGH",
                        message=f"{from_mod} (observer) emite result.out y no debería cerrar ni informar",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )
                continue

            if to_port in {"action.in", "plan.in", "result.in"}:
                self.violations.append(
                    ClosureViolation(
                        module=from_mod,
                        role_expected=ClosureRole.OBSERVER,
                        role_violation="observer_in_execution_flow",
                        severity="MEDIUM",
                        message=f"{from_mod} (observer) envía a {to_ep} y no debería participar en flujo de ejecución/cierre",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )
                continue

            if to_port and to_port not in self.SAFE_OBSERVER_INPUT_PORTS and from_port != "event.out":
                self.violations.append(
                    ClosureViolation(
                        module=from_mod,
                        role_expected=ClosureRole.OBSERVER,
                        role_violation="observer_to_unexpected_port",
                        severity="LOW",
                        message=f"{from_mod} (observer) envía a puerto no esperado: {to_ep}",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )

    def _validate_no_closure_broadcast(self):
        """
        supervisor.main:result.out no debería hacer broadcast operativo.
        Solo se tolera log/memoria si existiera.
        """
        supervisor_result_outs = [
            c for c in self.blueprint.get("connections", [])
            if c.get("from", "").startswith("supervisor.main:result.out")
        ]

        for conn in supervisor_result_outs:
            from_ep = conn["from"]
            to_ep = conn["to"]
            to_mod, _ = self._split_endpoint(to_ep)

            if to_mod != "memory.log.main":
                self.violations.append(
                    ClosureViolation(
                        module="supervisor.main",
                        role_expected=ClosureRole.CLOSER,
                        role_violation="closer_broadcast",
                        severity="MEDIUM",
                        message=f"supervisor.main (closer) hace broadcast de result.out a {to_mod}",
                        location=f"blueprints/system.v0.json: {from_ep} -> {to_ep}",
                    )
                )

    def print_report(self):
        """Imprime reporte de violaciones."""
        print("=" * 70)
        print("CLOSURE GOVERNANCE VALIDATION REPORT")
        print("=" * 70)
        print()

        if not self.violations:
            print("✓ No se encontraron violaciones del gobierno de cierre")
            print()
            print("Roles validados:")
            print("  • supervisor.main = CLOSER (único principal)")
            print("  • workers = INFORMERS (reportan a verifier/supervisor)")
            print("  • verifier.engine.main = VERIFIER (enriquece para supervisor)")
            print("  • ui/memory/gamification/learning = OBSERVERS (solo escuchan)")
            print()
            print("=" * 70)
            return

        critical = [v for v in self.violations if v.severity == "CRITICAL"]
        high = [v for v in self.violations if v.severity == "HIGH"]
        medium = [v for v in self.violations if v.severity == "MEDIUM"]
        low = [v for v in self.violations if v.severity == "LOW"]

        if critical:
            print(f"🚨 CRITICAL ({len(critical)}):")
            for v in critical:
                print(f"\n  [{v.module}] {v.role_violation}")
                print(f"    {v.message}")
                print(f"    → {v.location}")

        if high:
            print(f"\n⚠️  HIGH ({len(high)}):")
            for v in high:
                print(f"\n  [{v.module}] {v.role_violation}")
                print(f"    {v.message}")
                print(f"    → {v.location}")

        if medium:
            print(f"\n📋 MEDIUM ({len(medium)}):")
            for v in medium:
                print(f"\n  [{v.module}] {v.role_violation}")
                print(f"    {v.message}")
                print(f"    → {v.location}")

        if low:
            print(f"\nℹ️  LOW ({len(low)}):")
            for v in low:
                print(f"\n  [{v.module}] {v.role_violation}")
                print(f"    {v.message}")
                print(f"    → {v.location}")

        print()
        print("=" * 70)
        print(f"Resumen: {len(self.violations)} violaciones")
        print(f"  - CRITICAL: {len(critical)}")
        print(f"  - HIGH: {len(high)}")
        print(f"  - MEDIUM: {len(medium)}")
        print(f"  - LOW: {len(low)}")
        print("=" * 70)


def main():
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"

    governance = ClosureGovernance(str(blueprint_path))
    violations = governance.validate()
    governance.print_report()

    critical_count = len([v for v in violations if v.severity == "CRITICAL"])
    high_count = len([v for v in violations if v.severity == "HIGH"])

    if critical_count > 0:
        sys.exit(2)
    elif high_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
