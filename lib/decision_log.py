#!/usr/bin/env python3
"""
Decision Log Manager - Gestión de Decisiones Arquitectónicas (ADR)

Operaciones:
- Listar decisiones
- Agregar nueva decisión
- Actualizar status
- Validar contra auditoría
- Revisar decisiones vencidas
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class DecisionStatus(Enum):
    PERMANENT = "permanent"
    TEMPORAL = "temporal"
    TECH_DEBT = "tech_debt"
    SUPERSEDED = "superseded"

    @classmethod
    def values(cls) -> List[str]:
        return [item.value for item in cls]


@dataclass
class Decision:
    id: str
    title: str
    rule_affected: str
    exception: str
    status: str
    decision_date: str
    context: str
    motivation: str
    impact: str
    alternatives_considered: Optional[List[str]] = None
    mitigation: Optional[str] = None
    review_date: Optional[str] = None
    reviewed_by: Optional[str] = None
    superseded_by: Optional[str] = None

    def __post_init__(self):
        if self.alternatives_considered is None:
            self.alternatives_considered = []

        if self.status not in DecisionStatus.values():
            raise ValueError(
                f"Status inválido '{self.status}'. Debe ser uno de: {', '.join(DecisionStatus.values())}"
            )


class DecisionLogManager:
    """Gestiona el registro de decisiones arquitectónicas."""

    def __init__(self, decision_log_path: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.decision_log_path = decision_log_path or (self.base_dir / "docs" / "ARCHITECTURE_DECISION_LOG.json")
        self.decisions: List[Decision] = []
        self._load()

    def _load(self):
        """Carga el decision log desde JSON."""
        if self.decision_log_path.exists():
            with open(self.decision_log_path, encoding="utf-8") as f:
                data = json.load(f)
                self.decisions = [Decision(**d) for d in data.get("decisions", [])]
        else:
            self.decisions = []

    def _save(self):
        """Guarda el decision log a JSON."""
        self.decision_log_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "schema_version": "1.0",
            "description": "Registro de Decisiones Arquitectónicas (ADR) para blueprint-v0",
            "last_updated": datetime.now().isoformat(),
            "decisions": [
                {
                    "id": d.id,
                    "title": d.title,
                    "rule_affected": d.rule_affected,
                    "exception": d.exception,
                    "status": d.status,
                    "decision_date": d.decision_date,
                    "context": d.context,
                    "motivation": d.motivation,
                    "impact": d.impact,
                    "alternatives_considered": d.alternatives_considered,
                    "mitigation": d.mitigation,
                    "review_date": d.review_date,
                    "reviewed_by": d.reviewed_by,
                    "superseded_by": d.superseded_by,
                }
                for d in self.decisions
            ],
            "metadata": self._get_metadata(),
        }

        with open(self.decision_log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def _get_metadata(self) -> Dict:
        """Genera metadata del decision log."""
        status_counts: Dict[str, int] = {}
        for d in self.decisions:
            status_counts[d.status] = status_counts.get(d.status, 0) + 1

        pending_review = [
            d for d in self.decisions
            if d.review_date and d.status in (DecisionStatus.TEMPORAL.value, DecisionStatus.TECH_DEBT.value)
        ]

        next_review = None
        if pending_review:
            dates = [d.review_date for d in pending_review if d.review_date]
            if dates:
                next_review = min(dates)

        return {
            "total_decisions": len(self.decisions),
            "by_status": status_counts,
            "pending_review": len(pending_review),
            "next_review_date": next_review,
        }

    def get_next_id(self) -> str:
        """Genera el próximo ID de decisión."""
        if not self.decisions:
            return "ADR-001"

        max_num = 0
        for d in self.decisions:
            try:
                num = int(d.id.split("-")[1])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                continue

        return f"ADR-{max_num + 1:03d}"

    def add_decision(self, **kwargs) -> Decision:
        """Agrega una nueva decisión."""
        decision_id = kwargs.get("id") or self.get_next_id()
        status = kwargs["status"]

        if status not in DecisionStatus.values():
            raise ValueError(
                f"Status inválido '{status}'. Debe ser uno de: {', '.join(DecisionStatus.values())}"
            )

        decision = Decision(
            id=decision_id,
            title=kwargs["title"],
            rule_affected=kwargs["rule_affected"],
            exception=kwargs["exception"],
            status=status,
            decision_date=kwargs.get("decision_date", datetime.now().strftime("%Y-%m-%d")),
            context=kwargs["context"],
            motivation=kwargs["motivation"],
            impact=kwargs["impact"],
            alternatives_considered=kwargs.get("alternatives_considered", []),
            mitigation=kwargs.get("mitigation"),
            review_date=kwargs.get("review_date"),
            reviewed_by=kwargs.get("reviewed_by"),
            superseded_by=kwargs.get("superseded_by"),
        )

        self.decisions.append(decision)
        self._save()
        return decision

    def list_decisions(self, status: Optional[str] = None, rule: Optional[str] = None) -> List[Decision]:
        """Lista decisiones filtradas."""
        filtered = self.decisions

        if status:
            filtered = [d for d in filtered if d.status == status]

        if rule:
            filtered = [d for d in filtered if d.rule_affected == rule]

        return filtered

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        """Obtiene una decisión por ID."""
        for d in self.decisions:
            if d.id == decision_id:
                return d
        return None

    def update_status(self, decision_id: str, new_status: str, reviewed_by: Optional[str] = None) -> Decision:
        """Actualiza el status de una decisión."""
        if new_status not in DecisionStatus.values():
            raise ValueError(
                f"Status inválido '{new_status}'. Debe ser uno de: {', '.join(DecisionStatus.values())}"
            )

        decision = self.get_decision(decision_id)
        if not decision:
            raise ValueError(f"Decisión {decision_id} no encontrada")

        decision.status = new_status
        decision.reviewed_by = reviewed_by or "manual"

        self._save()
        return decision

    def check_overdue_reviews(self) -> List[Decision]:
        """Retorna decisiones que necesitan revisión."""
        today = datetime.now().date()
        overdue = []

        for d in self.decisions:
            if d.status not in (DecisionStatus.TEMPORAL.value, DecisionStatus.TECH_DEBT.value):
                continue

            if d.review_date:
                review_date = datetime.strptime(d.review_date, "%Y-%m-%d").date()
                if review_date <= today:
                    overdue.append(d)

        return overdue

    def is_exception_justified(self, exception_key: str) -> tuple[bool, Optional[Decision]]:
        """Verifica si una excepción está justificada en el decision log."""
        for d in self.decisions:
            if d.exception == exception_key or exception_key in d.exception:
                if d.status != DecisionStatus.SUPERSEDED.value:
                    return True, d
        return False, None

    def print_summary(self):
        """Imprime resumen del decision log."""
        meta = self._get_metadata()

        print("=" * 70)
        print("ARCHITECTURE DECISION LOG - Resumen")
        print("=" * 70)
        print()
        print(f"Total decisiones: {meta['total_decisions']}")
        print()

        print("Por status:")
        for status, count in meta["by_status"].items():
            emoji = {
                "permanent": "🟢",
                "temporal": "🟡",
                "tech_debt": "🔵",
                "superseded": "⚪",
            }.get(status, "⚪")
            print(f"  {emoji} {status}: {count}")

        print()

        if meta["pending_review"] > 0:
            print(f"⚠️  Decisiones pendientes de revisión: {meta['pending_review']}")
            if meta["next_review_date"]:
                print(f"   Próxima revisión: {meta['next_review_date']}")

        print()

        for status in [
            DecisionStatus.TECH_DEBT.value,
            DecisionStatus.TEMPORAL.value,
            DecisionStatus.PERMANENT.value,
        ]:
            decisions = self.list_decisions(status=status)
            if decisions:
                print(f"\n{status.upper()}:")
                for d in decisions[:5]:
                    review_info = f" (revisar: {d.review_date})" if d.review_date else ""
                    print(f"  [{d.id}] {d.title}{review_info}")

        print()
        print("=" * 70)


def prompt_non_empty(label: str) -> str:
    while True:
        value = input(f"{label}: ").strip()
        if value:
            return value
        print("Este campo es obligatorio.")


def prompt_optional(label: str) -> Optional[str]:
    value = input(f"{label} (opcional): ").strip()
    return value or None


def prompt_status() -> str:
    valid = DecisionStatus.values()
    while True:
        value = input(f"status {valid}: ").strip()
        if value in valid:
            return value
        print(f"Status inválido. Usá uno de: {', '.join(valid)}")


def cmd_add(manager: DecisionLogManager):
    print("Agregar nueva decisión")
    print("-" * 40)

    title = prompt_non_empty("title")
    rule_affected = prompt_non_empty("rule_affected")
    exception = prompt_non_empty("exception")
    status = prompt_status()
    context = prompt_non_empty("context")
    motivation = prompt_non_empty("motivation")
    impact = prompt_non_empty("impact")
    mitigation = prompt_optional("mitigation")
    review_date = prompt_optional("review_date YYYY-MM-DD")
    reviewed_by = prompt_optional("reviewed_by")
    superseded_by = prompt_optional("superseded_by")

    alternatives_raw = input("alternatives_considered (separadas por coma, opcional): ").strip()
    alternatives = [item.strip() for item in alternatives_raw.split(",") if item.strip()] if alternatives_raw else []

    decision = manager.add_decision(
        title=title,
        rule_affected=rule_affected,
        exception=exception,
        status=status,
        context=context,
        motivation=motivation,
        impact=impact,
        mitigation=mitigation,
        review_date=review_date,
        reviewed_by=reviewed_by,
        superseded_by=superseded_by,
        alternatives_considered=alternatives,
    )

    print(f"✓ Decisión creada: {decision.id}")


def cmd_review(manager: DecisionLogManager):
    if len(sys.argv) < 4:
        print("Uso: python decision_log.py review <id> <new_status> [reviewed_by]")
        return

    decision_id = sys.argv[2]
    new_status = sys.argv[3]
    reviewed_by = sys.argv[4] if len(sys.argv) > 4 else "manual"

    updated = manager.update_status(decision_id, new_status, reviewed_by=reviewed_by)
    print(f"✓ Decisión actualizada: {updated.id} -> {updated.status}")


def main():
    """CLI para gestionar decision log."""
    if len(sys.argv) < 2:
        print("Uso: python decision_log.py <comando> [args...]")
        print()
        print("Comandos:")
        print("  list [status] [rule]  - Listar decisiones")
        print("  show <id>             - Mostrar decisión")
        print("  add                   - Agregar decisión interactivo")
        print("  review <id> <status> [reviewed_by] - Marcar/reclasificar")
        print("  overdue               - Mostrar vencidas")
        print("  summary               - Resumen")
        return

    manager = DecisionLogManager()
    cmd = sys.argv[1]

    if cmd == "summary":
        manager.print_summary()

    elif cmd == "list":
        status = sys.argv[2] if len(sys.argv) > 2 else None
        rule = sys.argv[3] if len(sys.argv) > 3 else None
        decisions = manager.list_decisions(status=status, rule=rule)

        print(f"Decisiones ({len(decisions)}):")
        for d in decisions:
            print(f"  [{d.id}] {d.title} ({d.status})")

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Error: Se requiere ID de decisión")
            return

        decision = manager.get_decision(sys.argv[2])
        if decision:
            print(f"\n[{decision.id}] {decision.title}")
            print(f"Status: {decision.status}")
            print(f"Regla: {decision.rule_affected}")
            print(f"Excepción: {decision.exception}")
            print(f"Fecha: {decision.decision_date}")
            print(f"\nContexto: {decision.context}")
            print(f"Motivación: {decision.motivation}")
            print(f"Impacto: {decision.impact}")
            if decision.alternatives_considered:
                print(f"Alternativas: {', '.join(decision.alternatives_considered)}")
            if decision.mitigation:
                print(f"Mitigación: {decision.mitigation}")
            if decision.review_date:
                print(f"Revisar: {decision.review_date}")
            if decision.reviewed_by:
                print(f"Reviewed by: {decision.reviewed_by}")
            if decision.superseded_by:
                print(f"Superseded by: {decision.superseded_by}")
        else:
            print(f"Decisión {sys.argv[2]} no encontrada")

    elif cmd == "add":
        cmd_add(manager)

    elif cmd == "review":
        cmd_review(manager)

    elif cmd == "overdue":
        overdue = manager.check_overdue_reviews()
        if overdue:
            print(f"⚠️  Decisiones vencidas ({len(overdue)}):")
            for d in overdue:
                print(f"  [{d.id}] {d.title} - venció: {d.review_date}")
        else:
            print("✓ No hay decisiones vencidas")

    else:
        print(f"Comando desconocido: {cmd}")


if __name__ == "__main__":
    main()