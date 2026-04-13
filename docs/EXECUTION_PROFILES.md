# Perfiles de Ejecución

## Overview

Los perfiles de ejecución permiten configurar el sistema con diferentes conjuntos de módulos según el caso de uso, optimizando recursos y reduciendo ruido en debugging.

## Perfiles Disponibles

### 🔴 Minimal

**Descripción**: Core esencial únicamente. Para headless/scripting sin UI.

**Casos de uso**:
- Scripts automatizados
- Servicios headless
- CI/CD pipelines
- Recuperación de emergencia
- Debugging de core

**Módulos incluidos**: 10 módulos

🔴 **Core Absoluto** (siempre presente):
- `interface.main` - CLI básico
- `planner.main` - Planificación
- `agent.main` - Orquestación
- `safety.guard.main` - Seguridad
- `router.main` - Enrutamiento
- `supervisor.main` - Gestión de tareas
- `worker.python.desktop` - Ejecución desktop
- `worker.python.system` - Ejecución sistema
- `memory.log.main` - Persistencia básica

🟠 **Core con comportamiento especial**:
- `approval.main` - Aprobaciones (en headless, rechaza sin UI)

> **⚠️ Política canónica de approval.main en Minimal**:
> En modo headless/scripting, `approval.main` **no puede esperar UI interactiva**.
>
> **Comportamiento por defecto**: **Auto-rechazar**
> - Acciones que requieren aprobación se rechazan automáticamente
> - Se retorna error al usuario: "Acción requiere aprobación pero UI no disponible"
>
> **Variantes futuras posibles** (requieren configuración explícita):
> - **Bypass**: `safety.guard.main` configura políticas para auto-aprobar acciones de bajo riesgo
> - **CLI approval**: `interface.main` muestra prompt de aprobación en terminal (solo si hay TTY)

**Módulos excluidos** (Core Interactivo):
- Todos los satellites (AI, gamification)
- Interfaces Telegram
- Menús
- Verificador de ejecución
- UI avanzada

**Límites de recursos**:
- Memoria máxima: 512 MB
- CPU máximo: 50%

**Uso**:
```bash
BOOTSTRAP_PROFILE=minimal npm start
```

---

### 🟡 Standard

**Descripción**: Core completo + interfaces + persistencia. Uso diario sin IA.

**Casos de uso**:
- Uso interactivo diario
- Automatización con UI
- Sistema sin dependencias de IA
- Recursos limitados
- Entornos de producción

**Módulos incluidos**: ~19 módulos

🔴 **Core Absoluto** (los 10 de minimal):
- Todo el perfil minimal

🟠 **Core Interactivo** (modo UI):
- `interface.telegram` - Bot Telegram
- `telegram.hud.main` - HUD Telegram
- `telegram.menu.main` - Menú Telegram
- `worker.python.terminal` - Terminal
- `worker.python.browser` - Navegador
- `ui.state.main` - Estado UI
- `guide.main` - Guía de usuario
- `apps.session.main` - Gestión de apps
- `verifier.engine.main` - Verificación

🟡 **Satellites (excluidos en Standard)**:
- AI assistants
- AI learning
- Gamification

> Estos módulos **solo** están disponibles en el perfil **Full**.

**Límites de recursos**:
- Memoria máxima: 1024 MB
- CPU máximo: 70%

**Uso**:
```bash
BOOTSTRAP_PROFILE=standard npm start
# O por defecto
npm start
```

---

### 🟢 Full

**Descripción**: Todos los módulos incluyendo IA y gamificación.

**Casos de uso**:
- Desarrollo y testing
- Demo completa
- Sistema con IA asistida
- Gamification activa
- Enriquecimiento con AI

**Módulos incluidos**: Todos los disponibles (31 módulos)
- Todo el perfil standard, más:
- `ai.assistant.main` - Asistente IA
- `ai.intent.main` - Detección de intenciones
- `ai.learning.engine.main` - Aprendizaje
- `ai.memory.semantic.main` - Memoria semántica
- `ai.self.audit.main` - Auto-auditoría
- `gamification.main` - Sistema RPG/XP
- `system.menu.main` - Menú sistema
- `apps.menu.main` - Menú apps
- `memory.menu.main` - Menú memoria
- `project.audit.main` - Auditoría proyecto

**Módulos excluidos**: Ninguno

**Límites de recursos**:
- Memoria máxima: 2048 MB
- CPU máximo: 90%

**Requisitos adicionales**:
- Ollama para IA local (opcional)

**Uso**:
```bash
BOOTSTRAP_PROFILE=full npm start
```

---

## Comparación

| Aspecto | Minimal | Standard | Full |
|---------|---------|----------|------|
| Módulos | ~10 | ~19 | ~31 |
| Memoria | 512 MB | 1024 MB | 2048 MB |
| CPU | 50% | 70% | 90% |
| UI | CLI | CLI + Telegram | Completa |
| IA | ❌ | ❌ | ✅ |
| Gamification | ❌ | ❌ | ✅ |
| Debug | Fácil | Moderado | Complejo |
| Tiempo arranque | ~3s | ~8s | ~15s |

## Selección Automática por Entorno

El sistema puede seleccionar automáticamente el perfil según el entorno:

```bash
# Desarrollo local → full
NODE_ENV=development npm start

# Staging/Testing → standard  
NODE_ENV=staging npm start

# Producción → standard
NODE_ENV=production npm start

# CI/CD → minimal
NODE_ENV=ci npm start
```

## Configuración

Los perfiles se definen en `config/profiles.json`:

```json
{
  "profiles": {
    "minimal": {
      "modules": ["supervisor.main", "router.main", ...],
      "excluded_categories": ["satellite", "ai", "gamification"]
    },
    "standard": {
      "modules": [...],
      "excluded_categories": ["ai", "gamification"]
    },
    "full": {
      "modules": null,  // Todos
      "excluded_categories": []
    }
  }
}
```

## Health Checks por Perfil

### Minimal
- **Críticos**: supervisor, router, agent
- **Opcionales**: interface

### Standard
- **Críticos**: supervisor, router, agent, planner
- **Opcionales**: telegram, menus

### Full
- **Críticos**: supervisor, router, agent, planner
- **Opcionales**: AI, gamification, todos los menús

## Orden de Arranque

Cada perfil define un orden de fases:

1. **Phase 1**: Core crítico (supervisor, router)
2. **Phase 2**: Core funcional (agent, planner, safety)
3. **Phase 3**: Workers
4. **Phase 4**: Interfaces
5. **Phase 5**: Menús y utilities
6. **Phase 6**: Satellites lazy (solo full)

## Políticas de Restart

| Tier | Minimal | Standard | Full |
|------|---------|----------|------|
| Critical Core | Inmediato (1s) | Inmediato (1s) | Inmediato (1s) |
| Core | Inmediato (3s) | Inmediato (3s) | Inmediato (3s) |
| Satellite | N/A | Lazy (10s) | Lazy (10s) |
| Optional | N/A | On-demand | On-demand |

## Ejemplos de Uso

### Script Automatizado
```bash
# Minimal para script headless
BOOTSTRAP_PROFILE=minimal node runtime/main.js < script.txt
```

### Bot de Producción
```bash
# Standard sin IA
BOOTSTRAP_PROFILE=standard TELEGRAM_BOT_TOKEN=xxx npm start
```

### Desarrollo con IA
```bash
# Full con todas las capacidades
BOOTSTRAP_PROFILE=full npm start
```

### Recuperación de Emergencia
```bash
# Minimal si algo rompe el perfil standard
BOOTSTRAP_PROFILE=minimal npm start
```

## Migración entre Perfiles

Para cambiar de perfil en caliente:

```bash
# 1. Detener actual
Ctrl+C

# 2. Iniciar nuevo perfil
BOOTSTRAP_PROFILE=minimal npm start
```

**Nota**: No se soporta cambio de perfil sin reinicio. Cada perfil carga un conjunto diferente de módulos.

## Troubleshooting

### Problema: Standard/Full lento
**Solución**: Usar minimal para debugging:
```bash
BOOTSTRAP_PROFILE=minimal npm start
```

### Problema: Falta funcionalidad en minimal
**Solución**: Migrar a standard:
```bash
BOOTSTRAP_PROFILE=standard npm start
```

### Problema: AI no responde
**Verificar**:
1. Perfil es `full`
2. Ollama está corriendo
3. Logs de `ai.assistant.main`

## Referencias

- Configuración: `config/profiles.json`
- Implementación: `runtime/tier_manager.js`
- Documentación ADR: `docs/ARCHITECTURE_DECISION_LOG.json`
