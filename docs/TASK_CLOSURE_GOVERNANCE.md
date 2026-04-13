# Gobierno de Cierre de Tareas

## Propósito

Definir quién tiene autoridad para cerrar una tarea y quién solo informa.

Esto implementa la **Regla #9: Un solo resultado final**.

---

## Roles en el Flujo de Tarea

### 🔒 CLOSER (Único)

**Quién**: `supervisor.main`

**Autoridad**: Es el único módulo que puede marcar una tarea como `completed`, `error`, `timeout`, `cancelled`.

**Responsabilidad**:
- Recibe `result.in` del flujo de ejecución
- Decide el estado final de la tarea
- Emite el cierre oficial
- Mantiene el registro de ciclo de vida

**Input**: `supervisor.main:result.in`

**Regla inviolable**: Si `supervisor.main` no recibe el resultado, la tarea queda en `pending` hasta timeout.

---

### 📝 INFORMER (Múltiples)

**Quiénes**: Todos los workers y módulos de ejecución

- `worker.python.desktop`
- `worker.python.system`
- `worker.python.browser`
- `worker.python.terminal`
- `ai.assistant.main`

**Autoridad**: Reportan el resultado de su ejecución, pero **no cierran** la tarea.

**Responsabilidad**:
- Ejecutar la acción
- Enviar `result.out` con `status: success|error`
- Incluir `task_id` original
- Propagar `trace_id` y `meta`

**Output**: `:result.out`

**Restricción**: Un informer puede enviar a **UN SOLO** módulo de ejecución downstream (el closer o el verifier). No puede hacer broadcast de resultados.

---

### 🔍 VERIFIER (Complemento)

**Quién**: `verifier.engine.main`

**Autoridad**: Verifica el resultado del worker, pero **no reemplaza** al closer.

**Responsabilidad**:
- Recibe `result.out` del worker
- Verifica si el resultado es válido
- Enriquece el resultado con metadata de verificación
- Envía al closer con el veredicto adjunto

**Flujo**:
```
worker:result.out → verifier:result.in
verifier:result.out → supervisor:result.in
```

**Regla**: El verifier siempre termina enviando al supervisor. Nunca cierra directamente.

---

### 👁️ OBSERVER (Side-effect free)

**Quiénes**: Módulos de observación internos

- `memory.log.main` (persistencia)
- `ui.state.main` (estado visual)
- `guide.main` (contexto)
- `gamification.main` (XP/recompensas)
- `ai.learning.engine.main` (aprendizaje)

**Autoridad**: Reciben `event.out` para observar, pero **no afectan** el estado de la tarea.

**Reglas**:
1. **Nunca** responden al mensaje recibido
2. **Nunca** modifican el payload
3. **Nunca** emiten eventos que afecten el flujo
4. Solo leen y almacenan/muestran

**Patrón correcto**:
```
worker:event.out ──► memory.log.main:event.in     (observación)
             ├────► ui.state.main:event.in       (UI interna)
             └────► guide.main:event.in   (contexto)
```

---

### 📱 INTERFACE TARGET (Respuesta al usuario)

**Quiénes**: Interfaces de entrada/salida

- `interface.main` (CLI)
- `interface.telegram` (Telegram Bot)

**Autoridad**: Reciben `response.out` del supervisor con el resultado final.

**Reglas**:
1. Solo reciben mensajes, no emiten respuestas de estado
2. No observan `event.out`, solo reciben `response.out`
3. No afectan el flujo de ejecución

**Patrón correcto**:
```
supervisor:response.out ──► interface.main:response.in     (CLI)
supervisor:response.out ──► interface.telegram:response.in (Telegram)
```

**Patrones incorrectos** (violaciones):
```
# ❌ Mezclar observación con ejecución
worker:result.out ──► supervisor:result.in
              └────► memory.log:result.in       (❌ result.out no es para observar)

# ❌ Worker hablando directo a interfaz
worker:result.out ──► interface.main:response.in  (❌ bypass de supervisor)

# ❌ Approval cerrando tareas
approval.main:result.out ──► supervisor:result.in "cancelled"
                                   (❌ approval no es closer, solo aprueba/rechaza)
```

---

## Matriz de Autoridad

| Módulo | Recibe de | Envía a | Rol | Puede cerrar? |
|--------|-----------|---------|-----|---------------|
| supervisor.main | verifier, workers (via verifier) | - | CLOSER | ✅ Sí |
| verifier.engine.main | workers | supervisor | VERIFIER | ❌ No |
| worker.* | router | verifier (o supervisor si no hay verifier) | INFORMER | ❌ No |
| memory.log.main | anyone | - | OBSERVER | ❌ No |
| ui.state.main | anyone | - | OBSERVER | ❌ No |
| interface.* | supervisor | - | INTERFACE TARGET | ❌ No |
| approval.main | safety.guard | router | CONTROL | ❌ No (solo aprueba/rechaza) |

---

## Flujos Válidos

### Flujo simple (sin verifier)

```
router → worker ──► supervisor (cierra)
         │
         ├── result.out ──► supervisor
         │
         └── event.out ───► memory.log, ui.state (observan)

supervisor ── response.out ──► interface (mensaje al usuario)
```

### Flujo con verifier

```
router → worker ──► verifier ──► supervisor (cierra)
         │
         └── event.out ───► memory.log, ui.state (observan)

supervisor ── response.out ──► interface (mensaje al usuario)
```

### Flujo con aprobación

```
agent ──► safety.guard ──► approval ──► router ──► worker ──► supervisor (cierra)
         │
         └── event.out ───► memory.log, ui.state (observan)

supervisor ── response.out ──► interface (mensaje al usuario)
```

> **📌 Nota sobre aprobación (estricta)**:
> - `approval.main` solo **aprueba o rechaza** planes. **NO es closer**.
> - El **cierre oficial SIEMPRE** viene de `supervisor.main`.
> - Si approval rechaza, emite un plan cancelado que **llega al supervisor** para el **cierre formal único**.
> - **Nunca** approval emite `task.close.out` o mensajes de cierre directamente.

---

## Anti-patrones Detectados

### ❌ Broadcast de resultados

```
worker:result.out ──► supervisor:result.in
              ├────► verifier:result.in    (❌ verifier es cadena, no paralelo)
              ├────► memory.log:result.in   (❌ observación va por event.out)
              └────► interface:response.in  (❌ respuesta va por supervisor:response.out)
```

**Problema**: El worker está haciendo demasiado. Debería:
```
worker:result.out ──► verifier:result.in
verifier:result.out ──► supervisor:result.in  (cadena de cierre única)

# Observación separada (NO desde verifier:result.out)
supervisor:event.out ──► memory.log:event.in
supervisor:response.out ──► interface:response.in
```

### Modelo consistente para AI/Gamificación

> **Decisión**: `ai.learning` y `gamification` son **ejecutores secundarios**, no observadores puros.

Reciben `action.in` (no `event.in`) cuando el supervisor decide ejecutar acciones derivadas:

```
supervisor:action.out ──► ai.learning:action.in  (ejecución secundaria)
supervisor:action.out ──► gamification:action.in
```

**Por qué no `event.in`**: Son módulos de ejecución (procesan y responden), no solo de observación. Si usaran `event.in`, no podrían emitir resultados de vuelta.

### ❌ Cierre paralelo

```
worker:result.out ──► supervisor:result.in
              └────► approval:result.in   (❌ approval no cierra)
```

**Problema**: Dos módulos reciben `result.in`. Si approval también cierra, hay doble cierre.

### ❌ Observer que responde

```
memory.log:query.out ──► agent:query.in   (❌ memory no deberia llamar a agent)
```

---

## Contrato de Mensajes por Rol

### INFORMER (worker) → result.out

```json
{
  "module": "worker.python.desktop",
  "port": "result.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "worker.python.desktop",
    "timestamp": "2026-01-01T00:00:00Z",
    "plan_id": "plan_123",
    "step_id": "step_1"
  },
  "payload": {
    "task_id": "uuid",
    "status": "success|error",
    "result": {},
    "execution_time_ms": 1234
  }
}
```

> **⚠️ NOTA**: `trace_id` y `meta` van a **nivel superior del envelope**, NO dentro de `payload`.

### VERIFIER → result.out

```json
{
  "module": "verifier.engine.main",
  "port": "result.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "verifier.engine.main",
    "timestamp": "2026-01-01T00:00:01Z",
    "plan_id": "plan_123",
    "step_id": "step_1"
  },
  "payload": {
    "task_id": "uuid",
    "status": "success|error",
    "verification": {
      "verified": true,
      "original_result": {},
      "checks_passed": ["check1", "check2"]
    }
  }
}
```

### CLOSER → task.close.out (cierre)

```json
{
  "module": "supervisor.main",
  "port": "task.close.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "supervisor.main",
    "timestamp": "2026-01-01T00:00:02Z"
  },
  "payload": {
    "task_id": "uuid",
    "final_status": "success|error|timeout|cancelled",
    "closed_by": "supervisor.main",
    "execution_chain": ["agent", "safety", "router", "worker", "verifier"]
  }
}
```

---

## Decisiones de Diseño

### ¿Por qué solo supervisor puede cerrar?

1. **Single source of truth**: Un solo lugar para consultar estado de tareas
2. **Timeout handling**: Solo el supervisor sabe cuándo una tarea expiró
3. **Reconciliation**: Si hay discrepancias (worker dice success, verifier dice fail), el supervisor decide
4. **Auditoría**: Facilita trazabilidad completa

### ¿Por qué verifier no cierra?

El verifier es una capa opcional de confianza. Si no hay verifier, el worker informa directo al supervisor. El verifier enriquece, pero no reemplaza.

### ¿Por qué observers no pueden ser informers?

Para mantener la separación ejecución/observación (Regla #5). Si un observer necesita informar, es porque en realidad es parte del flujo de ejecución y debería ser tratado como tal.

---

## Checklist de Implementación

Al agregar un nuevo módulo:

- [ ] ¿Es closer? → Solo puede haber uno (supervisor)
- [ ] ¿Es verifier? → Siempre envía a supervisor
- [ ] ¿Es informer? → Solo envía a verifier o supervisor (uno solo)
- [ ] ¿Es observer? → Nunca modifica payload, nunca responde
- [ ] ¿Necesita hacer algo con el resultado? → Si es más que guardar/mostrar, no es observer

---

## Referencias

- Regla #9: `@docs/ARCHITECTURE_RULES.md`
- Auditoría de violaciones: `@lib/blueprint_auditor.py`
- Tipos de puertos: `@docs/PORT_TYPES.md`
