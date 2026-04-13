#!/usr/bin/env python3
"""
Blueprint Cleaner - Limpieza conservadora de broadcast de result.out

Objetivo:
1. worker.*:result.out solo va a verifier y/o supervisor
2. verifier.engine.main:result.out solo va a supervisor
3. ai.assistant.main:result.out solo va a supervisor
4. NO crear nuevas rutas de ejecución derivada
5. NO tocar approval.main ni phase.engine.main automáticamente

Modo seguro:
- Por defecto hace dry-run
- Solo escribe si se pasa --apply
"""

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Tuple, Any


WORKERS = [
    "worker.python.desktop",
    "worker.python.terminal",
    "worker.python.system",
    "worker.python.browser",
]

SAFE_WORKER_RESULT_TARGETS = {
    "supervisor.main:result.in",
    "verifier.engine.main:result.in",
}

SAFE_VERIFIER_RESULT_TARGETS = {
    "supervisor.main:result.in",
}

SAFE_AI_RESULT_TARGETS = {
    "supervisor.main:result.in",
}


def load_blueprint(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_blueprint(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"✓ Blueprint guardado en {path}")


def conn_key(conn: Dict[str, str]) -> Tuple[str, str]:
    return (conn["from"], conn["to"])


def add_connection_if_missing(connections: List[Dict[str, str]], conn: Dict[str, str]) -> bool:
    existing = {conn_key(c) for c in connections}
    key = conn_key(conn)
    if key in existing:
        return False
    connections.append(conn)
    return True


def analyze_result_out_connections(blueprint: Dict[str, Any]) -> Dict[str, List[Tuple[str, str]]]:
    result = {
        "worker": [],
        "verifier": [],
        "ai_assistant": [],
    }

    for conn in blueprint.get("connections", []):
        from_key = conn.get("from", "")
        to_key = conn.get("to", "")

        if any(from_key.startswith(f"{w}:result.out") for w in WORKERS):
            result["worker"].append((from_key, to_key))
        elif from_key.startswith("verifier.engine.main:result.out"):
            result["verifier"].append((from_key, to_key))
        elif from_key.startswith("ai.assistant.main:result.out"):
            result["ai_assistant"].append((from_key, to_key))

    return result


def clean_worker_broadcast(
    blueprint: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    Mantiene worker.result.out solo hacia verifier/supervisor.
    Agrega observación segura hacia supervisor.event.out solo para context/event consumers.
    """
    connections = blueprint.get("connections", [])
    new_connections: List[Dict[str, str]] = []
    removed: List[Tuple[str, str]] = []
    added: List[Tuple[str, str]] = []

    for conn in connections:
        from_key = conn.get("from", "")
        to_key = conn.get("to", "")

        is_worker_result = any(from_key.startswith(f"{w}:result.out") for w in WORKERS)

        if is_worker_result:
            if to_key in SAFE_WORKER_RESULT_TARGETS:
                new_connections.append(conn)
                print(f"  ✓ Mantiene: {from_key} → {to_key}")
            else:
                removed.append((from_key, to_key))
                print(f"  ✗ Elimina: {from_key} → {to_key}")
        else:
            new_connections.append(conn)

    # Solo conexiones observacionales seguras
    safe_supervisor_event_connections = [
        {"from": "supervisor.main:event.out", "to": "ui.state.main:event.in"},
        {"from": "supervisor.main:event.out", "to": "memory.log.main:event.in"},
        {"from": "supervisor.main:event.out", "to": "apps.session.main:event.in"},
        {"from": "supervisor.main:event.out", "to": "guide.main:context.in"},
    ]

    for conn in safe_supervisor_event_connections:
        if add_connection_if_missing(new_connections, conn):
            added.append((conn["from"], conn["to"]))
            print(f"  + Agrega: {conn['from']} → {conn['to']}")
        else:
            print(f"  ~ Ya existe: {conn['from']} → {conn['to']}")

    blueprint["connections"] = new_connections
    return blueprint, removed, added


def clean_verifier_broadcast(
    blueprint: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    verifier.result.out solo debe ir a supervisor.
    """
    connections = blueprint.get("connections", [])
    new_connections: List[Dict[str, str]] = []
    removed: List[Tuple[str, str]] = []
    added: List[Tuple[str, str]] = []

    for conn in connections:
        from_key = conn.get("from", "")
        to_key = conn.get("to", "")

        if from_key.startswith("verifier.engine.main:result.out"):
            if to_key in SAFE_VERIFIER_RESULT_TARGETS:
                new_connections.append(conn)
                print(f"  ✓ Mantiene: {from_key} → {to_key}")
            else:
                removed.append((from_key, to_key))
                print(f"  ✗ Elimina: {from_key} → {to_key}")
        else:
            new_connections.append(conn)

    safe_verifier_observation = [
        {"from": "verifier.engine.main:event.out", "to": "memory.log.main:event.in"},
        {"from": "verifier.engine.main:event.out", "to": "guide.main:context.in"},
    ]

    for conn in safe_verifier_observation:
        if add_connection_if_missing(new_connections, conn):
            added.append((conn["from"], conn["to"]))
            print(f"  + Agrega: {conn['from']} → {conn['to']}")

    blueprint["connections"] = new_connections
    return blueprint, removed, added


def clean_ai_assistant_broadcast(
    blueprint: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    ai.assistant.main:result.out solo debe ir a supervisor.
    No convertir event.out a response.in automáticamente.
    """
    connections = blueprint.get("connections", [])
    new_connections: List[Dict[str, str]] = []
    removed: List[Tuple[str, str]] = []
    added: List[Tuple[str, str]] = []

    for conn in connections:
        from_key = conn.get("from", "")
        to_key = conn.get("to", "")

        if from_key.startswith("ai.assistant.main:result.out"):
            if to_key in SAFE_AI_RESULT_TARGETS:
                new_connections.append(conn)
                print(f"  ✓ Mantiene: {from_key} → {to_key}")
            else:
                removed.append((from_key, to_key))
                print(f"  ✗ Elimina: {from_key} → {to_key}")
        else:
            new_connections.append(conn)

    safe_ai_observation = [
        {"from": "ai.assistant.main:event.out", "to": "memory.log.main:event.in"},
        {"from": "ai.assistant.main:event.out", "to": "guide.main:context.in"},
    ]

    for conn in safe_ai_observation:
        if add_connection_if_missing(new_connections, conn):
            added.append((conn["from"], conn["to"]))
            print(f"  + Agrega: {conn['from']} → {conn['to']}")

    blueprint["connections"] = new_connections
    return blueprint, removed, added


def summarize_changes(
    original_count: int,
    final_count: int,
    removed_workers: List[Tuple[str, str]],
    added_workers: List[Tuple[str, str]],
    removed_verifier: List[Tuple[str, str]],
    added_verifier: List[Tuple[str, str]],
    removed_ai: List[Tuple[str, str]],
    added_ai: List[Tuple[str, str]],
) -> None:
    print("=" * 70)
    print("RESUMEN:")
    print("=" * 70)
    print(f"Conexiones originales: {original_count}")
    print(f"Conexiones finales: {final_count}")
    print(
        f"Conexiones eliminadas: "
        f"{len(removed_workers) + len(removed_verifier) + len(removed_ai)}"
    )
    print(
        f"Conexiones agregadas: "
        f"{len(added_workers) + len(added_verifier) + len(added_ai)}"
    )
    print()
    print("Categorías de conexiones eliminadas:")
    print(f"  Worker result.out → no-ejecución segura: {len(removed_workers)}")
    print(f"  Verifier result.out → no-supervisor: {len(removed_verifier)}")
    print(f"  AI Assistant result.out → no-supervisor: {len(removed_ai)}")
    print()
    print("Categorías de conexiones agregadas:")
    print(f"  Observación desde supervisor.event.out: {len(added_workers)}")
    print(f"  Observación desde verifier.event.out: {len(added_verifier)}")
    print(f"  Observación desde ai.assistant.event.out: {len(added_ai)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Blueprint Cleaner - modo conservador")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica cambios al blueprint. Sin esto, solo dry-run.",
    )
    args = parser.parse_args()

    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"
    backup_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json.backup"

    print("=" * 70)
    print("BLUEPRINT CLEANER - Limpieza conservadora de result.out")
    print("=" * 70)
    print()

    print(f"Cargando: {blueprint_path}")
    blueprint = load_blueprint(str(blueprint_path))
    original_blueprint = deepcopy(blueprint)

    original_count = len(blueprint.get("connections", []))
    print(f"Conexiones originales: {original_count}")
    print()

    analysis = analyze_result_out_connections(blueprint)
    print("ANÁLISIS INICIAL:")
    print("-" * 70)
    print(f"worker.*:result.out -> {len(analysis['worker'])} conexiones")
    print(f"verifier.engine.main:result.out -> {len(analysis['verifier'])} conexiones")
    print(f"ai.assistant.main:result.out -> {len(analysis['ai_assistant'])} conexiones")
    print()

    print("LIMPIEZA WORKER BROADCAST:")
    print("-" * 70)
    blueprint, removed_workers, added_workers = clean_worker_broadcast(blueprint)
    print()

    print("LIMPIEZA VERIFIER BROADCAST:")
    print("-" * 70)
    blueprint, removed_verifier, added_verifier = clean_verifier_broadcast(blueprint)
    print()

    print("LIMPIEZA AI ASSISTANT BROADCAST:")
    print("-" * 70)
    blueprint, removed_ai, added_ai = clean_ai_assistant_broadcast(blueprint)
    print()

    final_count = len(blueprint.get("connections", []))
    summarize_changes(
        original_count,
        final_count,
        removed_workers,
        added_workers,
        removed_verifier,
        added_verifier,
        removed_ai,
        added_ai,
    )

    if not args.apply:
        print("DRY-RUN: no se escribió ningún archivo.")
        print("Usá --apply para guardar cambios.")
        print()
        print("NOTA:")
        print("  - approval.main NO se toca automáticamente")
        print("  - phase.engine.main NO se toca automáticamente")
        print("  - no se crean rutas nuevas hacia action.in")
        return

    print("Creando backup...")
    save_blueprint(str(backup_path), original_blueprint)
    print(f"Backup creado: {backup_path}")
    print()

    print("Guardando blueprint limpio...")
    save_blueprint(str(blueprint_path), blueprint)
    print()
    print("✓ Limpieza completada")
    print("✓ Backup disponible en: blueprints/system.v0.json.backup")
    print()
    print("NOTA:")
    print("  - approval.main quedó intacto")
    print("  - phase.engine.main quedó intacto")
    print("  - solo se agregaron rutas observacionales seguras")


if __name__ == "__main__":
    main()