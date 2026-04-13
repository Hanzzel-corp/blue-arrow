# Resiliencia Avanzada y Versionado

## Back-Pressure (Control de Flujo)

### Propósito

Evitar la saturación de módulos mediante control de flujo automático. Cuando un módulo no puede procesar mensajes a la velocidad que llegan, el sistema aplica back-pressure para proteger la estabilidad.

### Estrategias

| Estrategia | Cuándo se aplica | Acción |
|------------|------------------|--------|
| **Rate Limiting** | >50 mensajes/seg | Delay o drop |
| **Queue Limiting** | Cola >100 mensajes | Shedding o pausa |
| **Load Shedding** | Sobrecarga extrema | Descartar mensajes no críticos |
| **Flow Control** | Cola >95% capacidad | Pausar emisores |

### Configuración

```javascript
// runtime/config.js
const backpressureConfig = {
  maxQueueSize: 100,        // Mensajes pendientes máximos
  maxRatePerSecond: 50,     // Rate por módulo
  rateWindowMs: 1000,       // Ventana de medición
  
  // Tipos de mensaje
  sheddableTypes: ['event.out', 'query.in'],  // Descartables
  criticalTypes: ['action.in', 'plan.in'],      // Protegidos
  
  // Umbrales
  warningThreshold: 0.8,    // 80% - warning
  criticalThreshold: 0.95  // 95% - backpressure
};
```

### Comportamiento

```
Mensaje llega → Rate limit OK? → Queue space OK? → Enviar
                    ↓ No                    ↓ No
              [Delay si crítico]      [Drop si sheddable]
              [Drop si no crítico]    [Backpressure si crítico]
```

### Logs

```
[WARN] Rate limit exceeded for agent.main, delaying critical message
[WARN] Queue full for memory.log.main, shedding message (event.out)
[ERROR] Queue full for router.main, applying backpressure
[INFO] Backpressure released for router.main
```

### Métricas

```javascript
// Acceso a estadísticas
const stats = runtimeBus.backPressure.getStats();

// Retorna:
{
  global: {
    totalDropped: 15,      // Mensajes descartados
    totalDelayed: 3,       // Mensajes retrasados
    pausedModules: ['memory.log.main']  // Módulos pausados
  },
  modules: {
    'agent.main': {
      queueSize: 45,
      queueUtilization: 0.45,
      currentRate: 30,
      rateUtilization: 0.60,
      isPaused: false
    }
  }
}
```

---

## Contract Versioning (Versionado de Contratos)

### Propósito

Permitir la evolución de los contratos de mensajes sin romper compatibilidad. Cada puerto tiene versiones soportadas y migraciones automáticas.

### Versionado Semántico

- **Major**: Cambios breaking (requieren migración)
- **Minor**: Adiciones compatibles
- **Patch**: Fixes sin cambio de interface

### Versiones Actuales

| Contrato | v1.0.0 | v2.0.0 | Cambios v2 |
|----------|--------|--------|------------|
| `message` | module, port, payload | **envelope** con trace_id, meta + payload | Estructura plana: todo a nivel superior |
| `action.in` | task_id, action, params | task_id, action, params + meta | Contexto obligatorio en envelope.meta |
| `result.out` | task_id, status | task_id, status + meta | Propagación de contexto vía envelope |
| `event.out` | event_type | +timestamp, +meta | Metadata obligatoria |

### Migración v1 → v2

> **⚠️ IMPORTANTE**: La migración v1→v2 **no es solo de payload**, es del **envelope completo**:
> - v1: `{ module, port, payload }` con metadata dentro de `payload`
> - v2: `{ module, port, trace_id, meta, payload }` con metadata a nivel superior

**Automática** para campos compatibles:
- `task_id` → preservado (dentro de payload)
- `payload` → preservado (contenido)
- `meta` (si existía en payload) → movido a **nivel superior del envelope**
- `trace_id` → **nuevo campo obligatorio** a nivel superior

**Requiere actualización manual**:
- Agregar `trace_id` generado en envelope
- Verificar `module` y `port` en envelope
- Actualizar handlers que lean `payload.meta` → ahora es `envelope.meta`
- Los que leían `payload.trace_id` → ahora es `envelope.trace_id`

### Negociación

Los módulos negocian versión al conectar:

```
Productor (v2.0.0) ──→ ←── Consumidor (v1.0.0, v2.0.0)
                              Versión negociada: v2.0.0
```

Si no hay versión común → Error de conexión

### Migraciones Automáticas

```javascript
// Ejemplo: v1.0.0 → v2.0.0
const v1Message = {
  module: "agent.main",
  port: "action.out",
  payload: { task_id: "abc", action: "open" }
};

// Migración automática
const v2Message = {
  ...v1Message,
  trace_id: "gen-1234567890",  // Generado si falta
  meta: {
    source: "unknown",         // Default si falta
    timestamp: "2024-01-15T10:30:00Z"
  }
};
```

### Registro de Versiones

```javascript
// En manifest.json
{
  "id": "agent.main",
  "ports": {
    "action.out": {
      "versions": ["1.0.0", "2.0.0"],
      "defaultVersion": "2.0.0"
    }
  }
}
```

### Validación Estricta

```javascript
// Mensaje inválido (falta campo requerido en v2)
const invalid = {
  module: "agent.main",
  port: "action.out",
  payload: {},
  trace_id: "abc"
  // ❌ Falta meta!
};

// Resultado de validación
{
  valid: false,
  errors: ["Missing required field: meta"],
  version: "2.0.0"
}
```

---

## Integración en Runtime

### Configuración

```javascript
const runtimeBus = new RuntimeBus(registry, blueprint, {
  backpressure: {
    maxQueueSize: 100,
    maxRatePerSecond: 50
  }
});
```

### Flujo Completo

```
1. Mensaje recibido
   ↓
2. Contract versioning → Negociar versión
   ↓
3. Contract enforcer → Validar campos
   ↓
4. Back-pressure → Verificar capacidad
   ↓
5. Enviar a módulo destino
   ↓
6. Notificar procesamiento (liberar cola)
```

### Prioridad de Sistemas

| Orden | Sistema | Propósito |
|-------|---------|-----------|
| 1 | Contract Versioning | Negociar versión compatible |
| 2 | Contract Enforcer | Validar estructura |
| 3 | Back-Pressure | Control de flujo |
| 4 | Tier Manager | Gestión de prioridades |

---

## Monitoreo

### Métricas de Back-Pressure

```bash
# Logs periódicos (cada 60s)
[INFO] Backpressure stats: { dropped: 0, delayed: 2, paused: 0 }

# Alertas
[WARN] Module agent.main under pressure (queue: 85/100)
[ERROR] Module supervisor.main CRITICAL (queue: 98/100)
```

### Métricas de Versionado

```bash
# Negociaciones exitosas
[INFO] Negotiated action.in@2.0.0 for agent.main -> router.main

# Fallos de compatibilidad
[ERROR] No common version for result.out between worker.desktop(v1) and supervisor(v2)
```

---

## Troubleshooting

### Back-Pressure Excesivo

**Síntoma**: Muchos mensajes descartados

```bash
# Ver estadísticas
python3 -c "from runtime.backpressure import getBackPressureManager; print(getBackPressureManager().getStats())"
```

**Soluciones**:
1. Aumentar `maxQueueSize` (temporal)
2. Optimizar módulo lento (permanente)
3. Añadir más workers (escalar)
4. Reducir carga de entrada

### Incompatibilidad de Versiones

**Síntoma**: Mensajes rechazados por versión

```bash
[ERROR] Validation failed: Missing required field: meta
```

**Soluciones**:
1. Actualizar módulo consumidor a versión más nueva
2. Agregar migración al version manager
3. Rollback de productor a versión anterior

---

## Referencias

- Implementación: `runtime/backpressure.js`
- Versionado: `runtime/contract_versioning.js`
- Configuración: `runtime/config.js`
- Contratos: `schemas/*.json`
