# Contratos de Puertos - Blueprint v0

## Resumen

Este documento define los contratos de comunicación entre módulos en el sistema blueprint-v0. Cada puerto tiene un schema JSON definido en `schemas/ports.json` y sigue un formato estandarizado.

## Formato de Mensajes

Todos los mensajes entre módulos siguen este formato base (contrato v2):

```json
{
  "module": "module.id",
  "port": "port.direction",
  "trace_id": "abc-123",
  "meta": {
    "source": "cli|telegram|internal",
    "timestamp": "2026-01-01T00:00:00Z",
    "chat_id": 123456789
  },
  "payload": { /* port-specific data */ }
}
```

**Campos obligatorios**:
- `module`: ID del módulo emisor
- `port`: Puerto de salida (`*.in` o `*.out`)
- `trace_id`: Identificador único de traza (se propaga entre mensajes)
- `meta`: Metadatos del mensaje (nivel superior)
- `meta.source`: Origen del comando (`cli`, `telegram`, `internal`)
- `meta.timestamp`: Timestamp ISO8601
- `payload`: Datos específicos del puerto

**⚠️ IMPORTANTE**: `trace_id` y `meta` deben estar en el **nivel superior** del mensaje, NO dentro del payload.

## Contratos por Puerto

### Comandos (Commands)

#### `command.in` / `command.out`
**Propósito**: Comandos de usuario desde interfaces

**Schema**:
```json
{
  "command_id": "cmd_1234567890",
  "text": "abrir chrome",
  "source": "cli|telegram",
  "chat_id": 123456789,
  "user_id": "user123"
}
```

**Módulos que lo usan**:
- `interface.main` → `planner.main` (`command.out`)
- `interface.telegram` → `planner.main` (`command.out`)

### Planes (Plans)

#### `plan.in` / `plan.out`
**Propósito**: Planes de ejecución generados por el agente

**Schema**:
```json
{
  "plan_id": "plan_1234567890",
  "kind": "single_step|multi_step",
  "original_command": "abrir chrome",
  "steps": [
    {
      "action": "open_application",
      "params": {"name": "chrome"},
      "step_id": "step_1"
    }
  ],
  "confidence": 0.95,
  "chat_id": 123456789
}
```

**Módulos que lo usan**:
- `planner.main` → `agent.main` (`plan.out`)
- `agent.main` → `safety.guard.main` (`plan.out`)
- `safety.guard.main` → `router.main` (out - approved)
- `approval.main` → `router.main` (out - approved)

### Acciones (Actions)

#### `action.in` / `action.out`
**Propósito**: Acciones específicas para workers

**Tipos de acciones**:

**Desktop Action**:
```json
{
  "task_id": "task_1234567890",
  "action": "open_application|focus_window|echo_text",
  "params": {
    "name": "chrome",
    "text": "Hola mundo",
    "visible": true,
    "execute": true
  },
  "context": {
    "plan_id": "plan_123",
    "step_id": "step_1"
  }
}
```

**Terminal Action**:
```json
{
  "task_id": "task_1234567890",
  "action": "terminal.write_command|terminal.show_command",
  "params": {
    "command": "ls -l",
    "visible": true
  },
  "context": {
    "plan_id": "plan_123",
    "step_id": "step_1"
  }
}
```

**Acciones de Desktop disponibles**:
- `open_application`: Abre una aplicación (params: name)
- `focus_window`: Enfoca una ventana (params: name)
- `echo_text`: Retorna el texto proporcionado (params: text)

**Acciones de Terminal disponibles**:
- `terminal.write_command`: Escribe un comando en la terminal (params: command)
- `terminal.show_command`: Muestra un comando en la terminal (params: command)

**System Action**:
```json
{
  "task_id": "task_1234567890",
  "action": "search_file",
  "params": {
    "pattern": "*.py",
    "directory": "/home/user"
  }
}
```

**Browser Action**:
```json
{
  "task_id": "task_1234567890",
  "action": "open_url",
  "params": {
    "url": "https://example.com"
  }
}
```

**Módulos que lo usan**:
- `router.main` → `worker.python.desktop` (out - desktop.action)
- `router.main` → `worker.python.terminal` (out - terminal.action)
- `router.main` → `worker.python.system` (out - system.action)
- `router.main` → `worker.python.browser` (out - browser.action)

### Resultados (Results)

#### `result.in` / `result.out`
**Propósito**: Resultados de ejecución de workers

**Schema**:
```json
{
  "task_id": "task_1234567890",
  "status": "success|error|timeout",
  "result": {
    "message": "Application opened successfully",
    "data": {"window_id": 12345}
  },
  "error": "Error message if status is error",
  "execution_time": 1.23,
  "action": "open_application"
}
```

**Módulos que lo usan**:
- `worker.python.*` → `supervisor.main` (out - **cadena de cierre**)
- `verifier.engine.main` → `supervisor.main` (out - verificado)

> **📌 Separación de responsabilidades**:
> - `result.out` → Solo cadena de cierre (worker → [verifier] → supervisor)
> - `event.out` → Observadores internos (memory.log, ui.state, gamification)
> - `response.out` → Interfaces (desde supervisor)

### Eventos (Events)

#### `event.in` / `event.out`
**Propósito**: Eventos del sistema para logging y supervisión

**Schema**:
```json
{
  "event_type": "plan_created|plan_approved|task_started|module_error",
  "source": "agent.main",
  "data": {
    "plan_id": "plan_1234567890",
    "reason": "Safety check passed"
  },
  "timestamp": "2026-01-01T00:00:00Z"
}
```

**Tipos de eventos**:
- `plan_created`: Nuevo plan creado
- `plan_approved`: Plan aprobado por safety
- `plan_rejected`: Plan rechazado por safety
- `plan_started`: Plan comenzó ejecución
- `plan_completed`: Plan completado exitosamente
- `plan_failed`: Plan falló
- `task_started`: Tarea individual comenzó
- `task_completed`: Tarea individual completada
- `task_failed`: Tarea individual falló
- `module_started`: Módulo iniciado
- `module_error`: Error en módulo
- `safety_block`: Safety bloqueó acción
- `approval_required`: Requiere aprobación manual

**Módulos que lo usan**:
- Todos los módulos → `memory.log.main` (out - observación)
- Módulos relevantes → `ui.state.main` (out - observación de UI interna)
- `supervisor.main` emite sus propios `event.out` y `response.out` según el estado final de la tarea

### Memoria (Memory)

#### `query.in` / `memory.out`
**Propósito**: Consultas y respuestas de memoria

**Query Schema**:
```json
{
  "query_type": "last_command|last_result|last_app_opened|system_status",
  "filters": {
    "source": "cli",
    "limit": 10
  }
}
```

**Memory Response Schema**:
```json
{
  "query_type": "last_command",
  "data": {
    "command": "abrir chrome",
    "timestamp": "2026-01-01T00:00:00Z",
    "source": "cli"
  },
  "timestamp": "2026-01-01T00:00:00Z"
}
```

**Tipos de queries**:
- `last_command`: Último comando ejecutado
- `last_result`: Último resultado obtenido
- `last_app_opened`: Última aplicación abierta
- `last_file_search`: Última búsqueda de archivos
- `system_status`: Estado actual del sistema
- `session_info`: Información de la sesión

**Módulos que lo usan**:
- `agent.main` ↔ `memory.log.main` (query/response)
- `telegram.menu.main` ↔ `memory.log.main` (query/response)
- `memory.menu.main` ↔ `memory.log.main` (query/response)

### Aprobaciones (Approvals)

#### `request.in` / `response.out`
**Propósito**: Sistema de aprobaciones manuales

**Request Schema**:
```json
{
  "request_id": "req_1234567890",
  "plan": {
    "plan_id": "plan_1234567890",
    "kind": "multi_step",
    "steps": [...]
  },
  "reason": "Action requires manual approval",
  "timeout": 300,
  "source": "safety.guard.main"
}
```

**Response Schema**:
```json
{
  "request_id": "req_1234567890",
  "decision": "approved|rejected|timeout",
  "reason": "User approved action",
  "approved_by": "user123"
}
```

**Módulos que lo usan**:
- `safety.guard.main` → `approval.main` (out - blocked.plan)
- `approval.main` → `router.main` (out - approved.plan)
- `telegram.menu.main` ↔ `approval.main` (request/response)

### UI y Respuestas

#### `response.out`
**Propósito**: Respuesta final al usuario desde el supervisor

**Schema**:
```json
{
  "module": "supervisor.main",
  "port": "response.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "supervisor.main",
    "destination": "interface.telegram",
    "timestamp": "2026-01-01T00:00:05Z"
  },
  "payload": {
    "task_id": "task_123",
    "user_message": "✅ Tarea completada",
    "type": "success",
    "chat_id": 123456789
  }
}
```

**Módulos que lo usan**:
- `supervisor.main` → `interface.main` (out - response)
- `supervisor.main` → `interface.telegram` (out - response)

### Estado UI (UI State)

#### `event.in` / `ui.state.out`

**Propósito**: Estado y actualización de la interfaz de usuario interna

**Entrada (`event.in`)**:
- `supervisor.main` → `ui.state.main` (out - event)
- `worker.python.*` → `ui.state.main` (out - event)

**UI State Schema**:
```json
{
  "current_plan": {
    "plan_id": "plan_1234567890",
    "status": "running",
    "progress": 0.6
  },
  "active_tasks": [
    {
      "task_id": "task_123",
      "action": "open_application",
      "status": "running"
    }
  ],
  "recent_results": [
    {
      "task_id": "task_122",
      "status": "success",
      "timestamp": "2026-01-01T00:00:00Z"
    }
  ]
}
```

**Módulos que lo usan**:
- `supervisor.main` → `ui.state.main` (out - event)
- `worker.python.*` → `ui.state.main` (out - event)
- `ui.state.main` → `telegram.hud.main` (out - ui.state)

### Callbacks de Telegram

#### `callback.out`
**Propósito**: Manejo de callbacks de botones inline de Telegram

**Callback Schema**:
```json
{
  "callback_id": "cb_1234567890",
  "data": "view_plan_123",
  "user": {
    "id": 123456789,
    "username": "user123"
  },
  "message": {
    "message_id": 456,
    "chat_id": 123456789
  }
}
```

**Módulos que lo usan**:
- `interface.telegram` → `telegram.menu.main` (out)
- `interface.telegram` → `system.menu.main` (out)
- `interface.telegram` → `memory.menu.main` (out)
- `interface.telegram` → `apps.menu.main` (out)
- `interface.telegram` → `ui.state.main` (out)

### Sesión de Aplicaciones

#### `app.session.in` / `memory.sync.out`
**Propósito**: Seguimiento de estado de aplicaciones abiertas

**App Context Schema**:
```json
{
  "app_name": "chrome",
  "window_id": 12345,
  "process_id": 67890,
  "opened_at": "2026-01-01T00:00:00Z",
  "last_action": "open_application",
  "meta": {
    "url": "https://example.com",
    "tabs": 3
  }
}
```

**Módulos que lo usan**:
- `worker.python.desktop` → `apps.session.main` (out - result)
- `worker.python.browser` → `apps.session.main` (out - result)
- `apps.session.main` → `ui.state.main` (out - app.context)
- `apps.session.main` → `memory.log.main` (out - app.session)

## Validación

Todos los mensajes son validados contra los schemas definidos en:
- `schemas/message.json` - Schema base de mensajes
- `schemas/ports.json` - Schemas específicos de puertos

La validación se realiza en el runtime usando `runtime/schema_validator.js`.

## Convenciones

1. **Nomenclatura de puertos**: `entity.direction` (ej: `command.in`, `result.out`)
2. **IDs únicos**: Todos los IDs deben seguir patrones específicos
   - `command_id`: `cmd_` + timestamp
   - `plan_id`: `plan_` + timestamp  
   - `task_id`: `task_` + timestamp
   - `request_id`: `req_` + timestamp
3. **Timestamps**: Formato ISO 8601 cuando se incluyen
4. **Meta campo**: Para contexto transversal (source, chat_id, etc.)
5. **Errores**: Siempre incluir campo `error` cuando `status` es `error`

## Flujo Típico

```
1. interface.main:command.out → planner.main:command.in
2. planner.main:plan.out → agent.main:plan.in
3. agent.main:plan.out → safety.guard.main:plan.in
4. safety.guard.main:approved.plan.out → router.main:plan.in
5. router.main:action.out → worker.python.desktop:action.in
6. worker.python.desktop:result.out → [verifier.engine.main:result.in]
7. [verifier.engine.main:result.out] → supervisor.main:result.in
8. supervisor.main:response.out → interface.main:response.in
```

**Separación de salidas**:
```
worker.python.desktop:result.out ──► [verifier] ──► supervisor ──► response.out ──► interface
worker.python.desktop:event.out ──────────────────────────────────────► memory.log, ui.state
```

> **📌 Nota**: El verifier es opcional. En perfiles minimal/standard:
> `worker.python.desktop:result.out → supervisor.main:result.in` (directo)

**Flujo canonico completo**:
```
interface → planner → agent → safety → [approval] → router → workers → [verifier] → supervisor
                                                                             ↓
                                                                    response.out → interfaces
                                                                    event.out → observers
