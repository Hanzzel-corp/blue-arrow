> **⚠️ DISEÑO TÉCNICO LISTO PARA IMPLEMENTACIÓN**
>
> Este documento describe fixes propuestos para mejorar consistencia, determinismo y confiabilidad del runtime.
> - No implica que todos los fixes ya estén aplicados en el código actual
> - Los snippets deben adaptarse al contrato v2 y al wiring canónico vigente
> - Ver contratos actuales en `PORT_CONTRACTS.md` y `CONTRACTS_GUIDE.md` 

# 🔧 DISEÑO TÉCNICO - 4 FIXES DE RUNTIME

**Versión:** 1.0  
**Estado:** Diseño listo para implementación  
**Objetivo:** Consistencia, determinismo y confiabilidad en runtime

---

## 📋 RESUMEN EJECUTIVO

| Fix | Problema Actual | Solución | Archivos |
|-----|-----------------|----------|----------|
| **1** | `meta.action: "unknown"` | Propagación obligatoria + fallback + warning | router, workers, verifier |
| **2** | `level: "none"` + `confidence: 1.0` | Normalización por rangos de confidence | `lib/execution_verifier.py` |
| **3** | `ai.query` timeout duro | Heartbeat cada 3s + timeout por tipo + fallback | `ai-assistant/main.py`, supervisor |
| **4** | Eventos duplicados | Lock por task_id + máquina de estados + idempotencia | `supervisor/main.js` |

---

## A. DISEÑO TÉCNICO DETALLADO

---

## 🔥 FIX 1: META.ACTION PROPAGACIÓN OBLIGATORIA

### A.1 Contrato de Metadata

```typescript
interface MetaContract {
  action: string;           // OBLIGATORIO - ej: "open_application"
  worker: string;           // OBLIGATORIO - ej: "worker.python.desktop"
  source?: string;          // Opcional - ej: "telegram"
  chat_id?: string;         // Opcional
  timestamp?: string;       // Opcional - ISO 8601
  routed_at?: string;       // Opcional - ISO 8601 generado por router
}
```

### A.2 Flujo de Propagación

```
planner.main:plan.out
    ↓
agent.main:plan.in ──► agent genera plan estructurado
    ↓
agent.main:plan.out
    ↓
safety.guard.main:plan.in ──► validación de seguridad
    ↓
safety.guard.main:approved.plan.out / approval.main:approved.plan.out
    ↓
router.main:plan.in ──► router deriva acciones del plan
    ↓
router.main:action.out ──► EMITE con meta.action + meta.worker
    ↓
worker.python.*:action.in ──► worker VERIFICA meta.action
    ↓
worker.python.*:result.out ──► worker INCLUYE meta.action
    ↓
verifier-engine:result.in ──► verifier LEE action de meta
    ↓
verifier-engine:result.out ──► verifier EMITE action verificada
```

### A.3 Implementación por Archivo

#### `router/main.js` - Añadir antes de emitir

> **Nota:** `routeAction(payload)` opera sobre un paso/acción individual derivado del plan, 
> no sobre el plan completo que entra por `router.main:plan.in`. El router descompone el plan 
> en acciones y enruta cada una a su worker correspondiente.

```javascript
// Línea: ~85 (antes de emitir a workers)
function routeAction(payload) {
  const action = payload.action;
  const taskId = payload.task_id;
  
  // CONTRATO: garantizar meta.action
  const meta = {
    ...payload.meta,
    action: action,                    // ← OBLIGATORIO
    worker: inferWorkerType(action),   // ← OBLIGATORIO
    routed_at: new Date().toISOString()
  };
  
  if (!action) {
    emit("event.out", {
      level: "warn",
      type: "router_missing_action",
      task_id: taskId,
      message: "Action no definida, usando 'unknown'"
    });
    meta.action = "unknown";
  }
  
  // Enviar a worker específico
  const targetPort = getWorkerPort(action);
  emit(targetPort, {
    task_id: taskId,
    action: action,
    params: payload.params,
    meta: meta  // ← SIEMPRE incluir meta completa
  });
}

function inferWorkerType(action) {
  if (!action) return "worker.python.desktop";
  if (action.startsWith("ai.")) return "ai.assistant.main";
  if (action.startsWith("terminal.")) return "worker.python.terminal";
  if (action.includes("browser") || action.includes("web") || action.startsWith("open_url") || action.startsWith("search")) {
    return "worker.python.browser";
  }
  if (action.includes("file") || action.includes("system") || action.startsWith("monitor_resources")) {
    return "worker.python.system";
  }
  return "worker.python.desktop";
}
```

#### `modules/worker-python/main.py` - Añadir al inicio del handler

```python
# Línea: ~1115 (antes de procesar acción)
def handle_message(msg):
    payload = msg.get("payload", {})
    task_id = payload.get("task_id", "unknown")
    action = payload.get("action", "unknown")
    meta = payload.get("meta", {}) or {}
    
    # CONTRATO: validar/establecer action en meta
    if "action" not in meta or not meta["action"]:
        if action and action != "unknown":
            meta["action"] = action
            emit("event.out", {
                "level": "warn",
                "text": f"meta.action missing, using payload.action: {action}",
                "task_id": task_id
            })
        else:
            # FALLBACK: inferir del resultado
            meta["action"] = infer_action_from_params(payload.get("params", {}))
            emit("event.out", {
                "level": "warn",
                "text": f"action inferred from params: {meta['action']}",
                "task_id": task_id
            })
    
    # CONTRATO: validar worker en meta
    if "worker" not in meta:
        meta["worker"] = MODULE_ID
    
    # ... resto del procesamiento

def infer_action_from_params(params):
    if params.get("name") and not params.get("command"):
        return "open_application"
    if params.get("command") and params.get("window_id"):
        return "terminal.write_command"
    if params.get("url"):
        return "browser.open_url"
    return "unknown"
```

#### `modules/verifier-engine/main.py` - Mejorar extracción de action

```python
# Línea: ~206 (en process_result)
def process_result(self, task_id: str, payload: Dict) -> Dict:
    # Estrategia de extracción con fallback
    action = (
        payload.get("meta", {}).get("action")      # 1. De meta
        or payload.get("action")                    # 2. De payload directo
        or payload.get("result", {}).get("action") # 3. Del resultado
        or "unknown"
    )
    
    if action == "unknown":
        emit_event("warn", f"meta.action missing for task {task_id}", 
                  task_id=task_id, payload_keys=list(payload.keys()))
    else:
        emit_event("info", f"Verifying action: {action}", 
                  task_id=task_id, action=action)
    
    result = payload.get("result", {})
    meta = payload.get("meta", {})
    
    # ... resto de verificación
```

### A.4 Logs Esperados (FIX 1)

```
# Éxito - flujo correcto:
[router] routing action: open_application → worker.python.desktop
[worker.python.desktop] meta.action validated: open_application
[verifier] Verifying action: open_application (confidence: 0.95)

# Warning - recuperación:
[worker.python.desktop] meta.action missing, using payload.action: open_application
[verifier] meta.action missing for task task_123, inferring from result

# Error - no se pudo determinar:
[verifier] action unknown for task task_456, using generic verification rules
```

---

## 🔥 FIX 2: NORMALIZACIÓN LEVEL vs CONFIDENCE

### B.1 Reglas de Normalización

```python
NORMALIZATION_RULES = {
    # confidence >= 0.90 → NUNCA level="none"
    (0.90, 1.00): {
        "level": "confirmed",           # Genérico alto
        "level_with_evidence": {        # Específico
            "focus+window": "window_confirmed",
            "window": "window_detected",
            "process": "process_confirmed",
            "none": "signal_confirmed"    # ← NUEVO: high confidence, no evidence
        }
    },
    (0.75, 0.89): {
        "level": "high",
        "level_with_evidence": {
            "window": "window_detected",
            "process": "process_detected",
            "none": "signal_detected"
        }
    },
    (0.50, 0.74): {
        "level": "partial",
        "level_with_evidence": {
            "process": "process_only",
            "none": "partial_evidence"
        }
    },
    (0.25, 0.49): {
        "level": "weak",
        "level_with_evidence": {
            "any": "minimal_evidence"
        }
    },
    (0.00, 0.24): {
        "level": "unverified",
        "executive_state_override": "success_weak"  # o "success_unverified"
    }
}
```

### B.2 Implementación en `lib/execution_verifier.py`

```python
class VerificationNormalizer:
    """Normaliza verificación para garantizar consistencia."""
    
    @staticmethod
    def normalize(verification: Dict) -> Dict:
        """Corrige inconsistencias level/confidence."""
        confidence = verification.get("confidence", 0)
        level = verification.get("level", "unknown")
        executive_state = verification.get("executive_state", "unknown")
        evidence = verification.get("evidence", {})
        
        # DETECTAR y CORREGIR inconsistencia
        is_inconsistent = False
        
        # Regla 1: confidence >= 0.90 NUNCA level="none"
        if confidence >= 0.90 and level in ["none", "unknown"]:
            is_inconsistent = True
            level = VerificationNormalizer._infer_level_from_evidence(
                confidence, evidence
            )
        
        # Regla 2: confidence < 0.25 NUNCA state="success_verified"
        if confidence < 0.25 and executive_state == "success_verified":
            is_inconsistent = True
            executive_state = "success_weak" if confidence >= 0.10 else "success_unverified"
        
        # Regla 3: level y confidence deben estar alineados
        expected_level = VerificationNormalizer._expected_level(confidence)
        if level == "none" and expected_level != "none":
            is_inconsistent = True
            level = expected_level
        
        if is_inconsistent:
            verification["_normalized"] = True
            verification["_original_level"] = verification.get("level")
            verification["_original_state"] = verification.get("executive_state")
        
        verification["confidence"] = confidence
        verification["level"] = level
        verification["executive_state"] = executive_state
        
        return verification
    
    @staticmethod
    def _infer_level_from_evidence(confidence: float, evidence: Dict) -> str:
        """Infiere nivel basado en evidencia disponible."""
        if evidence.get("focus_confirmed") and evidence.get("window_detected"):
            return "window_confirmed"
        if evidence.get("window_detected"):
            return "window_detected"
        if evidence.get("process_detected"):
            return "process_confirmed"
        if evidence.get("signal_detected") or evidence.get("output_captured"):
            return "signal_confirmed"
        # High confidence pero sin evidencia concreta
        return "signal_confirmed" if confidence >= 0.90 else "signal_detected"
    
    @staticmethod
    def _expected_level(confidence: float) -> str:
        """Devuelve level esperado para un confidence."""
        if confidence >= 0.90:
            return "confirmed"
        elif confidence >= 0.75:
            return "high"
        elif confidence >= 0.50:
            return "partial"
        elif confidence >= 0.25:
            return "weak"
        else:
            return "unverified"

# Uso en VerificationBuilder.build():
def build(self, success: bool = True, target: str = None) -> Dict:
    elapsed_ms = int((time.time() - self.start_time) * 1000)
    
    verification = {
        "version": self.version,
        "verified_at": datetime.now().isoformat(),
        "level": self.determine_level(),
        "confidence": self.calculate_confidence(),
        "executive_state": self.determine_executive_state(success),
        "evidence": self.evidence,
        "signals": self.signals,
        "classification": self.build_classification(self.action, target),
        "limitations": self.limitations if self.limitations else [],
        "warnings": self.warnings if self.warnings else [],
        "verification_time_ms": elapsed_ms
    }
    
    # NORMALIZAR antes de devolver
    normalizer = VerificationNormalizer()
    return normalizer.normalize(verification)
```

### B.3 Validación Automática

```python
def validate_consistency(verification: Dict) -> Tuple[bool, List[str]]:
    """Valida consistencia interna de verificación."""
    errors = []
    confidence = verification.get("confidence", 0)
    level = verification.get("level", "unknown")
    state = verification.get("executive_state", "unknown")
    
    # Check 1: confidence alto → no level="none"
    if confidence >= 0.90 and level in ["none", "unverified"]:
        errors.append(f"HIGH_CONFIDENCE_LOW_LEVEL: {confidence} vs {level}")
    
    # Check 2: level vs confidence alignment
    expected = VerificationNormalizer._expected_level(confidence)
    if level != expected and level not in ["window_confirmed", "process_confirmed"]:
        errors.append(f"MISALIGNED: confidence={confidence} expects {expected}, got {level}")
    
    # Check 3: state vs confidence
    if state == "success_verified" and confidence < 0.90:
        errors.append(f"WEAK_VERIFIED: state={state} with confidence={confidence}")
    
    return len(errors) == 0, errors
```

### B.4 Logs Esperados (FIX 2)

```
# Normalización aplicada:
[verifier] Normalized verification: level changed from "none" to "signal_confirmed"
[verifier] Warning: HIGH_CONFIDENCE_LOW_LEVEL detected and fixed

# Validación exitosa:
[verifier] Verification validated: confidence=0.95, level=window_confirmed ✓

# Inconsistencia encontrada:
[verifier] Consistency error: confidence=1.0 but level=none → auto-corrected to signal_confirmed
```

---

## 🔥 FIX 3: TIMEOUT HANDLING IA CON HEARTBEAT

### C.1 Arquitectura de Timeout

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  supervisor │     │   worker    │     │   ollama    │
│             │     │  ai.assist  │     │             │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │ 1. send action    │                   │
       │──────────────────►│                   │
       │                   │ 2. start watchdog │
       │                   │──────────────────►
       │                   │                   │
       │                   │ 3. heartbeat ─────┼──► every 3s
       │◄──────────────────│                   │
       │   {status:processing}                 │
       │                   │                   │
       │                   │ 4. query ollama    │
       │                   │──────────────────►
       │                   │◄──────────────────│
       │                   │   response        │
       │                   │                   │
       │                   │ 5. stop watchdog  │
       │ 6. result         │                   │
       │◄──────────────────│                   │
       │                   │                   │
```

### C.2 Timeouts por Tipo de Acción

```javascript
// En supervisor/main.js
const ACTION_TIMEOUTS = {
  // AI operations (largas)
  "ai.query": 15000,
  "ai.analyze_intent": 10000,
  "ai.generate_code": 20000,
  "ai.analyze_project": 25000,
  
  // Desktop (rápidas)
  "open_application": 5000,
  "terminal.write_command": 3000,
  "focus_window": 2000,
  
  // Browser (media)
  "open_url": 8000,
  "search": 10000,
  "click": 5000,
  "fill_form": 6000,
  
  // System (variable)
  "search_file": 5000,
  "monitor_resources": 3000,
  
  // Default
  "default": 10000
};

function getTimeoutForAction(action) {
  return ACTION_TIMEOUTS[action] || ACTION_TIMEOUTS["default"];
}
```

### C.3 Implementación en `ai-assistant/main.py`

```python
import threading
import time

class ProcessingHeartbeat:
    """Emite heartbeats periódicos durante operaciones largas."""
    
    def __init__(self, task_id: str, interval: float = 3.0):
        self.task_id = task_id
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._start_time = time.time()
    
    def _emit_heartbeat(self):
        while not self._stop.is_set():
            elapsed = time.time() - self._start_time
            emit("event.out", {
                "level": "info",
                "type": "ai_processing_heartbeat",
                "task_id": self.task_id,
                "status": "processing",
                "elapsed_seconds": round(elapsed, 1),
                "timestamp": datetime.now().isoformat()
            })
            # Esperar intervalo o hasta que se detenga
            self._stop.wait(self.interval)
    
    def start(self):
        self._thread = threading.Thread(target=self._emit_heartbeat, daemon=True)
        self._thread.start()
    
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)

# Timeouts por acción
AI_TIMEOUTS = {
    "ai.query": 15,
    "ai.analyze_intent": 10,
    "ai.generate_code": 20,
    "ai.explain_error": 12,
    "ai.analyze_project": 25,
    "default": 10
}

def handle_ai_action(action: str, params: Dict, task_id: str, meta: Dict):
    """Handler con heartbeat y timeout configurables."""
    
    heartbeat = ProcessingHeartbeat(task_id, interval=3.0)
    timeout = AI_TIMEOUTS.get(action, AI_TIMEOUTS["default"])
    
    try:
        # Emitir inicio inmediato
        emit("event.out", {
            "level": "info",
            "type": "ai_action_started",
            "task_id": task_id,
            "action": action,
            "timeout_configured": timeout
        })
        
        # Iniciar heartbeat
        heartbeat.start()
        
        if action == "ai.query":
            result = llama_interface.query(
                prompt=params.get("prompt", ""),
                system_prompt=params.get("system_prompt"),
                timeout=timeout  # ← Timeout configurable
            )
        # ... otros actions
        
        # Detener heartbeat
        heartbeat.stop()
        
        emit_result(task_id, "success" if result["success"] else "error", result, meta)
        
    except subprocess.TimeoutExpired:
        heartbeat.stop()
        
        # FALLBACK: resultado parcial
        emit_result(task_id, "error", {
            "success": False,
            "error": f"Timeout after {timeout}s",
            "error_type": "timeout",
            "partial_result": {
                "action_received": action,
                "params_received": list(params.keys()),
                "timeout_at": datetime.now().isoformat(),
                "suggestion": "El servicio de IA está lento. Intenta de nuevo."
            },
            "confidence": 0.0
        }, meta)
        
    except Exception as e:
        heartbeat.stop()
        emit_result(task_id, "error", {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "partial_result": {
                "stage": "execution",
                "error_at": datetime.now().isoformat()
            }
        }, meta)
```

### C.4 Supervisor: Nuevo Estado `timeout_soft`

```javascript
// En supervisor/main.js - handleResult() [FRAGMENTO: solo sección timeout]

if (payload.status === "timeout" || payload.status === "timeout_soft") {
  const isSoft = payload.status === "timeout_soft" || 
                 payload?.result?.partial_result != null;
  
  const nextStatus = isSoft ? "timeout_soft" : "timeout_hard";
  const transition = transitionTask(taskId, nextStatus, {
    trigger: "timeout_received",
    partial_result: payload?.result?.partial_result || null
  });
  if (!transition.success) return;
  
  if (isSoft) {
    // Timeout con resultado parcial - no es error crítico
    emit("event.out", {
      level: "warn",
      type: "supervisor_task_timeout_soft",
      task_id: taskId,
      status: "timeout_soft",
      partial_result: payload?.result?.partial_result,
      suggestion: "La operación tomó demasiado tiempo pero hay datos parciales",
      meta
    });
  } else {
    // Timeout duro - error real
    emit("event.out", {
      level: "error",
      type: "supervisor_task_timeout_hard",
      task_id: taskId,
      status: "timeout_hard",
      meta
    });
  }
  return;
}
```

### C.5 Logs Esperados (FIX 3)

```
# Flujo normal con heartbeat:
[ai.assistant] ai_action_started: ai.query (timeout: 15s)
[ai.assistant] ai_processing_heartbeat: elapsed=3.0s
[ai.assistant] ai_processing_heartbeat: elapsed=6.0s
[ai.assistant] ai_processing_heartbeat: elapsed=9.0s
[ai.assistant] Result emitted successfully

# Timeout con fallback:
[ai.assistant] ai_action_started: ai.analyze_project (timeout: 25s)
[ai.assistant] ai_processing_heartbeat: elapsed=3.0s
...
[ai.assistant] ai_processing_heartbeat: elapsed=24.0s
[ai.assistant] Timeout after 25s
[supervisor] supervisor_task_timeout_soft: partial_result available
```

---

## 🔥 FIX 4: LIFECYCLE LOCK POR TASK_ID

### D.1 Máquina de Estados del Task

```
                    ┌─────────────┐
         ┌─────────►│   RUNNING   │◄────────┐
         │          └──────┬──────┘         │
         │                 │ result          │
         │                 ▼                 │
         │          ┌─────────────┐          │
         │          │  VERIFYING  │          │
         │          └──────┬──────┘          │
         │                 │                 │
         │        ┌────────┴────────┐        │
         │        ▼                 ▼        │
         │   ┌─────────────┐   ┌─────────────┐
         │   │  COMPLETED  │   │    ERROR    │
         │   └─────────────┘   └─────────────┘
         │
         │ timeout
         ▼
   ┌─────────────┐
   │ TIMEOUT     │
   │   (SOFT)    │
   └──────┬──────┘
          │
          ├────────────► COMPLETED
          │
          └────────────► ERROR

   ┌─────────────┐
   │ TIMEOUT     │
   │   (HARD)    │
   └─────────────┘
```

**Transiciones Válidas:**
- `running` → `verifying` ✓
- `verifying` → `completed` ✓
- `verifying` → `error` ✓
- `running` → `timeout_soft` ✓
- `running` → `timeout_hard` ✓
- `timeout_soft` → `completed` ✓
- `timeout_soft` → `error` ✓

**Transiciones INVÁLIDAS (bloqueadas):**
- `completed` → `running` ✗ (task cerrado)
- `error` → `running` ✗ (necesita nuevo task_id)

### D.2 Implementación en `supervisor/main.js`

```javascript
// Estado global de tasks
const taskLifecycle = new Map(); // taskId → {status, history, locks}
const processedEvents = new Set(); // Para idempotencia

// Definición de transiciones válidas
const VALID_TRANSITIONS = {
  "running": ["verifying", "timeout_soft", "timeout_hard", "error"],
  "verifying": ["completed", "error"],
  "completed": [], // Terminal
  "error": [],     // Terminal
  "timeout_soft": ["completed", "error"],
  "timeout_hard": [] // Terminal
};

function canTransition(taskId, fromStatus, toStatus) {
  // Validar transición
  const validTargets = VALID_TRANSITIONS[fromStatus] || [];
  return validTargets.includes(toStatus);
}

function transitionTask(taskId, newStatus, context = {}) {
  const lifecycle = taskLifecycle.get(taskId);
  
  if (!lifecycle) {
    // Nuevo task
    taskLifecycle.set(taskId, {
      status: newStatus,
      history: [{from: null, to: newStatus, at: now(), context}],
      created_at: now()
    });
    return {success: true, transition: {from: null, to: newStatus}};
  }
  
  const currentStatus = lifecycle.status;
  
  // Check 1: Idempotencia - mismo estado
  if (currentStatus === newStatus) {
    emit("event.out", {
      level: "warn",
      type: "supervisor_duplicate_transition_blocked",
      task_id: taskId,
      status: newStatus,
      message: `Task already in status ${newStatus}`
    });
    return {success: false, reason: "already_in_state"};
  }
  
  // Check 2: Transición válida
  if (!canTransition(taskId, currentStatus, newStatus)) {
    emit("event.out", {
      level: "error",
      type: "supervisor_invalid_transition_blocked",
      task_id: taskId,
      from: currentStatus,
      to: newStatus,
      valid_transitions: VALID_TRANSITIONS[currentStatus],
      message: `Invalid transition: ${currentStatus} → ${newStatus}`
    });
    return {success: false, reason: "invalid_transition"};
  }
  
  // Ejecutar transición
  lifecycle.history.push({
    from: currentStatus,
    to: newStatus,
    at: now(),
    context
  });
  lifecycle.status = newStatus;
  lifecycle.updated_at = now();
  
  return {success: true, transition: {from: currentStatus, to: newStatus}};
}

// Idempotencia de eventos
function isEventProcessed(taskId, eventType, eventId = null) {
  const key = eventId || `${taskId}:${eventType}`;
  return processedEvents.has(key);
}

function markEventProcessed(taskId, eventType, eventId = null) {
  const key = eventId || `${taskId}:${eventType}`;
  processedEvents.add(key);
  
  // Cleanup si crece mucho
  if (processedEvents.size > 5000) {
    const toDelete = Array.from(processedEvents).slice(0, 1000);
    toDelete.forEach(k => processedEvents.delete(k));
  }
}

// Uso en handlers:
function handlePlan(taskId, payload) {
  // Idempotencia
  if (isEventProcessed(taskId, "plan_received")) {
    emit("event.out", {level: "warn", type: "supervisor_duplicate_plan", task_id: taskId});
    return;
  }
  markEventProcessed(taskId, "plan_received");
  
  // Transición
  const result = transitionTask(taskId, "running", {trigger: "plan_received"});
  if (!result.success) return;
  
  // ... resto del procesamiento
  startTask(taskId, payload.meta);
}

function handleResult(payload) {
  const taskId = payload?.task_id;
  if (!taskId) return;
  
  // Idempotencia de resultado
  const resultKey = `${taskId}:${payload?.step_id || 'final'}:${payload?.status}`;
  if (isEventProcessed(taskId, "result", resultKey)) {
    emit("event.out", {
      level: "warn",
      type: "supervisor_duplicate_result_blocked",
      task_id: taskId,
      result_key: resultKey
    });
    return;
  }
  markEventProcessed(taskId, "result", resultKey);
  
  // Determinar nuevo estado basado en resultado
  let newStatus;
  if (payload.status === "timeout") {
    newStatus = payload?.result?.partial_result ? "timeout_soft" : "timeout_hard";
  } else if (payload.status === "success") {
    newStatus = "verifying";
  } else {
    newStatus = "error";
  }
  
  // Transición
  const result = transitionTask(taskId, newStatus, {trigger: "result_received"});
  if (!result.success) return;
  
  // ... procesar resultado
}
```

### D.3 Estructura de Datos del Task

// Ejemplo de task en taskLifecycle
{
  "task_20260413_194530_123": {
    "status": "completed",
    "created_at": "2026-04-06T19:45:30.200Z",
    "updated_at": "2026-04-06T19:45:35.456Z",
    "history": [
      {
        "from": null,
        "to": "running",
        "at": "2026-04-06T19:45:30.200Z",
        "context": {"trigger": "execution_started", "action": "open_application"}
      },
      {
        "from": "running",
        "to": "verifying",
        "at": "2026-04-06T19:45:32.500Z",
        "context": {"trigger": "result_received", "confidence": 0.95}
      },
      {
        "from": "verifying",
        "to": "completed",
        "at": "2026-04-06T19:45:35.456Z",
        "context": {"trigger": "verification_confirmed"}
      }
    ],
    "context": {
      "last_action": "open_application",
      "chat_id": "123456789"
    }
  }
}

### D.4 Logs Esperados (FIX 4)

```
# Transición exitosa:
[supervisor] Task transition: running → verifying (task_123)
[supervisor] Task transition: verifying → completed (task_123)

# Bloqueo de duplicado:
[supervisor] supervisor_duplicate_transition_blocked: Task already in status running (task_123)
[supervisor] supervisor_duplicate_result_blocked: Result already processed (task_123:final:success)

# Bloqueo de transición inválida:
[supervisor] supervisor_invalid_transition_blocked: Invalid transition: completed → running
  Valid transitions from completed: []
  
# Historial completo:
[supervisor] Task lifecycle complete (task_123):
  running → verifying @ 19:45:32.500Z
  verifying → completed @ 19:45:35.456Z
```

---

## E. ESTRATEGIA INCREMENTAL DE IMPLEMENTACIÓN

### Fase A: Preparación (Sin impacto runtime)

1. **Agregar logging** de diagnóstico:
   - Log cada vez que falte `meta.action`
   - Log cada inconsistencia level/confidence
   - Log cada transición de task

2. **No cambiar lógica**, solo observar:
   ```javascript
   // Solo loguear, no bloquear
   if (!meta.action) {
     console.warn("[DIAGNOSTIC] meta.action missing", taskId);
   }
   ```

### Fase B: Implementación por Fix (Uno por vez)

**Orden recomendado:**

| Día | Fix | Razón |
|-----|-----|-------|
| 1 | FIX 4 (Lock) | Previene duplicados, base para otros |
| 2 | FIX 1 (meta.action) | Trazabilidad correcta |
| 3 | FIX 2 (Normalización) | Consistencia de datos |
| 4 | FIX 3 (Heartbeat) | Resiliencia IA |

**Proceso por Fix:**
1. Implementar código
2. Probar en desarrollo
3. Deploy con feature flag (si aplica)
4. Monitorear logs
5. Siguiente fix

### Fase C: Validación

**Métricas a observar:**

```
Antes:
- supervisor_duplicate_result_blocked: 50/hour
- verifier_unknown_action: 30/hour
- confidence_inconsistency: 10/hour
- ai_timeout_hard: 5/hour

Después (objetivo):
- supervisor_duplicate_result_blocked: 0/hour
- verifier_unknown_action: 0/hour
- confidence_inconsistency: 0/hour
- ai_timeout_soft: <3/hour (aceptable)
- ai_timeout_hard: 0/hour
```

---

## F. RESUMEN DE MODIFICACIONES POR ARCHIVO

### Archivos a Modificar

| Archivo | Líneas aprox | Cambio Principal |
|---------|--------------|------------------|
| `lib/execution_verifier.py` | +40 | `VerificationNormalizer` class |
| `modules/verifier-engine/main.py` | +15 | Usar normalizer, mejorar extracción action |
| `modules/worker-python/main.py` | +20 | Validar/establecer meta.action |
| `modules/ai-assistant/main.py` | +60 | `ProcessingHeartbeat` class, timeouts configurables |
| `modules/supervisor/main.js` | +80 | `taskLifecycle` Map, transiciones, idempotencia |
| `modules/router/main.js` | +25 | Establecer meta.action, meta.worker |

### Archivos Nuevos (Opcional)

```
lib/
  task_lifecycle.js          # Si se quiere separar del supervisor
  verification_validator.py   # Validaciones de consistencia
```

---

## G. CHECKLIST DE IMPLEMENTACIÓN

- [ ] FIX 4: Agregar `taskLifecycle` Map en supervisor
- [ ] FIX 4: Definir `VALID_TRANSITIONS`
- [ ] FIX 4: Implementar `transitionTask()`
- [ ] FIX 4: Agregar `processedEvents` Set
- [ ] FIX 4: Probar bloqueo de duplicados
- [ ] FIX 1: Modificar router para establecer meta.action
- [ ] FIX 1: Modificar worker para validar meta.action
- [ ] FIX 1: Modificar verifier para leer meta.action
- [ ] FIX 1: Probar trazabilidad completa
- [ ] FIX 2: Crear `VerificationNormalizer`
- [ ] FIX 2: Integrar en `VerificationBuilder.build()`
- [ ] FIX 2: Probar consistencia level/confidence
- [ ] FIX 3: Crear `ProcessingHeartbeat` en ai-assistant
- [ ] FIX 3: Definir `AI_TIMEOUTS` por acción
- [ ] FIX 3: Agregar estado `timeout_soft` en supervisor
- [ ] FIX 3: Probar heartbeat y fallback
- [ ] Todos: Ejecutar test suite
- [ ] Todos: Validar en runtime real

---

**Fin del Diseño Técnico**

*Listo para implementación incremental*
