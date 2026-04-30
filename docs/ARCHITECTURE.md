# Arquitectura

> 🌐 [English version → ARCHITECTURE_EN.md](ARCHITECTURE_EN.md)

## Resumen

El sistema sigue una arquitectura modular por procesos:

- `runtime` (Node.js) descubre modulos y enruta mensajes
- cada modulo vive en su propio proceso
- contratos de comunicacion por puertos + JSON Lines
- topologia declarada en `blueprints/system.v0.json`

## Componentes

- `runtime/main.js`: arranque, validacion de modulos, bootstrap del bus
- `runtime/registry.js`: descubrimiento de `manifest.json`
- `runtime/bus.js`: conexion de puertos entre modulos
- `runtime/transforms.js`: normalizacion de mensajes entre modulos

## Blueprint

`blueprints/system.v0.json` define:
- `modules`: modulos que deben existir y levantarse
- `connections`: wiring desde `moduleA:port.out` hacia `moduleB:port.in`

Esta definicion evita acoplamiento por imports directos.

## Contrato de mensajes (v2)

Formato general emitido por modulos:

```json
{
  "module": "module.id",
  "port": "event.out",
  "trace_id": "uuid-trace-123",
  "meta": {
    "source": "cli|telegram|internal",
    "timestamp": "2026-01-01T00:00:00Z",
    "chat_id": 123456789,
    "task_id": "task_123"
  },
  "payload": {}
}
```

**⚠️ REGLA**: `trace_id` y `meta` deben estar en el **nivel superior**, NO dentro del payload.

Recomendaciones:
- puertos con semantica clara (`command.in`, `result.out`, `event.out`)
- `trace_id` obligatorio para trazabilidad completa
- `meta.source`, `meta.timestamp` obligatorios
- evitar campos implicitos no documentados

## Flujo principal

```text
interface -> planner -> agent -> safety/approval -> router -> workers
                                     \-> supervisor (cierra tarea)
workers:result.out -> verifier -> supervisor (cierre con verificación)
workers:result.out -> memory/ui/interface (observación, no cierra)
```

**Patrón de cierre único**: `supervisor.main` es el único módulo con autoridad para cerrar tareas. Workers informan, observers escuchan.

## Workers

- `worker.python.desktop`: acciones sobre aplicaciones y terminal
- `worker.python.system`: recursos y busquedas en filesystem
- `worker.python.browser`: navegacion/acciones web via Playwright

## Persistencia

Persistencia de estado en `logs/`:
- memoria de sesion
- trazas de eventos
- estado de UI y sesiones de apps

## Limites y decisiones de diseno

- sin imports cruzados entre modulos de dominio
- integracion por puertos declarados
- orquestacion centralizada en runtime
- extensibilidad por nuevos modulos/manifests y wiring en blueprint
