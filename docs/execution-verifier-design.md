> **⚠️ DISEÑO ARQUITECTÓNICO DEL EXECUTION VERIFIER**
>
> Este documento describe la **arquitectura objetivo/extendida** del Execution Verifier Engine.
> - El cierre formal de tareas sigue siendo responsabilidad exclusiva de `supervisor.main` 
> - La UI final sigue dependiendo del flujo `supervisor.main:response.out` 
> - Este documento no reemplaza los contratos operativos actuales de cierre y respuesta
> - Ver también: `TASK_CLOSURE_GOVERNANCE.md`, `PORT_CONTRACTS.md` 

# Execution Verifier Engine - Diseño Arquitectónico Completo

## Para: blueprint-v0
## Versión: 1.0
## Estado: Diseño Conceptual Aprobado para Implementación

---

# A. DISEÑO CONCEPTUAL COMPLETO

## Principio Central

**"Execute → Verify → Classify → Respond"**

El Execution Verifier Engine es una capa de verificación post-ejecución que:
1. Recibe resultados enriquecidos de los workers
2. Calcula confidence scores basados en evidencia concreta
3. Clasifica el resultado en taxonomía ejecutiva
4. Alimenta al supervisor con semántica de verificación
5. Mejora las respuestas de UI/Telegram

## Arquitectura del Engine

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXECUTION VERIFIER ENGINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   WORKERS    │───▶│  ENRICHED    │───▶│  VERIFIER    │       │
│  │  (desktop,   │    │   RESULT     │    │   CORE       │       │
│  │  browser,    │    │  (with       │    │              │       │
│  │  system)     │    │  evidence)   │    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                 │                │
│                                                 ▼                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    CONFIDENCE CALCULATOR                  │  │
│  │  • Signal weights per action type                          │  │
│  │  • Evidence combination rules                            │  │
│  │  • Score normalization (0.0 - 1.0)                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                 │                │
│                                                 ▼                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 VERIFICATION CLASSIFIER                   │  │
│  │  • Taxonomy mapping (verified → error)                     │  │
│  │  • Executive state determination                           │  │
│  │  • Human-readable classification                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                 │                │
│                                                 ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ SUPERVISOR   │    │    UI/       │    │   MEMORY     │       │
│  │   (with      │    │  TELEGRAM    │    │   LOG        │       │
│  │  enriched     │    │  (human      │    │  (verified   │       │
│  │  lifecycle)   │    │  responses)  │    │  results)    │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Responsabilidades por Componente

### 1. Workers (Ya existen - Se enriquecen)
- Ejecutan la acción
- Recolectan evidencia concreta (PIDs, window IDs, URLs, etc.)
- Emiten **EnrichedResult** (no solo booleanos)

### 2. Verifier Core (Nuevo módulo: `verifier.engine.main`)
- Recibe resultados enriquecidos
- Aplica reglas de verificación por tipo de acción
- Calcula confidence score
- Determina verification level
- Emite eventos de verificación

### 3. Confidence Calculator (Dentro de Verifier Core)
- Peso por señal de evidencia
- Combinación ponderada
- Normalización final

### 4. Verification Classifier (Dentro de Verifier Core)
- Mapea scores a taxonomía
- Genera estado ejecutivo
- Crea mensajes human-readable

### 5. Supervisor (Extendido)
- Consume metadata de verificación
- Distingue éxito verificado vs no verificado
- Emite eventos de lifecycle enriquecidos

### 6. UI/Telegram (Extendido)
- Recibe classification human-readable
- Muestra badges de verificación
- Adapta mensajes según confidence

---

# B. CONTRATO JSON PROPUESTO - ENRICHED RESULT

## Estructura Base (Compatible con contrato actual)

```json
{
  "task_id": "task_123",
  "status": "success",
  "result": {
    // Campos específicos de la acción (mantener compatibilidad)
    "opened": true,
    "application": "Firefox",
    
    // ─────────────────────────────────────────────────────────
    // NUEVO: Execution Verification Metadata
    // ─────────────────────────────────────────────────────────
    "_verification": {
      "version": "1.0",
      "verified_at": "2026-04-06T18:30:00Z",
      
      // Nivel de verificación alcanzado
      "level": "window_confirmed",
      
      // Score de confianza 0.0 - 1.0
      "confidence": 0.95,
      
      // Estado ejecutivo para supervisor
      "executive_state": "success_verified",
      
      // Evidencia recolectada
      "evidence": {
        "process_detected": true,
        "pid": 12345,
        "window_detected": true,
        "window_id": "0x04200001",
        "window_title": "Firefox - New Tab",
        "target_matched": true,
        "focus_confirmed": true,
        "command_executed": "firefox",
        "launch_mode": "detached_popen",
        "verification_method": "wmctrl_xdotool",
        "screenshot_available": false,
        "response_time_ms": 850
      },
      
      // Señales individuales con pesos
      "signals": [
        {"name": "process_detected", "present": true, "weight": 0.25, "contribution": 0.25},
        {"name": "window_detected", "present": true, "weight": 0.35, "contribution": 0.35},
        {"name": "target_matched", "present": true, "weight": 0.25, "contribution": 0.25},
        {"name": "focus_confirmed", "present": true, "weight": 0.15, "contribution": 0.15}
      ],
      
      // Mensaje human-readable de verificación
      "classification": {
        "code": "success_verified",
        "short": "Aplicación abierta y verificada",
        "detailed": "Firefox detectado con ventana activa (0x04200001) y foco confirmado",
        "user_message": "✅ Firefox abierto y verificado correctamente"
      },
      
      // Límites y advertencias
      "limitations": [],
      "warnings": []
    }
  },
  "meta": {
    "worker": "worker.python.desktop",
    "action": "open_application",
    "timestamp": "2026-04-06T18:30:00Z"
  }
}
```

## Campos Obligatorios vs Opcionales

### Obligatorios (siempre presente si `_verification` existe)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `_verification.version` | string | Versión del schema ("1.0") |
| `_verification.level` | string | Nivel de verificación alcanzado |
| `_verification.confidence` | number | Score 0.0 - 1.0 |
| `_verification.executive_state` | string | Estado para supervisor |
| `_verification.evidence` | object | Evidencia concreta recolectada |
| `_verification.classification` | object | Mensajes human-readable |

### Opcionales (dependen del tipo de acción)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `_verification.signals` | array | Desglose de señales individuales |
| `_verification.verified_at` | string | Timestamp ISO 8601 |
| `_verification.limitations` | array | Strings de limitaciones conocidas |
| `_verification.warnings` | array | Strings de advertencias |

## Niveles de Verificación (`_verification.level`)

| Nivel | Descripción | Ejemplo |
|-------|-------------|---------|
| `none` | Sin verificación posible | Comando ejecutado pero sin feedback |
| `process_only` | Proceso detectado, sin ventana | Daemon o app sin UI |
| `window_detected` | Ventana detectada, no confirmada | Window ID encontrado pero no enfocado |
| `window_confirmed` | Ventana detectada y enfocada | App abierta con foco activo |
| `target_verified` | Target específico confirmado | URL correcta, título esperado |
| `fully_verified` | Verificación completa con screenshot | Todo confirmado + imagen |

## Estados Ejecutivos (`_verification.executive_state`)

| Estado | Confidence | Uso |
|--------|------------|-----|
| `success_verified` | 0.90 - 1.00 | Éxito con evidencia fuerte |
| `success_high_confidence` | 0.75 - 0.89 | Éxito probable, buena evidencia |
| `success_partial` | 0.50 - 0.74 | Éxito parcial, evidencia mixta |
| `success_unverified` | 0.00 - 0.49 | Acción ejecutada, sin verificación |
| `error_confirmed` | - | Error confirmado por evidencia |
| `error_timeout` | - | Timeout durante verificación |
| `unknown` | - | Estado indeterminado |

## Compatibilidad con Workers Actuales

Los workers actuales ya emiten algunos campos de verificación (como `process_detected`, `window_detected`, `confidence`). El Engine los normalizará al nuevo schema `_verification`.

---

# C. TABLA DE SEÑALES / PESOS / CONFIDENCE

## Sistema de Ponderación por Tipo de Acción

### A. Desktop - `open_application`

| Señal | Peso | Condición | Cómo detectar |
|-------|------|-----------|---------------|
| `process_detected` | 0.20 | PID existe en `/proc` | `pgrep -f command` |
| `window_detected` | 0.30 | Window ID encontrado | `wmctrl -l` + match |
| `target_matched` | 0.25 | Título/case coincide | Regex en window title |
| `focus_confirmed` | 0.15 | Ventana tiene foco | `xdotool getactivewindow` |
| `window_raised` | 0.10 | WindowRaise exitoso | Exit code de xdotool |

**Fórmula:**
```
confidence = Σ(signal.present × signal.weight)

Ejemplo:
- process_detected: true × 0.20 = 0.20
- window_detected: true × 0.30 = 0.30
- target_matched: true × 0.25 = 0.25
- focus_confirmed: false × 0.15 = 0.00
- window_raised: true × 0.10 = 0.10
─────────────────────────────────────
Total: 0.85 (success_high_confidence)
```

### B. Desktop - `terminal.write_command`

| Señal | Peso | Condición | Cómo detectar |
|-------|------|-----------|---------------|
| `terminal_exists` | 0.20 | Window ID válida | `wmctrl -l` |
| `window_active` | 0.25 | Terminal tiene foco | `xdotool getactivewindow` |
| `command_typed` | 0.20 | xdotool type exitoso | Exit code 0 |
| `command_executed` | 0.25 | Enter presionado | Exit code 0 |
| `output_captured` | 0.10 | stdout/stderr no vacío | Captura del comando |

### C. Browser - `open_url`

| Señal | Peso | Condición | Cómo detectar |
|-------|------|-----------|---------------|
| `browser_opened` | 0.20 | Browser process existe | `pgrep chrome/firefox` |
| `page_loaded` | 0.30 | Playwright page existe | `page.url()` no error |
| `url_matches` | 0.25 | URL actual contiene target | `page.url().includes(target)` |
| `title_available` | 0.15 | Título no vacío | `page.title()` |
| `dom_ready` | 0.10 | DOMContentLoaded | Playwright event |

### D. Browser - `search` 

| Señal | Peso | Condición | Cómo detectar |
|-------|------|-----------|---------------|
| `search_page_loaded` | 0.25 | Página de búsqueda cargada | `page.url()` válido |
| `query_in_url` | 0.25 | Query string presente | `URL.searchParams` |
| `results_found` | 0.30 | Locator encuentra resultados | `locator('a[href]').count() > 0` |
| `results_extracted` | 0.20 | Array de resultados no vacío | `results.length > 0` |

### E. System - `search_file`

| Señal | Peso | Condición | Cómo detectar |
|-------|------|-----------|---------------|
| `command_executed` | 0.30 | Comando terminó | Exit code 0 |
| `output_received` | 0.30 | stdout no vacío | `result.stdout` |
| `paths_found` | 0.25 | Líneas parseables como paths | Regex match |
| `paths_exist` | 0.15 | Al menos un path existe | `fs.existsSync()` |

## Umbrales de Clasificación

| Confidence | Executive State | User Message Style |
|------------|-------------------|-------------------|
| 0.90 - 1.00 | `success_verified` | "✅ {action} completado y verificado" |
| 0.75 - 0.89 | `success_high_confidence` | "✓ {action} ejecutado (alta confianza)" |
| 0.50 - 0.74 | `success_partial` | "⚠ {action} ejecutado con verificación parcial" |
| 0.25 - 0.49 | `success_weak` | "? {action} ejecutado pero no verificado" |
| 0.00 - 0.24 | `success_unverified` | "⚠ {action} enviado, estado desconocido" |

---

# D. REGLAS POR WORKER

## 1. Desktop Worker (`worker.python.desktop`)

### `open_application`

**Verificación paso a paso:**

1. **Pre-ejecución:**
   - Capturar lista de ventanas antes (`before_windows`)
   - Capturar lista de procesos antes (`before_pids`)

2. **Ejecución:**
   - Lanzar con `detached_popen`, `gtk-launch`, o `subprocess`
   - Guardar launch_mode utilizado

3. **Post-ejecución (polling por 4 segundos):**
   - Check 1: ¿Proceso aparece en `pgrep`? (0.20)
   - Check 2: ¿Nueva ventana en `wmctrl -l`? (0.30)
   - Check 3: ¿Título de ventana coincide con target? (0.25)
   - Check 4: ¿Ventana tiene foco? (0.15)
   - Check 5: ¿Se pudo hacer raise? (0.10)

4. **Decisiones por caso:**
   - **Caso A:** Todo OK → `level: window_confirmed`, `executive_state: success_verified`
   - **Caso B:** Proceso + Ventana pero sin foco → `level: window_detected`, `executive_state: success_high_confidence`
   - **Caso C:** Solo proceso → `level: process_only`, `executive_state: success_partial`
   - **Caso D:** Nada → `level: none`, `executive_state: error_confirmed`

5. **Evidencia a recolectar:**
   ```json
   {
     "pid": 12345,
     "window_id": "0x04200001",
     "window_title": "Firefox - New Tab",
     "before_windows": 12,
     "after_windows": 13,
     "launch_mode": "detached_popen",
     "verification_time_ms": 850,
     "focus_attempted": true,
     "focus_success": true
   }
   ```

### `terminal.write_command`

**Verificación paso a paso:**

1. **Validación pre-ejecución:**
   - ¿Window ID proporcionado existe? → `terminal_exists` (0.20)
   - ¿Es ventana activa? → `window_active` (0.25)

2. **Ejecución con tracking:**
   - Ejecutar `xdotool type` → `command_typed` (0.20)
   - Ejecutar `xdotool key Return` → `command_executed` (0.25)

3. **Captura de salida (opcional):**
   - Si se puede capturar stdout → `output_captured` (0.10)

4. **Decisiones:**
   - Typed + Executed + Active → confidence 0.70 → `success_partial`
   - Typed + Executed pero no Active → confidence 0.45 → `success_weak`
   - Fallo en type → confidence 0.00 → `error_confirmed`

## 2. Browser Worker (`worker.python.browser`)

### `open_url`

**Verificación paso a paso:**

1. **Pre-navegación:**
   - Guardar URL objetivo
   - Verificar browser conectado

2. **Navegación:**
   - `page.goto(url, wait_until="domcontentloaded")`
   - Timeout 30s

3. **Verificación post-navegación:**
   - ¿Page object válido? → `page_loaded` (0.30)
   - ¿`page.url()` contiene target domain? → `url_matches` (0.25)
   - ¿`page.title()` no vacío? → `title_available` (0.15)

4. **Decisiones:**
   - URL matches + Title OK → confidence 0.70 → `success_high_confidence`
   - Page loaded pero URL diferente → confidence 0.30 → `success_partial` + warning redirect
   - Timeout → confidence 0.00 → `error_timeout`

### `search`

**Verificación paso a paso:**

1. **Verificación de URL:**
   - ¿`page.url()` es `google.com/search`? → `search_page_loaded` (0.25)
   - ¿Query string contiene término buscado? → `query_in_url` (0.25)

2. **Extracción de resultados:**
   - ¿`locator('a[href]').count() > 0`? → `results_found` (0.30)
   - ¿Array `results` no vacío? → `results_extracted` (0.20)

3. **Decisiones:**
   - Todo OK → confidence 1.00 → `success_verified`
   - Sin resultados → confidence 0.50 → `success_partial` + warning "no results"

## 3. System Worker (`worker.python.system`)

### `search_file`

**Verificación paso a paso:**

1. **Ejecución del comando:**
   - `find` o `locate` con timeout
   - Guardar exit code

2. **Análisis de output:**
   - ¿Exit code 0? → `command_executed` (0.30)
   - ¿stdout no vacío? → `output_received` (0.30)
   - ¿Líneas parseables como paths? → `paths_found` (0.25)
   - ¿Al menos un path existe? → `paths_exist` (0.15)

3. **Decisiones:**
   - Paths encontrados y existen → confidence 0.85 → `success_high_confidence`
   - Output recibido pero paths no existen → confidence 0.55 → `success_partial` + warning stale
   - Output vacío → confidence 0.30 → `success_weak` + "no files found"

---

# E. LÓGICA DE SUPERVISOR INTEGRADA

## Eventos de Supervisor Extendidos

El supervisor actual emite:
- `supervisor_task_started`
- `supervisor_task_success`
- `supervisor_task_error`
- `supervisor_task_timeout`

**Nuevos eventos con verificación:**
- `supervisor_task_verified` → confidence >= 0.90
- `supervisor_task_high_confidence` → confidence 0.75-0.89
- `supervisor_task_partial` → confidence 0.50-0.74
- `supervisor_task_weak` → confidence 0.25-0.49
- `supervisor_task_unverified` → confidence < 0.25
- `supervisor_task_failed_verified` → error con evidencia del fallo

## Lógica de Decisión del Supervisor

```javascript
function processResultWithVerification(result, meta) {
  const verification = result?._verification;
  
  if (!verification) {
    // Modo legacy: comportamiento actual
    return result?.status === "success" 
      ? emit("supervisor_task_success") 
      : emit("supervisor_task_error");
  }
  
  const { executive_state, confidence, classification } = verification;
  
  // Mapeo de executive_state a evento
  const eventMap = {
    "success_verified": "supervisor_task_verified",
    "success_high_confidence": "supervisor_task_high_confidence",
    "success_partial": "supervisor_task_partial",
    "success_weak": "supervisor_task_weak",
    "success_unverified": "supervisor_task_unverified",
    "error_confirmed": "supervisor_task_failed_verified",
    "error_timeout": "supervisor_task_timeout"
  };
  
  const eventType = eventMap[executive_state] || "supervisor_task_unknown";
  
  emit("event.out", {
    level: getLevelForState(executive_state),
    type: eventType,
    task_id: result.task_id,
    status: executive_state,
    confidence: confidence,
    user_message: classification.user_message,
    evidence_summary: summarizeEvidence(verification.evidence)
  });
  
  // Para result.out: mantener compatibilidad pero añadir metadata
  emit("result.out", {
    task_id: result.task_id,
    status: executive_state.startsWith("success") ? "success" : "error",
    result: result.result,  // Mantener resultado original
    verification: {         // Añadir metadata nueva
      confidence: confidence,
      level: verification.level,
      executive_state: executive_state
    },
    meta: meta
  });
}
```

## Payloads Sugeridos

### `supervisor_task_verified`
```json
{
  "level": "info",
  "type": "supervisor_task_verified",
  "task_id": "task_123",
  "status": "success_verified",
  "confidence": 0.95,
  "user_message": "✅ Firefox abierto y verificado correctamente",
  "verification": {
    "level": "window_confirmed",
    "evidence_count": 5,
    "primary_evidence": "window_id: 0x04200001"
  }
}
```

### `supervisor_task_partial`
```json
{
  "level": "warn",
  "type": "supervisor_task_partial",
  "task_id": "task_123",
  "status": "success_partial",
  "confidence": 0.65,
  "user_message": "⚠ Proceso iniciado pero ventana no detectada",
  "warnings": ["process_running_but_no_window"]
}
```

---

# F. INTEGRACIÓN CON UI / TELEGRAM / MEMORIA

## 1. Telegram - Respuestas Humanizadas

### Mapeo de Classification a Mensajes

```javascript
const messageTemplates = {
  "open_application": {
    "success_verified": "✅ {app} abierto y verificado. Ventana activa: {window_title}",
    "success_high_confidence": "✓ {app} abierto (ventana detectada)",
    "success_partial": "⚠ {app} iniciado, pero no pude confirmar la ventana",
    "success_weak": "? Comando enviado a {app}, estado pendiente",
    "error_confirmed": "❌ No se pudo abrir {app}. Error: {error}"
  },
  "terminal.write_command": {
    "success_verified": "✅ Comando escrito en terminal activa y ejecutado",
    "success_partial": "⚠ Comando enviado, pero la terminal no tenía foco",
    "success_weak": "? Intenté escribir el comando"
  },
  "open_url": {
    "success_verified": "✅ {url} abierta y verificada",
    "success_high_confidence": "✓ Navegador cargó {domain}",
    "success_partial": "⚠ Página cargada pero URL diferente: {actual_url}"
  }
};
```

### Ejemplo de Respuesta en Telegram

**Caso: Éxito Verificado**
> ✅ Firefox abierto y verificado. Ventana activa: "Firefox - New Tab"

**Caso: Éxito Parcial**
> ⚠ LibreOffice iniciado, pero no pude confirmar la ventana. El proceso está corriendo (PID: 12345).

**Caso: Error Confirmado**
> ❌ No se pudo abrir "app-desconocida". Error: Aplicación no encontrada en el sistema.

## 2. HUD / UI State - Badges de Verificación

### Estados Visuales

| Estado | Badge | Color |
|--------|-------|-------|
| `success_verified` | ✓✓ | Verde brillante |
| `success_high_confidence` | ✓ | Verde |
| `success_partial` | ~ | Amarillo |
| `success_weak` | ? | Naranja |
| `success_unverified` | ○ | Gris |
| `error_confirmed` | ✗ | Rojo |

### Persistencia en UI State

```json
{
  "active_app": {
    "id": "firefox",
    "label": "Firefox",
    "verification": {
      "state": "success_verified",
      "confidence": 0.95,
      "verified_at": "2026-04-06T18:30:00Z",
      "evidence": {
        "window_id": "0x04200001",
        "pid": 12345
      }
    }
  }
}
```

## 3. Memory Log - Almacenamiento de Resultados Verificados

### Estructura en `logs/session-memory.json`

```json
{
  "verified_results": [
    {
      "task_id": "task_123",
      "timestamp": "2026-04-06T18:30:00Z",
      "action": "open_application",
      "target": "Firefox",
      "verification": {
        "state": "success_verified",
        "confidence": 0.95,
        "level": "window_confirmed",
        "evidence": {
          "pid": 12345,
          "window_id": "0x04200001",
          "window_title": "Firefox - New Tab"
        }
      },
      "context": {
        "chat_id": 1781005414,
        "user_command": "Abrir firefox"
      }
    }
  ]
}
```

### Query de Resultados Verificados

```javascript
// Buscar último resultado verificado para una app
function getLastVerifiedResult(appId) {
  return memory.verified_results
    .filter(r => r.target === appId)
    .filter(r => r.verification.confidence >= 0.75)
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
}
```

---

# G. ROADMAP DE MIGRACIÓN POR FASES

## FASE 1: Enrich Results (Semana 1)
**Objetivo:** Workers emiten `_verification` sin romper flujos existentes

### Tareas:
1. **Crear `ExecutionVerifier` helper class** en cada worker
   - Python: `execution_verifier.py` para workers Python
   - JavaScript: `execution-verifier.js` para workers Node

2. **Actualizar Desktop Worker:**
   - `open_application`: migrar a `_verification` schema
   - `terminal.write_command`: añadir verificación de foco
   - Mantener campos legacy (`opened`, `process_detected`) para compatibilidad

3. **Actualizar Browser Worker:**
   - `open_url`: añadir verificación de URL match
   - `search`: añadir verificación de resultados
   - `fill_form`: añadir verificación de fields filled

4. **Actualizar System Worker:**
   - `search_file`: añadir verificación de paths existentes
   - `monitor_resources`: añadir verificación de métricas leídas

### Entregable:
- Workers emiten `_verification` en resultado
- Sistema funciona igual (no se usa `_verification` todavía)
- Tests pasan

---

## FASE 2: Verifier Core (Semana 2)
**Objetivo:** Nuevo módulo `verifier.engine.main` consume y normaliza

### Tareas:
1. **Crear módulo `verifier.engine.main`:**
   - Puerto: `result.in` (escucha resultados de workers)
   - Puerto: `result.out` (emite resultados verificados)
   - Puerto: `event.out` (emite eventos de verificación)

2. **Implementar Confidence Calculator:**
   - Reglas por tipo de acción (archivo de configuración)
   - Normalización de scores

3. **Implementar Verification Classifier:**
   - Mapeo de scores a estados ejecutivos
   - Generador de mensajes human-readable

4. **Integrar en Blueprint:**
   - Añadir `verifier.engine.main` a `system.v0.json`
   - Conectar workers → verifier → supervisor

### Entregable:
- Módulo verifier funcionando
- Eventos de verificación visibles en logs
- Supervisor recibe resultados enriquecidos

---

## FASE 3: Supervisor Enriquecido (Semana 3)
**Objetivo:** Supervisor interpreta `_verification` y emite eventos nuevos

### Tareas:
1. **Extender `supervisor.main`:**
   - Leer `_verification` de resultados
   - Implementar `processResultWithVerification()`
   - Emitir nuevos eventos (`supervisor_task_verified`, etc.)

2. **Mantener Backward Compatibility:**
   - Si no hay `_verification`, usar lógica actual
   - Resultados `result.out` mantienen `status: success/error`

3. **Tests de Integración:**
   - Verificar que supervisor emite eventos correctos por cada estado

### Entregable:
- Supervisor distingue éxito verificado vs no verificado
- Eventos de lifecycle enriquecidos funcionando
- Dashboard de tasks muestra confidence

---

## FASE 4: UI/Telegram (Semana 4)
**Objetivo:** Interfaces muestran verificación al usuario

### Tareas:
1. **Actualizar `ui.state.main`:**
   - Consumir eventos de verificación del supervisor
   - Almacenar `verification` en estado de active_app
   - Emitir badges para HUD

2. **Actualizar `telegram.interface`:**
   - Templates de mensajes por estado de verificación
   - Mapeo de classification a mensajes en español

3. **Actualizar `telegram.hud`:**
   - Mostrar badges de verificación en menús
   - Colores según confidence

### Entregable:
- Telegram responde con mensajes verificados
- HUD muestra estado de verificación
- Usuario sabe si la acción realmente pasó

---

## FASE 5: Planner/Learning (Semana 5)
**Objetivo:** Planner puede usar confidence para decisiones

### Tareas:
1. **Actualizar `planner.main`:**
   - Leer confidence de últimos resultados
   - Ajustar planes basado en verificación previa
   - Si confidence < 0.50, agregar pasos de confirmación

2. **Actualizar `ai.learning.engine`:**
   - Aprender de patrones de verificación
   - "Cuando abro Chrome, window_confirmed en 95% de casos"

### Entregable:
- Planner más inteligente con confidence
- Learning engine usa verificación para patrones
- Sistema más robusto

---

# H. CASOS BORDE Y MANEJO

## 1. Proceso existe pero ventana no aparece

**Situación:** App de background (daemon) o app con problema gráfico

**Detección:**
- `process_detected: true`
- `window_detected: false`
- `timeout: true`

**Clasificación:**
- Confidence: 0.20 (solo process)
- Level: `process_only`
- Executive state: `success_partial`
- Warning: ["process_running_but_no_window"]

**User message:**
> ⚠ {app} iniciado (proceso detectado) pero no se detectó ventana. Puede ser una aplicación de fondo o tener problema gráfico.

---

## 2. Ventana aparece pero no coincide con target

**Situación:** App abrió pero es diferente a la solicitada (ej: pidgin vs telegram)

**Detección:**
- `window_detected: true`
- `target_matched: false`
- `window_title: "Pidgin"` vs `target: "Telegram"`

**Clasificación:**
- Confidence: 0.50 (process + window, no target)
- Level: `window_detected`
- Executive state: `success_partial`
- Warning: ["window_found_but_not_target", "expected: Telegram, found: Pidgin"]

**User message:**
> ⚠ Se abrió una ventana, pero no coincide con "Telegram". Se detectó: "Pidgin".

---

## 3. Terminal activa no es la esperada

**Situación:** Usuario cambió de ventana mientras bot escribía

**Detección:**
- `command_typed: true`
- `window_active_before: true`
- `window_active_after: false`
- `actual_active_window: "0x03abc"` vs `target_window: "0x04200001"`

**Clasificación:**
- Confidence: 0.40 (typed + executed, no active)
- Level: `weak_signal`
- Executive state: `success_weak`
- Warning: ["terminal_lost_focus_during_execution"]

**User message:**
> ? Comando escrito, pero la terminal perdió el foco durante la ejecución. Verificá la ventana correcta.

---

## 4. Browser abre pero carga otra URL

**Situación:** Redirect, error DNS, o homepage override

**Detección:**
- `page_loaded: true`
- `url_matches: false`
- `expected_url: "github.com"`
- `actual_url: "google.com"` (redirect)

**Clasificación:**
- Confidence: 0.30 (page loaded, wrong URL)
- Level: `unverified`
- Executive state: `success_weak`
- Warning: ["url_mismatch", "expected: github.com, got: google.com"]

**User message:**
> ⚠ Página cargada, pero la URL es diferente. Esperaba: github.com, cargó: google.com

---

## 5. search_file devuelve vacío

**Situación:** No se encontraron archivos

**Detección:**
- `command_executed: true`
- `output_received: true` (pero vacío)
- `paths_found: false`

**Clasificación:**
- Confidence: 0.30 (command OK, no results)
- Level: `process_only`
- Executive state: `success_weak`
- Warning: ["search_completed_no_results"]

**User message:**
> ⚠ Búsqueda completada pero no se encontraron archivos.

---

## 6. Worker emite success pero sin evidencia suficiente

**Situación:** Worker actual devuelve `{opened: true}` sin verificación

**Detección:**
- `_verification: null` o missing
- `status: "success"`

**Clasificación:**
- Confidence: 0.00 (no data)
- Level: `unknown`
- Executive state: `success_unverified`

**User message:**
> ○ Acción reportada como exitosa pero sin verificación disponible.

---

## 7. Falta dependencia (wmctrl, xdotool)

**Situación:** Sistema Linux minimal sin herramientas X11

**Detección:**
- `which wmctrl` → no encontrado
- `which xdotool` → no encontrado
- `verification_method: "process_only"`

**Clasificación:**
- Confidence: 0.20 (solo process)
- Level: `process_only`
- Executive state: `success_partial`
- Limitation: ["wmctrl_not_installed", "xdotool_not_installed"]

**User message:**
> ⚠ {app} iniciado. Instalá `wmctrl` y `xdotool` para verificación completa: `sudo apt install wmctrl xdotool`

---

## 8. Se reutiliza ventana vieja y no una nueva

**Situación:** App abrió en ventana existente (ej: Chrome nueva tab)

**Detección:**
- `before_windows: 5`
- `after_windows: 5` (no cambió)
- `window_detected: true` (ventana vieja)
- `is_new_window: false`

**Clasificación:**
- Confidence: 0.65 (process + window, not new)
- Level: `window_detected`
- Executive state: `success_partial`
- Info: ["existing_window_reused"]

**User message:**
> ✓ {app} activado en ventana existente.

---

## 9. Foco cambia tarde

**Situación:** App abrió pero focus() tardó

**Detección:**
- `window_detected: true` (inmediato)
- `focus_confirmed: false` (inmediato)
- `focus_confirmed_delayed: true` (después de 2s)

**Clasificación:**
- Confidence: 0.80 (process + window + delayed focus)
- Level: `window_confirmed`
- Executive state: `success_high_confidence`

**User message:**
> ✓ {app} abierto y verificado (foco confirmado con pequeña demora).

---

## 10. Timeout parcial

**Situación:** Timeout durante verificación pero proceso existe

**Detección:**
- `timeout: true`
- `process_detected: true`
- `window_detected: false`
- `verification_time_ms: 4000` (límite)

**Clasificación:**
- Confidence: 0.20 (timeout, solo process)
- Level: `process_only`
- Executive state: `success_partial`
- Warning: ["verification_timeout", "process_may_be_starting_slowly"]

**User message:**
> ⚠ {app} proceso detectado pero verificación de ventana timeout. La app puede estar cargando lentamente.

---

# I. RECOMENDACIÓN FINAL - QUÉ TOCAR PRIMERO

## Prioridad 1: Desktop Worker + open_application (Esta semana)

**Por qué primero:**
1. Es el worker más usado
2. Ya tiene lógica de verificación (solo hay que normalizar a `_verification`)
3. Impacto inmediato en UX
4. Base para los demás workers

**Cambios concretos:**
```python
# En worker-python/main.py, función open_application()
# Cambiar return actual:
return {
    "opened": True,
    "application": name,
    "process_detected": True,
    "window_detected": True,
    "confidence": 1.0
}

# A:
return {
    "opened": True,  # Legacy compatibility
    "application": name,
    "_verification": {
        "version": "1.0",
        "level": "window_confirmed",
        "confidence": 1.0,
        "executive_state": "success_verified",
        "evidence": {
            "process_detected": True,
            "pid": detected_pid,
            "window_detected": True,
            "window_id": detected_window_id,
            "window_title": detected_title,
            "target_matched": True,
            "focus_confirmed": True
        },
        "signals": [
            {"name": "process_detected", "present": True, "weight": 0.20, "contribution": 0.20},
            {"name": "window_detected", "present": True, "weight": 0.30, "contribution": 0.30},
            {"name": "target_matched", "present": True, "weight": 0.25, "contribution": 0.25},
            {"name": "focus_confirmed", "present": True, "weight": 0.15, "contribution": 0.15},
            {"name": "window_raised", "present": True, "weight": 0.10, "contribution": 0.10}
        ],
        "classification": {
            "code": "success_verified",
            "short": "Aplicación abierta y verificada",
            "detailed": f"{name} detectado con ventana activa y foco confirmado",
            "user_message": f"✅ {name} abierto y verificado correctamente"
        }
    }
}
```

## Prioridad 2: Verifier Core Module (Próxima semana)

Crear `modules/verifier-engine/main.py` que:
1. Escuche `result.in` de todos los workers
2. Normalice resultados legacy a `_verification`
3. Calcule confidence faltante
4. Emita a `result.out` hacia supervisor

## Prioridad 3: Supervisor Extension (Semana 3)

Modificar `supervisor.main` para:
1. Leer `_verification` si existe
2. Emitir nuevos eventos (`supervisor_task_verified`, etc.)
3. Mantener backward compatibility

## Prioridad 4: Telegram/UI (Semana 4)

Templates de mensajes en `telegram.interface` que usen `classification.user_message`.

---

# J. ARCHIVOS A CREAR/MODIFICAR

## Nuevos Archivos

1. **`modules/verifier-engine/main.py`** - Core del engine
2. **`modules/verifier-engine/manifest.json`** - Manifest del módulo
3. **`lib/execution_verifier.py`** - Helper para workers Python
4. **`lib/execution-verifier.js`** - Helper para workers Node
5. **`docs/execution-verifier-spec.md`** - Especificación completa

## Archivos a Modificar (en orden)

1. **`modules/worker-python/main.py`**
   - Función `open_application()`: añadir `_verification`
   - Función `write_in_terminal()`: añadir `_verification`

2. **`modules/worker-browser/main.py`**
   - Función `open_url()`: añadir `_verification`
   - Función `search()`: añadir `_verification`

3. **`modules/supervisor/main.js`**
   - Extender `processResult()` para leer `_verification`
   - Añadir nuevos eventos

4. **`modules/telegram.interface/main.js`**
   - Templates de mensajes por estado de verificación

5. **`modules/ui.state.main.js`**
   - Almacenar verification en active_app

6. **`blueprints/system.v0.json`**
   - Añadir `verifier.engine.main` al wiring

---

# K. MÉTRICAS DE ÉXITO

## Cómo saber si funciona

### Métricas Técnicas
- [ ] 100% de acciones `open_application` emiten `_verification`
- [ ] 0% de resultados con `confidence: null`
- [ ] 95% de éxitos con confidence >= 0.75
- [ ] <5% de falsos positivos (éxito reportado pero sin evidencia)

### Métricas de UX
- [ ] Usuario sabe si app realmente abrió
- [ ] Mensajes claros en Telegram sobre estado de verificación
- [ ] Reducción de "¿Se abrió o no?" en uso

### Métricas de Confiabilidad
- [ ] Supervisor distingue éxito verificado vs no verificado
- [ ] Planner usa confidence para decisiones
- [ ] Learning engine aprende de patrones de verificación

---

**Fin del Documento de Diseño**

**Próximo paso:** Revisión del diseño → Aprobación → Implementación Fase 1
