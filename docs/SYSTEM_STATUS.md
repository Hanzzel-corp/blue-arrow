# Estado Actual del Sistema - blueprint-v0

**Fecha de auditoría**: 2026-04-07  
**Versión**: 1.0.0 + AI Extension  
**Módulos totales**: 31  
**Conexiones**: ~90

---

## 1. Capacidades Actuales del Sistema

### 1.1 Arquitectura Core

| Componente | Estado | Descripción |
|------------|--------|-------------|
| Runtime Bus | ✅ Activo | Orquestación de 28 módulos, reinicio automático (max 3) |
| Registry | ✅ Activo | Descubrimiento de módulos por manifest.json |
| Blueprint | ✅ Válido | system.v0.json con 30 módulos definidos |
| Mensajería | ✅ JSON Lines | Comunicación stdin/stdout por puertos |

### 1.2 Módulos de IA Implementados

| Módulo | Capacidades | Archivo Principal |
|--------|-------------|-------------------|
| `ai.assistant.main` | LLaMA local, queries, generación de código, explicación de errores | `modules/ai-assistant/main.py` |
| `ai.memory.semantic.main` | Embeddings 128D, búsqueda semántica, contexto | `modules/ai-memory-semantic/main.py` |
| `ai.self.audit.main` | Análisis estático, score de salud, sugerencias | `modules/ai-self-audit/main.py` |
| `ai.learning.engine.main` | Aprendizaje de patrones, predicción de acciones | `modules/ai-learning-engine/main.py` |

**Acciones de IA disponibles**:
- `ai.query` - Consultas generales con contexto
- `ai.analyze_intent` - Detección de intención del usuario
- `ai.generate_code` - Generación automática de código
- `ai.explain_error` - Explicación de errores del sistema
- `ai.analyze_project` - Análisis completo del proyecto
- `ai.learn` - Aprendizaje de preferencias
- `memory.store` - Almacenar recuerdos con embeddings
- `memory.search` - Búsqueda semántica en memoria
- `audit.run` - Auditoría de código y arquitectura

### 1.3 Sistemas de Soporte

| Sistema | Estado | Ubicación |
|---------|--------|-----------|
| Health Check | ✅ Implementado | `health_check.py` |
| Logger Estructurado | ✅ Implementado | `runtime/logger.js`, `logger.py` |
| Setup Automatizado | ✅ Implementado | `setup.py` |
| Gamificación RPG | ✅ Implementado | `modules/gamification/main.js` |
| Métricas | ✅ Implementado | `runtime/metrics.js`, `metrics.py` |
| Schema Validator | ✅ Implementado | `runtime/schema_validator.js` |
| Config Centralizada | ✅ Implementado | `runtime/config.js`, `config.py` |

### 1.4 Interfaces de Usuario

| Interface | Estado | Características |
|-----------|--------|-----------------|
| CLI | ✅ Activa | Comandos interactivos, planificación |
| Telegram Bot | ✅ Activa | Menús RPG, barras de progreso, botones con iconos |
| HUD | ✅ Activo | Estado visual en Telegram |

---

## 2. Arquitectura de Mensajes

### 2.1 Formato de Mensajes (Contrato v2)

```json
{
  "module": "nombre.modulo",
  "port": "action.in",
  "trace_id": "abc-123-trace",
  "meta": {
    "source": "cli|telegram|internal",
    "timestamp": "2026-01-01T00:00:00Z",
    "chat_id": 123456789
  },
  "payload": {
    "task_id": "uuid",
    "action": "nombre_accion",
    "params": {}
  }
}
```

**⚠️ IMPORTANTE**: `trace_id` y `meta` deben estar en el **nivel superior** del mensaje, NO dentro del payload.

### 2.2 Puertos Principales

| Puerto | Dirección | Uso |
|--------|-----------|-----|
| `action.in` | Entrada | Comandos y acciones a ejecutar |
| `result.out` | Salida | Resultados de operaciones |
| `event.out` | Salida | Eventos de logging y debug |
| `command.in` | Entrada | Comandos de usuario |
| `plan.out` | Salida | Planes generados |
| `approval.in/out` | Bidireccional | Circuito de aprobaciones |

---

## 3. Sistema de IA - Detalles

### 3.1 Configuración de IA

```python
# Configuración actual en ai-assistant/main.py
TIMEOUTS = {
    "ai.query": 20,
    "ai.analyze_intent": 10,
    "ai.generate_code": 45,
    "ai.explain_error": 15,
    "ai.analyze_project": 30,
    "ai.learn": 10,
    "ai.get_preferences": 5,
    "ai.predict": 8,
    "ai.clear_history": 5
}

MAX_HISTORY = 10  # Pares de conversación
WATCHDOG_INTERVAL = 3  # Segundos entre heartbeats
```

### 3.2 Estados del Procesamiento IA

```
idle → processing → responding → completed
                    ↓
                  error
```

**Mecanismos de protección**:
- Watchdog con heartbeats cada 3 segundos durante operaciones largas
- Resultados garantizados con fallback
- Métricas de success/error/timeout
- Historial de conversación con límite

### 3.3 Memoria Semántica

- **Embeddings**: 128 dimensiones
- **Almacenamiento**: FAISS index local
- **Búsqueda**: Similitud por coseno
- **Persistencia**: Archivos en `logs/ai-memory/`

### 3.4 Aprendizaje Continuo

**Datos almacenados**:
- Preferencias del usuario (`logs/user-learning.json`)
- Patrones de comandos frecuentes
- Correcciones realizadas
- Atajos sugeridos automáticamente

---

## 4. Sistema de Seguridad

### 4.1 Política de Acciones

| Categoría | Acciones |
|-----------|----------|
| **Allow** (sin confirmación) | `echo_text`, `search_file`, `monitor_resources`, `ai.query`, `ai.analyze_intent`, ... |
| **Confirm** (requiere aprobación) | `open_application`, `delete_file`, `run_shell`, `ai.learn`, ... |
| **Block** (prohibidas) | `disable_antivirus`, `extract_passwords`, `credential_dumping`, ... |

### 4.2 Circuito de Aprobaciones

```
Acción requiere confirmación
        ↓
safety-guard → approval
        ↓
   [Usuario aprueba/rechaza]
        ↓
   Continúa/Aborta
```

---

## 5. Persistencia

### 5.1 Archivos de Estado

| Archivo | Contenido | Actualización |
|---------|-----------|---------------|
| `logs/session-memory.json` | Historial de comandos, apps abiertas, búsquedas | Cada operación |
| `logs/events.log` | Log de eventos del sistema | Append continuo |
| `logs/user-learning.json` | Preferencias y patrones de usuario | Aprendizaje |
| `logs/apps-session.json` | Sesiones de aplicaciones | Apertura/cierre |
| `logs/gamification.json` | Progreso RPG del usuario | XP y logros |
| `logs/ai-memory/` | Embeddings y memoria semántica | Memoria IA |

### 5.2 Deduplicación

- Ventana de 2.5 segundos para comandos duplicados
- Clave basada en: `action::chat_id::params_hash`

---

## 6. Gamificación RPG

### 6.1 Sistema de Niveles

```
XP necesario = 100 × nivel²

Nivel 1 (Novato): 0-100 XP
Nivel 2 (Aprendiz): 100-400 XP
Nivel 3 (Explorador): 400-900 XP
...
Nivel 10 (Legendario): 9000+ XP
```

### 6.2 Logros Desbloqueables

| Logro | Condición | Recompensa |
|-------|-----------|------------|
| Primeros Pasos | 10 comandos ejecutados | 50 XP |
| Explorador | 5 aplicaciones abiertas | 75 XP |
| Maestro del Sistema | 50 comandos exitosos | 200 XP |
| Bug Hunter | Reportar/corregir error | 100 XP |
| Power User | 100 comandos totales | 300 XP |

---

## 7. Tests y Verificación

### 7.1 Tests Existentes

| Test | Tipo | Cobertura |
|------|------|-----------|
| `test_blueprint.py` | Integración | Validación de blueprint |
| `test_workers.py` | Funcional | 5 casos de workers Python |
| `smoke_runtime.py` | Smoke | Inicio del runtime |
| `health_check.py` | Sistema | Dependencias y recursos |

### 7.2 Scripts de Verificación

```bash
npm run health         # Health check
npm run check:node     # Verificar sintaxis Node.js
npm run check:py       # Verificar sintaxis Python
npm run verify         # Verificación completa
npm run test:all       # Todos los tests
```

---

## 8. Dependencias

### 8.1 Sistema

- Node.js 18+
- Python 3.11+
- Ollama (para funcionalidades IA)

### 8.2 Node.js

```json
{
  "dotenv": "^16.4.5",
  "node-telegram-bot-api": "^0.65.1"
}
```

### 8.3 Python

```
playwright
psutil
numpy          # Embeddings
faiss-cpu      # Búsqueda vectorial
```

### 8.4 Opcionales

- `xdotool` / `wmctrl` - Control de ventanas (Linux)
- Google Chrome / Chromium - Automatización browser

---

## 9. Flujo de Comandos

### 9.1 Flujo Normal

```
[CLI/Telegram] → interface → agent → planner
                                              ↓
[Resultado] ← memory-log ← executor ← runner
```

### 9.2 Flujo con IA

```
[Consulta IA] → agent → ai-assistant
                            ↓
[Respuesta] ← memory-log ← result
```

### 9.3 Flujo con Aprobación

```
[Acción riesgosa] → safety-guard → approval
                                        ↓
[Continuar] ← router ← [Usuario aprueba]
```

---

## 10. Métricas del Sistema

### 10.1 Rendimiento Actual

| Métrica | Valor | Nota |
|---------|-------|------|
| Latencia IA (promedio) | 15-30s | Dependiente de hardware |
| Tiempo de inicio runtime | 2-5s | 28 módulos |
| Reinicios automáticos | Max 3 | Con delay 5s |
| Memoria base | ~100MB | Sin IA activa |
| Memoria con IA | ~500MB-1GB | Dependiendo de modelo LLaMA |

### 10.2 Límites Conocidos

| Aspecto | Límite | Descripción |
|---------|--------|-------------|
| Historial IA | 10 pares | Límite de conversación |
| Cola mensajes | Sin límite | Riesgo de memory bloat |
| Restart | 3 intentos | Luego requiere intervención |
| Timeouts IA | 5-45s | Según acción |

---

## 11. Estado de Documentación

| Documento | Estado | Descripción |
|-----------|--------|-------------|
| `README.md` | ✅ Completo | Guía rápida de inicio |
| `PROJECT_STATUS.md` | ✅ Actualizado | Estado y roadmap |
| `PROJECT_DESCRIPTION.md` | ✅ Completo | Arquitectura detallada |
| `AI_IMPLEMENTATION_SUMMARY.md` | ✅ Completo | Resumen de capacidades IA |
| `IMPROVEMENTS.md` | ✅ Completo | Mejoras implementadas |
| `IMPROVEMENTS_GUIDE.md` | ✅ Completo | Guía de futuras mejoras |
| `docs/ARCHITECTURE.md` | ✅ Completo | Documentación técnica |
| `docs/AI_CAPABILITIES.md` | ✅ Completo | Guía de uso de IA |
| `docs/OLLAMA_SETUP.md` | ✅ Completo | Instalación Ollama |
| `docs/GAMIFICATION.md` | ✅ Completo | Sistema RPG |

---

*Documento generado para reflejar el estado actual del sistema post-auditoría*
