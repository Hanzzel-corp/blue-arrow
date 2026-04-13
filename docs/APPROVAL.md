# Approval Module - Documentación

## ✅ Circuito de Aprobaciones

<p align="center">
  <b>Módulo core que gestiona aprobaciones explícitas del usuario para acciones de riesgo medio-alto</b>
</p>

---

## 📋 Índice

1. [Visión General](#visión-general)
2. [Flujo de Aprobación](#flujo-de-aprobación)
3. [API y Puertos](#api-y-puertos)
4. [Tipos de Aprobación](#tipos-de-aprobación)
5. [Timeout y Expiración](#timeout-y-expiración)
6. [Configuración](#configuración)
7. [Ejemplos](#ejemplos)

---

## Visión General

`approval.main` implementa el **circuit breaker humano**. Cuando `agent.main` o `safety.guard.main` detectan una acción que requiere confirmación, el plan se pausa y se solicita aprobación explícita al usuario vía la interfaz activa (Telegram/CLI).

### Rol en el Sistema

| Característica | Valor |
|----------------|-------|
| **Tipo** | Core - Circuito de Control |
| **Autoridad** | Puede aprobar/rechazar, pero no ejecutar |
| **Puerto de Entrada** | `plan.in` desde `safety.guard.main` |
| **Puerto de Salida** | `plan.out` hacia `router.main` (si aprobado) |

### Flujo de Control

```
safety.guard.main ──► approval.main ──► router.main
   (detecta riesgo)    (aprueba/rechaza)   (ejecuta)
```

### Integración con Interfaces

El approval module **no conecta directamente** a las interfaces. El flujo real es:

```
approval.main:approval.request.out
         │
         ▼
┌─────────────────┐
│  supervisor o   │  (el observador distribuye)
│  memory/state   │
└────────┬────────┘
         │
         ├──────────► interface.telegram (UI al usuario)
         │
         ◀─────────── interface.telegram (respuesta usuario)
         │             approval.response.in
         ▼
    approval.main
         │
         ▼ (si aprobado)
    router.main
```

> **Nota**: En la práctica, el approval puede emitir `event.out` que el `ui.state.main` o `interface.telegram` escuchan para mostrar botones. La respuesta del usuario viene por `callback.in` o un puerto similar.

---

## Flujo de Aprobación

### Diagrama de Estados

```
┌──────────┐    plan.in (riesgo detectado)    ┌──────────┐
│  IDLE    │─────────────────────────────────▶│ PENDING  │
└──────────┘                                 └──────────┘
                                                    │
                         ┌────────────────────────┤
                         ▼                        ▼
                  ┌──────────┐           ┌──────────┐
                  │ APPROVED │           │ REJECTED │
                  └────┬─────┘           └────┬─────┘
                       │                        │
                       ▼                        ▼
               plan.out (to router)     event.out (rechazo)
```

### Proceso Completo

```
1. RECEPCIÓN DE PLAN CON RIESGO
   plan.in: {
     "requires_approval": true,
     "risk_level": "high",
     "approval_reason": "Acción destructiva"
   }
           │
           ▼
2. GENERACIÓN DE SOLICITUD
   - Crear approval_id
   - Generar mensaje de UI
   - Calcular timeout
           │
           ▼
3. SOLICITUD AL USUARIO
   approval.request.out → (observadores)
   ↳ ui.state.main / interface.telegram detectan el evento y muestran UI
   "⚠️ Esta acción eliminará archivos. ¿Aprobar? [Sí] [No]"
           │
           ▼
4. ESPERA DE RESPUESTA
   (timeout: 60 segundos por defecto)
           │
           ▼
5. PROCESAMIENTO DE RESPUESTA
   IF approved:
     plan.out → router.main
   ELSE:
     event.out (rechazado)
```

---

## API y Puertos

### Entrada: `plan.in`

```json
{
  "plan_id": "plan_123",
  "requires_approval": true,
  "risk_level": "high",
  "approval_reason": "Eliminación de archivos",
  "approval_prompt": "¿Desea eliminar el directorio '/tmp/old_files'?",
  "timeout_ms": 60000,
  "trace_id": "abc-123"
}
```

### Salida: `approval.request.out`

```json
{
  "approval_id": "approval_123",
  "plan_id": "plan_123",
  "prompt": "¿Desea eliminar el directorio '/tmp/old_files'?",
  "risk_level": "high",
  "timeout_ms": 60000,
  "options": ["approve", "reject"],
  "trace_id": "abc-123"
}
```

### Salida: `plan.out` (si aprobado)

```json
{
  "plan_id": "plan_123",
  "approved": true,
  "approval_id": "approval_123",
  "approved_at": "2026-01-01T00:01:00Z",
  "approved_by": "user_123",
  "steps": [...]
}
```

### Entrada: `approval.response.in`

```json
{
  "approval_id": "approval_123",
  "response": "approve|reject",
  "responded_by": "user_123",
  "timestamp": "2026-01-01T00:01:00Z"
}
```

---

## Tipos de Aprobación

### Según Nivel de Riesgo

| Nivel | Descripción | Timeout | UI |
|-------|-------------|---------|-----|
| `medium` | Comandos de terminal | 60s | Botón simple |
| `high` | Borrar archivos, instalar software | 120s | Confirmación con detalles |
| `critical` | Formatear, acceso root | 300s | Doble confirmación |

### Ejemplos por Categoría

```javascript
const APPROVAL_TEMPLATES = {
  file_delete: {
    risk: 'high',
    prompt: '¿Eliminar {count} archivos de {directory}?',
    timeout_ms: 60000
  },
  terminal_command: {
    risk: 'medium',
    prompt: '¿Ejecutar "{command}" en terminal?',
    timeout_ms: 60000
  },
  install_package: {
    risk: 'high',
    prompt: '¿Instalar {package}? Requiere permisos de administrador.',
    timeout_ms: 120000
  }
};
```

---

## Timeout y Expiración

### Comportamiento por Timeout

```javascript
function handleTimeout(approval) {
  if (approval.elapsed_ms > approval.timeout_ms) {
    // Default: rechazar en timeout
    return {
      status: 'expired',
      action: 'reject',
      reason: 'Timeout - usuario no respondió'
    };
  }
}
```

### Configuración de Timeouts

| Tipo de Acción | Timeout | Acción en Timeout |
|----------------|---------|-------------------|
| Media riesgo | 60s | Rechazar (seguro por defecto) |
| Alto riesgo | 120s | Rechazar |
| Crítico | 300s | Rechazar + alerta |

---

## Configuración

### Manifest

```json
{
  "id": "approval.main",
  "name": "Circuito de Aprobaciones",
  "tier": "core",
  "priority": "high",
  "inputs": ["plan.in", "approval.response.in"],
  "outputs": ["plan.out", "approval.request.out", "event.out"],
  "config": {
    "default_timeout_ms": 60000,
    "max_pending_approvals": 5,
    "auto_reject_on_timeout": true,
    "require_confirmation_for": ["high", "critical"]
  }
}
```

---

## Ejemplos

### Ejemplo 1: Aprobación Exitosa

**Entrada**:
```json
{
  "plan_id": "plan_001",
  "requires_approval": true,
  "risk_level": "high",
  "approval_reason": "Eliminar archivos"
}
```

**Solicitud a Usuario**:
```json
{
  "approval_id": "approval_001",
  "prompt": "⚠️ ¿Eliminar 5 archivos de /tmp?",
  "options": ["✅ Sí, eliminar", "❌ No, cancelar"]
}
```

**Respuesta de Usuario**:
```json
{
  "approval_id": "approval_001",
  "response": "approve"
}
```

**Salida**:
```json
{
  "plan_id": "plan_001",
  "approved": true,
  "approval_id": "approval_001"
}
```

### Ejemplo 2: Timeout

**Solicitud** enviada a las 10:00:00
**Sin respuesta hasta** 10:01:00 (timeout)

**Salida**:
```json
{
  "type": "approval_expired",
  "approval_id": "approval_002",
  "plan_id": "plan_002",
  "reason": "Timeout - usuario no respondió en 60s",
  "auto_action": "rejected"
}
```

---

## Referencias

- **[SAFETY_GUARD.md](SAFETY_GUARD.md)** - Validación de seguridad previa
- **[AGENT.md](AGENT.md)** - Detección de riesgo
- **[TASK_CLOSURE_GOVERNANCE.md](TASK_CLOSURE_GOVERNANCE.md)** - Gobierno de cierre

---

<p align="center">
  <b>Approval Module v1.0.0</b><br>
  <sub>Circuito de aprobaciones - Core de control</sub>
</p>
