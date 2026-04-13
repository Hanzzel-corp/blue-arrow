#!/usr/bin/env python3
"""
Fix Closure Violations - Limpia conexiones que violan el gobierno de cierre.

Problema: Módulos satélite (gamification, ai.*) envían result.out a memory.log
Solución: Cambiar a event.out o eliminar, ya que son observadores, no informers.
"""

import json
from pathlib import Path


def load_blueprint(path: str):
    with open(path) as f:
        return json.load(f)


def save_blueprint(path: str, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def fix_closure_violations(blueprint: dict) -> tuple[dict, list]:
    """Limpia violaciones de gobierno de cierre."""
    connections = blueprint.get("connections", [])
    new_connections = []
    removed = []
    added = []
    
    # Módulos que NO deberían enviar result.out (son observers)
    observer_modules = [
        "gamification.main",
        "ai.learning.engine.main",
        "ai.memory.semantic.main",
        "ai.self.audit.main",
    ]
    
    for conn in connections:
        from_key = conn.get("from", "")
        to_key = conn.get("to", "")
        
        from_mod = from_key.split(":")[0]
        from_port = from_key.split(":")[1] if ":" in from_key else ""
        
        # ¿Es un observer enviando result.out?
        is_observer = any(from_mod.startswith(obs) for obs in observer_modules)
        is_result_out = "result.out" in from_port
        
        if is_observer and is_result_out:
            # Esto viola el gobierno - observers no deben "cerrar" nada
            removed.append((from_key, to_key))
            print(f"  ✗ Elimina: {from_key} -> {to_key}")
            
            # Opcionalmente, agregar como event.out si va a memory.log
            if "memory.log.main" in to_key:
                new_event_conn = {
                    "from": from_key.replace("result.out", "event.out"),
                    "to": to_key.replace("result.in", "event.in")
                }
                added.append(new_event_conn)
                print(f"  + Agrega: {new_event_conn['from']} -> {new_event_conn['to']}")
            continue
        
        new_connections.append(conn)
    
    # Agregar nuevas conexiones
    for conn in added:
        # Evitar duplicados
        exists = any(
            c["from"] == conn["from"] and c["to"] == conn["to"]
            for c in new_connections
        )
        if not exists:
            new_connections.append(conn)
    
    blueprint["connections"] = new_connections
    return blueprint, removed, added


def main():
    blueprint_path = Path(__file__).parent.parent / "blueprints" / "system.v0.json"
    
    print("=" * 70)
    print("FIX CLOSURE VIOLATIONS")
    print("=" * 70)
    print()
    
    print(f"Cargando: {blueprint_path}")
    blueprint = load_blueprint(str(blueprint_path))
    original_count = len(blueprint["connections"])
    print(f"Conexiones originales: {original_count}")
    print()
    
    print("Limpiando violaciones de gobierno...")
    print("-" * 70)
    blueprint, removed, added = fix_closure_violations(blueprint)
    print()
    
    final_count = len(blueprint["connections"])
    
    print("=" * 70)
    print("RESUMEN:")
    print("=" * 70)
    print(f"Conexiones originales: {original_count}")
    print(f"Conexiones finales: {final_count}")
    print(f"Eliminadas: {len(removed)}")
    print(f"Agregadas (como event): {len(added)}")
    print()
    
    if removed:
        print("Conexiones eliminadas:")
        for from_key, to_key in removed:
            print(f"  - {from_key} -> {to_key}")
        print()
    
    print("Guardando...")
    save_blueprint(str(blueprint_path), blueprint)
    print("✓ Blueprint actualizado")
    print()
    
    # Validar de nuevo
    print("Re-validando gobierno de cierre...")
    print("-" * 70)


if __name__ == "__main__":
    main()
