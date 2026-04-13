# Tipos de Puertos en blueprint-v0

Documentación de la semántica de puertos según la Regla #5: Separar Ejecución de Observación.

---

## Clasificación de Puertos

### 🔧 execution

**Propósito**: Flujo real de acciones que modifican estado o ejecutan operaciones.

**Características**:
- Conllevan una operación con side-effects
- Deben pasar por safety-guard y approval
- Tienen timeout definido
- Generan un resultado final

**Puertos típicos**:
- `command.in` → planner.main
- `plan.in` → agent.main, safety.guard.main, router.main
- `action.in` → workers
- `result.in` → verifier.engine.main, supervisor.main

**Schema**: `@schemas/port-action-in.json`

---

### 👁 observation

**Propósito**: Monitoreo, logging, eventos sin side-effects.

**Características**:
- No modifican estado del sistema
- Son "fire and forget"
- Múltiples consumidores permitidos
- No requieren aprobación

**Puertos típicos**:
- `event.out` → memory-log, ui-state (observadores puros)

**Schema**: `@schemas/port-event-out.json`

**Nota**: `result.out` NO es observación. Es el puerto de **cierre de ejecución** (worker → supervisor). Los observadores reciben `event.out` emitido por workers y/o por `supervisor.main` según el punto del flujo; `result.out` no se usa para observación.

---

### 🖥 ui

**Propósito**: Interacción con interfaces de usuario.

**Características**:
- Dirigidos a interfaces específicas (Telegram, CLI)
- Pueden incluir formateo visual
- No modifican estado de dominio

**Puertos típicos**:
- `response.in/out` → interfaces
- `ui.response.out` → telegram-interface
- `ui.state.out` → telegram-hud

---

### 💾 persistence

**Propósito**: Almacenamiento y recuperación de datos.

**Características**:
- Operaciones de lectura/escritura
- Idempotencia preferida
- No generan eventos de dominio

**Puertos típicos**:
- `query.in/out` → memory-log
- `memory.in/out` → ai-memory-semantic

---

### 🎛 control

**Propósito**: Señales de control del sistema.

**Características**:
- No son acciones de dominio
- Controlan flujo de ejecución
- Tienen prioridad alta

**Puertos típicos**:
- `signal.in/out` → phase-engine
- `approval.in/out` → approval

---

## Reglas de Uso

### 1. Un puerto, un tipo semántico

Cada puerto debe tener un tipo claro definido en su `manifest.json`:

```json
{
  "ports": {
    "action.in": {
      "type": "execution",
      "schema": "port-action-in.json",
      "timeout_ms": 5000
    },
    "event.out": {
      "type": "observation",
      "schema": "port-event-out.json"
    }
  }
}
```

### 2. Meta.propagate según tipo

| Tipo | trace_id | meta | payload |
|------|----------|------|---------|
| execution | ✅ Sí | ✅ Sí | ✅ Completo |
| observation | ✅ Sí | ✅ Sí | 📋 Resumido |
| ui | ✅ Sí | ✅ Sí | 🎨 Formateado |
| persistence | ✅ Sí | ✅ Sí | 💾 Raw |
| control | ✅ Sí | ✅ Sí | ⚡ Signal |

### 3. No mezclar flujos

```
❌ Incorrecto:
worker.result.out ──► supervisor (ejecución)
                └──► memory-log (observación)
                └──► telegram (UI)

✅ Correcto:
worker.result.out ──► supervisor (cadena de cierre)
worker.event.out ──► memory-log (observación)
worker.event.out ──► ui-state (observación interna)
supervisor.response.out ──► interface (respuesta al usuario)
```

---

## Port Naming Convention

| Patrón | Significado | Ejemplo |
|--------|-------------|---------|
| `*.in` | Entrada de mensajes | `action.in` |
| `*.out` | Salida de mensajes | `result.out` |
| `command.*` | Comandos de usuario | `command.in` |
| `plan.*` | Planes de ejecución | `plan.out` |
| `event.*` | Eventos de observación | `event.out` |
| `result.*` | Resultados de acciones | `result.out` |
| `response.*` | Respuestas a usuario | `response.out` |
| `ui.*` | UI específico | `ui.state.out` |
| `memory.*` | Persistencia | `memory.query.out` |
| `signal.*` | Control | `signal.in` |

---

## Validación en Runtime

El bus valida:

1. **trace_id obligatorio**: Todo mensaje debe tener trace_id
2. **meta.source obligatorio**: Debe indicar el origen (cli/telegram/internal/system)
3. **meta.timestamp**: Auto-generado si no existe
4. **port_type**: Enforzado según manifest del módulo

---

## Ejemplo de Flujo Completo

```
Usuario: "Abrir firefox"

[CLI] ──► interface.main:command.out
              │ type: execution
              │ trace_id: abc-123
              │ meta: {source: cli}
              ▼
[PLANNER] ──► planner.main:command.in
              │ type: execution
              │ parsea y emite plan
              ▼
[AGENT] ──► agent.main:plan.out
              │ type: execution
              │ enrich con contexto
              ▼
[SAFETY] ──► safety.guard.main:plan.in
              │ type: execution
              │ valida y aprueba
              ▼
[ROUTER] ──► router.main:plan.in
              │ type: execution
              │ enruta a worker
              ▼
[WORKER] ──► worker.python.desktop:action.in
              │ type: execution
              │ ejecuta xdotool
              ├─► event.out ──► memory-log (observation)
              ├─► event.out ──► ui-state (observation)
              └─► result.out ──► supervisor (ejecución - único)
                                   ▼
                              supervisor:result.in
                                   │ type: execution
                                   │ cierra tarea
                                   ├─► event.out ──► memory-log (observation)
                                   └─► response.out ──► interface (UI)
```

---

## Referencias

- Schema base: `@schemas/message.json`
- Schema action.in: `@schemas/port-action-in.json`
- Schema result.out: `@schemas/port-result-out.json`
- Schema event.out: `@schemas/port-event-out.json`
