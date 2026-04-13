# Interfaces - Documentación

## 🖥️ Interfaces de Usuario

<p align="center">
  <b>Módulos de entrada/salida que conectan al sistema con los usuarios</b>
</p>

---

## Visión General

Las **interfaces** son los puntos de entrada del sistema. Reciben comandos de usuario, los transforman al formato interno, y muestran resultados.

### ⚠️ Formatos de Documentación

Este documento usa **dos niveles de ejemplos**:

| Nivel | Uso | Ubicación |
|-------|-----|-----------|
| **Formato Conceptual** | Para entender la lógica de negocio | Ejemplos tempranos en cada sección |
| **Contrato Real del Bus** | Para implementar contra el bus JSON Lines | Sección "Formatos de Mensaje" |

> **🔴 IMPORTANTE**: Si vas a implementar un módulo, usa el **Contrato Real del Bus** (con `module`, `port`, `trace_id`, `meta`, `payload`). Los ejemplos conceptuales son solo para comprensión humana.

### Tipos de Interfaces

| Interfaz | Propósito | Tecnología |
|-----------|-----------|------------|
| `interface.main` | CLI local | Node.js + readline |
| `interface.telegram` | Bot de Telegram | Node.js + node-telegram-bot-api |

### Rol en el Sistema

```
┌─────────────────────────────────────────────────────────┐
│                    FLUJO INTERFACES                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────┐         command.out          ┌────────┐ │
│  │ interface   │ ─────────────────────────────▶│planner │ │
│  │             │                               │        │ │
│  │  - CLI      │◀──────────────────────────────│super   │ │
│  │  - Telegram │         response.in           │visor  │ │
│  └─────────────┘                               └────────┘ │
│       ▲                                                  │
│       │         callbacks (aprobaciones)                 │
│       └──────────────────────────────────────────────────┘
│                                                          │
│  NOTA: La respuesta final viene del supervisor.main      │
│  El planner NO devuelve directamente a la interface      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Interface CLI

### Responsabilidades

- Leer comandos desde terminal
- Mostrar resultados en consola
- Soporte para modo interactivo y batch

### Comandos Soportados

```
> abrir firefox
> buscar archivo.pdf
> ejecutar ls -la
> ayuda
> salir
```

### Salida: `command.out` (Formato Conceptual)

> 📋 **Ejemplo simplificado** (para comprensión lógica):

```json
{
  "command_id": "cmd_123",
  "text": "abrir firefox",
  "source": "cli",
  "user_id": "local",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

### Entrada: `response.in` (Formato Conceptual)

> 📋 **Ejemplo simplificado**:

```json
{
  "text": "✅ Firefox abierto",
  "type": "success",
  "trace_id": "abc-123"
}
```

---

## Interface Telegram

### Responsabilidades

- Recibir mensajes de usuarios vía bot
- Mostrar menús interactivos
- Botones de aprobación
- HUD con estado del sistema

### Características

| Feature | Descripción |
|---------|-------------|
| **Menús** | Botones inline para acciones comunes |
| **Aprobaciones** | Botones [✅ Sí] [❌ No] |
| **HUD** | Estado visual con barras de progreso |
| **Gamificación** | XP, niveles, logros visuales |

### Flujo de Mensaje

```
Usuario envía: "abrir firefox"
         │
         ▼
┌─────────────────┐
│ Telegram API    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ interface.telegram│
│ - Parse message  │
│ - Extract chat_id│
└────────┬────────┘
         │
         ▼
    command.out
         │
         ▼
    planner.main
```

### Salida: `command.out` (Formato Conceptual)

> 📋 **Ejemplo simplificado**:

```json
{
  "command_id": "cmd_456",
  "text": "abrir firefox",
  "source": "telegram",
  "chat_id": 1781005414,
  "user_id": "user_789",
  "username": "@usuario",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

### Entrada: `response.in` (Formato Conceptual)

> 📋 **Ejemplo simplificado**:

```json
{
  "text": "✅ Firefox abierto y verificado",
  "chat_id": 1781005414,
  "type": "success",
  "keyboard": null,
  "trace_id": "abc-123"
}
```

### Mensajes con Botones

**Solicitud de Aprobación**:
```json
{
  "text": "⚠️ ¿Eliminar archivos?",
  "chat_id": 1781005414,
  "keyboard": {
    "inline_keyboard": [
      [{"text": "✅ Sí", "callback_data": "approve_123"}],
      [{"text": "❌ No", "callback_data": "reject_123"}]
    ]
  }
}
```

---

## Formatos de Mensaje

### 🔴 CONTRATO REAL DEL BUS (para implementación)

> **Esta sección muestra el formato exacto que debe usarse al implementar módulos.**
> 
> El bus usa JSON Lines con: `module`, `port`, `trace_id`, `meta`, `payload`

#### Entrada al Sistema (command.out)

```json
{
  "module": "interface.telegram",
  "port": "command.out",
  "trace_id": "cmd_123_trace",
  "meta": {
    "source": "telegram",
    "chat_id": 1781005414,
    "timestamp": "2026-01-01T00:00:00Z"
  },
  "payload": {
    "command_id": "cmd_123",
    "text": "abrir firefox",
    "source": "telegram",
    "chat_id": 1781005414,
    "user_id": "user_789"
  }
}
```

### Salida del Sistema (response.in)

> **📌 Origen**: `supervisor.main:response.out` (no del planner)

> La respuesta final al usuario la emite el **supervisor.main**, que es quien:
> - Recibe `result.out` de workers/verifier
> - Decide el estado final de la tarea
> - Construye el mensaje para el usuario
> - Emite `response.out` a la interfaz

```json
{
  "module": "interface.telegram",
  "port": "response.in",
  "trace_id": "task_123_trace",
  "meta": {
    "source": "supervisor.main",
    "timestamp": "2026-01-01T00:00:05Z"
  },
  "payload": {
    "text": "✅ Firefox abierto",
    "chat_id": 1781005414,
    "type": "success",
    "task_id": "task_123"
  }
}
```

---

## Menús de Telegram

### Canales de Callbacks y Aprobaciones

La interfaz Telegram tiene un **canal especial** para manejar respuestas de usuario en flujos de aprobación:

```
┌─────────────────────────────────────────────────────────────┐
│              FLUJO DE APROBACIÓN VIA TELEGRAM              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. approval.main emite approval.request.out                │
│     (observado por ui.state / interface.telegram)           │
│                                                              │
│  2. interface.telegram muestra botones [✅ Sí] [❌ No]        │
│                                                              │
│  3. Usuario presiona botón → callback.in                    │
│                                                              │
│  4. interface.telegram emite approval.response.in         │
│     hacia approval.main (respuesta directa)                   │
│     callback.out para notificación de interacción          │
│                                                              │
│  5. approval.main decide: plan.out → router (aprobar)     │
│     o response.out → supervisor (rechazar)                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Puertos específicos para aprobaciones**:

| Puerto | Dirección | Descripción |
|--------|-----------|-------------|
| `callback.in` | Entrada | Botones inline presionados por usuario |
| `approval.response.in` | Salida | **Canal canónico** - Respuesta aprobación/rechazo |
| `callback.out` | Salida | Notificación de interacción (secundario) |

### Menú Principal (RPG)

```
╔══════════════════════════════════════╗
║  🎮 JARVIS RPG v1.0                 ║
╠══════════════════════════════════════╣
║ ⭐ Nivel 5 ⭐⭐⭐                     ║
║ XP: [██████░░░░] 60%                ║
╚══════════════════════════════════════╝

[🏰 Menú Principal] [⚔️ Apps]
[🌐 Web] [⚙️ Sistema]
[💭 Memoria] [🏆 Logros]
```

### Categorías de Menús

| Menú | Módulo | Descripción |
|------|--------|-------------|
| Principal | `telegram.menu.main` | Navegación principal |
| Apps | `apps.menu.main` | Aplicaciones disponibles |
| Web | - | Navegación web |
| Sistema | `system.menu.main` | Comandos de sistema |
| Memoria | `memory.menu.main` | Gestión de memoria |

---

## Configuración

### Interface Telegram

```json
{
  "id": "interface.telegram",
  "name": "Telegram Bot Interface",
  "tier": "core",
  "priority": "medium",
  "inputs": [
    "response.in",
    "callback.in",
    "approval.response.in"
  ],
  "outputs": [
    "command.out",
    "event.out",
    "callback.out"
  ],
  "config": {
    "telegram_token_env": "TELEGRAM_BOT_TOKEN",
    "allowed_chats": [],
    "admin_users": [],
    "features": {
      "menus": true,
      "gamification": true,
      "inline_buttons": true
    }
  }
}
```

### Interface CLI

```json
{
  "id": "interface.main",
  "name": "CLI Interface",
  "tier": "core",
  "priority": "high",
  "inputs": ["response.in"],
  "outputs": ["command.out", "event.out"],
  "config": {
    "prompt": "jarvis> ",
    "history_file": ".jarvis_history",
    "colors": true
  }
}
```

---

## Ejemplos

### Ejemplo 1: Comando CLI

```
jarvis> abrir firefox

✅ Firefox abierto y verificado
Proceso: 12345
Ventana: 0x04200001
Confianza: 95%
```

### Ejemplo 2: Interacción Telegram

**Usuario**: "abrir chrome"

**Bot**:
```
⏳ Procesando...

✅ Chrome abierto y verificado
[Nivel 6 - 85%]
+15 XP
```

### Ejemplo 3: Aprobación vía Botones

**Bot**: "⚠️ ¿Eliminar 5 archivos?"
```
[✅ Sí, eliminar] [❌ No, cancelar]
```

**Usuario**: Toca "✅ Sí, eliminar"

**Bot**: "✅ Archivos eliminados"

---

## Referencias

- **[GAMIFICATION.md](GAMIFICATION.md)** - Sistema RPG
- **[PLANNER.md](PLANNER.md)** - Procesamiento de comandos
- **[SUPERVISOR.md](SUPERVISOR.md)** - Respuestas de tareas

---

<p align="center">
  <b>Interfaces v1.0.0</b><br>
  <sub>Puertas de entrada al sistema - Core interactivo</sub>
</p>
