# Sistema de Gamificación - Documentación

## 🎮 Interfaz RPG de Telegram

Este documento describe el sistema de gamificación implementado para hacer la interfaz de Telegram más divertida e interactiva, estilo videojuego RPG.

---

## 📋 Resumen

La interfaz de Telegram ha sido transformada en una experiencia tipo videojuego con:

- **Niveles y XP**: Sistema de progresión basado en acciones
- **Logros**: Coleccionables al completar tareas específicas
- **Barras de progreso**: Visuales tipo RPG con bloques █░
- **Menús temáticos**: Diseño de salones y torres estilo juego
- **Rachas**: Multiplicadores por acciones consecutivas exitosas

---

## 🏗️ Arquitectura

### Módulos Implementados

> **Nota:** Los nombres en **negrita** son IDs lógicos de módulos. Las carpetas físicas pueden diferir.

| Módulo (ID lógico) | Descripción | Implementación |
|-------------------|-------------|----------------|
| **gamification.main** | Sistema de niveles, XP y logros | Node.js Extension |
| **telegram.hud.main** | HUD con barras de vida/XP y escenas RPG | Node.js Extension |
| **telegram.menu.main** | Menús interactivos estilo juego | Node.js Extension |
| **interface.telegram** | Tracking de XP en comandos | Node.js Extension |

---

## 🎯 Sistema de Gamificación

### Niveles y XP

**Fórmula de Nivel**: `nivel = √(XP / 100) + 1`

| Nivel | XP Requerido | Rango | Icono |
|-------|-------------|-------|-------|
| 1 | 0 | Novato | 🎮 |
| 3 | 300 | Aprendiz | 🥉 |
| 5 | 900 | Usuario | 🥈 |
| 7 | 1,600 | Avanzado | 🥇 |
| 10 | 3,600 | Experto | ⭐ |
| 15 | 8,100 | Maestro | 👑 |
| 20 | 14,400 | Legendario | 🏆 |

### Ganancia de XP

| Acción | XP Base | Bonus |
|--------|---------|-------|
| Comando ejecutado | 10 | +5 si éxito |
| Streak 3+ acciones | +2 por streak | Máx +20 |
| Logro desbloqueado | Variable | 50-1000 XP |

---

## 🏆 Logros Disponibles

| Logro | Descripción | XP | Rareza |
|-------|-------------|-----|--------|
| 🎯 Primeros Pasos | Ejecuta tu primer comando | 50 | Común |
| 💻 Maestro Terminal | 10 comandos en terminal | 150 | Raro |
| 🚀 Abreapp | 5 aplicaciones abiertas | 100 | Común |
| 🏄 Surfer Web | 5 URLs navegadas | 120 | Común |
| 📂 Cazador de Archivos | 3 búsquedas de archivos | 80 | Común |
| 🧠 Explorador IA | 5 consultas a IA | 200 | Raro |
| 🔥 Usuario Power | 50 acciones exitosas | 500 | Épico |
| ⭐ Mago del Sistema | Nivel 10 alcanzado | 1,000 | Legendario |
| 📊 Auditor | Ejecutar auditoría | 150 | Raro |
| 💭 Maestro de Memoria | 10 usos de memoria | 200 | Raro |

---

## 🎨 Diseño Visual

### HUD (Head-Up Display)

El HUD muestra información tipo videojuego:

```
╔══════════════════════════════════════╗
║  🎮 JARVIS RPG v1.0               ║
╠══════════════════════════════════════╣
║ ⭐ Nivel 5 ⭐⭐⭐                     ║
║ XP: [██████░░░░] 60%                ║
║ HP: [████████░░] 80%                ║
╚══════════════════════════════════════╝
```

**Elementos**:
- 🎮 Nombre del "juego": JARVIS RPG v1.0
- ⭐ Nivel actual con icono de rango
- ████ Barras de progreso (10 bloques)
- HP basado en tasa de éxito de acciones

### Escenas RPG

| Escena | Título | Emoji | Descripción |
|--------|--------|-------|-------------|
| main | 🏰 BASE PRINCIPAL | Menú principal con stats |
| awaiting_approval | ⚔️ BATALLA EN PAUSA | Esperando decisión |
| task_running | ⚔️ EN COMBATE | Ejecutando tarea |
| web_active | 🌐 EXPLORANDO | Navegando web |
| app_active | 🎮 APP ACTIVA | App en uso |
| task_result | ✨ RESULTADO | Tarea completada |

### Menús Temáticos

**Menú Principal** (`🏰 MENÚ PRINCIPAL 🏰`):
```
⚔️ Apps    🌐 Web
⚙️ Sistema 💭 Memoria
🏆 Logros  📊 Estadísticas
⏳ Pendientes  🔍 Auditoría
❓ Ayuda
```

**Menú Web** (`🌐 ZONA WEB 🌐`):
```
🐙 GitHub    📺 YouTube
🔍 Google    🤖 ChatGPT
📧 Gmail     🦊 GitLab
⬅️ Volver al Menú
```

---

## 🎮 Navegación

### Botones Principales

| Botón | Acción | Icono |
|-------|--------|-------|
| Apps | Menú de aplicaciones | ⚔️ |
| Web | Navegación web | 🌐 |
| Sistema | Comandos de sistema | ⚙️ |
| Memoria | Gestión de memoria | 💭 |
| Logros | Ver logros | 🏆 |
| Stats | Estadísticas | 📊 |
| Pendientes | Aprobaciones | ⏳ |
| Auditoría | Auditar proyecto | 🔍 |
| Ayuda | Guía del jugador | ❓ |

### Flujo de Interacción

1. **Inicio**: Usuario abre Telegram → Ve HUD con su nivel/XP
2. **Menú**: Presiona "Menú Principal" → Navega opciones
3. **Acción**: Selecciona comando → Gana XP automáticamente
4. **Progreso**: Barra de XP avanza → Puede subir de nivel
5. **Logros**: Completar tareas desbloquea logros con bonus

---

## 📊 Estadísticas Trackeadas

El sistema guarda:

```json
{
  "commands_executed": 25,
  "apps_opened": 8,
  "urls_visited": 12,
  "files_searched": 5,
  "ai_queries": 10,
  "successful_actions": 42,
  "failed_actions": 3,
  "login_streak": 3
}
```

---

## 🔧 API del Sistema

### Acciones Disponibles

**game.track**: Registrar acción
```json
{
  "action": "game.track",
  "params": {
    "user_id": "123456",
    "action_type": "command",
    "success": true,
    "result": {...}
  }
}
```

**game.profile**: Obtener perfil
```json
{
  "action": "game.profile",
  "params": {"user_id": "123456"}
}
```

**game.xp**: Agregar XP manual
```json
{
  "action": "game.xp",
  "params": {
    "user_id": "123456",
    "amount": 50,
    "reason": "Bonus por logro"
  }
}
```

**game.leaderboard**: Tabla de clasificación
```json
{
  "action": "game.leaderboard",
  "params": {"limit": 10}
}
```

**game.achievements**: Ver logros
```json
{
  "action": "game.achievements",
  "params": {"user_id": "123456"}
}
```

---

## 💾 Persistencia

Los datos se guardan en:
- **Ruta**: `logs/gamification.json`
- **Formato**: JSON por usuario (key = chat_id)
- **Backup**: Automático en cada acción

Estructura:
```json
{
  "123456": {
    "user_id": "123456",
    "username": "Player_3456",
    "level": 5,
    "xp": 1450,
    "total_xp": 2450,
    "achievements": ["first_command", "app_opener"],
    "stats": {...},
    "created_at": "2026-04-13T12:00:00"
  }
}
```

---

## 🚀 Comandos de Usuario

### Consultar Progreso

```
mi perfil
mis estadísticas
mi progreso
```

### Ver Logros

```
mis logros
logros disponibles
```

### Leaderboard

```
ranking
leaderboard
tabla de clasificación
```

---

## 🎨 Personalización

### Cambiar Nombre de Usuario

```json
{
  "action": "game.update_username",
  "params": {
    "user_id": "123456",
    "username": "MiNuevoNombre"
  }
}
```

### Configuración Visual (Futuro)

- Temas de color para el HUD
- Iconos personalizados
- Sonidos de notificación (concepto)

---

## 🔒 Seguridad

- ✅ Datos locales (no en cloud)
- ✅ Por usuario (chat_id)
- ✅ Sin datos sensibles
- ✅ Reset disponible con confirmación

---

## 📈 Roadmap

### Completado ✅
- [x] Sistema de niveles y XP
- [x] Logros con bonus
- [x] HUD visual RPG
- [x] Menús temáticos
- [x] Tracking automático
- [x] Leaderboard

### Futuro 🚧
- [ ] Misiones diarias
- [ ] Eventos especiales (doble XP)
- [ ] Tienda virtual (skins, iconos)
- [ ] Logros ocultos
- [ ] Modo competencia PvP
- [ ] Integración con insignias reales

---

## 🎯 Ejemplos de Uso

### Escenario 1: Nuevo Usuario

1. Usuario envía: "Abrir terminal"
2. Sistema ejecuta comando
3. Gamificación otorga: +10 XP
4. HUD muestra: "Nivel 1 → 10/100 XP"
5. Desbloquea logro: 🎯 Primeros Pasos (+50 XP)

### Escenario 2: Subida de Nivel

1. Usuario ejecuta 10 comandos
2. Acumula 100+ XP
3. Sistema calcula: √(150/100) + 1 = Nivel 2
4. HUD anima: "⭐ SUBISTE DE NIVEL ⭐"
5. Bonus de racha: +20 XP extra

### Escenario 3: Uso de Menús

1. Usuario presiona: "🏰 Menú Principal"
2. Ve opciones con iconos RPG
3. Selecciona: "🏆 Logros"
4. Muestra progreso de colección
5. Navega a: "📊 Estadísticas"

---

## 📞 Soporte

Para problemas con gamificación:

1. Verificar `logs/gamification.json` existe
2. Revisar permisos de escritura
3. Consultar logs en `logs/events.log`
4. Reset opcional: `game.reset` con confirmación

---

**Versión**: 1.0.0  
**Fecha**: 2026-04-13  
**Estado**: ✅ Operativo
