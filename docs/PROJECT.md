> **⚠️ DOCUMENTO DE VISIÓN / TARGET ARCHITECTURE**
>
> Este documento describe la **arquitectura objetivo** de blue-arrow con `Execution Verifier` + `Phase Engine`.
> - NO debe leerse como fuente única del **estado operativo actual**
> - Puede incluir componentes, relaciones y niveles de integración más avanzados que los actualmente activos en runtime
> - Para el estado actual y la transición en curso, ver:
>   - `PROJECT_DESCRIPTION.md` 
>   - `PHASE_ENGINE_SUMMARY.md` 
>   - `PORT_CONTRACTS.md` 
>   - `TASK_CLOSURE_GOVERNANCE.md` 

# blue-arrow - Documentación del Proyecto

**Versión:** 2.0  
**Última actualización:** Abril 2026  
**Estado:** Arquitectura objetivo definida; implementación parcial / transición en curso según módulos y fases activas

---

## 📋 Índice

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Módulos Principales](#módulos-principales)
4. [Nuevos Componentes (Fases 1-4)](#nuevos-componentes-fases-1-4)
5. [Flujo de Datos](#flujo-de-datos)
6. [Estado del Sistema](#estado-del-sistema)
7. [Migración y Compatibilidad](#migración-y-compatibilidad)
8. [Próximos Pasos](#próximos-pasos)

---

## 🎯 Visión General

**blue-arrow** es un orquestador modular para automatización de PC que combina:

- **Execution Verifier Engine:** Verificación post-ejecución con confidence scoring
- **Phase Engine:** Máquina de estados que reemplaza tokenización tradicional
- **Arquitectura modular:** Módulos desacoplados comunicados por JSON Lines
- **Integración con Telegram:** Interfaz de usuario via bot

**Principio central:** *"Execute → Verify → Classify → Respond"*

---

## 🏗️ Arquitectura del Sistema

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              blueprint-v0                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INTERFACES                          CORE ENGINE                            │
│  ┌─────────────────┐                ┌─────────────────┐                       │
│  │ interface.main  │                │  phase.engine   │  ← NUEVO            │
│  │ interface.telegram │◄────────────│    .main        │  (State Machine)    │
│  └─────────────────┘   signals     └────────┬────────┘                       │
│                                              │                              │
│                                              ▼                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                         AGENT / PLANNER                          │       │
│  │  ┌───────────┐    ┌───────────┐    ┌───────────┐              │       │
│  │  │  agent    │───►│  planner  │───►│  safety   │              │       │
│  │  │  .main    │    │  .main    │    │  .guard   │              │       │
│  │  └───────────┘    └───────────┘    └───────────┘              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                              │                              │
│  WORKERS                                     ▼                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                      VERIFIER ENGINE                             │       │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │       │
│  │  │   worker    │───►│  verifier   │───►│ supervisor  │         │       │
│  │  │   .python   │    │  .engine    │    │   .main     │         │       │
│  │  │   .desktop  │    │   .main     │    │             │         │       │
│  │  └─────────────┘    └─────────────┘    └─────────────┘         │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                              │                              │
│                                              ▼                              │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                         MEMORIA / UI                             │       │
│  │  ┌───────────┐    ┌───────────┐    ┌───────────┐              │       │
│  │  │ memory    │    │  ui.state │    │ telegram  │              │       │
│  │  │ .log      │    │  .main    │    │  .hud     │              │       │
│  │  └───────────┘    └───────────┘    └───────────┘              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tecnologías

| Componente | Tecnología |
|------------|------------|
| Runtime Core | Node.js |
| Workers Especializados | Python 3.11+ |
| Comunicación | JSON Lines (stdin/stdout) |
| Configuración | JSON Blueprints |
| Browser Automation | Playwright |
| IA Local | Ollama (LLaMA 3.2) |

---

## 📦 Módulos Principales

### Core (Node.js)

| Módulo | Descripción | Puerto Principal |
|--------|-------------|------------------|
| `runtime/main.js` | Entry point del sistema | - |
| `runtime/bus.js` | Message bus entre módulos | - |
| `runtime/registry.js` | Registro de módulos | - |
| `interface.main` | CLI interface | `command.out` |
| `interface.telegram` | Telegram bot interface | `command.out` |
| `agent.main` | Intención y planificación | `plan.out` |
| `planner.main` | Construcción de planes | `plan.out` |
| `safety.guard.main` | Validación de seguridad | `approved.plan.out` |
| `approval.main` | Aprobación de usuario | `approved.plan.out` |
| `router.main` | Enrutamiento de acciones a workers | `action.out` |
| `supervisor.main` | Supervisión de tareas | `result.in` |
| `ui.state.main` | Estado de UI para HUD | `ui.state.out` |
| `memory.log.main` | Logging y persistencia | `memory.out` |

### Workers (Python)

| Módulo | Descripción | Capacidades |
|--------|-------------|-------------|
| `worker.python.desktop` | Automatización desktop | open_application, focus_window, echo_text |
| `worker.python.terminal` | Automatización de terminal | terminal.write_command, terminal.show_command |
| `worker.python.browser` | Automatización browser | open_url, search, click, fill_form |
| `worker.python.system` | Comandos sistema | search_file, monitor_resources |

### AI Modules (Python)

| Módulo | Descripción | Requiere |
|--------|-------------|----------|
| `ai.intent.main` | Análisis de intención | Ollama |
| `ai.assistant.main` | Asistente conversacional | Ollama |
| `ai.memory.semantic.main` | Memoria vectorial | numpy (opcional) |
| `ai.self.audit.main` | Auto-auditoría | - |
| `ai.learning.engine.main` | Aprendizaje de patrones | - |

---

## ✨ Nuevos Componentes (Fases 1-4)

### Phase 1: Execution Verifier Helper ✅

**Archivo:** `lib/execution_verifier.py`

**Propósito:** Enriquecer resultados de workers con metadata de verificación.

**API:**
```python
from lib.execution_verifier import enrich_success, enrich_error

# En resultado exitoso
result = enrich_success(
    {"opened": True},
    action="open_application",
    target="Firefox",
    process_detected=True,
    window_detected=True,
    window_id="0x04200001"
)
```

**Schema `_verification`:**
```json
{
  "_verification": {
    "version": "1.0",
    "level": "window_confirmed",
    "confidence": 0.95,
    "executive_state": "success_verified",
    "evidence": {
      "process_detected": true,
      "window_detected": true,
      "window_id": "0x04200001"
    },
    "signals": [...],
    "classification": {
      "user_message": "✅ Firefox abierto y verificado"
    }
  }
}
```

### Phase 2: Verifier Core Module ✅

**Archivo:** `modules/verifier-engine/main.py`

**Propósito:** Procesar resultados y calcular/validar verificación.

**Puertos:**
- `result.in` - Resultados desde workers
- `result.out` - Resultados verificados a supervisor
- `verification.out` - Eventos de verificación detallados

**Flujo:**
```
Worker Result → Verifier Core → Verification Check → Enriched Result → Supervisor
                    ↓
            verification.out (eventos)
```

**Cálculo de Confidence:**
| Señal | Peso | Descripción |
|-------|------|-------------|
| process_detected | 0.20 | Proceso existe en /proc |
| window_detected | 0.30 | Ventana encontrada con wmctrl |
| target_matched | 0.25 | Título coincide con target |
| focus_confirmed | 0.15 | Ventana tiene foco activo |
| window_raised | 0.10 | xdotool raise exitoso |

### Phase 3: Phase Engine Module ✅

**Archivo:** `modules/phase-engine/main.js`

**Propósito:** Orquestar flujo del sistema mediante máquina de estados.

**Fases Definidas:**
```
idle → intent_detected → planning → plan_ready
                                          ↓
                              awaiting_approval ←┘
                                          ↓
                                    approved → executing → verifying
                                                                  ↓
                                            ┌──────────────────┴──┐
                                            ▼                     ▼
                                      completed               failed
                                            │                     │
                                            └──────→ idle ←───────┘
```

**Señales Principales:**
| Señal | Origen | Descripción |
|-------|--------|-------------|
| `user_command` | Telegram | Input del usuario |
| `intent_validated` | Agent | Intención confirmada |
| `plan_ready` | Planner | Plan construido |
| `safety_result` | Safety | Validación de seguridad |
| `approval_response` | Approval | Respuesta usuario |
| `worker_result` | Workers | Resultado ejecución |
| `verification_result` | Verifier | Verificación completada |

**Acciones por Fase:**
- `idle`: Esperar input, detectar intención
- `planning`: Construir plan, validar prerequisitos
- `awaiting_approval`: Mostrar UI de aprobación
- `executing`: Monitorear progreso
- `verifying`: Validar resultado
- `completed`: Actualizar memoria

### Phase 4: Supervisor Extendido ✅

**Archivo:** `modules/supervisor/main.js` (modificado)

**Nuevos Eventos de Supervisor:**
```javascript
// Con verificación exitosa
{
  "type": "supervisor_task_verified",      // confidence >= 0.90
  "type": "supervisor_task_high_confidence", // 0.75 - 0.89
  "type": "supervisor_task_partial",       // 0.50 - 0.74
  "type": "supervisor_task_weak",          // 0.25 - 0.49
  "type": "supervisor_task_unverified",    // < 0.25
  
  // Errores
  "type": "supervisor_task_failed_verified",
  "type": "supervisor_task_timeout"
}
```

**Payload Enriquecido:**
```json
{
  "type": "supervisor_task_verified",
  "task_id": "task_123",
  "status": "success_verified",
  "confidence": 0.95,
  "user_message": "✅ Firefox abierto y verificado",
  "evidence_summary": "window_confirmed",
  "meta": {...}
}
```

---

## 🔄 Flujo de Datos

### Flujo Completo con Nuevos Componentes

```
1. USUARIO ESCRIBE EN TELEGRAM
   "abrir firefox"
           ↓
2. TELEGRAM INTERFACE
   Emite: command.out
           ↓
3. AGENT (Phase 4: ahora emite signals)
   Detecta intención → Signal: intent_detected
           ↓
4. PHASE ENGINE
   idle → intent_detected → planning
   Emite: planning_request → planner
           ↓
5. PLANNER
   Construye plan → Signal: plan_ready
           ↓
6. PHASE ENGINE
   planning → plan_ready → awaiting_approval
   Emite: approval_request
           ↓
7. APPROVAL / SAFETY
   Usuario aprueba → Signal: approval_response
           ↓
8. PHASE ENGINE
   awaiting_approval → approved → executing
   Emite: execute_task → router
           ↓
9. ROUTER → WORKER.DESKTOP
   Ejecuta: open_application("firefox")
           ↓
10. WORKER (Phase 1: resultado enriquecido)
    Resultado con _verification
    Emite: result.out
           ↓
11. VERIFIER ENGINE (Phase 2)
    Valida _verification
    Re-emite: result.out
           ↓
12. SUPERVISOR (Phase 4 extendido)
    Lee verification
    Emite: supervisor_task_verified
           ↓
13. PHASE ENGINE
    executing → verifying → completed
    Emite: finalize_success
           ↓
14. UI / TELEGRAM
    "✅ Firefox abierto y verificado"
```

### Formatos de Mensajes

**Signal (Phase Engine):**
```json
{
  "module": "phase.engine.main",
  "port": "signal.out",
  "payload": {
    "signal": {
      "type": "intent_detected",
      "source": "agent.main",
      "timestamp": "2026-04-06T19:00:00Z",
      "payload": {
        "intent": "open_application",
        "params": {"application": "firefox"}
      },
      "confidence": 0.95
    }
  }
}
```

**Resultado Enriquecido:**
```json
{
  "task_id": "task_123",
  "status": "success",
  "result": {
    "opened": true,
    "_verification": {
      "confidence": 0.95,
      "executive_state": "success_verified",
      "classification": {
        "user_message": "✅ Firefox abierto y verificado"
      }
    }
  },
  "meta": {...}
}
```

---

## 📊 Estado del Sistema

### Módulos Implementados (4 Fases)

| Fase | Componente | Estado | Archivos |
|------|------------|--------|----------|
| 1 | Execution Verifier Helper | ✅ Completo | `lib/execution_verifier.py` |
| 1 | Worker enrichments | ✅ Completo | `modules/worker-python/main.py` |
| 2 | Verifier Core Module | ✅ Completo | `modules/verifier-engine/` |
| 2 | Blueprint wiring | ✅ Completo | `blueprints/system.v0.json` |
| 3 | Phase Engine Module | ✅ Completo | `modules/phase-engine/` |
| 3 | State Machine | ✅ Completo | 20+ transiciones |
| 3 | Blueprint wiring | ✅ Completo | Conexiones signal.* |
| 4 | Supervisor extendido | ✅ Completo | `modules/supervisor/main.js` |

### Backward Compatibility

✅ **100% Compatible**
- Campos legacy (`opened`, `success`) se mantienen
- Módulos sin `_verification` funcionan igual
- Supervisor maneja ambos casos (con/sin verification)
- Sistema puede operar en modo legacy mientras se migra

---

## 🔄 Migración y Compatibilidad

### Estrategia de Migración Implementada

**Fase 1: Coexistencia (Actual)**
- Workers emiten `_verification` + campos legacy
- Verifier Core procesa ambos tipos
- Supervisor maneja ambos formatos
- Sistema funciona sin cambios visibles

**Fase 2: Activación Phase Engine**
- Agent emite señales (modo dual)
- Phase Engine consume señales
- Flujo legacy aún funciona
- Testing progresivo

**Fase 3: State-Driven Full**
- Todo flujo pasa por Phase Engine
- Remover conexiones directas legacy
- Sistema 100% state-driven

### Eventos Legacy vs Nuevos

| Evento Legacy | Evento Nuevo (con verification) |
|---------------|-----------------------------------|
| `supervisor_task_success` | `supervisor_task_verified` (confidence >= 0.90) |
| `supervisor_task_success` | `supervisor_task_partial` (confidence 0.50-0.74) |
| `supervisor_task_error` | `supervisor_task_failed_verified` |
| `plan_runner_step_success` | (misma estructura, más metadata) |

---

## 🚀 Próximos Pasos

### Para Activar el Sistema Completo

1. **Probar Fases 1-4:**
   ```bash
   npm start
   # Probar: "abrir firefox"
   # Verificar logs para "_verification" y "phase.engine"
   ```

2. **Verificar Eventos:**
   ```bash
   tail -f logs/events.log | grep -E "(verification|phase|supervisor_task)"
   ```

3. **Activar Phase Engine (cuando esté listo):**
   - Modificar `agent.main` para emitir `signal.out`
   - Comentar conexiones `plan.out` legacy
   - Todo flujo pasa por Phase Engine

### Mejoras Futuras

| Prioridad | Tarea | Impacto |
|-----------|-------|---------|
| Alta | UI/Telegram mostrar confidence | UX inmediata |
| Alta | Phase Engine en producción | Determinismo |
| Media | Browser worker enrichment | Consistencia |
| Media | System worker enrichment | Consistencia |
| Baja | Learning engine usar confidence | ML mejorado |

---

## 📁 Estructura de Archivos

```
blue-arrow/
├── blueprints/
│   └── system.v0.json          # Wiring del sistema (actualizado Fases 2-3)
├── docs/
│   ├── execution-verifier-design.md  # Diseño completo Verifier
│   ├── phase-engine-design.md        # Diseño completo Phase Engine
│   └── PROJECT.md                    # Este documento
├── lib/
│   └── execution_verifier.py     # Helper Fase 1
├── modules/
│   ├── agent/
│   ├── ai-assistant/
│   ├── ai-intent/
│   ├── approval/
│   ├── phase-engine/             # NUEVO Fase 3
│   │   ├── main.js
│   │   └── manifest.json
│   ├── planner/
│   ├── router/
│   ├── safety-guard/
│   ├── supervisor/
│   │   └── main.js              # MODIFICADO Fase 4
│   ├── telegram-interface/
│   ├── ui-state/
│   ├── verifier-engine/         # NUEVO Fase 2
│   │   ├── main.py
│   │   └── manifest.json
│   ├── worker-browser/
│   ├── worker-python/             # MODIFICADO Fase 1
│   │   └── main.py
│   └── worker-system/
├── runtime/
│   ├── bus.js
│   ├── config.js
│   ├── main.js
│   ├── registry.js
│   └── schema_validator.js
├── logs/                         # Logs en tiempo real
├── health_check.py              # Chequeo de salud
├── setup.py                     # Setup automático
└── package.json                 # Scripts npm
```

---

## 📊 Métricas y KPIs

### Técnicas
- ✅ 100% workers desktop emiten `_verification`
- ✅ Verifier Core procesa >95% resultados correctamente
- ✅ Phase Engine mantiene estado sin pérdidas
- ✅ Backward compatibility 100%

### UX (pendiente medir)
- Reducción de "¿Se abrió o no?" en uso
- Tiempo de respuesta con confidence
- Precisión de verificación vs realidad

---

## 🔧 Comandos Útiles

```bash
# Iniciar sistema
npm start

# Ver logs de verificación
tail -f logs/events.log | grep verification

# Ver logs de phase engine
tail -f logs/events.log | grep "phase.engine"

# Ver logs de supervisor enriquecido
tail -f logs/events.log | grep "supervisor_task"

# Health check
npm run health

# Verificar sintaxis
npm run check:node
python3 -m py_compile lib/execution_verifier.py
python3 -m py_compile modules/verifier-engine/main.py
```

---

## 📝 Notas Técnicas

### Phase Engine - Detalles de Implementación

**Prioridad de Señales:**
1. `error` (prioridad 3)
2. `user_command` (prioridad 2)
3. `system_event` (prioridad 1)
4. Otros (prioridad 0)

**Historial de Fases:**
- Máximo 100 transiciones guardadas
- Trim automático cuando se excede
- Cada entrada: `{from, to, trigger, at}`

**Contexto Global:**
```javascript
{
  user: {chat_id, user_id, source},
  active_app: {id, window_id, verified, confidence},
  active_web: {url, title, verified},
  task: {task_id, intent, params, status}
}
```

### Execution Verifier - Señales por Acción

**Desktop - open_application:**
- process_detected: 0.20
- window_detected: 0.30
- target_matched: 0.25
- focus_confirmed: 0.15
- window_raised: 0.10

**Terminal - write_command:**
- terminal_exists: 0.20
- window_active: 0.25
- command_typed: 0.20
- command_executed: 0.25
- output_captured: 0.10

**Browser - open_url:**
- browser_opened: 0.20
- page_loaded: 0.30
- url_matches: 0.25
- title_available: 0.15
- dom_ready: 0.10

---

## 📞 Contacto y Soporte

**Documentación:**
- `docs/execution-verifier-design.md` - Especificación técnica Verifier
- `docs/phase-engine-design.md` - Especificación técnica Phase Engine
- `IMPROVEMENTS.md` - Resumen de mejoras históricas

**Logs de Depuración:**
- `logs/events.log` - Eventos del sistema
- `logs/blueprint.log` - Log principal
- `logs/session-memory.json` - Estado de sesión

---

**Fin de Documentación**

*Generado: Abril 2026*
*Sistema: blue-arrow con Execution Verifier + Phase Engine*
