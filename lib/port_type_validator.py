#!/usr/bin/env python3
"""
Port Type Validator - Clasificación y validación de puertos por tipo semántico.

Tipos:
- execution: Flujo real de acciones (action.in, plan.in, result.out)
- observation: Monitoreo sin side-effects (event.out, event.in)
- ui: Interfaces de usuario (response.in, ui.response.out)
- persistence: Almacenamiento (memory.in, query.in)
- control: Señales de control (signal.in, approval.in)
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum


class PortType(Enum):
    """Tipos semánticos de puertos."""
    EXECUTION = "execution"
    OBSERVATION = "observation"
    UI = "ui"
    PERSISTENCE = "persistence"
    CONTROL = "control"
    UNKNOWN = "unknown"


@dataclass
class PortViolation:
    """Violación de tipo de puerto."""
    connection_from: str
    connection_to: str
    violation_type: str
    expected: str
    actual: str
    severity: str
    message: str


class PortTypeValidator:
    """
    Valida que las conexiones del blueprint respeten los tipos de puertos.
    """

    # Mapeo de patrones de puerto a tipo
    PORT_PATTERNS = {
        # EXECUTION - flujo real de acciones
        PortType.EXECUTION: {
            "action.in", "action.out",
            "plan.in", "plan.out",
            "command.in", "command.out",
            "result.in", "result.out",
            "approval.in", "approval.out",
        },
        
        # OBSERVATION - monitoreo
        PortType.OBSERVATION: {
            "event.in", "event.out",
            "audit.in", "audit.out",
        },
        
        # UI - interfaces
        PortType.UI: {
            "response.in", "response.out",
            "ui.response.in", "ui.response.out",
            "ui.state.in", "ui.state.out",
            "ui.render.request.out",
        },
        
        # PERSISTENCE - almacenamiento
        PortType.PERSISTENCE: {
            "memory.in", "memory.out",
            "query.in", "query.out",
            "app.session.in", "app.session.out",
            "memory.sync.out",
        },
        
        # CONTROL - señales
        PortType.CONTROL: {
            "signal.in", "signal.out",
            "context.in", "context.out",
            "callback.in", "callback.out",
        },
    }

    # Reglas de validación
    VALIDATION_RULES = {
        # Un puerto de ejecución NO debería conectar a múltiples ejecuciones
        "execution_broadcast": {
            "description": "Puerto de ejecución hace broadcast",
            "severity": "high"
        },
        
        # Mezcla execution -> observation es válida pero con advertencia
        "execution_to_observation": {
            "description": "Ejecución conecta a observación",
            "severity": "low"
        },
        
        # Observation NO debería conectar a execution
        "observation_to_execution": {
            "description": "Observación intenta afectar ejecución",
            "severity": "critical"
        },
        
        # UI puede recibir de execution (para mostrar)
        "execution_to_ui": {
            "description": "Ejecución conecta a UI (válido)",
            "severity": "info"
        },
        
        # UI NO debería conectar a execution
        "ui_to_execution": {
            "description": "UI intenta disparar ejecución",
            "severity": "medium"
        },
    }

    def __init__(self, blueprint_path: str):
        self.blueprint_path = Path(blueprint_path)
        self.blueprint = self._load_blueprint()
        self.port_types: Dict[str, PortType] = {}
        self._classify_ports()

    def _load_blueprint(self) -> dict:
        with open(self.blueprint_path) as f:
            return json.load(f)

    def _classify_ports(self):
        """Clasifica todos los puertos mencionados en conexiones."""
        for conn in self.blueprint.get("connections", []):
            from_port = conn["from"].split(":")[1]
            to_port = conn["to"].split(":")[1]
            
            if conn["from"] not in self.port_types:
                self.port_types[conn["from"]] = self._get_port_type(from_port)
            
            if conn["to"] not in self.port_types:
                self.port_types[conn["to"]] = self._get_port_type(to_port)

    def _get_port_type(self, port_name: str) -> PortType:
        """Determina el tipo de un puerto por su nombre."""
        for port_type, patterns in self.PORT_PATTERNS.items():
            if any(port_name.endswith(pattern) or port_name.startswith(pattern.replace(".in", "").replace(".out", "")) 
                   for pattern in patterns):
                return port_type
        
        return PortType.UNKNOWN

    def get_port_type(self, full_port: str) -> PortType:
        """Obtiene el tipo de un puerto completo (module:port)."""
        return self.port_types.get(full_port, PortType.UNKNOWN)

    def _is_satellite_module(self, module_id: str) -> bool:
        """Verifica si un módulo es satélite (no core)."""
        core_modules = {
            "supervisor.main", "router.main", "agent.main", "planner.main",
            "safety.guard.main", "approval.main", "worker.python.desktop",
            "worker.python.terminal", "worker.python.system", "worker.python.browser",
            "memory.log.main", "interface.main"
        }
        return module_id not in core_modules

    def validate_connection(self, conn: dict) -> Optional[PortViolation]:
        """Valida una conexión individual."""
        from_key = conn["from"]
        to_key = conn["to"]
        from_type = self.get_port_type(from_key)
        to_type = self.get_port_type(to_key)
        to_module = to_key.split(":")[0]
        
        # Regla 1: Observation NO debe conectar a Execution...
        # EXCEPTO si es a un módulo satélite (acción derivada)
        if from_type == PortType.OBSERVATION and to_type == PortType.EXECUTION:
            if self._is_satellite_module(to_module):
                # Es una acción derivada (ej: supervisor.event -> gamification)
                # Esto es válido pero genera warning
                return PortViolation(
                    connection_from=from_key,
                    connection_to=to_key,
                    violation_type="observation_to_satellite",
                    expected="observation -> observation",
                    actual=f"observation -> satellite execution ({to_key})",
                    severity="low",
                    message=f"Observación {from_key} dispara acción en satélite {to_key} (aceptable si es derivada)"
                )
            else:
                # Observation conecta a core execution - CRÍTICO
                return PortViolation(
                    connection_from=from_key,
                    connection_to=to_key,
                    violation_type="observation_to_execution",
                    expected="observation -> observation|ui|persistence",
                    actual=f"observation -> core execution ({to_key})",
                    severity="critical",
                    message=f"Puerto de observación {from_key} no debería conectar a ejecución core {to_key}"
                )
        
        # Regla 2: UI NO debe conectar a Execution (excepto command.in)
        if from_type == PortType.UI and to_type == PortType.EXECUTION:
            # command.in es la excepción: UI puede enviar comandos
            if not to_key.endswith("command.in"):
                return PortViolation(
                    connection_from=from_key,
                    connection_to=to_key,
                    violation_type="ui_to_execution",
                    expected="ui -> ui|observation",
                    actual=f"ui -> execution ({to_key})",
                    severity="medium",
                    message=f"Puerto UI {from_key} no debería conectar a ejecución {to_key}"
                )
        
        return None

    def validate_all(self) -> List[PortViolation]:
        """Valida todas las conexiones del blueprint."""
        violations = []
        
        # Primero, detectar broadcasts (mismo origen, múltiples destinos de ejecución)
        source_targets: Dict[str, List[str]] = {}
        for conn in self.blueprint.get("connections", []):
            from_key = conn["from"]
            to_key = conn["to"]
            
            if from_key not in source_targets:
                source_targets[from_key] = []
            source_targets[from_key].append(to_key)
        
        # Detectar broadcasts de ejecución
        for source, targets in source_targets.items():
            source_type = self.get_port_type(source)
            
            if source_type == PortType.EXECUTION and len(targets) > 1:
                # Contar cuántos son de ejecución
                exec_targets = [t for t in targets if self.get_port_type(t) == PortType.EXECUTION]
                
                if len(exec_targets) > 1:
                    violations.append(PortViolation(
                        connection_from=source,
                        connection_to=", ".join(exec_targets[:3]),
                        violation_type="execution_broadcast",
                        expected="1 destino de ejecución",
                        actual=f"{len(exec_targets)} destinos de ejecución",
                        severity="high",
                        message=f"{source} hace broadcast a {len(exec_targets)} destinos de ejecución"
                    ))
        
        # Validar conexiones individuales
        for conn in self.blueprint.get("connections", []):
            violation = self.validate_connection(conn)
            if violation:
                violations.append(violation)
        
        return violations

    def get_port_stats(self) -> Dict:
        """Estadísticas de puertos por tipo."""
        stats = {port_type: 0 for port_type in PortType}
        
        for port, port_type in self.port_types.items():
            stats[port_type] += 1
        
        return {
            "total_ports": len(self.port_types),
            "by_type": {k.value: v for k, v in stats.items()},
            "ports_by_type": {
                port_type.value: [p for p, t in self.port_types.items() if t == port_type]
                for port_type in PortType
            }
        }

    def print_report(self, violations: List[PortViolation]):
        """Imprime reporte de validación."""
        print("=" * 70)
        print("PORT TYPE VALIDATION REPORT")
        print("=" * 70)
        print()
        
        # Estadísticas
        stats = self.get_port_stats()
        print(f"Total puertos clasificados: {stats['total_ports']}")
        print("\nDistribución por tipo:")
        for port_type, count in stats['by_type'].items():
            if count > 0:
                print(f"  {port_type}: {count}")
        
        print()
        
        # Violaciones
        if violations:
            print(f"🚨 VIOLACIONES ({len(violations)}):")
            print("-" * 70)
            
            by_severity = {"critical": [], "high": [], "medium": [], "low": [], "info": []}
            for v in violations:
                by_severity[v.severity].append(v)
            
            for severity in ["critical", "high", "medium"]:
                if by_severity[severity]:
                    print(f"\n[{severity.upper()}]")
                    for v in by_severity[severity][:5]:  # Max 5 por severidad
                        print(f"  {v.violation_type}")
                        print(f"    {v.connection_from} -> {v.connection_to}")
                        print(f"    {v.message}")
        else:
            print("✓ No se encontraron violaciones de tipos de puerto")
        
        print()
        print("=" * 70)


def main():
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"
    
    validator = PortTypeValidator(str(blueprint_path))
    violations = validator.validate_all()
    validator.print_report(violations)
    
    # Exit code
    critical = len([v for v in violations if v.severity == "critical"])
    high = len([v for v in violations if v.severity == "high"])
    
    if critical > 0:
        exit(2)
    elif high > 0:
        exit(1)
    else:
        exit(0)


if __name__ == "__main__":
    main()
