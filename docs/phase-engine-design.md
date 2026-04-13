> **⚠️ DISEÑO CONCEPTUAL / TARGET ARCHITECTURE**
>
> Este documento describe el **modelo objetivo state-driven** para blueprint-v0.
> - NO representa necesariamente el wiring canónico activo del runtime
> - Algunas responsabilidades aquí descritas para `phase.engine.main`, `agent.main`, `planner.main` y `ui.state.main` pertenecen a la **arquitectura objetivo**
> - Para el estado actual de transición, ver `PHASE_ENGINE_SUMMARY.md` 
> - Para contratos y flujo operativo canónico actual, ver `PORT_CONTRACTS.md` y `TASK_CLOSURE_GOVERNANCE.md` 
>
> **Rol de este documento**: resumen ejecutivo de la arquitectura objetivo y de la estrategia de migración por módulos/fases.

# Phase Engine - Sistema State-Driven para blueprint-v0

## Diseño Completo: Reemplazo de Tokenización por Máquina de Estados

**Versión:** 1.0  
**Estado:** Diseño Conceptual Listo para Implementación  
**Relación:** Complementa y potencia el Execution Verifier Engine

---

# A. PRINCIPIO CENTRAL

## De Tokenos a Estados

```
ANTES (Token-based):
texto → tokens → intención → acción
  ↓       ↓        ↓         ↓
"abrir   [abrir]  open_app  ejecutar
 terminal"

DESPUÉS (State-driven):
señal → estado_actual → transición → acción → nuevo_estado
  ↓         ↓            ↓          ↓           ↓
user    idle        planning    open_app   executing
command             → approve
```

**La diferencia clave:**
- **Antes:** Interpretamos qué dice el usuario (ambiguo, depende del lenguaje)
- **Ahora:** Procesamos señales estructuradas en contexto de estado (determinista, verificable)

---

# B. MODELO DE ESTADO GLOBAL

## Estructura del Estado del Sistema

```json
{
  "version": "1.0",
  "timestamp": "2026-04-06T19:00:00Z",
  "session_id": "sess_1775512000",
  
  "phase": {
    "current": "planning",
    "previous": "idle",
    "history": [
      {"from": "idle", "to": "intent_detected", "at": "19:00:01"},
      {"from": "intent_detected", "to": "planning", "at": "19:00:02"}
    ]
  },
  
  "context": {
    "user": {
      "chat_id": 1781005414,
      "user_id": 1781005414,
      "source": "telegram"
    },
    "active_app": {
      "id": "terminal",
      "window_id": "0x04200001",
      "verified": true,
      "confidence": 0.95
    },
    "active_web": null,
    "task": {
      "task_id": "task_123",
      "intent": "open_terminal_and_run_command",
      "params": {"command": "ls"},
      "status": "planning"
    }
  },
  
  "signals": {
    "pending": [],
    "last_processed": {
      "type": "user_command",
      "intent": "open_terminal_and_run_command",
      "confidence": 0.95,
      "at": "19:00:00"
    }
  },
  
  "memory": {
    "short_term": {
      "last_command": "open_terminal_and_run_command",
      "last_result": "success_verified"
    },
    "session": {
      "commands_count": 5,
      "success_rate": 0.95
    }
  }
}
```

## Fases del Sistema (State Machine)

```
┌────────────────────────────────────────────────────────────────────┐
│                    PHASE STATE MACHINE                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│   ┌─────────┐                                                       │
│   │  IDLE   │◄─────────────────────────────────────────────────┐     │
│   └────┬────┘                                                  │     │
│        │ user_command                                           │     │
│        ▼                                                       │     │
│   ┌─────────────┐     plan_ready     ┌─────────────┐           │     │
│   │   INTENT    │───────────────────►│   SAFETY    │           │     │
│   │  DETECTED   │                    │   CHECK     │           │     │
│   └──────┬──────┘                    └──────┬──────┘           │     │
│          │                                  │                  │     │
│          │                                  │ needs_approval   │     │
│          │                                  ▼                  │     │
│          │                           ┌─────────────┐           │     │
│          │                           │  APPROVAL   │           │     │
│          │                           │   PENDING   │           │     │
│          │                           └──────┬──────┘           │     │
│          │                                  │ approved         │     │
│          │                                  │ rejected         │     │
│          │                                  ▼                  │     │
│          ▼                           ┌─────────────┐           │     │
│   ┌─────────────┐    rejected        │  APPROVED   │───────────┘     │
│   │  PLANNING   │◄───────────────────│   (ready)   │                 │
│   │             │──────────────────►└─────────────┘                 │
│   └──────┬──────┘     no_plan_needed                                │
│          │                                                          │
│          ▼ execute                                                   │
│   ┌─────────────┐                                                    │
│   │  EXECUTING  │◄────────────────────────────────────────────┐     │
│   └──────┬──────┘                                             │     │
│          │ worker_result                                      │     │
│          ▼                                                    │     │
│   ┌─────────────┐     error              ┌─────────────┐        │     │
│   │  VERIFYING  │───────────────────────►│   FAILED    │        │     │
│   └──────┬──────┘                        │  (terminal) │        │     │
│          │ verified                     └─────────────┘        │     │
│          ▼                                                       │     │
│   ┌─────────────┐                                                │     │
│   │  COMPLETED  │───────────────────────────────────────────────┘     │
│   └─────────────┘                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Descripción de Fases

| Fase | Descripción | Entradas Permitidas | Acciones |
|------|-------------|---------------------|----------|
| `idle` | Sistema esperando input | `user_command`, `system_event` | Detectar intención, actualizar contexto |
| `intent_detected` | Señal de intención recibida | `intent_confirmed` | Validar intención, determinar si necesita plan |
| `planning` | Construyendo plan de acción | `plan_ready`, `no_plan_needed` | Generar pasos, validar prerequisitos |
| `plan_ready` | Plan listo para validación | `safety_check` | Enviar a safety guard |
| `awaiting_approval` | Esperando aprobación usuario | `approved`, `rejected` | Mostrar UI de approval, timeout handling |
| `approved` | Plan aprobado | `execute` | Enviar a router para ejecución |
| `executing` | Ejecutando acciones | `worker_result`, `timeout`, `error` | Monitorear progreso, recolectar resultados |
| `verifying` | Verificando resultado | `verified`, `verification_failed` | Aplicar Execution Verifier Engine |
| `completed` | Acción completada exitosamente | `reset`, `new_command` | Actualizar memoria, volver a idle |
| `failed` | Acción falló | `retry`, `abort`, `new_command` | Loggear error, ofrecer retry, volver a idle |
| `unknown` | Estado indeterminado (error recovery) | `reset`, `diagnose` | Diagnóstico, limpieza, recovery |

---

# C. SISTEMA DE SEÑALES (SIGNALS)

## Principio: Todo es una Señal

**No parseamos texto. Procesamos señales estructuradas.**

```json
{
  "signal": {
    "id": "sig_1775512000_001",
    "type": "user_command | worker_result | system_event | approval_response | error | timeout",
    "source": "telegram | desktop_worker | browser_worker | system_worker | safety_guard | approval_module | phase_engine",
    "timestamp": "2026-04-06T19:00:00Z",
    "payload": {},
    "confidence": 0.95,
    "context": {
      "phase_at_receipt": "idle",
      "session_id": "sess_1775512000"
    }
  }
}
```

## Tipos de Señales

### 1. `user_command` - Señal de entrada del usuario

```json
{
  "signal": {
    "type": "user_command",
    "source": "telegram",
    "payload": {
      "raw_input": "abrir terminal y ejecutar ls",
      "intent": "open_terminal_and_run_command",
      "params": {
        "application": "terminal",
        "command": "ls"
      },
      "entities": {
        "app": "terminal",
        "command": "ls"
      }
    },
    "confidence": 0.92,
    "requires_disambiguation": false
  }
}
```

**NO es NLP tradicional:** El `intent` y `params` vienen de un sistema de **resolución estructurada** (puede ser LLM, reglas, o matching contra catálogo de capacidades), NO de tokenización.

### 2. `intent_detected` - Intención validada

```json
{
  "signal": {
    "type": "intent_detected",
    "source": "agent.main",
    "payload": {
      "intent": "open_application",
      "target": "terminal",
      "params": {},
      "resolved_app": {
        "id": "terminal",
        "command": "gnome-terminal",
        "verified": true
      }
    },
    "confidence": 0.95
  }
}
```

### 3. `plan_ready` - Plan de acción construido

```json
{
  "signal": {
    "type": "plan_ready",
    "source": "planner.main",
    "payload": {
      "plan_id": "plan_123",
      "steps": [
        {
          "step_id": "step_1",
          "action": "open_application",
          "params": {"name": "terminal"},
          "depends_on": null
        },
        {
          "step_id": "step_2",
          "action": "terminal.write_command",
          "params": {"command": "ls"},
          "depends_on": "step_1"
        }
      ],
      "estimated_duration_ms": 3000,
      "risk_level": "low"
    }
  }
}
```

### 4. `safety_result` - Resultado de safety check

```json
{
  "signal": {
    "type": "safety_result",
    "source": "safety_guard.main",
    "payload": {
      "plan_id": "plan_123",
      "policy": "allow",  // allow | confirm | block
      "risk": "low",      // low | medium | high
      "can_proceed": true,
      "requires_approval": false
    }
  }
}
```

### 5. `approval_response` - Respuesta del usuario

```json
{
  "signal": {
    "type": "approval_response",
    "source": "approval.main",
    "payload": {
      "plan_id": "plan_123",
      "response": "approved",  // approved | rejected
      "user_id": 1781005414,
      "approved_at": "2026-04-06T19:00:15Z"
    }
  }
}
```

### 6. `worker_result` - Resultado de ejecución

```json
{
  "signal": {
    "type": "worker_result",
    "source": "worker.python.desktop",
    "payload": {
      "task_id": "task_123",
      "action": "open_application",
      "status": "success",
      "result": {
        "opened": true,
        "_verification": {
          "confidence": 0.95,
          "level": "window_confirmed",
          "executive_state": "success_verified"
        }
      }
    }
  }
}
```

### 7. `verification_result` - Resultado de verificación

```json
{
  "signal": {
    "type": "verification_result",
    "source": "verifier.engine.main",
    "payload": {
      "task_id": "task_123",
      "verified": true,
      "confidence": 0.95,
      "classification": "success_verified",
      "evidence_summary": "window_confirmed, process_detected"
    }
  }
}
```

### 8. `error` - Error del sistema

```json
{
  "signal": {
    "type": "error",
    "source": "worker.python.desktop",
    "payload": {
      "task_id": "task_123",
      "error_type": "window_not_found",
      "error_message": "La aplicación no mostró ventana nueva",
      "recoverable": true,
      "suggested_action": "retry_with_longer_timeout"
    }
  }
}
```

### 9. `timeout` - Timeout de operación

```json
{
  "signal": {
    "type": "timeout",
    "source": "supervisor.main",
    "payload": {
      "task_id": "task_123",
      "phase": "executing",
      "timeout_ms": 30000,
      "partial_result": {
        "process_detected": true,
        "window_detected": false
      }
    }
  }
}
```

### 10. `state_transition` - Transición de estado completada

```json
{
  "signal": {
    "type": "state_transition",
    "source": "phase.engine.main",
    "payload": {
      "from": "idle",
      "to": "intent_detected",
      "trigger": "user_command",
      "duration_ms": 50,
      "success": true
    }
  }
}
```

---

# D. PHASE ENGINE CORE

## Arquitectura del Motor

```
┌────────────────────────────────────────────────────────────────────┐
│                     PHASE ENGINE CORE                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐         │
│  │   SIGNAL    │────►│   STATE     │────►│ TRANSITION  │         │
│  │   QUEUE     │     │   STORE     │     │   ENGINE    │         │
│  └─────────────┘     └─────────────┘     └──────┬──────┘         │
│         ▲                                        │                │
│         │                                        ▼                │
│         │                               ┌─────────────┐          │
│         │                               │   ACTION    │          │
│         │                               │   HANDLER   │          │
│         │                               └──────┬──────┘          │
│         │                                      │                 │
│         │                    ┌─────────────────┼─────────────────┐│
│         │                    │                 │                 ││
│         │                    ▼                 ▼                 ▼│
│         │             ┌──────────┐    ┌──────────┐    ┌──────────┐│
│         │             │  WORKER  │    │   UI     │    │  MEMORY  ││
│         │             │ COMMANDS │    │ UPDATES  │    │  STORE   ││
│         │             └──────────┘    └──────────┘    └──────────┘│
│         │                                                          │
│         └──────────────────────────────────────────────────────────┘
│                    (new signals generated)                         │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Componentes Internos

### 1. Signal Queue
- Cola de señales pendientes
- Prioridad por tipo (error > user_command > system_event)
- Deduplicación automática

### 2. State Store
- Estado global del sistema (JSON)
- Historial de transiciones
- Snapshots para recovery

### 3. Transition Engine
- Reglas de transición (state + signal → action + new_state)
- Validadores de condiciones
- Manejo de transiciones inválidas

### 4. Action Handlers
- Ejecutores de acciones por fase
- Integración con workers
- Emisión de nuevas señales

## Contrato del Módulo

### Puertos

```json
{
  "ports": {
    "signal.in": {
      "description": "Señales de entrada desde cualquier módulo"
    },
    "signal.out": {
      "description": "Señales de salida hacia otros módulos"
    },
    "state.query.in": {
      "description": "Queries de estado actual"
    },
    "state.out": {
      "description": "Updates de estado para UI/memoria"
    },
    "command.out": {
      "description": "Comandos a workers (delegado)"
    },
    "event.out": {
      "description": "Eventos de lifecycle"
    }
  }
}
```

### Mensajes de Entrada

**`signal.in`:**
```json
{
  "port": "signal.in",
  "payload": {
    "signal": {
      "type": "user_command",
      "payload": {...}
    }
  }
}
```

**`state.query.in`:**
```json
{
  "port": "state.query.in",
  "payload": {
    "query": "current_phase | full_state | task_status",
    "requester": "ui.state.main"
  }
}
```

### Mensajes de Salida

**`signal.out`:**
```json
{
  "port": "signal.out",
  "payload": {
    "signal": {
      "type": "state_transition",
      "payload": {...}
    }
  }
}
```

**`state.out`:**
```json
{
  "port": "state.out",
  "payload": {
    "phase": "executing",
    "context": {...},
    "transition": {
      "from": "approved",
      "to": "executing",
      "trigger": "worker_execution_start"
    }
  }
}
```

---

# E. TRANSICIONES DE ESTADO

## Tabla de Transiciones

| Estado Actual | Señal de Entrada | Condición | Nueva Fase | Acciones | Emite |
|---------------|------------------|-----------|------------|----------|-------|
| `idle` | `user_command` | `confidence > 0.7` | `intent_detected` | Detectar intención, validar | `intent_detected` |
| `idle` | `user_command` | `confidence <= 0.7` | `idle` | Pedir clarificación | `needs_clarification` |
| `intent_detected` | `intent_validated` | `requires_planning == true` | `planning` | Iniciar planificación | `planning_started` |
| `intent_detected` | `intent_validated` | `requires_planning == false` | `plan_ready` | Crear plan single-step | `plan_ready` |
| `planning` | `plan_ready` | `risk_level <= medium` | `plan_ready` | Validar plan | `plan_validated` |
| `planning` | `plan_failed` | - | `failed` | Loggear error | `planning_error` |
| `plan_ready` | `safety_result` | `policy == allow` | `approved` | Auto-aprobar | `auto_approved` |
| `plan_ready` | `safety_result` | `policy == confirm` | `awaiting_approval` | Enviar a approval UI | `approval_requested` |
| `plan_ready` | `safety_result` | `policy == block` | `failed` | Bloquear, notificar | `plan_blocked` |
| `awaiting_approval` | `approval_response` | `response == approved` | `approved` | Proceder | `plan_approved` |
| `awaiting_approval` | `approval_response` | `response == rejected` | `failed` | Cancelar | `plan_rejected` |
| `awaiting_approval` | `timeout` | `timeout > 30s` | `failed` | Cancelar por timeout | `approval_timeout` |
| `approved` | `execute` | - | `executing` | Enviar a router | `execution_started` |
| `executing` | `worker_result` | `status == success` | `verifying` | Iniciar verificación | `verification_started` |
| `executing` | `worker_result` | `status == error` | `failed` | Procesar error | `execution_failed` |
| `executing` | `timeout` | `partial_result != null` | `verifying` | Verificar resultado parcial | `partial_execution` |
| `executing` | `timeout` | `partial_result == null` | `failed` | Fallo total | `execution_timeout` |
| `verifying` | `verification_result` | `verified == true` | `completed` | Completar, actualizar memoria | `task_completed` |
| `verifying` | `verification_result` | `verified == false` | `failed` | Fallo de verificación | `verification_failed` |
| `completed` | `reset` | - | `idle` | Limpiar contexto task | `ready_for_next` |
| `failed` | `retry` | `retry_count < 3` | `planning` | Reintentar plan | `retrying` |
| `failed` | `abort` | - | `idle` | Limpiar, listo | `aborted` |
| `any` | `system_reset` | - | `idle` | Forzar reset | `system_reset` |
| `any` | `emergency_stop` | - | `idle` | Parada de emergencia | `emergency_stop` |

## Diagrama de Transiciones (Visual)

```
                    ┌─────────────────────────────────────┐
                    │          EMERGENCY_STOP             │
                    │   (desde cualquier estado)          │
                    └──────────────┬──────────────────────┘
                                   │
                                   ▼
    ┌─────────┐   user_command   ┌─────────────┐   intent_validated   ┌───────────┐
    │  IDLE   │──────────────────►│    INTENT   │──────────────────────►│ PLANNING  │
    │         │◄────────────────│   DETECTED  │                      │           │
    └────┬────┘   reset          └─────────────┘                      └─────┬─────┘
         │                                                                  │
         │                                                                  │ plan_ready
         │                                                                  ▼
         │                                                            ┌───────────┐
         │                                                            │ PLAN_READY│
         │                                                            │           │
         │         ┌──────────────────────────────────────────────────┤           │
         │         │                                                  └─────┬─────┘
         │         │                                                        │
         │         │         ┌───────────────┐                              │ safety_result
         │         │         │ AWAITING_    │◄─────────────────────────────┤ (needs approval)
         │         │         │   APPROVAL   │                              │
         │         │         └───────┬───────┘                              │
         │         │                 │ approved                            │
         │         │                 │ rejected                          │ safety_result
         │         │                 ▼                                    │ (allow)
         │         │           ┌─────────┐                                │
         │         └───────────┤APPROVED │◄─────────────────────────────────┘
         │                     └────┬────┘
         │                          │ execute
         │                          ▼
         │                    ┌───────────┐
         │                    │ EXECUTING │◄──────────────────────────────┐
         │                    └─────┬─────┘                               │
         │                          │                                     │
         │          ┌───────────────┼───────────────┐                     │
         │          │               │               │                     │
         │          ▼               ▼               ▼                     │
         │    ┌───────────┐   ┌───────────┐   ┌───────────┐              │
         │    │   ERROR   │   │  TIMEOUT  │   │  SUCCESS  │              │
         │    │           │   │ (partial) │   │           │              │
         │    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘              │
         │          │               │               │                     │
         │          │               └───────┬───────┘                     │
         │          │                       │                             │
         │          │                       ▼                             │
         │          │               ┌───────────┐                         │
         │          │               │ VERIFYING │─────────────────────────┘
         │          │               └─────┬─────┘   (retry worker_result)
         │          │                     │
         │          │         ┌───────────┴───────────┐
         │          │         │                       │
         │          │         ▼                       ▼
         │          │   ┌───────────┐         ┌───────────┐
         │          └──►│  FAILED   │         │ COMPLETED │
         │              │           │         │           │
         │              └─────┬─────┘         └─────┬─────┘
         │                    │                     │
         │              retry   │                     │ reset
         │              abort   │                     │
         └──────────────────────┴─────────────────────┘
```

---

# F. INTEGRACIÓN CON MÓDULOS EXISTENTES

## Opción Recomendada: Phase Engine como Módulo Central

```
ANTES:
interface → agent → planner → safety → approval → router → workers → supervisor → ui

DESPUÉS:
interface → agent → PHASE ENGINE (coordina) → ...
                   ↓
              ┌────┴────┐
              ▼         ▼
          planner    safety → approval → router → workers → supervisor
              ↑                                    ↓
              └──────────────────────────────────────┘
                                                   ↓
                                            PHASE ENGINE (estado)
                                                   ↓
                                               ui.state
```

## Cambios por Módulo

### 1. `agent.main` - Solo Detector de Intención

**ANTES:**
- Parseaba texto
- Construía planes
- Enviaba a planner

**DESPUÉS:**
- Recibe texto del usuario
- **Genera señal** `intent_detected` (NO construye plan)
- Señal va a Phase Engine

```javascript
// ANTES
function handleCommand(text) {
  const plan = buildPlan(text);  // ❌ Parser interno
  emit("plan.out", plan);
}

// DESPUÉS
function handleCommand(text) {
  const intent = detectIntent(text);  // Resolución estructurada
  emit("signal.out", {
    type: "intent_detected",
    payload: { intent, confidence: 0.95 }
  });  // ✅ Señal estructurada
}
```

### 2. `phase.engine.main` - Nuevo Módulo (NÚCLEO)

**Responsabilidades:**
- Recibir todas las señales
- Mantener estado global
- Ejecutar transiciones
- Orquestar flujo entre módulos

**Wiring en blueprint:**
```json
{
  "modules": ["phase.engine.main", "..."],
  "connections": [
    {"from": "agent.main:signal.out", "to": "phase.engine.main:signal.in"},
    {"from": "phase.engine.main:signal.out", "to": "planner.main:signal.in"},
    {"from": "phase.engine.main:command.out", "to": "router.main:command.in"},
    {"from": "phase.engine.main:state.out", "to": "ui.state.main:state.in"}
  ]
}
```

### 3. `planner.main` - Solo Planificador

**ANTES:**
- Recibía texto o intención
- Decidía qué hacer
- Enviaba a safety

**DESPUÉS:**
- Recibe señal `planning_request` desde Phase Engine
- Construye plan
- **Emite señal** `plan_ready` de vuelta a Phase Engine

### 4. `supervisor.main` - Monitoreo con Contexto de Fase

**ANTES:**
- Seguía task_id
- Timeout genérico

**DESPUÉS:**
- Recibe estado actual desde Phase Engine
- Ajusta timeouts según fase
- Emite señales de timeout contextualizadas

### 5. `ui.state.main` - UI Basada en Estado

**ANTES:**
- Escuchaba eventos dispersos
- Construía estado reactivamente

**DESPUÉS:**
- Recibe `state.out` completo desde Phase Engine
- UI es proyección directa del estado
- Badges de fase actual: "🔄 Ejecutando...", "✅ Completado"

---

# G. ESTRATEGIA DE MIGRACIÓN

## Fase 0: Preparación (Semana 1)

1. Crear `phase.engine.main` módulo básico
2. Definir schema de señales
3. Implementar Signal Queue y State Store
4. Tests unitarios del core

## Fase 1: Coexistencia (Semana 2-3)

1. `agent.main` emite señales ESTRUCTURADAS (además de mantener flujo actual)
2. `phase.engine.main` consume señales en modo **observador** (solo logging)
3. Validar que señales capturan todo el flujo
4. No cambiar comportamiento aún

## Fase 2: Signal-Driven (Semana 4-5)

1. Activar transiciones en Phase Engine
2. `agent.main` deja de enviar a `planner` directamente
3. Todo flujo pasa por Phase Engine
4. Fallback a flujo antiguo si Phase Engine falla

## Fase 3: State-Driven (Semana 6-7)

1. `planner` recibe desde Phase Engine, no directo
2. `supervisor` lee estado desde Phase Engine
3. `ui.state` lee estado completo desde Phase Engine
4. Sistema completamente state-driven

## Fase 4: Eliminación (Semana 8)

1. Remover código legacy de parsing en `agent`
2. Limpiar conexiones directas obsoletas
3. Documentación y optimización

---

# H. EJEMPLOS CONCRETOS (4 CASOS)

## Caso 1: "Abrir terminal"

### Flujo State-Driven

```
1. USER INPUT
   Usuario escribe: "abrir terminal"

2. SEÑAL GENERADA (agent.main)
   {
     "signal": {
       "type": "user_command",
       "source": "telegram",
       "payload": {
         "raw_input": "abrir terminal",
         "intent": "open_application",
         "params": {"application": "terminal"},
         "resolved_app": {"id": "terminal", "command": "gnome-terminal"}
       },
       "confidence": 0.95
     }
   }

3. TRANSICIÓN 1 (Phase Engine)
   Estado: idle
   Señal: user_command (confidence 0.95)
   Condición: confidence > 0.7 ✓
   ─────────────────────────────
   Nueva Fase: intent_detected
   Acción: Validar intención
   Emite: intent_validated

4. TRANSICIÓN 2 (Phase Engine)
   Estado: intent_detected
   Señal: intent_validated
   Condición: requires_planning == false (single action)
   ─────────────────────────────
   Nueva Fase: plan_ready
   Acción: Crear plan single-step
   Plan: [{action: "open_application", params: {name: "terminal"}}]
   Emite: plan_ready

5. TRANSICIÓN 3 (Phase Engine)
   Estado: plan_ready
   Señal: safety_result (policy: allow)
   ─────────────────────────────
   Nueva Fase: approved
   Acción: Auto-aprobar (bajo riesgo)
   Emite: auto_approved

6. TRANSICIÓN 4 (Phase Engine)
   Estado: approved
   Señal: execute
   ─────────────────────────────
   Nueva Fase: executing
   Acción: Enviar comando a router
   Emite: execution_started → router.main

7. WORKER EJECUTA (worker.python.desktop)
   Ejecuta: open_application("terminal")
   Resultado: {
     "opened": true,
     "_verification": {
       "confidence": 0.95,
       "executive_state": "success_verified"
     }
   }

8. SEÑAL WORKER_RESULT
   {
     "signal": {
       "type": "worker_result",
       "payload": {
         "status": "success",
         "result": {"_verification": {...}}
       }
     }
   }

9. TRANSICIÓN 5 (Phase Engine)
   Estado: executing
   Señal: worker_result (success)
   ─────────────────────────────
   Nueva Fase: verifying
   Acción: Enviar a Verifier Engine
   Emite: verification_started

10. TRANSICIÓN 6 (Phase Engine)
    Estado: verifying
    Señal: verification_result (verified: true)
    ─────────────────────────────
    Nueva Fase: completed
    Acción: Actualizar memoria, notificar UI
    Emite: task_completed → ui.state

11. RESPUESTA TELEGRAM
    "✅ Terminal abierta y verificada. Ventana activa detectada."
```

## Caso 2: "Abrir chrome y buscar X"

### Flujo State-Driven (Multi-step)

```
1. USER INPUT
   "abrir chrome y buscar recetas de pasta"

2. SEÑAL
   {
     "type": "user_command",
     "intent": "open_browser_and_search",
     "params": {
       "browser": "chrome",
       "query": "recetas de pasta"
     }
   }

3. TRANSICIÓN: idle → intent_detected

4. TRANSICIÓN: intent_detected → planning
   (requires_planning == true porque son 2 pasos)

5. PLAN CONSTRUIDO
   [
     {step: 1, action: "open_application", params: {name: "chrome"}},
     {step: 2, action: "search_google", params: {query: "recetas de pasta"},
      depends_on: 1}
   ]

6. TRANSICIÓN: planning → plan_ready → approved → executing

7. EJECUCIÓN PASO 1
   Phase Engine envía: execute step 1
   Worker abre Chrome
   Resultado: success_verified

8. EJECUCIÓN PASO 2
   Phase Engine detecta step 1 completado
   Envía: execute step 2
   Worker busca "recetas de pasta"
   Resultado: success_verified (results: [...])

9. TRANSICIÓN: executing → verifying → completed

10. RESPUESTA TELEGRAM
    "✅ Chrome abierto y búsqueda completada. Encontré 5 resultados sobre recetas de pasta."
```

## Caso 3: Flujo con Approval (Comando de riesgo medio)

```
1. USER INPUT
   "borrar archivo importante.txt"

2. SEÑAL
   {
     "type": "user_command",
     "intent": "delete_file",
     "params": {"file": "importante.txt"},
     "risk": "medium"
   }

3. TRANSICIONES
   idle → intent_detected → planning → plan_ready

4. SAFETY CHECK
   {
     "policy": "confirm",
     "risk": "medium",
     "reason": "delete_file puede ser destructivo"
   }

5. TRANSICIÓN: plan_ready → awaiting_approval
   Phase Engine pausa y espera

6. UI TELEGRAM MUESTRA
   "⚠️ Se solicitó borrar 'importante.txt'. ¿Confirmás?
    [Aprobar] [Rechazar]"

7. USER RESPONSE
   Usuario aprieta "Aprobar"

8. SEÑAL
   {
     "type": "approval_response",
     "payload": {"response": "approved"}
   }

9. TRANSICIÓN: awaiting_approval → approved

10. CONTINÚA FLUJO NORMAL
    approved → executing → verifying → completed

11. RESPUESTA
    "✅ Archivo 'importante.txt' eliminado."
```

## Caso 4: Error + Recuperación

```
1. USER INPUT
   "abrir app-inventada"

2. FLUJO NORMAL HASTA EXECUTING
   idle → intent_detected → planning → plan_ready → approved → executing

3. WORKER FALLA
   worker.python.desktop:
   - Busca "app-inventada"
   - No encuentra en sistema
   - Devuelve error

4. SEÑAL ERROR
   {
     "type": "worker_result",
     "payload": {
       "status": "error",
       "error": {
         "type": "application_not_found",
         "message": "No encontré 'app-inventada' en el sistema",
         "recoverable": false
       }
     }
   }

5. TRANSICIÓN: executing → failed

6. PHASE ENGINE DECIDE
   error.recoverable == false
   → No ofrecer retry
   → Limpiar y volver a idle

7. RESPUESTA TELEGRAM
   "❌ No encontré la aplicación 'app-inventada'. Verificá el nombre o instalá la app."

8. ESTADO FINAL
   {
     "phase": "idle",
     "context": {"task": null},
     "memory": {
       "last_error": {
         "app": "app-inventada",
         "error": "not_found",
         "at": "2026-04-06T19:30:00Z"
       }
     }
   }
```

---

# I. VENTAJAS DEL ENFOQUE STATE-DRIVEN

## 1. Determinismo

**ANTES:**
- Mismo texto → diferentes resultados según contexto implícito
- "abrir" → ¿abrir qué? depende de parsing

**DESPUÉS:**
- Mismo estado + misma señal → SIEMPRE mismo resultado
- Estado explícito elimina ambigüedad

## 2. Verificabilidad

**ANTES:**
- ¿Qué pasó en el paso 3? → revisar logs dispersos

**DESPUÉS:**
- Estado es snapshot completo en cada momento
- Historial de transiciones es traza audit perfecta

## 3. Debuggabilidad

**ANTES:**
- "El bot no hizo lo que quería"
- Revisar 5 archivos de logs

**DESPUÉS:**
- "Fase: executing, Última señal: worker_result timeout"
- Un solo `state.json` dice todo

## 4. Integración con Execution Verifier

**ANTES:**
- Verifier recibe resultado suelto sin contexto

**DESPUÉS:**
```
Phase Engine: "Estoy en fase 'executing', esperando worker_result"
        ↓
Verifier: "OK, sé que debe verificar 'window_confirmed'"
        ↓
Phase Engine: "Recibo verification_result, transiciono a 'completed'"
```

El Verifier sabe QUÉ verificar según la fase.

## 5. Robustez

**ANTES:**
- Error en parsing → todo el flujo falla

**DESPUÉS:**
- Señal inválida → Phase Engine rechaza transición
- Sistema se queda en estado seguro (idle, failed)
- Fácil de recuperar

## 6. Extensibilidad

**ANTES:**
- Agregar nueva capacidad = modificar parsers

**DESPUÉS:**
- Agregar nueva señal = agregar transición
- No tocar código existente

---

# J. IMPLEMENTACIÓN: PRIMEROS PASOS CONCRETOS

## Archivos a Crear

1. **`modules/phase-engine/main.js`** - Core del motor
2. **`modules/phase-engine/manifest.json`** - Manifest
3. **`lib/phase-engine/state-store.js`** - State management
4. **`lib/phase-engine/transition-rules.js`** - Reglas de transición
5. **`docs/phase-engine-signals.md`** - Catálogo de señales

## Cambios Iniciales

### 1. Crear Phase Engine básico

```javascript
// modules/phase-engine/main.js
const stateStore = require('./state-store');
const transitionRules = require('./transition-rules');

function emit(port, payload) {
  process.stdout.write(JSON.stringify({module: "phase.engine.main", port, payload}) + "\n");
}

// Estado inicial
const currentState = {
  phase: "idle",
  context: {},
  history: []
};

// Loop principal
for await (const line of readLines()) {
  const msg = JSON.parse(line);
  
  if (msg.port === "signal.in") {
    const signal = msg.payload.signal;
    const transition = transitionRules.find(
      currentState.phase,
      signal.type,
      signal.payload
    );
    
    if (transition) {
      // Ejecutar transición
      const newState = await executeTransition(currentState, transition, signal);
      currentState = newState;
      
      // Notificar cambio de estado
      emit("state.out", {
        phase: currentState.phase,
        context: currentState.context,
        transition: {
          from: transition.from,
          to: transition.to,
          trigger: signal.type
        }
      });
    }
  }
}
```

### 2. Modificar agent.main (paso 1)

```javascript
// Agregar a agent.main:
function emitSignal(type, payload, confidence) {
  emit("signal.out", {
    signal: {
      type,
      source: "agent.main",
      payload,
      confidence,
      timestamp: Date.now()
    }
  });
}

// En handleCommand:
function handleCommand(text) {
  const intent = detectIntentStructured(text);  // No más parsing
  emitSignal("intent_detected", intent, intent.confidence);
}
```

### 3. Wiring en blueprint

```json
{
  "connections": [
    {"from": "agent.main:signal.out", "to": "phase.engine.main:signal.in"},
    {"from": "phase.engine.main:signal.out", "to": "planner.main:signal.in"},
    {"from": "planner.main:signal.out", "to": "phase.engine.main:signal.in"},
    {"from": "phase.engine.main:command.out", "to": "router.main:command.in"},
    {"from": "phase.engine.main:state.out", "to": "ui.state.main:state.in"}
  ]
}
```

---

# K. UNIÓN CON EXECUTION VERIFIER ENGINE

## Sistema Combinado: State Machine + Verification

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SISTEMA COMPLETO                                  │
│                                                                      │
│   PHASE ENGINE                      EXECUTION VERIFIER              │
│   (Orquestación)                    (Validación)                    │
│                                                                      │
│   ┌─────────────┐                  ┌─────────────┐                 │
│   │  FASE:      │                  │   EVIDENCE   │                 │
│   │  executing  │─────────────────►│  COLLECTOR   │                 │
│   └─────────────┘                  └──────┬──────┘                 │
│        │                                  │                         │
│        │ worker_result                    │                         │
│        ▼                                  ▼                         │
│   ┌─────────────┐                  ┌─────────────┐                 │
│   │  FASE:      │◄─────────────────│  CONFIDENCE │                 │
│   │  verifying  │   result         │  CALCULATOR │                 │
│   └─────────────┘                  └─────────────┘                 │
│        │                                                            │
│        │ verification_result                                        │
│        ▼                                                            │
│   ┌─────────────┐                                                   │
│   │  FASE:      │                                                   │
│   │  completed  │                                                   │
│   │ (verified)  │                                                   │
│   └─────────────┘                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Flujo Combinado

1. **Phase Engine** entra en fase `executing`
2. **Worker** ejecuta y retorna resultado con evidencia
3. **Phase Engine** recibe `worker_result` y transiciona a `verifying`
4. **Verifier Engine** calcula confidence de la evidencia
5. **Verifier** emite `verification_result`
6. **Phase Engine** recibe `verification_result` y:
   - Si `verified: true` → `completed`
   - Si `verified: false` → `failed`
7. UI muestra: "✅ Completado y verificado (95% confianza)"

## Estados + Verificación = Sistema Determinista Real

| Fase | Verificación Esperada | Si Falla Verificación |
|------|----------------------|----------------------|
| `executing` | Proceso/ventana detectada | → `failed` |
| `verifying` | Confidence >= 0.75 | → `failed` o `retry` |
| `completed` | Evidencia almacenada | → logging |

---

# L. RESUMEN EJECUTIVO

## Qué se propone

**Dejar de parsear texto. Empezar a procesar estados.**

## Componentes clave

1. **Phase Engine** - Máquina de estados central
2. **Signals** - Mensajes estructurados entre módulos
3. **Transitions** - Reglas deterministas de cambio de estado
4. **State Store** - Estado global del sistema

## Cambio fundamental

| Aspecto | Antes | Después |
|---------|-------|---------|
| Unidad de trabajo | Texto parseado | Señal estructurada |
| Control de flujo | Cadenas de llamadas | Transiciones de estado |
| Contexto | Implícito, disperso | Explícito, centralizado |
| Debug | Revisar logs múltiples | Un `state.json` |
| Extensibilidad | Modificar parsers | Agregar transiciones |

## Próximos pasos

1. ✅ Aprobar diseño
2. Crear `phase.engine.main` módulo básico
3. Modificar `agent.main` para emitir señales
4. Wiring en blueprint
5. Testing de coexistencia
6. Activar state-driven gradualmente

---

**Documento completo: `docs/phase-engine-design.md`**

**Relacionado con:** `docs/execution-verifier-design.md`
