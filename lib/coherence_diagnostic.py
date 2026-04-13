#!/usr/bin/env python3
"""
Coherence Diagnostic - Diagnóstico de Coherencia entre Planos

Mide:
- Coherencia entre físico, lógico y operativo
- Qué tan alineados están los 3 planos
- Inconsistencias semánticas
- Nombres implícitos no resueltos

No mide cantidades, mide coherencia.
"""

import json
import sys
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.ontology import get_ontology, CanonicalEntity


class PresenceStatus(Enum):
    """Estado de presencia en un plano"""
    PRESENT = "present"
    ABSENT = "absent"
    MISMATCH = "mismatch"
    DEGRADED = "degraded"


@dataclass
class PlanePresence:
    """Presencia de una entidad en un plano"""
    plane: str
    status: PresenceStatus
    details: Dict = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


@dataclass
class CoherenceReport:
    """Reporte de coherencia para una entidad"""
    canonical_id: str
    physical: PlanePresence
    logical: PlanePresence
    operational: PlanePresence
    coherence_score: float
    cross_plane_issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "canonical_id": self.canonical_id,
            "coherence_score": round(self.coherence_score, 1),
            "physical": {
                "plane": self.physical.plane,
                "status": self.physical.status.value,
                "details": self.physical.details,
                "issues": self.physical.issues,
            },
            "logical": {
                "plane": self.logical.plane,
                "status": self.logical.status.value,
                "details": self.logical.details,
                "issues": self.logical.issues,
            },
            "operational": {
                "plane": self.operational.plane,
                "status": self.operational.status.value,
                "details": self.operational.details,
                "issues": self.operational.issues,
            },
            "cross_plane_issues": self.cross_plane_issues,
        }


class PhysicalPlane:
    """
    Plano Físico: Archivos, carpetas, disco
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.modules_dir = self.root / "modules"
        self.runtime_dir = self.root / "runtime"
        self.lib_dir = self.root / "lib"

    def check_entity(self, entity: CanonicalEntity, ontology=None) -> PlanePresence:
        """Verifica presencia física de una entidad"""
        expected_dir = self.modules_dir / entity.directory_name
        manifest_path = expected_dir / "manifest.json"

        issues: List[str] = []
        details = {
            "expected_directory": str(expected_dir.relative_to(self.root)) if expected_dir.exists() else str(expected_dir).replace(str(self.root), "").lstrip("/"),
            "directory_exists": expected_dir.exists(),
            "manifest_exists": manifest_path.exists(),
        }

        if not expected_dir.exists():
            return PlanePresence(
                plane="physical",
                status=PresenceStatus.ABSENT,
                details=details,
                issues=[f"Directory not found: {entity.directory_name}"],
            )

        if not manifest_path.exists():
            issues.append(f"Manifest not found in {entity.directory_name}")
            return PlanePresence(
                plane="physical",
                status=PresenceStatus.DEGRADED,
                details=details,
                issues=issues,
            )

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            manifest_id = manifest.get("id", "")
            details["manifest_id"] = manifest_id

            id_matches = False
            if manifest_id == entity.canonical_id:
                id_matches = True
            elif ontology:
                resolved = ontology.resolve(manifest_id)
                if resolved and resolved.canonical_id == entity.canonical_id:
                    id_matches = True
                if not id_matches and manifest_id in getattr(entity, "aliases", []):
                    id_matches = True

            if not id_matches:
                issues.append(
                    f"ID mismatch: manifest says '{manifest_id}', ontology says '{entity.canonical_id}'"
                )

            entry = manifest.get("entry", "main.js")
            entry_path = expected_dir / entry
            details["entry_file"] = entry
            details["entry_exists"] = entry_path.exists()

            if not entry_path.exists():
                issues.append(f"Entry file not found: {entry}")

            language = manifest.get("language", "javascript")
            details["language"] = language

            details["files"] = sorted([p.name for p in expected_dir.iterdir()])

        except json.JSONDecodeError as e:
            issues.append(f"Invalid manifest JSON: {e}")
        except Exception as e:
            issues.append(f"Error reading manifest: {e}")

        status = PresenceStatus.PRESENT if not issues else PresenceStatus.MISMATCH

        return PlanePresence(
            plane="physical",
            status=status,
            details=details,
            issues=issues,
        )

    def find_orphans(self, canonical_entities: Set[str], ontology) -> List[Dict]:
        """Encuentra directorios de módulos no en ontología"""
        orphans = []

        if not self.modules_dir.exists():
            return orphans

        for entry in self.modules_dir.iterdir():
            if not entry.is_dir():
                continue

            entity = ontology.resolve(entry.name)

            if not entity:
                manifest_path = entry / "manifest.json"
                manifest_id = None

                if manifest_path.exists():
                    try:
                        with open(manifest_path, encoding="utf-8") as f:
                            manifest = json.load(f)
                        manifest_id = manifest.get("id")
                    except Exception:
                        pass

                orphans.append({
                    "directory": entry.name,
                    "manifest_id": manifest_id,
                    "issue": "Directory exists but not in ontology",
                })

        return orphans


class LogicalPlane:
    """
    Plano Lógico: Módulos, roles, tiers, blueprint
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.blueprint_path = self.root / "blueprints" / "system.v0.json"

    def check_entity(self, entity: CanonicalEntity, blueprint: Dict, ontology=None) -> PlanePresence:
        """Verifica presencia lógica de una entidad"""
        issues: List[str] = []
        details = {
            "in_blueprint": False,
            "has_connections": False,
            "role_defined": bool(getattr(entity, "role", None)),
            "tier": getattr(entity, "tier", None),
        }

        blueprint_modules = blueprint.get("modules", [])
        connections = blueprint.get("connections", [])

        matching_blueprint_id = None
        if entity.canonical_id in blueprint_modules:
            matching_blueprint_id = entity.canonical_id
        elif ontology:
            for bp_id in blueprint_modules:
                resolved = ontology.resolve(bp_id)
                if resolved and resolved.canonical_id == entity.canonical_id:
                    matching_blueprint_id = bp_id
                    break

        if matching_blueprint_id:
            details["in_blueprint"] = True

            entity_connections = []
            for conn in connections:
                from_module = conn.get("from", "").split(":")[0]
                to_module = conn.get("to", "").split(":")[0]

                matches_from = from_module in {entity.canonical_id, matching_blueprint_id}
                matches_to = to_module in {entity.canonical_id, matching_blueprint_id}

                if matches_from or matches_to:
                    entity_connections.append(conn)

            details["connection_count"] = len(entity_connections)
            details["has_connections"] = len(entity_connections) > 0

            if not entity_connections:
                issues.append("Entity in blueprint but has no connections")

            defined_inputs = set(getattr(entity, "inputs", []))
            defined_outputs = set(getattr(entity, "outputs", []))

            used_inputs = set()
            used_outputs = set()

            for conn in entity_connections:
                from_port = conn.get("from", "")
                to_port = conn.get("to", "")

                if from_port.startswith(entity.canonical_id) or from_port.startswith(matching_blueprint_id):
                    port_name = from_port.split(":")[1] if ":" in from_port else from_port
                    used_outputs.add(port_name)

                if to_port.startswith(entity.canonical_id) or to_port.startswith(matching_blueprint_id):
                    port_name = to_port.split(":")[1] if ":" in to_port else to_port
                    used_inputs.add(port_name)

            unused_outputs = defined_outputs - used_outputs
            unused_inputs = defined_inputs - used_inputs

            reserved_inputs = unused_inputs & set(getattr(entity, "reserved_inputs", set()))
            reserved_outputs = unused_outputs & set(getattr(entity, "reserved_outputs", set()))
            obsolete_inputs = unused_inputs & set(getattr(entity, "obsolete_inputs", set()))
            obsolete_outputs = unused_outputs & set(getattr(entity, "obsolete_outputs", set()))

            misdefined_inputs = unused_inputs - reserved_inputs - obsolete_inputs
            misdefined_outputs = unused_outputs - reserved_outputs - obsolete_outputs

            if misdefined_outputs:
                issues.append(f"Misdefined outputs (fix needed): {sorted(misdefined_outputs)}")
            if misdefined_inputs:
                issues.append(f"Misdefined inputs (fix needed): {sorted(misdefined_inputs)}")
            if obsolete_outputs:
                issues.append(f"Obsolete outputs (deprecated): {sorted(obsolete_outputs)}")
            if obsolete_inputs:
                issues.append(f"Obsolete inputs (deprecated): {sorted(obsolete_inputs)}")

            details["used_inputs"] = sorted(used_inputs)
            details["used_outputs"] = sorted(used_outputs)
            details["unused_inputs"] = sorted(unused_inputs)
            details["unused_outputs"] = sorted(unused_outputs)
            details["reserved_inputs"] = sorted(reserved_inputs)
            details["reserved_outputs"] = sorted(reserved_outputs)
            details["obsolete_inputs"] = sorted(obsolete_inputs)
            details["obsolete_outputs"] = sorted(obsolete_outputs)
            details["misdefined_inputs"] = sorted(misdefined_inputs)
            details["misdefined_outputs"] = sorted(misdefined_outputs)
        else:
            issues.append("Entity not in blueprint")

        if not getattr(entity, "role", None):
            issues.append("Entity has no defined role")

        status = PresenceStatus.PRESENT if not issues else PresenceStatus.MISMATCH
        if not details["in_blueprint"]:
            status = PresenceStatus.ABSENT

        return PlanePresence(
            plane="logical",
            status=status,
            details=details,
            issues=issues,
        )

    def load_blueprint(self) -> Dict:
        """Carga el blueprint"""
        if self.blueprint_path.exists():
            with open(self.blueprint_path, encoding="utf-8") as f:
                return json.load(f)
        return {"modules": [], "connections": []}

    def find_logical_orphans(self, canonical_entities: Set[str], blueprint: Dict, ontology=None) -> List[Dict]:
        """Encuentra módulos en blueprint no en ontología"""
        orphans = []
        blueprint_modules = blueprint.get("modules", [])

        for module_id in blueprint_modules:
            if module_id in canonical_entities:
                continue

            if ontology:
                resolved = ontology.resolve(module_id)
                if resolved and resolved.canonical_id in canonical_entities:
                    continue

            orphans.append({
                "module_id": module_id,
                "issue": "In blueprint but not in ontology",
            })

        return orphans


class OperationalPlane:
    """
    Plano Operativo: Procesos, mensajes, salud
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def check_entity(self, entity: CanonicalEntity) -> PlanePresence:
        """Verifica presencia operativa de una entidad"""
        issues: List[str] = []
        details = {
            "syntax_valid": False,
            "can_execute": False,
            "health_check": "unknown",
        }

        syntax_result = self._check_syntax_valid(entity)
        details["syntax_valid"] = syntax_result["valid"]

        if not syntax_result["valid"]:
            issues.append(f"Syntax error: {syntax_result.get('error', 'invalid code')}")

        can_execute = self._can_execute(entity)
        details["can_execute"] = can_execute

        if not can_execute:
            issues.append("Module cannot execute (missing dependencies or entry point)")

        if getattr(entity, "tier", None) == "core":
            if syntax_result["valid"] and can_execute:
                details["health_check"] = "healthy"
            else:
                details["health_check"] = "unhealthy"
                if not syntax_result["valid"]:
                    issues.append("Core module has syntax errors (critical)")

        if syntax_result["valid"] and can_execute:
            status = PresenceStatus.PRESENT
        elif syntax_result["valid"]:
            status = PresenceStatus.DEGRADED
        else:
            status = PresenceStatus.MISMATCH

        return PlanePresence(
            plane="operational",
            status=status,
            details=details,
            issues=issues,
        )

    def _check_syntax_valid(self, entity: CanonicalEntity) -> Dict:
        module_dir = self.root / "modules" / entity.directory_name
        manifest_path = module_dir / "manifest.json"

        if not manifest_path.exists():
            return {"valid": False, "error": "No manifest"}

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            entry = manifest.get("entry", "main.js")
            language = manifest.get("language", "javascript")
            entry_path = module_dir / entry

            if not entry_path.exists():
                return {"valid": False, "error": f"Entry file not found: {entry}"}

            if language == "python":
                import ast
                try:
                    with open(entry_path, "r", encoding="utf-8", errors="ignore") as f:
                        ast.parse(f.read())
                    return {"valid": True}
                except SyntaxError as e:
                    return {"valid": False, "error": str(e), "line": e.lineno}
            else:
                try:
                    with open(entry_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if len(content) < 10:
                            return {"valid": False, "error": "Entry file too small or empty"}
                        js_indicators = [
                            "function", "const", "let", "var",
                            "module.exports", "require(", "import "
                        ]
                        if not any(ind in content for ind in js_indicators):
                            return {"valid": False, "error": "Does not appear to be valid JS"}
                        return {"valid": True}
                except Exception as e:
                    return {"valid": False, "error": str(e)}

        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _can_execute(self, entity: CanonicalEntity) -> bool:
        module_dir = self.root / "modules" / entity.directory_name
        manifest_path = module_dir / "manifest.json"

        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            entry = manifest.get("entry", "main.js")
            entry_path = module_dir / entry

            if not entry_path.exists():
                return False

            with open(entry_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if len(content.strip()) < 20:
                    return False

            return True
        except Exception:
            return False


class CoherenceDiagnostic:
    """
    Diagnóstico de coherencia entre los 3 planos
    """

    def __init__(self, duration_minutes: int = 50):
        self.duration = duration_minutes * 60
        self.ontology = get_ontology()
        self.physical = PhysicalPlane(PROJECT_ROOT)
        self.logical = LogicalPlane(PROJECT_ROOT)
        self.operational = OperationalPlane(PROJECT_ROOT)

    def analyze_entity(self, entity: CanonicalEntity, blueprint: Dict) -> CoherenceReport:
        physical = self.physical.check_entity(entity, self.ontology)
        logical = self.logical.check_entity(entity, blueprint, self.ontology)
        operational = self.operational.check_entity(entity)

        score = 100.0
        cross_issues: List[str] = []

        for plane in [physical, logical, operational]:
            if plane.status == PresenceStatus.ABSENT:
                score -= 40
            elif plane.status == PresenceStatus.MISMATCH:
                score -= 25
            elif plane.status == PresenceStatus.DEGRADED:
                score -= 15

        if physical.status == PresenceStatus.PRESENT and logical.status == PresenceStatus.ABSENT:
            cross_issues.append("Entity exists physically but not in blueprint (orphan)")
            score -= 20

        if logical.status == PresenceStatus.PRESENT and physical.status == PresenceStatus.ABSENT:
            cross_issues.append("Entity in blueprint but no files on disk (ghost)")
            score -= 20

        if getattr(entity, "tier", None) == "core":
            if operational.status == PresenceStatus.MISMATCH:
                score -= 30
                cross_issues.append("Core entity has syntax errors (critical)")
            elif operational.status == PresenceStatus.DEGRADED:
                score -= 10
                cross_issues.append("Core entity has execution issues")

        if getattr(entity, "tier", None) == "satellite" and logical.status == PresenceStatus.PRESENT:
            if not logical.details.get("has_connections", False):
                cross_issues.append("Satellite has no connections (isolated)")
                score -= 10

        score = max(0, score)

        return CoherenceReport(
            canonical_id=entity.canonical_id,
            physical=physical,
            logical=logical,
            operational=operational,
            coherence_score=score,
            cross_plane_issues=cross_issues,
        )

    def run(self) -> Dict:
        print("\n" + "=" * 80)
        print("🔬 COHERENCE DIAGNOSTIC - 3 Planes de Realidad")
        print("=" * 80)
        print("\n📋 Plano FÍSICO:    Archivos, carpetas, disco")
        print("📋 Plano LÓGICO:    Módulos, roles, blueprint")
        print("📋 Plano OPERATIVO: Procesos, mensajes, salud")
        print("=" * 80 + "\n")

        blueprint = self.logical.load_blueprint()
        print(f"✓ Blueprint cargado: {len(blueprint.get('modules', []))} módulos definidos")

        canonical_entities = self.ontology.get_all_canonical_ids()
        print(f"✓ Ontología cargada: {len(canonical_entities)} entidades canónicas\n")

        reports: List[CoherenceReport] = []
        blueprint_reports: List[CoherenceReport] = []
        extra_reports: List[CoherenceReport] = []

        print("📊 ANALIZANDO COHERENCIA POR ENTIDAD:\n")

        blueprint_modules = blueprint.get("modules", [])

        for entity_id in sorted(canonical_entities):
            entity = self.ontology.entities[entity_id]
            report = self.analyze_entity(entity, blueprint)
            reports.append(report)

            in_blueprint = entity_id in blueprint_modules
            if not in_blueprint:
                for bp_id in blueprint_modules:
                    resolved = self.ontology.resolve(bp_id)
                    if resolved and resolved.canonical_id == entity_id:
                        in_blueprint = True
                        break

            if in_blueprint:
                blueprint_reports.append(report)
            else:
                extra_reports.append(report)

            symbol = "✓" if report.coherence_score >= 80 else "⚠" if report.coherence_score >= 60 else "✗"
            extra_mark = " [EXTRA]" if not in_blueprint else ""
            print(f"{symbol} {entity.canonical_id:<30} Score: {report.coherence_score:>3.0f}/100{extra_mark}")

            if report.cross_plane_issues:
                for issue in report.cross_plane_issues:
                    print(f"   → {issue}")

        print("\n" + "-" * 80)
        print("\n🔍 BUSCANDO HUÉRFANOS:\n")

        physical_orphans = self.physical.find_orphans(canonical_entities, self.ontology)
        if physical_orphans:
            print(f"⚠ Huérfanos FÍSICOS ({len(physical_orphans)}):")
            for orphan in physical_orphans[:5]:
                print(f"   • {orphan['directory']} - {orphan['issue']}")
        else:
            print("✓ No hay huérfanos físicos")

        logical_orphans = self.logical.find_logical_orphans(canonical_entities, blueprint, self.ontology)
        if logical_orphans:
            print(f"\n⚠ Huérfanos LÓGICOS ({len(logical_orphans)}):")
            for orphan in logical_orphans[:5]:
                print(f"   • {orphan['module_id']} - {orphan['issue']}")
        else:
            print("✓ No hay huérfanos lógicos")

        coherence_scores = [r.coherence_score for r in blueprint_reports]

        print("\n" + "=" * 80)
        print("📊 MÉTRICAS DE COHERENCIA GLOBAL (Sistema Core)")
        print("=" * 80)
        print(f"   Analizando {len(blueprint_reports)} entidades del blueprint")
        if extra_reports:
            print(f"   ({len(extra_reports)} entidades extra excluidas del score global)")

        high_coherence = len([s for s in coherence_scores if s >= 80])
        medium_coherence = len([s for s in coherence_scores if 60 <= s < 80])
        low_coherence = len([s for s in coherence_scores if s < 60])
        avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0

        print(f"\nCoherencia ALTA (80-100):   {high_coherence:>3} entidades")
        print(f"Coherencia MEDIA (60-79):   {medium_coherence:>3} entidades")
        print(f"Coherencia BAJA (0-59):     {low_coherence:>3} entidades")
        print(f"\nPROMEDIO DE COHERENCIA:     {avg_coherence:>5.1f}/100")

        if avg_coherence >= 90:
            grade = "A"
            status = "EXCELENTE"
        elif avg_coherence >= 80:
            grade = "B"
            status = "BUENO"
        elif avg_coherence >= 60:
            grade = "C"
            status = "REGULAR"
        elif avg_coherence >= 40:
            grade = "D"
            status = "DÉBIL"
        else:
            grade = "F"
            status = "CRÍTICO"

        print(f"\n🏆 GRADO DE COHERENCIA: {grade} ({status})")

        physical_issues = sum(len(r.physical.issues) for r in reports)
        logical_issues = sum(len(r.logical.issues) for r in reports)
        operational_issues = sum(len(r.operational.issues) for r in reports)
        cross_issues = sum(len(r.cross_plane_issues) for r in reports)

        total_reserved = sum(
            len(r.logical.details.get("reserved_inputs", [])) +
            len(r.logical.details.get("reserved_outputs", []))
            for r in blueprint_reports
        )
        total_obsolete = sum(
            len(r.logical.details.get("obsolete_inputs", [])) +
            len(r.logical.details.get("obsolete_outputs", []))
            for r in blueprint_reports
        )
        total_misdefined = sum(
            len(r.logical.details.get("misdefined_inputs", [])) +
            len(r.logical.details.get("misdefined_outputs", []))
            for r in blueprint_reports
        )

        print(f"\n📋 Análisis de Contratos:")
        print(f"   Puertos reservados (futuro):  {total_reserved}")
        print(f"   Puertos obsoletos:            {total_obsolete}")
        print(f"   Puertos mal definidos:        {total_misdefined}")

        print(f"\n📋 Problemas detectados:")
        print(f"   Plano físico:     {physical_issues} issues")
        print(f"   Plano lógico:     {logical_issues} issues")
        print(f"   Plano operativo:  {operational_issues} issues")
        print(f"   Cross-plane:      {cross_issues} inconsistencias")

        print("\n💡 RECOMENDACIONES:")

        if physical_orphans:
            print(f"   • {len(physical_orphans)} directorios de módulos no están en la ontología")
            print("     → Agregar a ontology.py o eliminar si obsoletos")

        if logical_orphans:
            print(f"   • {len(logical_orphans)} módulos en blueprint no tienen definición ontológica")
            print("     → Agregar entidad canónica a ontology.py")

        if low_coherence > 0:
            print(f"   • {low_coherence} entidades blueprint con coherencia baja (<60)")
            print("     → Revisar inconsistencias entre físico/lógico/operativo")

        if extra_reports:
            print(f"   • {len(extra_reports)} entidades extra analizadas pero no incluidas en score global")

        if blueprint_reports and high_coherence == len(blueprint_reports):
            print("   • Sistema completamente coherente - todos los planos alineados")

        print("=" * 80 + "\n")

        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "blueprint_entities": len(blueprint_reports),
                "extra_entities": len(extra_reports),
                "total_entities": len(reports),
                "avg_coherence": round(avg_coherence, 1),
                "grade": grade,
                "status": status,
                "high_coherence": high_coherence,
                "medium_coherence": medium_coherence,
                "low_coherence": low_coherence,
                "physical_orphans": len(physical_orphans),
                "logical_orphans": len(logical_orphans),
                "issues": {
                    "physical": physical_issues,
                    "logical": logical_issues,
                    "operational": operational_issues,
                    "cross_plane": cross_issues,
                },
            },
            "blueprint_entities": [r.to_dict() for r in blueprint_reports],
            "extra_entities": [r.to_dict() for r in extra_reports],
            "entities": [r.to_dict() for r in reports],
            "orphans": {
                "physical": physical_orphans,
                "logical": logical_orphans,
            },
        }

        report_path = PROJECT_ROOT / "logs" / f"coherence_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        print(f"💾 Reporte completo guardado en: {report_path}\n")
        return report_data


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Coherence Diagnostic")
    parser.add_argument(
        "--duration",
        type=int,
        default=3000,
        help="Duración en segundos (no usado en modo análisis)",
    )
    args = parser.parse_args()

    diagnostic = CoherenceDiagnostic(duration_minutes=args.duration / 60)

    try:
        report = diagnostic.run()

        if report["summary"]["grade"] in ["A", "B"]:
            sys.exit(0)
        elif report["summary"]["grade"] == "C":
            sys.exit(1)
        else:
            sys.exit(2)

    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
