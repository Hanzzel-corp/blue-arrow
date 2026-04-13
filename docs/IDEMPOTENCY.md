# Idempotencia y Deduplicación

## Propósito

Prevenir efectos duplicados cuando:
- Un mensaje se re-entrega (reconexión de módulo)
- Un worker se reinicia y re-procesa
- Un timeout hace reintentar
- Hay loops en el grafo (planner ↔ phase.engine)

**Regla de oro**: Una acción con efecto real (escribir, abrir, modificar) debe ejecutarse **una sola vez**.

---

## Principio de Idempotencia

> **Regla de oro**: Una acción ejecutada N veces debe tener el mismo efecto que ejecutarla 1 vez.

### Jerarquía de Claves de Identificación

| Clave | Rol | Uso Principal |
|-------|-----|---------------|
| **task_id** | Clave principal de ejecución | Identifica una tarea específica dentro de un plan |
| **fingerprint** | Refuerzo de deduplicación | Hash de task_id + acción + params normalizados |
| **trace_id** | Trazabilidad | Rastrea el flujo completo de un mensaje, no reemplaza task_id |

> **⚠️ IMPORTANTE**: `trace_id` es para trazabilidad (auditoría, debugging), NO para deduplicación de ejecución. La deduplicación se hace por `task_id` + `fingerprint`.

### `task_id` como clave principal

```javascript
// task_id es la unidad mínima de ejecución
// Se genera en el routing y se propaga a los workers
const execution_key = task_id;  // Clave principal
const dedup_key = `${task_id}:${action}:${hash(normalized_params)}`;  // Fingerprint
```

---

## Principios

### 1. Task ID como Clave

El `task_id` es la **clave primaria de ejecución**. Su asignación efectiva queda consolidada en el **flujo operativo/routing**.

**Jerarquía**:
| Campo | Rol | Dónde se asigna |
|-------|-----|-----------------|
| `task_id` | Clave de ejecución | Routing / flujo operativo |
| `trace_id` | Trazabilidad | Inicio del flujo (no para deduplicación) |

**Flujo**:
```
routing/planner → task_id: "abc-123" → agent → router → worker
                                    └────► memory.log (observa via event.out)
```

> **⚠️ IMPORTANTE**: `trace_id` rastrea el flujo completo para auditoría/debugging. `task_id` identifica la unidad de ejecución para deduplicación. No mezclar sus usos.

Si el mismo `task_id` llega dos veces al worker, es duplicado.

### 2. Fingerprint de Acción

Para acciones sin `task_id` (eventos), usar fingerprint del payload:

```
fingerprint = hash(task_id + action + normalized_params)
```

Campos ignorados en hash:
- `_trace_id`, `_meta` (metadata interna)
- `timestamp` (varía entre reintentos)
- `request_id` (generado por módulos intermedios)

### 3. Ventana de Deduplicación

**Default**: 5 minutos (300 segundos)

Razón:
- Reconexiones de módulos son rápidas (< 30s)
- Timeouts de IA pueden ser largos (30-45s)
- Margen de seguridad

**Persistencia**: Opcional, para recovery del runtime.

---

## Implementación por Tipo de Acción

### Acciones Idempotentes (naturales)

Algunas acciones son idempotentes por diseño:

| Acción | Por qué es idempotente |
|--------|------------------------|
| `search_file` | Buscar no modifica estado |
| `monitor_resources` | Lectura de métricas |
| `ai.query` | Consulta sin side-effects |
| `memory.store` | Sobrescribe si misma clave |

**Acciones que requieren protección**:

| Acción | Efecto real | Estrategia |
|--------|-------------|------------|
| `open_application` | Abre ventana | Verificar si ya está abierta |
| `close_application` | Cierra ventana | Verificar si ya está cerrada |
| `write_file` | Escribe disco | Fingerprint de contenido |
| `send_message` | Envía mensaje | Deduplicación obligatoria |
| `run_shell` | Ejecuta comando | Deduplicación obligatoria |

---

## Contrato de Módulos

### Workers: Verificar antes de ejecutar

```python
# En worker python
import sys
import json
from lib.idempotency import check_idempotent

def handle_action(payload):
    task_id = payload.get('task_id')
    action = payload.get('action')
    params = payload.get('params', {})

    # 1. Verificar si es duplicado
    is_dup, key = check_idempotent(task_id, action, params)

    if is_dup:
        # Responder con éxito (idempotente) pero marcar como duplicado
        return {
            'task_id': task_id,
            'status': 'success',
            'result': {'executed': False, 'reason': 'duplicate', 'key': key},
            'meta': payload.get('meta', {})
        }

    # 2. Ejecutar solo si no es duplicado
    result = execute_action(action, params)

    return {
        'task_id': task_id,
        'status': 'success',
        'result': result,
        'meta': payload.get('meta', {})
    }
```

### Workers: Acciones con estado externo

Para acciones donde no podemos controlar el estado (ej: abrir app):

```python
def open_application(params):
    app_name = params.get('name')

    # 1. Verificar si ya está abierta (por nombre o PID)
    if is_app_running(app_name):
        return {'opened': False, 'already_running': True, 'pid': get_pid(app_name)}

    # 2. Solo si no está abierta, abrir
    pid = launch_app(app_name)
    return {'opened': True, 'pid': pid}
```

Esto hace la acción **idempotente por verificación de estado**.

---

## Estrategias por Acción

### Estrategia A: Deduplicación (generic)

Para acciones donde el efecto es irreversible (enviar mensaje, ejecutar shell):

```
if fingerprint ya visto:
    return success (sin ejecutar)
ejecutar
marcar fingerprint
```

### Estrategia B: Verificación de estado

Para acciones donde podemos leer el estado (abrir/cerrar apps):

```
if estado_deseado ya alcanzado:
    return success (sin ejecutar)
ejecutar
```

### Estrategia C: Transacción con rollback

Para acciones complejas (rara vez usado en este sistema):

```
start_transaction()
try:
    ejecutar_paso_1()
    ejecutar_paso_2()
    commit()
except:
    rollback()
    raise
```

---

## En el Runtime

El runtime puede ayudar con deduplicación a nivel de mensaje:

```javascript
// En runtime/bus.js
class MessageDeduplicator {
  constructor(windowMs = 300000) {
    this.seen = new Map(); // message_id -> timestamp
    this.windowMs = windowMs;
  }

  isDuplicate(msg) {
    // Usar task_id + action + normalized params como clave
    const taskId = msg.payload?.task_id || msg.meta?.task_id;
    const action = msg.payload?.action;
    const params = msg.payload?.params || {};

    const normalizedParams = JSON.stringify(
      Object.keys(params)
        .sort()
        .reduce((acc, key) => {
          acc[key] = params[key];
          return acc;
        }, {})
    );

    // Fallback para eventos sin task_id: usar fingerprint del contenido
    // trace_id NO se usa para deduplicación (solo trazabilidad)
    const effectiveId = taskId || `${action}:${normalizedParams}`;

    // trace_id es solo trazabilidad; la deduplicación se hace por task_id + acción + params
    const key = `${effectiveId}:${action}:${normalizedParams}`;

    if (this.seen.has(key)) {
      const age = Date.now() - this.seen.get(key);
      if (age < this.windowMs) {
        return true;
      }
    }

    this.seen.set(key, Date.now());
    return false;
  }
}
```

**Nota**: Esto es complementario, no reemplaza la deduplicación en workers.

---

## Casos de Borde

### Misma acción, diferentes params

```
task_id: "abc-123", action: "open_app", params: {name: "firefox"}
task_id: "abc-123", action: "open_app", params: {name: "chrome"}
```

**Resultado**: Diferente fingerprint → NO es duplicado (aunque mismo task_id).

### Diferente task_id, misma acción

```
task_id: "abc-123", action: "send_message", params: {text: "hola"}
task_id: "def-456", action: "send_message", params: {text: "hola"}
```

**Resultado**: Diferente task_id → NO es duplicado (usuario intencional).

### Reintentos del mismo upstream

```
agent envía: task_id "abc-123"
worker crashea antes de responder
agent reenvía: task_id "abc-123" (mismo ID)
```

**Resultado**: Mismo task_id + action + params → ES duplicado → rechazar.

---

## Logging y Observabilidad

### Eventos de deduplicación

```json
{
  "event_type": "action_deduplicated",
  "task_id": "abc-123",
  "action": "send_message",
  "fingerprint": "a1b2c3d4...",
  "original_timestamp": "2026-01-01T00:00:00Z",
  "duplicate_timestamp": "2026-01-01T00:00:02Z",
  "module": "worker.python.desktop"
}
```

### Métricas

- `deduplication_hits_total`: Cuántas acciones fueron deduplicadas
- `deduplication_window_seconds`: Tamaño de la ventana
- `deduplication_entries`: Entradas actuales en memoria

---

## Checklist de Implementación

Al agregar un nuevo worker:

- [ ] Identificar acciones con efecto real
- [ ] Para cada acción, elegir estrategia: dedupe o verificación de estado
- [ ] Implementar check de duplicado ANTES de ejecutar
- [ ] En caso de duplicado, responder success (no error)
- [ ] Incluir fingerprint en respuesta para debug
- [ ] Agregar tests con re-entrega de mensajes

---

## Referencias

- Implementación: `@lib/idempotency.py`
- Reglas de arquitectura: `@docs/ARCHITECTURE_RULES.md`
- Gobierno de tareas: `@docs/TASK_CLOSURE_GOVERNANCE.md`
