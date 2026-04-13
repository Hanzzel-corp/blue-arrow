# Guía de Contratos para Módulos

Cómo implementar contratos correctamente en tus módulos.

---

## Estructura Base Obligatoria

Todo mensaje que envíe un módulo debe seguir este shape:

```json
{
  "module": "tu.modulo",
  "port": "action.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "cli",
    "timestamp": "2024-01-01T00:00:00Z",
    "chat_id": 123
  },
  "payload": {
    "task_id": "uuid",
    "action": "nombre",
    "params": {}
  }
}
```

**Campos obligatorios**:
- `module`: ID del módulo emisor
- `port`: Puerto de salida
- `trace_id`: Identificador de traza (se propaga) - **nivel superior**
- `meta`: Metadatos del mensaje - **nivel superior**
- `meta.source`: Origen del comando
- `meta.timestamp`: Timestamp ISO8601
- `payload`: Datos del mensaje

**⚠️ IMPORTANTE**: `trace_id` y `meta` deben estar en el **nivel superior** del mensaje, NO dentro del payload.

---

## En Node.js

### 1. Leer mensajes con contexto

```javascript
import readline from 'readline';

const rl = readline.createInterface({ input: process.stdin });

rl.on('line', (line) => {
  const msg = JSON.parse(line);

  // Extraer contexto
  const { trace_id, meta, payload } = msg;

  // Procesar
  const result = processAction(payload);

  // Responder con contexto propagado
  respond({
    task_id: payload.task_id,
    status: 'success',
    result
  }, { trace_id, meta });
});
```

### 2. Enviar mensajes con contexto

```javascript
const MODULE_ID = "tu.modulo";

/**
 * Emite un mensaje completo con envelope v2
 * @param {string} port - Puerto de salida
 * @param {object} payload - Datos del mensaje
 * @param {string} trace_id - ID de trazabilidad (a nivel superior)
 * @param {object} meta - Metadatos (plan_id, step_id, etc. dentro de meta)
 */
function emit(port, payload, trace_id = null, meta = {}) {
  const finalTraceId = trace_id || `${MODULE_ID}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  const finalMeta = {
    source: MODULE_ID,
    timestamp: new Date().toISOString(),
    ...meta
  };
  
  process.stdout.write(
    JSON.stringify({
      module: MODULE_ID,
      port,
      trace_id: finalTraceId,  // ← A nivel superior, NO dentro de payload
      meta: finalMeta,           // ← A nivel superior, NO dentro de payload
      payload                   // ← Solo los datos de negocio
    }) + "\n"
  );
}

// Ejemplo de uso con contexto heredado:
// emit('result.out', {task_id: 't1', status: 'success'}, msg.trace_id, msg.meta)
```

---

## En Python

### 1. Leer mensajes con contexto

```python
import sys
import json

def read_messages():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Extraer contexto
        trace_id = msg.get('trace_id')
        meta = msg.get('meta', {})
        payload = msg.get('payload', {})

        # Procesar
        result = process_action(payload)

        # Responder con contexto
        respond({
            'task_id': payload.get('task_id'),
            'status': 'success',
            'result': result
        }, trace_id=trace_id, meta=meta)
```

### 2. Enviar mensajes con contexto

```python
import json
import sys
from datetime import datetime

def respond(payload, trace_id=None, meta=None):
    message = {
        'module': 'tu.modulo',
        'port': 'result.out',
        'payload': payload,
        'trace_id': trace_id,
        'meta': {
            **(meta or {}),
            'source': meta.get('source', 'internal') if meta else 'internal',
            'timestamp': datetime.now().isoformat()
        }
    }

    sys.stdout.write(json.dumps(message) + '\n')
    sys.stdout.flush()
```

---

## Helpers Disponibles

### En runtime/transforms.js

```javascript
import { createResponse, extractContext } from './transforms.js';

// Extraer contexto del ENVELOPE completo (mensaje recibido)
// NO del payload - trace_id y meta están a nivel superior del envelope
const { trace_id, meta, cleanPayload } = extractContext(envelope);

// envelope = { module, port, trace_id, meta, payload }
// cleanPayload = payload (datos de negocio puros)
// trace_id = envelope.trace_id (a nivel superior)
// meta = envelope.meta (a nivel superior)

// Crear respuesta con contexto preservado
const response = createResponse(
  { status: 'success', result: data },
  { trace_id, meta }
);
```

---

## Ejemplo Completo: Worker

```javascript
// modules/worker-python/main.js
import readline from 'readline';
import { spawn } from 'child_process';

const rl = readline.createInterface({ input: process.stdin });

rl.on('line', (line) => {
  const msg = JSON.parse(line);
  const { payload, trace_id, meta } = msg;

  // Validar contrato
  if (!payload.task_id || !payload.action) {
    errorResponse('Missing required fields', { task_id: payload.task_id, trace_id, meta });
    return;
  }

  // Ejecutar
  execute(payload.action, payload.params)
    .then(result => {
      respond({
        task_id: payload.task_id,
        status: 'success',
        result
      }, { trace_id, meta });

      // Evento de observación
      event({
        event_type: 'completed',
        task_id: payload.task_id,
        data: { action: payload.action }
      }, { trace_id, meta });
    })
    .catch(err => {
      respond({
        task_id: payload.task_id,
        status: 'error',
        error: { message: err.message }
      }, { trace_id, meta });
    });
});

function respond(payload, context) {
  console.log(JSON.stringify({
    module: 'worker.python.desktop',
    port: 'result.out',
    payload,
    trace_id: context.trace_id,
    meta: { ...context.meta, timestamp: new Date().toISOString() }
  }));
}

function event(payload, context) {
  console.log(JSON.stringify({
    module: 'worker.python.desktop',
    port: 'event.out',
    payload: { ...payload, timestamp: new Date().toISOString() },
    trace_id: context.trace_id,
    meta: { ...context.meta, timestamp: new Date().toISOString() }
  }));
}

function errorResponse(message, context) {
  // Errores de ejecución van por result.out para cerrar la tarea como fallida
  console.log(JSON.stringify({
    module: 'worker.python.desktop',
    port: 'result.out',
    trace_id: context?.trace_id,
    meta: { ...(context?.meta || {}), timestamp: new Date().toISOString() },
    payload: { 
      task_id: context?.task_id,
      status: 'error',
      error: message 
    }
  }));
}
```

---

## Checklist de Validación

Antes de enviar un mensaje, verificar:

- [ ] `module` está definido y es válido
- [ ] `port` sigue convención `*.in` o `*.out`
- [ ] `payload` tiene `task_id` (si es ejecución)
- [ ] `trace_id` está presente (heredado o generado)
- [ ] `meta.source` está definido
- [ ] `meta.timestamp` está presente

---

## Errores Comunes

### ❌ Perder el contexto

```javascript
// Mal: No propaga trace_id/meta
console.log(JSON.stringify({
  module: 'x',
  port: 'result.out',
  payload: { status: 'success' }
  // Falta trace_id y meta!
}));
```

### ✅ Propagar correctamente

```javascript
// Bien: Contexto completo
console.log(JSON.stringify({
  module: 'x',
  port: 'result.out',
  payload: { status: 'success' },
  trace_id: context.trace_id,
  meta: { ...context.meta, timestamp: new Date().toISOString() }
}));
```

---

## Depuración

El runtime loguea automáticamente:

- Mensajes sin `trace_id` (genera uno)
- Mensajes sin `meta` (crea uno mínimo)
- `trace_id` en cada mensaje enrutado

Ver logs:

```bash
tail -f logs/events.log | grep trace_id
```

---

## Referencias

- Schema base: `@schemas/message.json`
- Schema action.in: `@schemas/port-action-in.json`
- Schema result.out: `@schemas/port-result-out.json`
- Tipos de puertos: `@docs/PORT_TYPES.md`
