# Blue Arrow

<p align="center">
  <img src="https://img.shields.io/badge/Node.js-20+-green?style=flat-square&logo=node.js" />
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/Architecture-Modular-purple?style=flat-square" />
  <img src="https://img.shields.io/badge/AI-LLaMA_Integration-orange?style=flat-square" />
  <img src="https://img.shields.io/badge/Gamification-RPG_Style-gold?style=flat-square" />
  <img src="https://github.com/Hanzzel-corp/blue-arrow/workflows/CI/badge.svg" alt="CI" />
</p>

## English Summary

Blue Arrow is an open-source local orchestration framework that lets users control desktop, terminal, browser, system and document actions through Telegram.

It is built around a human-in-the-loop execution model: AI can assist, interpret and plan, but real actions are routed through safety checks, approval flows, workers and execution verification.

### Why it matters

Most automation agents move toward uncontrolled autonomy. Blue Arrow takes the opposite path: the human remains the final decision-maker, while the system provides structured execution, local-first AI integration and verifiable action results.

**Key features:**
- Local-first automation (Ollama/LLaMA)
- Telegram interface with human approval
- Safety guards and execution verification
- Modular event-driven architecture
- RPG-style gamification system

📖 **[Full English Documentation → README_EN.md](README_EN.md)**

---

## Resumen en Español

**Blue Arrow** es un sistema de orquestación modular que automatiza acciones en PC mediante una arquitectura basada en **blueprint** + **runtime** + **modules**. El sistema evoluciona desde un modelo token-based hacia una plataforma state-driven con verificación de ejecución, IA integrada y experiencia de usuario tipo videojuego RPG.

### Dirección Arquitectónica: Migración hacia State-Driven

> **Estado:** Transición en curso. El sistema actual combina elementos del modelo token-based (legado) con el nuevo modelo state-driven (objetivo).

```
MODELO ACTUAL (Token-based):            MODELO OBJETIVO (State-driven):
texto → tokens → intención → acción    señal → estado → transición → acción → nuevo_estado
  ↓       ↓        ↓         ↓            ↓        ↓          ↓          ↓            ↓
"abrir  [abrir]  open_app  ejecutar    user    idle      planning   open_app    executing
 Chrome"                                    ↓           ↓              ↓
                                       executing  verifying    completed
```

**La diferencia clave:** En lugar de interpretar texto ambiguo, el sistema procesa señales estructuradas en contexto de estado (determinista, verificable).

---

## 🏗️ Arquitectura del Sistema

### Componentes Principales

| Componente | Tecnología | Responsabilidad |
|------------|------------|-----------------|
| **Runtime** | Node.js 20+ | Orquestación, enrutamiento, gestión de procesos |
| **Modules** | Node.js / Python 3.11+ | 30 módulos especializados por dominio |
| **Blueprint** | JSON Declarativo | Topología de conexiones entre módulos |
| **Bus** | JSON Lines | Mensajería inter-procesos por stdin/stdout |
| **Phase Engine** | State Machine | Coordinación state-driven de ejecución |
| **Verifier Engine** | Python | Verificación post-ejecución con confidence scores |
| **Office Writer** | Node.js | Automatización de LibreOffice Writer con IA |
| **Flow Inspector** | Python | Análisis CLI de conexiones del sistema |

### Flujo de Ejecución Objetivo State-Driven

```
┌─────────┐    user_command     ┌─────────────┐    intent_confirmed     ┌───────────┐
│  IDLE   │────────────────────►│   INTENT    │────────────────────────►│ PLANNING  │
└────┬────┘                     │  DETECTED   │                         └─────┬─────┘
     ▲                          └─────────────┘                               │
     │                                                                        │ plan_ready
     │                                                                        ▼
┌────┴────┐    reset/new_command    ┌─────────────┐    approved        ┌───────────┐
│COMPLETED│◄─────────────────────────│  APPROVAL   │◄───────────────────│APPROVED   │
└─────────┘                          │   PENDING   │                      │ (ready)   │
                                     └─────────────┘                      └─────┬─────┘
                                                                                  │ execute
┌─────────┐    verified           ┌───────────┐    worker_result          ┌────────▼───┐
│ VERIFY  │◄──────────────────────│ EXECUTING │◄─────────────────────────│  WORKERS   │
└────┬────┘                       └───────────┘                          └────────────┘
     │
     │ verification_complete
     ▼
┌─────────┐
│COMPLETED│
└────┬────┘
     │ success
     ▼
┌─────────┐
│  IDLE   │◄──────────────────────────────────────────────────────────────────────┘
└─────────┘
```

---

## ✨ Características Principales

### 🤖 Sistema de IA Integrado

| Módulo | Capacidad principal | Descripción |
|--------|---------------------|-------------|
| `ai.assistant.main` | **LLaMA local** | Conversación natural, generación de código, explicación de errores y análisis general |
| `ai.intent.main` | **Análisis de intenciones** | Interpretación semántica de comandos y clasificación de intención |
| `ai.memory.semantic.main` | **Memoria vectorial** | Embeddings locales, búsqueda semántica y recuperación de contexto |
| `ai.self.audit.main` | **Auto-análisis** | Auditoría estática de código y verificación de consistencia arquitectónica |
| `ai.learning.engine.main` | **Aprendizaje adaptativo** | Patrones de uso, predicción de acciones y correcciones aprendidas |

**Ejemplo de uso del Asistente IA:**
```json
{
  "action": "ai.query",
  "params": {
    "prompt": "¿Cómo puedo optimizar este código?",
    "system_prompt": "Eres un experto en optimización Python",
    "temperature": 0.7
  }
}
```

### ✅ Execution Verifier Engine

Sistema de verificación post-ejecución que calcula **confidence scores** basados en evidencia concreta:

```json
{
  "_verification": {
    "version": "1.0",
    "level": "window_confirmed",
    "confidence": 0.95,
    "executive_state": "success_verified",
    "evidence": {
      "process_detected": true,
      "pid": 12345,
      "window_detected": true,
      "window_id": "0x04200001",
      "focus_confirmed": true,
      "verification_method": "wmctrl_xdotool"
    },
    "signals": [
      {"name": "process_detected", "present": true, "weight": 0.25, "contribution": 0.25},
      {"name": "window_detected", "present": true, "weight": 0.35, "contribution": 0.35},
      {"name": "focus_confirmed", "present": true, "weight": 0.15, "contribution": 0.15}
    ]
  }
}
```

**Niveles de Verificación:**
- `window_confirmed` (≥90% confidence) - Ventana detectada y enfocada
- `window_detected` (≥75%) - Ventana detectada
- `process_only` (≥50%) - Solo proceso detectado
- `signal_confirmed` (≥25%) - Señal de éxito

### 📝 Office Writer Automation

Automatización de **LibreOffice Writer** con redacción asistida por IA local:

**Flujo simplificado:**
```
Usuario: "abrir writer y escribir una carta"
   ↓
Office Writer Module → Worker Desktop (abrir)
   ↓
Consulta a ai.assistant.main (generar texto)
   ↓
Worker Desktop (escribir) → UI Telegram: "✅ Documento listo"
```

**Funcionalidades:**
- 🖊️ Abrir Writer automáticamente
- 🤖 Redacción con LLaMA local
- 📝 Escritura automática de texto
- 🔄 Flujo orquestado con gestión de sesión

---

### 🎮 Sistema de Gamificación RPG

Transforma la interfaz de Telegram en una experiencia tipo videojuego:

**Sistema de Niveles y XP:**
- Fórmula: `nivel = √(XP / 100) + 1`
- 20 niveles con iconos de rango (🎮 → 🏆)
- XP por comandos ejecutados, streaks y logros desbloqueados

**Logros Disponibles:**
| Logro | Descripción | XP | Rareza |
|-------|-------------|-----|--------|
| 🎯 Primeros Pasos | Ejecuta tu primer comando | 50 | Común |
| 💻 Maestro Terminal | 10 comandos en terminal | 150 | Raro |
| 🔥 Usuario Power | 50 acciones exitosas | 500 | Épico |
| ⭐ Mago del Sistema | Nivel 10 alcanzado | 1,000 | Legendario |

**Diseño Visual RPG:**
```
╔══════════════════════════════════════╗
║  🎮 JARVIS RPG v1.0                 ║
╠══════════════════════════════════════╣
║ ⭐ Nivel 5 ⭐⭐⭐                     ║
║ XP: [██████░░░░] 60%                ║
║ HP: [████████░░] 80%                ║
╚══════════════════════════════════════╝
```

**Escenas Temáticas:**
- 🏰 BASE PRINCIPAL - Menú principal
- ⚔️ BATALLA EN PAUSA - Aprobaciones pendientes
- ⚔️ EN COMBATE - Ejecución de tareas
- 🌐 EXPLORANDO - Navegación web

---

## 🛡️ Resiliencia y Seguridad

### Clasificación Core vs Satélite

| Tipo | Módulos | Impacto de Fallo |
|------|---------|-------------------|
| **🔴 Core** | interface, planner, agent, safety, router, supervisor, workers, memory | Sistema down o degradado críticamente |
| **🛰️ Satélite** | gamification, ai.assistant, menus, verifier, phase.engine | Features reducidas, flujo principal intacto |

### Perfiles de Ejecución

```json
// Minimal - Solo esencial para headless
["interface.main", "planner.main", "agent.main", "safety.guard.main",
 "router.main", "supervisor.main", "worker.python.*", "memory.log.main"]

// Standard - Uso diario con UI
[...minimal, "interface.telegram", "approval.main", "ui.state.main"]

// Full - Experiencia completa con IA y gamificación
[...standard, "gamification.main", "ai.*", "telegram.menu.main",
 "guide.main", "phase.engine.main", "verifier.engine.main"]
```

### Sistemas de Resiliencia

| Sistema | Descripción |
|---------|-------------|
| **Graceful Shutdown** | Cierre ordenado de módulos ante SIGINT/SIGTERM |
| **Auto-restart** | Reinicio automático con backoff (máx 3 intentos) |
| **Backpressure** | Control de flujo para prevenir OOM en buffers |
| **Circuit Breaker** | Protección contra patrones de fallo persistentes |
| **Health Checks** | Monitoreo de recursos, dependencias y módulos |
| **Contract Versioning** | Versionado semántico de contratos de mensajes |

---

## 📦 Estructura del Proyecto

> **Nota:** El árbol muestra **nombres de carpetas físicas** (algunas con wildcards `*`) y sus IDs lógicos aproximados. Los nombres canónicos reales de módulos están en los documentos de contratos (`PORT_CONTRACTS.md`).

```
blueprint-v0/
├── 📁 blueprints/
│   └── system.v0.json          # Topología: 30 módulos, 100+ conexiones
│
├── 📁 runtime/
│   ├── main.js                 # Orquestador principal
│   ├── bus.js                  # Message bus con backpressure
│   ├── registry.js             # Descubrimiento de módulos
│   ├── tier_manager.js         # Gestión Core/Satélite
│   ├── contract_enforcer.js    # Validación de contratos
│   └── logger.js               # Logging estructurado
│
├── 📁 modules/
│   ├── 📁 agent/               # Interpretación de intenciones
│   ├── 📁 ai-*/                # 5 módulos de IA
│   ├── 📁 approval/            # Circuito de aprobaciones
│   ├── 📁 gamification/         # Sistema RPG
│   ├── 📁 guide/               # Guía contextual
│   ├── 📁 interface/            # CLI y Telegram
│   ├── 📁 memory-*/            # Persistencia y estado
│   ├── 📁 office.writer.main/   # Automatización LibreOffice Writer
│   ├── 📁 phase-engine/         # State machine engine
│   ├── 📁 planner/             # Planificación de tareas
│   ├── 📁 project-audit/        # Auditoría de proyecto
│   ├── 📁 router/              # Enrutamiento de acciones
│   ├── 📁 safety-guard/         # Validación de seguridad
│   ├── 📁 supervisor/           # Ciclo de vida de tareas
│   ├── 📁 telegram-*/           # UI de Telegram (menus, HUD)
│   ├── 📁 ui-state/            # Gestión de estado UI
│   ├── 📁 verifier-engine/      # Verificación post-ejecución
│   └── 📁 worker-*/            # 4 workers especializados
│
├── 📁 lib/
│   ├── execution_verifier.py   # Helper de verificación
│   └── logger.py               # Logger estructurado Python
│
├── 📁 docs/
│   ├── ARCHITECTURE.md         # Arquitectura del sistema
│   ├── AI_CAPABILITIES.md      # Documentación de IA
│   ├── GAMIFICATION.md         # Sistema RPG
│   ├── PHASE_ENGINE_DESIGN.md  # Diseño state-driven
│   ├── execution-verifier-design.md  # Verificación
│   ├── IMPROVEMENTS_GUIDE.md   # Guía de mejoras
│   └── MODULE_CLASSIFICATION.md # Core vs Satélite
│
├── blueprint_flow_inspector.py # Análisis CLI de conexiones
├── 📁 logs/                    # Eventos y persistencia
├── 📁 tests/                   # Tests unitarios e integración
└── 📁 config/                  # Configuración del sistema
```

---

## 🚀 Instalación Rápida

### Requisitos

- **Node.js** 20+ (recomendado 20.12+)
- **Python** 3.11+ (recomendado 3.12)
- **Linux** con herramientas de desktop:
  - `xdotool` - Control de ventanas
  - `wmctrl` - Gestión de ventanas
  - `psutil` - Métricas de sistema
- **Playwright** (opcional para browser):
  ```bash
  pip install playwright
  playwright install chromium
  ```

### Setup Automático

```bash
# Clonar repositorio
git clone https://github.com/Hanzzel-corp/blue-arrow.git
cd blue-arrow

# Ejecutar setup automático
npm run setup
# o
python3 setup.py

# O instalación manual:
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuración

```bash
# Variables de entorno esenciales
export TELEGRAM_BOT_TOKEN="123456:ABCDEF..."
export BOOTSTRAP_PROFILE="full"  # minimal | standard | full
export LOG_LEVEL="info"          # error | warn | info | debug | trace

# Opcional: Configurar Ollama para IA
export OLLAMA_HOST="http://localhost:11434"
```

> **Para setup detallado:** Ver `DEVELOPMENT.md`  
> **Para IA local/Ollama:** Ver `OLLAMA_SETUP.md`  
> **Variables mínimas:** Ver `.env.example` para variables requeridas

---

## 🎮 Uso del Sistema

### Iniciar el Sistema

```bash
# Modo normal
npm start

# Con debug
npm run start:debug

# Perfil específico
BOOTSTRAP_PROFILE=minimal npm start
```

### Health Checks

```bash
# Verificación única
npm run health

# Monitoreo continuo
npm run health:watch

# Salida JSON
python3 health_check.py --json
```

### Comandos de Usuario

| Comando | Descripción |
|-----------|-------------|
| `abrir chrome` | Abre aplicación con verificación |
| `buscar archivo.pdf` | Búsqueda en filesystem |
| `navegar a github.com` | Browser automation |
| `ejecutar ls -la` | Terminal automation |
| `mi perfil` | Ver progreso RPG |
| `mis logros` | Logros desbloqueados |
| `auditar proyecto` | Análisis estático |
| `analizar con ia` | Consulta a LLaMA |
| `abrir writer y escribir una carta` | Office Writer Automation |

### 🕸️ Blueprint Flow Inspector

Herramienta CLI para analizar y visualizar las conexiones del sistema:

```bash
# Ver resumen del sistema
python3 blueprint_flow_inspector.py docs/system-architecture-diagram.md summary

# Trace desde un módulo
python3 blueprint_flow_inspector.py docs/system-architecture-diagram.md trace --direction from --module router.main --depth 3

# Camino más corto entre módulos
python3 blueprint_flow_inspector.py docs/system-architecture-diagram.md path --from-module interface.telegram --to-module worker.python.desktop

# Reporte detallado de un módulo
python3 blueprint_flow_inspector.py docs/system-architecture-diagram.md module --module office.writer.main

# Escenarios de dataops predefinidos
python3 blueprint_flow_inspector.py docs/system-architecture-diagram.md dataops
```

**Capacidades:**
- 📊 **Resumen del grafo:** módulos totales, conexiones, fan-in/fan-out
- 🔍 **Tracing:** seguimiento de flujos por categoría (command, event, result)
- 🛤️ **Shortest path:** rutas entre cualquier par de módulos
- 📈 **DataOps paths:** escenarios predefinidos como office_writer_roundtrip

---

### Menú de Telegram

Interfaz RPG interactiva con botones:
- 🏰 **Menú Principal** - Stats y navegación
- ⚔️ **Apps** - Aplicaciones disponibles
- 🌐 **Web** - Navegación web
- ⚙️ **Sistema** - Comandos de sistema
- 💭 **Memoria** - Gestión de memoria
- 🏆 **Logros** - Colección de logros

---

## 🧪 Testing

```bash
# Todos los tests
npm run test:all

# Tests Node.js
npm run test:node

# Tests Python
npm run test:py

# Verificación de sintaxis
npm run check:node
npm run check:py

# Tests con pytest (requiere requirements-dev.txt)
python3 -m pytest tests/ -v
```

---

## 📊 Métricas y Observabilidad

### Logs Estructurados

```json
{
  "timestamp": "2026-04-12T20:30:00Z",
  "level": "INFO",
  "module": "runtime.bus",
  "message": "Módulo iniciado",
  "trace_id": "uuid-único",
  "meta": {
    "pid": 12345,
    "tier": "core",
    "restart_count": 0
  }
}
```

### Archivos de Estado

| Archivo | Contenido |
|---------|-----------|
| `logs/events.log` | Eventos del sistema |
| `logs/session-memory.json` | Memoria de sesión |
| `logs/gamification.json` | Progreso RPG por usuario |
| `logs/phase-engine-state.json` | Estado de la máquina de estados |
| `logs/verifier-results.json` | Resultados de verificación |

---

## 📖 Documentación

### 🏆 Fuentes de Verdad (Canonical)

Documentos maestros de arquitectura y contratos:

- **[DOCUMENTATION_HIERARCHY.md](docs/DOCUMENTATION_HIERARCHY.md)** - Jerarquía canónica de documentos
- **[PROJECT_DESCRIPTION.md](docs/PROJECT_DESCRIPTION.md)** - Descripción general del proyecto
- **[PORT_CONTRACTS.md](docs/PORT_CONTRACTS.md)** - Contratos de puertos y mensajes v2
- **[PORT_TYPES.md](docs/PORT_TYPES.md)** - Tipos de puertos y separación semántica
- **[CONTRACTS_GUIDE.md](docs/CONTRACTS_GUIDE.md)** - Guía del contrato de mensajes v2

### 📊 Visión General y Estado

Overview y arquitectura actual del sistema:

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Arquitectura modular general
- **[PHASE_ENGINE_SUMMARY.md](docs/PHASE_ENGINE_SUMMARY.md)** - Estado actual de la migración state-driven

### 📋 Guías Operativas

Guías para uso y operación del sistema:

- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Setup local y desarrollo
- **[OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md)** - Configuración de IA local
- **[EXECUTION_PROFILES.md](docs/EXECUTION_PROFILES.md)** - Perfiles de ejecución (minimal/standard/full)
- **[TASK_CLOSURE_GOVERNANCE.md](docs/TASK_CLOSURE_GOVERNANCE.md)** - Gobierno de cierre de tareas
- **[GAMIFICATION.md](docs/GAMIFICATION.md)** - Sistema RPG completo
- **[BLUEPRINT_FLOW_INSPECTOR.md](docs/BLUEPRINT_FLOW_INSPECTOR.md)** - Análisis CLI de arquitectura

### 🎯 Diseño / Arquitectura Objetivo

Documentos de diseño técnico (arquitectura objetivo/migración futura):

- **[PHASE_ENGINE_DESIGN.md](docs/PHASE_ENGINE_DESIGN.md)** - Especificación state-driven objetivo
- **[EXECUTION_VERIFIER_DESIGN.md](docs/execution-verifier-design.md)** - Diseño del verificador
- **[RUNTIME_FIXES_DESIGN.md](docs/RUNTIME_FIXES_DESIGN.md)** - Fixes de runtime
- **[CONCEPTUAL_IMPROVEMENTS.md](docs/CONCEPTUAL_IMPROVEMENTS.md)** - Mejoras conceptuales futuras

---

## 🛠️ Desarrollo

### Agregar un Nuevo Módulo

1. Crear directorio en `modules/<nombre-modulo>/`
2. Crear `manifest.json`:
```json
{
  "id": "nombre.modulo",
  "name": "Mi Módulo",
  "version": "1.0.0",
  "language": "node",
  "entry": "main.js",
  "tier": "satellite",
  "priority": "medium",
  "inputs": ["command.in", "event.in"],
  "outputs": ["result.out", "event.out"]
}
```
3. Implementar `main.js` o `main.py`
4. Agregar conexiones en `blueprints/system.v0.json`

### Convenciones

- ✅ Usar puertos semánticos (`command.in`, `result.out`, `event.out`)
- ✅ Enriquecer mensajes con `trace_id` y `meta`
- ✅ No imports cruzados entre módulos
- ✅ Toda comunicación por puertos declarados
- ✅ Logs estructurados con niveles

---

## 📈 Roadmap

### Base Integrada ✅

- [x] Arquitectura modular con 30 módulos
- [x] Base de migración hacia arquitectura state-driven
- [x] Execution Verifier Engine integrado
- [x] Capacidades IA base con LLaMA local
- [x] Memoria semántica con embeddings
- [x] Sistema de gamificación RPG
- [x] Clasificación Core/Satélite
- [x] Graceful shutdown y auto-restart
- [x] Backpressure y circuit breaker
- [x] Health checks integrados
- [x] Perfiles de ejecución (minimal/standard/full)
- [x] UI Telegram con menús interactivos
- [x] Office Writer Automation con IA
- [x] Blueprint Flow Inspector para análisis de conexiones

### En Progreso 🚧

- [ ] Event Sourcing nativo
- [ ] CQRS para comandos/queries
- [ ] Streaming de respuestas IA
- [ ] Vector store integrado
- [ ] Misiones diarias en gamificación
- [ ] Auto-scaling de workers

### Futuro 🔮

- [ ] Pub/Sub semántico
- [ ] Message broker con persistencia
- [ ] Distributed tracing
- [ ] Metrics dashboard
- [ ] Plugin system

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crear rama feature: `git checkout -b feature/nueva-feature`
3. Commit cambios: `git commit -am 'Agregar nueva feature'`
4. Push a la rama: `git push origin feature/nueva-feature`
5. Crear Pull Request

---

## 📜 Licencia

MIT License - ver [LICENSE](LICENSE) para detalles.

---

<p align="center">
  <b>Blue Arrow</b> - Orquestación modular con migración state-driven en curso<br>
  <sub>Construido con ❤️ usando Node.js, Python y mucha cafeína</sub>
</p>
