# blueprint-v0 - Documentación Completa

## 1. Visión General

`blueprint-v0` es un sistema de agente modular para automatizar acciones en PC mediante una arquitectura desacoplada basada en **blueprint + runtime + modules**.

### 1.1 Propósito

Ejecutar módulos desacoplados (Node.js y Python) conectados por puertos, donde cada módulo recibe y emite mensajes JSON Lines por `stdin/stdout`, mientras el runtime central levanta procesos y enruta mensajes según la topología declarada en `blueprints/system.v0.json`.

### 1.2 Casos de Uso Soportados

- Comandos por CLI y Telegram
- Planificación y ejecución de acciones
- Automatización de desktop (abrir apps, escribir en terminal)
- Acciones de sistema (búsqueda de archivos, estado de recursos)
- Acciones de browser con Playwright
- Memoria de sesión y eventos persistidos en `logs/`
- Asistencia de IA local mediante LLaMA/Ollama
- Análisis de intenciones y generación de código
- Aprendizaje continuo del usuario

---

## 2. Estructura del Proyecto

```text
blueprint-v0/
├── blueprints/              # Topología de módulos y conexiones
│   └── system.v0.json       # Blueprint principal (conteo y wiring operativos en el blueprint vigente)
├── runtime/                 # Proceso orquestador (Node.js)
│   ├── main.js             # Bootstrap, validación, CLI
│   ├── bus.js              # Enrutamiento de mensajes entre procesos
│   ├── registry.js         # Descubrimiento de manifest.json
│   ├── transforms.js       # Normalización de mensajes
│   ├── logger.js           # Logging estructurado
│   ├── config.js           # Configuración centralizada
│   ├── metrics.js          # Métricas del sistema
│   └── schema_validator.js # Validación de mensajes
├── modules/                 # Módulos independientes (core + UI + IA + workers)
│   ├── agent/              # Core: Interpretación de comandos
│   ├── ai-assistant/       # IA: LLaMA local, asistencia inteligente
│   ├── ai-intent/          # IA: Análisis de intenciones
│   ├── ai-learning-engine/ # IA: Aprendizaje continuo del usuario
│   ├── ai-memory-semantic/ # IA: Memoria con embeddings (128D)
│   ├── ai-self-audit/      # IA: Auto-análisis del proyecto
│   ├── approval/           # Core: Circuito de aprobaciones
│   ├── apps-menu/          # UI: Menú de aplicaciones para Telegram
│   ├── apps-session/       # Core: Gestión de sesiones de apps
│   ├── gamification/       # Ext: Sistema de gamificación
│   ├── interface/          # Core: Interface CLI
│   ├── memory-log/         # Core: Persistencia de memoria
│   ├── memory-menu/        # UI: Menú de memoria para Telegram
│   ├── phase-engine/       # Core: Motor de fases de procesamiento
│   ├── plan-runner/        # Core: Ejecutor de planes
│   ├── planner/            # Core: Transforma comandos en planes
│   ├── project-audit/      # Ext: Auditoría de proyecto
│   ├── router/             # Core: Enrutamiento a workers
│   ├── safety-guard/       # Core: Política de seguridad
│   ├── supervisor/         # Core: Observación de ciclo de vida
│   ├── system-menu/        # UI: Menú de sistema para Telegram
│   ├── telegram-hud/       # UI: HUD de Telegram
│   ├── telegram-interface/ # Core: Bot de Telegram
│   ├── telegram-menu/      # UI: Menú principal de Telegram
│   ├── ui-state/           # Core: Estado de UI
│   ├── verifier-engine/    # Core: Verificación de resultados
│   ├── worker-browser/     # Worker: Navegación web (Playwright)
│   ├── worker-python/      # Worker: Control de apps y terminal
│   └── worker-system/      # Worker: Métricas y búsquedas
├── logs/                    # Eventos y memoria persistida
│   ├── session-memory.json
│   ├── events.log
│   ├── apps-session.json
│   └── user-learning.json
├── docs/                    # Documentación técnica
│   ├── ARCHITECTURE.md
│   └── DEVELOPMENT.md
├── tests/                   # Tests (unittest/pytest)
│   ├── test_blueprint.py
│   ├── test_workers.py
│   └── smoke_runtime.py
├── project_explainer.py     # Utilitario CLI para describir el proyecto
├── health_check.py        # Verificación de salud del sistema
├── setup.py                # Script de configuración
├── config.py               # Configuración Python
├── logger.py               # Logger Python
├── metrics.py              # Métricas Python
├── package.json            # Scripts npm
├── requirements.txt        # Dependencias Python
└── README.md               # Guía rápida
```

> **Nota**: El árbol de esta sección usa principalmente **nombres de carpetas físicas** del proyecto. Los **IDs lógicos/canónicos de módulos** se documentan en los contratos y en el blueprint operativo (por ejemplo: `worker.python.desktop`, `worker.python.terminal`, `worker.python.browser`, `interface.telegram`, `verifier.engine.main`).
>
> No siempre existe correspondencia **1:1** entre carpeta física, nombre histórico y **ID lógico activo**. Las tablas de módulos de este documento deben leerse como **clasificación lógica/operativa**, mientras que el árbol refleja principalmente la organización física del repositorio.

---

## 3. Arquitectura

### 3.1 Principios Arquitectónicos

- **Módulos desacoplados**: Sin imports cruzados entre módulos
- **Conexión por puertos**: Toda comunicación pasa por puertos declarados
- **Runtime central**: Orquesta y conecta módulos
- **Mensajería JSON Lines**: Sobre `stdin/stdout`
- **Node.js para orquestación**: Módulos core en JS
- **Python para workers**: Workers especializados en Python

### 3.2 Flujo Operativo

```text
┌─────────────┐
│ Interface   │
│ CLI/Telegram│
└──────┬──────┘
       │ command.out
       ▼
┌─────────────┐
│ Planner     │
└──────┬──────┘
       │ plan.out
       ▼
┌─────────────┐
│ Agent       │
└──────┬──────┘
       │ plan.out
       ▼
┌─────────────┐
│ Safety      │
│ / Approval  │
└──────┬──────┘
       │ approved.plan.out
       ▼
┌─────────────┐
│ Router      │
└──────┬──────┘
       │ action.in
       ▼
┌─────────────┐
│ Workers     │
└──────┬──────┘
       ├──────── event.out ───────► Memory / UI State
       │
       └──────── result.out ──────► Verifier (opcional) ─────► Supervisor
                                                             │
                                                             ├── event.out ─────► Observadores internos
                                                             └── response.out ──► Interfaces
```

### 3.3 Componentes del Runtime

| Componente | Función |
|------------|---------|
| `runtime/main.js` | Arranque, validación de módulos, bootstrap del bus, CLI |
| `runtime/registry.js` | Descubrimiento de `manifest.json` en `modules/*/manifest.json` |
| `runtime/bus.js` | Conexión de puertos entre módulos, reincio automático (max 3) |
| `runtime/transforms.js` | Normalización de mensajes entre módulos |
| `runtime/logger.js` | Logging estructurado con niveles |
| `runtime/config.js` | Configuración centralizada |
| `runtime/metrics.js` | Métricas de rendimiento |
| `runtime/schema_validator.js` | Validación de esquemas de mensajes |

### 3.4 Blueprint (`blueprints/system.v0.json`)

Define:
- `modules`: IDs de módulos declarados en el blueprint vigente
- `connections`: conexiones `from: "moduleA:port.out" → to: "moduleB:port.in"`

Patrón clave de conexiones:
interface.*:command.out → planner.main:command.in
planner.main:plan.out → agent.main:plan.in
agent.main:plan.out → safety.guard.main:plan.in
safety.guard.main:approved.plan.out → router.main:plan.in
approval.main:approved.plan.out → router.main:plan.in
router.main:* → worker.python.*:action.in
worker.python.*:result.out → [verifier.engine.main:result.in] → supervisor.main:result.in
worker.python.*:event.out → memory.log.main:event.in
worker.python.*:event.out → ui.state.main:event.in
supervisor.main:response.out → interface.*:response.in

### 3.5 Contrato de Mensajes

**Formato v2 (canónico):**
```json
{
  "module": "module.id",
  "port": "event.out",
  "trace_id": "abc-123",
  "meta": {
    "source": "module.id",
    "timestamp": "2026-01-01T00:00:00Z"
  },
  "payload": {}
}
```

> **⚠️ NOTA**: Este documento es un **overview introductorio**. Para especificaciones exactas del contrato v2, ver `PORT_CONTRACTS.md` y `CONTRACTS_GUIDE.md`.

---

## 4. Módulos (30 Total)

### 4.1 Interfaces (2)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `interface.main` | Node.js | Interface CLI, lee stdin, emite comandos |
| `interface.telegram` | Node.js | Bot de Telegram, recibe mensajes, envía respuestas |

### 4.2 Core - Procesamiento y Verificación (8)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `planner.main` | Node.js | Transforma comandos en planes |
| `agent.main` | Node.js | Interpreta intención y enriquece planes |
| `router.main` | Node.js | Enruta acciones a workers apropiados |
| `safety.guard.main` | Node.js | Política de allow/confirm/block |
| `approval.main` | Node.js | Circuito de aprobaciones |
| `supervisor.main` | Node.js | Cierre formal y respuesta al usuario |
| `phase.engine.main` | Node.js | Motor de fases del sistema |
| `verifier.engine.main` | Node.js | Verificación de resultados antes del cierre |

### 4.3 Core - Memoria y Estado (4)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `memory.log.main` | Node.js | Persistencia y consultas de memoria |
| `memory.menu.main` | Node.js | Menú de memoria para Telegram |
| `apps.session.main` | Node.js | Sesiones de aplicaciones |
| `ui.state.main` | Node.js | Estado de UI |

### 4.4 Workers Python (4)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `worker.python.desktop` | Python | Control de apps y ventanas |
| `worker.python.terminal` | Python | Comandos de terminal |
| `worker.python.system` | Python | Búsqueda de archivos y métricas |
| `worker.python.browser` | Python | Navegación web con Playwright |

**Capacidades confirmadas:**
- **Desktop**: `open_application`, `focus_window`, `echo_text`
- **Terminal**: `terminal.write_command`, `terminal.show_command`
- **System**: `search_file`, `monitor_resources`
- **Browser**: `open_url`, `search`, `click`, `fill_form`

### 4.5 IA - Inteligencia Artificial (5)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `ai.assistant.main` | Python | Asistente LLaMA local vía Ollama CLI |
| `ai.intent.main` | Node.js | Análisis de intenciones mejorado con IA |
| `ai.memory.semantic.main` | Python | Memoria con embeddings (128D) |
| `ai.self.audit.main` | Python | Auto-análisis del proyecto |
| `ai.learning.engine.main` | Python | Aprendizaje continuo del usuario |

**Capacidades de IA:**
- **LLaMA local**: Via Ollama CLI (`ollama run llama3.2`)
- **Timeout configurable**: 10-45s según acción
- **Actions soportadas**:
  - `ai.query`: Consultas generales (40s timeout)
  - `ai.analyze_intent`: Análisis de intenciones (20s)
  - `ai.generate_code`: Generación de código (40s)
  - `ai.explain_error`: Explicación de errores (25s)
  - `ai.analyze_project`: Análisis del proyecto (45s)
  - `ai.learn`: Aprendizaje de comandos
  - `ai.get_preferences`: Obtener preferencias
  - `ai.predict`: Predicción de acciones
  - `ai.clear_history`: Limpiar historial

### 4.6 UI y Mensajería Telegram (5)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `telegram.commands.main` | Node.js | Comandos de Telegram (/memoria, etc.) |
| `telegram.send.main` | Node.js | Envío de mensajes a Telegram |
| `telegram.hud.main` | Node.js | HUD de estado en Telegram |
| `telegram.menu.main` | Node.js | Menú principal interactivo |
| `system.menu.main` | Node.js | Menú de acciones del sistema |

### 4.7 Extensión (2)

| Módulo | Lenguaje | Propósito |
|--------|----------|-----------|
| `project.audit.main` | Node.js | Auditoría del proyecto |
| `gamification.main` | Node.js | Sistema de logros y puntos |

---

> **Nota**: Los flujos de esta sección representan la **lógica operativa canónica** del sistema. Cuando haya diferencias entre el árbol físico del proyecto y estos flujos, debe priorizarse la lectura operativa/canónica definida aquí y en los documentos de contratos.

## 5. Flujo Detallado de Mensajes

### 5.1 Flujo Principal de Comando

```text
1. Usuario escribe comando en CLI o Telegram
2. `interface.*` emite `command.out` 
3. `planner.main` recibe en `command.in` y emite `plan.out` 
4. `agent.main` recibe en `plan.in`, enriquece el plan y emite `plan.out` 
5. `safety.guard.main` valida el plan
6. Si el plan requiere aprobación, `approval.main` decide y emite `approved.plan.out` 
7. `router.main` recibe el plan aprobado y enruta a `worker.python.*:action.in` 
8. El worker ejecuta y emite:
   - `result.out` → `[verifier.engine.main:result.in]` → `supervisor.main:result.in` 
   - `event.out` → `memory.log.main:event.in` 
   - `event.out` → `ui.state.main:event.in` 
9. `supervisor.main` realiza el cierre formal
10. `supervisor.main` emite:
    - `response.out` → `interface.*:response.in` 
    - `event.out` → observadores internos
```

### 5.2 Flujo de IA

```text
1. `router.main` detecta una acción `ai.*` 
2. Emite a `ai.assistant.main:ai.action.in` 
3. `ai.assistant.main`:
   - verifica si Ollama está disponible
   - inicia watchdog (heartbeats cada 3s)
   - ejecuta la query con timeout
   - emite eventos de progreso
4. `ai.assistant.main` emite:
   - `result.out` → `[verifier.engine.main:result.in]` → `supervisor.main:result.in` 
   - `event.out` → `memory.log.main:event.in` 
   - `event.out` → `ui.state.main:event.in` 
5. `supervisor.main` realiza el cierre formal y emite:
   - `response.out` → `interface.*:response.in` 
   - `event.out` → observadores internos
```

### 5.3 Fases del Phase Engine

| Fase | Descripción |
|------|-------------|
| `idle` | Esperando comando |
| `processing` | Procesando intención/query |
| `responding` | Recibiendo respuesta de IA/worker |
| `completed` | Operación exitosa |
| `error` | Error en operación |

---

## 6. Persistencia

### 6.1 Archivos en `logs/`

| Archivo | Contenido |
|---------|-----------|
| `session-memory.json` | Memoria de sesión (últimos comandos, apps, búsquedas) |
| `events.log` | Trazas de eventos del sistema |
| `apps-session.json` | Estado de sesiones de aplicaciones |
| `desktop-apps.json` | Aplicaciones de desktop conocidas |
| `telegram-hud-state.json` | Estado del HUD de Telegram |
| `user-learning.json` | Preferencias y patrones de usuario |

### 6.2 Memoria de Sesión

La memoria sobrevive reinicios cargando `logs/session-memory.json` al inicio.

**Datos almacenados:**
- Último comando
- Última app abierta
- Última búsqueda de archivo
- Último estado del sistema
- Última respuesta
- Memoria semántica con embeddings (128D)

---

## 7. Configuración

### 7.1 Requisitos

- **Node.js**: 20+
- **Python**: 3.11+ (3.12 recomendado)
- **Linux** con herramientas de desktop:
  - `xdotool`
  - `wmctrl`
- **Playwright** para browser automation:
  - `pip install playwright`
  - `playwright install chromium`

### 7.2 Variables de Entorno

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Opcional | Habilita `interface.telegram` |

### 7.3 Instalación

```bash
# 1. Dependencias Node
npm install

# 2. Entorno Python
python3 -m venv .venv
source .venv/bin/activate

# 3. Dependencias Python
pip install -r requirements.txt

# 4. Browser Playwright
playwright install chromium
```

### 7.4 Ejecución

```bash
# Iniciar runtime
npm start

# Debug mode
npm run start:debug

# Verificar salud
npm run health

# Ver logs en vivo
npm run logs
```

---

## 8. Tests

### 8.1 Suite de Tests

| Comando | Descripción |
|---------|-------------|
| `npm run test:all` | Todos los tests (Node + Python + Smoke + Health) |
| `npm run test:node` | Valida sintaxis de `runtime/*.js` y `modules/*/main.js` |
| `npm run test:py` | Unittest en `tests/` |
| `npm run smoke` | Smoke test del runtime |
| `npm run health` | Verificación de salud del sistema |

### 8.2 Tests Python (`tests/`)

- `test_blueprint.py`: Valida que módulos del blueprint existan, que conexiones referencien módulos/puertos válidos
- `test_workers.py`: Tests de workers Python
- `smoke_runtime.py`: Test de smoke del runtime

### 8.3 Estructura de Tests

```python
# test_blueprint.py valida:
- Blueprint JSON carga correctamente
- Módulos en blueprint existen y tienen manifest
- No hay módulos huérfanos (con manifest pero no en blueprint)
- Conexiones referencian módulos existentes
- Puertos en conexiones están declarados en inputs/outputs
```

---

## 9. Scripts npm

| Script | Función |
|--------|---------|
| `npm start` | Inicia el runtime |
| `npm run start:debug` | Inicia con DEBUG=1 |
| `npm run explain` | Ejecuta project_explainer.py |
| `npm run health` | Verificación de salud |
| `npm run health:watch` | Health check cada 5s |
| `npm run check:node` | Chequeo de sintaxis JS |
| `npm run check:py` | Chequeo de sintaxis Python |
| `npm run test:node` | Tests de sintaxis Node |
| `npm run test:py` | Tests Python unittest |
| `npm run smoke` | Smoke test |
| `npm run test:all` | Suite completa |
| `npm run setup` | Script de setup |
| `npm run verify` | Verificación completa |
| `npm run status` | Alias de health |
| `npm run logs` | Tail de logs |
| `npm run clean` | Limpia cachés y logs |

---

## 10. Decisiones de Diseño Cerradas

No reabrir salvo bug real o necesidad fuerte:

- ✅ No rehacer arquitectura
- ✅ No simplificar a monolito
- ✅ Mantener runtime + blueprint + manifests + router + workers
- ✅ No introducir imports directos entre módulos
- ✅ JSON Lines sobre stdin/stdout
- ✅ Node.js para orquestación, Python para workers

---

## 11. Estado Actual

### 11.1 Versión

- **Versión**: 1.0.0 + AI Extension
- **Estado**: Base funcional + Capacidades de IA integradas
- **Módulos totales**: 30

### 11.2 Capacidades Implementadas

- ✅ Comandos CLI y Telegram coexisten
- ✅ Automatización desktop (apps, terminal)
- ✅ Acciones de sistema (búsqueda, métricas)
- ✅ Browser automation (Playwright)
- ✅ Memoria de sesión persistente
- ✅ IA local con LLaMA/Ollama
- ✅ Análisis de intenciones
- ✅ Memoria semántica con embeddings
- ✅ Auto-análisis del proyecto
- ✅ Aprendizaje continuo del usuario
- ✅ Sistema de fases (phase engine)
- ✅ Verificación de resultados
- ✅ Gamificación

### 11.3 Roadmap de IA

**Implementado ✅**
- Integración LLaMA local via Ollama CLI
- Memoria semántica con embeddings (128D)
- Auto-análisis de código y arquitectura
- Aprendizaje continuo del usuario
- Predicción de acciones
- Atajos automáticos

**En Desarrollo 🚧**
- Razonamiento multi-paso para tareas complejas
- Planificación automática de workflows
- Chat conversacional con memoria de largo plazo
- Integración con más modelos (Claude, GPT-4)

**Futuro 🔮**
- Visión por computadora (VLM)
- Generación automática de código para nuevos módulos
- Auto-optimización del blueprint
- Agentes especializados autónomos

---

## 12. Convenciones

### 12.1 Código

- No imports cruzados entre módulos
- Toda comunicación por puertos declarados
- Mensajería JSON Lines
- Módulos nuevos requieren:
  1. `modules/<nuevo>/manifest.json`
  2. `modules/<nuevo>/main.js|main.py`
  3. Conexiones en `blueprints/system.v0.json`

### 12.2 Estilo

- Node.js: ES modules (`"type": "module"` en package.json)
- Python: Type hints opcionales, manejo de excepciones explícito
- Format: consistente, sin comentarios de documentación a menos que se soliciten

---

## 13. Contacto y Recursos

- **Docs**: `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`
- **Explainer**: `python3 project_explainer.py`
- **Health Check**: `python3 health_check.py`

---

*Documentación generada para blueprint-v0 - Sistema de Agente Modular*
