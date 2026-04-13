# Clasificación de Módulos: Core vs Satélite

## Propósito

Definir qué módulos son **esenciales para el sistema** y cuáles son **opcionales/desactivables** sin afectar el flujo principal.

Esto permite:
- Saber qué priorizar en incidentes
- Definir perfiles de ejecución (minimal, standard, full)
- Entender el impacto real de fallos

---

## 🎯 Módulos Core

**Definición**: Sin estos, el sistema **no puede ejecutar comandos**.

Si falla un core → el sistema está **down** o **degradado críticamente**.

### 🔴 Core Absoluto (Sistema Base)

**Definición**: Core que debe estar presente en **todos los perfiles**, incluso en `minimal` headless.

| Módulo | Responsabilidad | Si falla... |
|--------|-----------------|-------------|
| `interface.main` | Entrada CLI | No hay entrada de comandos |
| `planner.main` | Planificación | No puede convertir comandos en planes |
| `agent.main` | Interpretación | No entiende intenciones |
| `safety.guard.main` | Validación | No puede aprobar/rechazar acciones |
| `approval.main` | Circuito de aprobación | Bloquea acciones que requieren confirm |
| `router.main` | Enrutamiento | No llegan acciones a workers |
| `supervisor.main` | Ciclo de vida | Tareas no se cierran, timeouts rotos |
| `worker.python.desktop` | Ejecución desktop | No abre apps ni controla ventanas |
| `worker.python.system` | Ejecución sistema | No busca archivos ni métricas |
| `memory.log.main` | Persistencia básica | Pierde memoria de sesión |

### 🟠 Core Interactivo (Modo UI)

**Definición**: Core necesario para el **modo interactivo**, pero opcional en perfiles headless (`minimal`).

| Módulo | Responsabilidad | Si falla... |
|--------|-----------------|-------------|
| `interface.telegram` | Entrada Telegram | Pierde canal secundario (graceful) |
| `ui.state.main` | Estado UI | Menús HUD no funcionan |
| `worker.python.terminal` | Terminal interactiva | No ejecuta comandos en terminal visible |
| `worker.python.browser` | Navegador | No puede navegar web |

**Nota**: Estos módulos son **core para el modo interactivo**, pero pueden excluirse del perfil `minimal` headless.

### Características Core

- **Restart agresivo**: Si crashean, se reinician inmediatamente
- **Monitoreo prioritario**: Health check los vigila primero
- **Core Absoluto**: Siempre activos en todos los perfiles
- **Core Interactivo**: Siempre activos en `standard` y `full`, opcionales en `minimal`

---

## 🛰️ Módulos Satélite

**Definición**: Mejoran la experiencia pero **no bloquean** el flujo principal.

Si falla un satélite → el sistema sigue, con menos features.

### Lista Satélite

| Módulo | Responsabilidad | Si falla... |
|--------|-----------------|-------------|
| `gamification.main` | Sistema RPG | Pierde XP/logros, pero todo funciona |
| `ai.learning.engine.main` | Aprendizaje | No aprende patrones, pero ejecuta |
| `ai.self.audit.main` | Auto-análisis | No audita, pero ejecuta |
| `ai.memory.semantic.main` | Embeddings | Búsqueda semántica falla, memoria básica sigue |
| `telegram.menu.main` | Menú Telegram | Botones desaparecen, comandos de texto siguen |
| `system.menu.main` | Menú sistema | Menú inline no aparece |
| `memory.menu.main` | Menú memoria | Consultas rápidas no disponibles |
| `apps.menu.main` | Menú apps | Listado de apps no disponible |
| `telegram.hud.main` | HUD visual | No hay barras de progreso, texto sigue |
| `ai.assistant.main` | LLaMA local | Consultas IA fallan, resto sigue |
| `guide.main` | Guía contextual | No explica, pero ejecuta |
| `phase.engine.main` | Fases de ejecución | Feature avanzada, flujo básico sigue |
| `verifier.engine.main` | Verificación | No verifica resultados, confía en workers |
| `apps.session.main` | Sesiones de apps | No trackea sesiones, apps siguen abriendo |
| `project.audit.main` | Auditoría proyecto | No audita, sistema sigue |

### Características Satélite

- **Desactivables**: Pueden excluirse de perfiles mínimos
- **Restart lazy**: Si crashean, pueden esperar o no reiniciarse
- **No críticos para health**: Health check puede ignorarlos
- **Pueden depender de core**: Un satélite sí puede depender de core

---

## 📊 Matriz de Impacto

| Fallo | Impacto en sistema | Usuario percibe |
|-------|-------------------|-----------------|
| Core: router.main | 🔴 Crítico | "No hace nada" |
| Core: safety.guard | 🔴 Crítico | "Se cuelga en aprobaciones" |
| Core: memory.log | 🟡 Degradado | "No recuerda" |
| Satélite: gamification | 🟢 Invisible | "No gano XP" |
| Satélite: ai.assistant | 🟢 Invisible | "No responde preguntas IA" |
| Satélite: telegram.menu | 🟢 Invisible | "No veo botones, escribo texto" |

---

## 🚀 Perfiles de Ejecución

### Minimal

Solo core esencial para ejecutar comandos básicos:

```json
{
  "profile": "minimal",
  "modules": [
    "interface.main",
    "planner.main",
    "agent.main",
    "safety.guard.main",
    "router.main",
    "supervisor.main",
    "worker.python.desktop",
    "worker.python.system",
    "memory.log.main"
  ]
}
```

**Uso**: Servidores headless, scripts de automatización, emergencias.

### Standard (default)

Core + interfaces + UI básica:

```json
{
  "profile": "standard",
  "modules": [
    // ...minimal
    "interface.telegram",
    "approval.main",
    "ui.state.main"
  ]
}
```

**Uso**: Uso diario normal.

### Full

Todo incluido:

```json
{
  "profile": "full",
  "modules": [
    // ...standard
    "gamification.main",
    "ai.assistant.main",
    "ai.learning.engine.main",
    "ai.memory.semantic.main",
    "ai.self.audit.main",
    "telegram.menu.main",
    "guide.main",
    "phase.engine.main",
    "verifier.engine.main"
  ]
}
```

**Uso**: Experiencia completa con IA y gamificación.

---

## 🔧 Implementación Técnica

### En manifest.json de cada módulo

```json
{
  "id": "gamification.main",
  "tier": "satellite",
  "priority": "low",
  "restart_policy": "on_demand",
  "dependencies": ["memory.log.main", "ui.state.main"]
}
```

```json
{
  "id": "router.main",
  "tier": "core",
  "priority": "critical",
  "restart_policy": "immediate",
  "dependencies": []
}
```

### En runtime

```javascript
// Al iniciar, separar tiers
const coreModules = modules.filter(m => m.manifest.tier === 'core');
const satelliteModules = modules.filter(m => m.manifest.tier === 'satellite');

// Iniciar core primero, con timeout agresivo
await Promise.all(coreModules.map(startWithTimeout(5000)));

// Luego satélites, pueden fallar silenciosamente
satelliteModules.forEach(m => startLazy(m));
```

### En health check

```python
def check_health():
    # Solo verificar core
    for mod in core_modules:
        if not is_healthy(mod):
            return CRITICAL

    # Satélites: loguear warning pero no fallar
    for mod in satellite_modules:
        if not is_healthy(mod):
            logger.warning(f"{mod.id} satélite no responde")

    return HEALTHY
```

---

## 🎨 Convención Visual

En documentación y diagramas:

- **Core**: Círculo sólido ● o cuadrado relleno ■
- **Satélite**: Círculo hueco ○ o cuadrado vacío □

En logs:

```
[CORE] router.main: action routed
[SAT] gamification.main: XP awarded
```

---

## Decisiones de Diseño

### ¿Por qué `memory.log` es core?

Aunque el sistema "funciona" sin memoria, la experiencia de usuario se degrada tanto (no recuerda contexto) que consideramos que el sistema no cumple su propósito sin memoria.

### ¿Por qué `ai.assistant` es satélite?

El sistema era funcional antes de la IA. La IA acompaña, no comanda.

### ¿Por qué `verifier.engine` es satélite?

Es una capa de confiabilidad adicional. El sistema confía en los workers por defecto; el verifier es extra.

---

## Referencias

- Auditoría de blueprint: `@lib/blueprint_auditor.py`
- Reglas de arquitectura: `@docs/ARCHITECTURE_RULES.md`
