#!/usr/bin/env python3
"""
Blueprint Auditor - Análisis de system.v0.json contra reglas arquitectónicas.

Detecta violaciones de:
1. Ruta única de ejecución
5. Separación ejecución/observación
9. Cierre único de tarea
- Duplicación de señales
- Riesgo de propagación de meta
- Complejidad del grafo
- Tipos de puertos
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from port_type_validator import PortTypeValidator


class BlueprintAuditor:
    """Audita un blueprint contra reglas arquitectónicas."""

    EXECUTION_PORTS = {
        "action.in",
        "plan.in",
        "command.in",
        "approval.in",
        "result.in",
        "approved.plan.out",
        "blocked.plan.out",
        "desktop.action.out",
        "browser.action.out",
        "system.action.out",
        "terminal.action.out",
    }
    OBSERVATION_PORTS = {
        "event.in",
        "event.out",
        "audit.in",
        "audit.out",
        "verification.out",
    }
    RESULT_PORTS = {"result.in", "result.out"}
    UI_PORTS = {
        "response.in",
        "response.out",
        "ui.response.in",
        "ui.response.out",
        "ui.state.in",
        "ui.state.out",
        "ui.render.request.out",
    }
    CONTROL_PORTS = {
        "signal.in",
        "signal.out",
        "context.in",
        "context.out",
        "callback.in",
        "callback.out",
        "request.in",
        "request.out",
    }

    def __init__(self, blueprint_path: str):
        self.blueprint_path = Path(blueprint_path)
        self.blueprint = self._load_blueprint()
        self.connections = self._parse_connections()
        self.violations = []
        self.warnings = []

    def _load_blueprint(self) -> dict:
        with open(self.blueprint_path, encoding="utf-8") as f:
            return json.load(f)

    def _split_endpoint(self, endpoint: str) -> tuple[str, str]:
        if ":" not in endpoint:
            return endpoint, ""
        module, port = endpoint.split(":", 1)
        return module, port

    def _parse_connections(self) -> dict:
        """Parsea conexiones en estructura navegable."""
        conns = {
            "by_source": defaultdict(list),
            "by_target": defaultdict(list),
            "execution_flow": [],
            "observation_flow": [],
        }

        for conn in self.blueprint.get("connections", []):
            from_mod, from_port = self._split_endpoint(conn["from"])
            to_mod, to_port = self._split_endpoint(conn["to"])

            conn_data = {
                "from_module": from_mod,
                "from_port": from_port,
                "to_module": to_mod,
                "to_port": to_port,
                "from": conn["from"],
                "to": conn["to"],
            }

            conns["by_source"][conn["from"]].append(conn_data)
            conns["by_target"][conn["to"]].append(conn_data)

            if self._is_execution_port(from_port) or self._is_execution_port(to_port):
                conns["execution_flow"].append(conn_data)
            elif self._is_observation_port(from_port) or self._is_observation_port(to_port):
                conns["observation_flow"].append(conn_data)

        return conns

    def _is_execution_port(self, port: str) -> bool:
        return any(
            port == p
            or port.endswith(p)
            or port.startswith(p.replace(".in", "").replace(".out", ""))
            for p in self.EXECUTION_PORTS
        )

    def _is_observation_port(self, port: str) -> bool:
        return any(port == p or port.endswith(p) for p in self.OBSERVATION_PORTS)

    def _is_result_port(self, port: str) -> bool:
        return any(port == p or port.endswith(p) for p in self.RESULT_PORTS)

    def _is_control_port(self, port: str) -> bool:
        return any(port == p or port.endswith(p) for p in self.CONTROL_PORTS)

    def audit(self) -> dict:
        """Ejecuta todas las auditorías."""
        self._audit_rule_1_single_execution_path()
        self._audit_rule_5_execution_vs_observation()
        self._audit_rule_9_single_task_closure()
        self._audit_signal_duplication()
        self._audit_meta_propagation_risk()
        self._audit_connection_complexity()
        self._audit_port_types()

        return {
            "violations": self.violations,
            "warnings": self.warnings,
            "stats": {
                "total_modules": len(self.blueprint.get("modules", [])),
                "total_connections": len(self.blueprint.get("connections", [])),
                "execution_flows": len(self.connections["execution_flow"]),
                "observation_flows": len(self.connections["observation_flow"]),
            },
        }

    def _audit_rule_1_single_execution_path(self):
        """
        Regla 1: Una sola ruta de ejecución real.
        Detecta rutas paralelas y loops simples.
        """
        execution_sources = defaultdict(list)
        for conn in self.connections["execution_flow"]:
            execution_sources[conn["from"]].append(conn)

        for source, conns in execution_sources.items():
            if len(conns) > 1:
                unique_targets = {c["to_module"] for c in conns}
                if len(unique_targets) > 1:
                    self.violations.append({
                        "rule": 1,
                        "severity": "high",
                        "type": "rutas_paralelas_ejecucion",
                        "source": source,
                        "targets": [c["to"] for c in conns],
                        "message": f"{source} tiene {len(conns)} salidas de ejecución a destinos diferentes",
                        "locations": [f"blueprints/system.v0.json: {source} -> {c['to']}" for c in conns],
                    })

        seen_pairs = set()
        for conn in self.blueprint.get("connections", []):
            from_mod, _ = self._split_endpoint(conn["from"])
            to_mod, _ = self._split_endpoint(conn["to"])

            if from_mod == to_mod:
                continue

            pair_key = tuple(sorted((from_mod, to_mod)))
            if pair_key in seen_pairs:
                continue

            reverse_exists = any(
                self._split_endpoint(c["from"])[0] == to_mod and self._split_endpoint(c["to"])[0] == from_mod
                for c in self.blueprint.get("connections", [])
            )

            if reverse_exists:
                seen_pairs.add(pair_key)
                self.warnings.append({
                    "rule": 1,
                    "severity": "medium",
                    "type": "posible_loop",
                    "modules": [from_mod, to_mod],
                    "message": f"Posible loop: {from_mod} <-> {to_mod}",
                    "location": f"blueprints/system.v0.json: conexiones entre {from_mod} y {to_mod}",
                })

    def _audit_rule_5_execution_vs_observation(self):
        """
        Regla 5: Separar ejecución de observación.
        """
        incoming = self.connections["by_target"]

        for module in self.blueprint.get("modules", []):
            module_incoming = [key for key in incoming.keys() if key.startswith(f"{module}:")]

            execution_ins = [
                key for key in module_incoming
                if self._is_execution_port(self._split_endpoint(key)[1])
            ]
            observation_ins = [
                key for key in module_incoming
                if self._is_observation_port(self._split_endpoint(key)[1])
            ]

            if execution_ins and observation_ins:
                exec_ports = {self._split_endpoint(k)[1] for k in execution_ins}
                obs_ports = {self._split_endpoint(k)[1] for k in observation_ins}

                shared_prefixes = set()
                for ep in exec_ports:
                    for op in obs_ports:
                        if ep.split(".")[0] == op.split(".")[0]:
                            shared_prefixes.add(ep.split(".")[0])

                if shared_prefixes:
                    self.warnings.append({
                        "rule": 5,
                        "severity": "medium",
                        "type": "mezcla_flujos",
                        "module": module,
                        "exec_ports": sorted(exec_ports),
                        "obs_ports": sorted(obs_ports),
                        "message": f"{module} tiene puertos de ejecución y observación con prefijos similares",
                        "location": f"blueprints/system.v0.json: module {module}",
                    })

        result_sources = defaultdict(list)
        for conn in self.blueprint.get("connections", []):
            from_mod, from_port = self._split_endpoint(conn["from"])
            if from_port == "result.out":
                result_sources[conn["from"]].append(conn["to"])

        for source, targets in result_sources.items():
            exec_targets = []
            obs_targets = []

            for t in targets:
                _, to_port = self._split_endpoint(t)
                if self._is_execution_port(to_port) or any(x in t for x in ["supervisor", "approval", "verifier"]):
                    exec_targets.append(t)
                if self._is_observation_port(to_port) or any(x in t for x in ["memory", "ui", "guide"]):
                    obs_targets.append(t)

            if exec_targets and obs_targets:
                self.violations.append({
                    "rule": 5,
                    "severity": "high",
                    "type": "result_ambiguo",
                    "source": source,
                    "exec_targets": exec_targets,
                    "obs_targets": obs_targets,
                    "all_targets": targets,
                    "message": f"{source} mezcla targets de ejecución y observación desde result.out",
                    "locations": [f"blueprints/system.v0.json: {source} -> {t}" for t in targets],
                })

    def _audit_rule_9_single_task_closure(self):
        """
        Regla 9: Un solo resultado final por tarea.
        """
        closure_modules = {"supervisor.main", "approval.main"}

        for closer in closure_modules:
            incoming_results = [
                c for c in self.blueprint.get("connections", [])
                if c["to"].startswith(f"{closer}:") and "result" in self._split_endpoint(c["to"])[1]
            ]

            if len(incoming_results) > 3:
                sources = [c["from"] for c in incoming_results]
                self.violations.append({
                    "rule": 9,
                    "severity": "high",
                    "type": "multiples_cierres",
                    "closer": closer,
                    "sources": sources,
                    "count": len(incoming_results),
                    "message": f"{closer} recibe resultados de {len(incoming_results)} fuentes diferentes",
                    "locations": [f"blueprints/system.v0.json: {s} -> {closer}" for s in sources],
                })

        workers = [m for m in self.blueprint.get("modules", []) if "worker" in m]
        for worker in workers:
            worker_results = [
                c for c in self.blueprint.get("connections", [])
                if c["from"].startswith(f"{worker}:") and self._split_endpoint(c["from"])[1] == "result.out"
            ]

            targets_by_module = defaultdict(list)
            for conn in worker_results:
                mod, _ = self._split_endpoint(conn["to"])
                targets_by_module[mod].append(conn["to"])

            exec_targets = [
                m for m in targets_by_module.keys()
                if any(x in m for x in ["supervisor", "approval", "verifier"])
            ]

            if len(exec_targets) > 1:
                self.violations.append({
                    "rule": 9,
                    "severity": "high",
                    "type": "worker_multiples_cierres",
                    "worker": worker,
                    "targets": list(targets_by_module.keys()),
                    "message": f"{worker} envía resultados a múltiples módulos de cierre",
                    "locations": [
                        f"blueprints/system.v0.json: {worker}:result.out -> {t}"
                        for t in targets_by_module.keys()
                    ],
                })

    def _audit_signal_duplication(self):
        signal_connections = [
            c for c in self.blueprint.get("connections", [])
            if "signal" in c["from"] or "signal" in c["to"]
        ]

        signal_sources = defaultdict(list)
        for conn in signal_connections:
            signal_sources[conn["from"]].append(conn["to"])

        for source, targets in signal_sources.items():
            unique_targets = sorted(set(targets))
            if len(unique_targets) > 2:
                self.warnings.append({
                    "rule": "signal",
                    "severity": "medium",
                    "type": "signal_broadcast",
                    "source": source,
                    "targets": unique_targets,
                    "count": len(unique_targets),
                    "message": f"{source} envía señales a {len(unique_targets)} destinos (posible broadcast innecesario)",
                    "locations": [f"blueprints/system.v0.json: {source} -> {t}" for t in unique_targets],
                })

    def _audit_meta_propagation_risk(self):
        for conn in self.blueprint.get("connections", []):
            _, to_port = self._split_endpoint(conn["to"])
            to_mod, _ = self._split_endpoint(conn["to"])

            if not (
                self._is_execution_port(to_port)
                or self._is_control_port(to_port)
                or self._is_result_port(to_port)
            ):
                continue

            outgoing = [
                c for c in self.blueprint.get("connections", [])
                if self._split_endpoint(c["from"])[0] == to_mod
            ]

            if len(outgoing) > 1:
                self.warnings.append({
                    "rule": "meta",
                    "severity": "low",
                    "type": "propagation_risk",
                    "module": to_mod,
                    "incoming": conn["from"],
                    "outgoing": [c["to"] for c in outgoing],
                    "message": f"{to_mod} recibe y re-emite; asegurar que propaga meta/trace_id",
                    "location": f"blueprints/system.v0.json: módulo {to_mod}",
                })

    def _audit_connection_complexity(self):
        total = len(self.blueprint.get("connections", []))
        modules = len(self.blueprint.get("modules", []))

        max_possible = modules * (modules - 1)
        density = total / max_possible if max_possible > 0 else 0

        if density > 0.1:
            self.warnings.append({
                "rule": "complexity",
                "severity": "low",
                "type": "alta_densidad",
                "connections": total,
                "modules": modules,
                "density": round(density, 3),
                "message": f"Grafo denso: {total} conexiones entre {modules} módulos (densidad: {round(density, 3)})",
            })

    def _audit_port_types(self):
        validator = PortTypeValidator(self.blueprint)
        report = validator.validate_all()

        for v in report.get("violations", []):
            severity = v.get("severity", "low")
            payload = {
                "rule": "port_type",
                "severity": "high" if severity == "critical" else ("medium" if severity in ("high", "medium") else "low"),
                "type": v.get("violation", "unknown_port_violation"),
                "message": v.get("message", "Port type violation"),
            }

            connection = v.get("connection")
            if connection:
                payload["locations"] = [
                    f"blueprints/system.v0.json: {connection.get('from')} -> {connection.get('to')}"
                ]

            if severity == "low":
                self.warnings.append(payload)
            else:
                self.violations.append(payload)

        self.warnings.append({
            "rule": "port_stats",
            "severity": "info",
            "type": "port_distribution",
            "message": f"Puertos auditados: {report.get('summary', {})}",
        })

    def print_report(self, results: dict):
        print("=" * 70)
        print("BLUEPRINT AUDIT REPORT")
        print("=" * 70)
        print(f"Archivo: {self.blueprint_path}")
        print(f"Módulos: {results['stats']['total_modules']}")
        print(f"Conexiones: {results['stats']['total_connections']}")
        print(f"Flujos de ejecución: {results['stats']['execution_flows']}")
        print(f"Flujos de observación: {results['stats']['observation_flows']}")
        print()

        if results["violations"]:
            print(f"🚨 VIOLACIONES ({len(results['violations'])}):")
            print("-" * 70)
            for v in results["violations"]:
                print(f"\n[{v['severity'].upper()}] Regla #{v['rule']}: {v['type']}")
                print(f"  {v['message']}")
                if "locations" in v:
                    for loc in v["locations"][:3]:
                        print(f"    → {loc}")
                    if len(v["locations"]) > 3:
                        print(f"    ... y {len(v['locations']) - 3} más")
        print()

        if results["warnings"]:
            print(f"⚠️  ADVERTENCIAS ({len(results['warnings'])}):")
            print("-" * 70)
            for w in results["warnings"]:
                print(f"\n[{w['severity'].upper()}] {w['type']}")
                print(f"  {w['message']}")

        print()
        print("=" * 70)
        print(f"Resumen: {len(results['violations'])} violaciones, {len(results['warnings'])} advertencias")
        print("=" * 70)


def main():
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"

    if not blueprint_path.exists():
        print(f"Error: No se encuentra {blueprint_path}")
        sys.exit(1)

    auditor = BlueprintAuditor(str(blueprint_path))
    results = auditor.audit()
    auditor.print_report(results)

    sys.exit(1 if results["violations"] else 0)


if __name__ == "__main__":
    main()