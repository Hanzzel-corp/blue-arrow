# Jerarquía de Documentación

## 📚 Fuentes Oficiales de Verdad

<p align="center">
  <b>Este documento establece qué documentos son fuente canónica para cada aspecto del sistema</b>
</p>

---

## 🎯 Principio Fundamental

> **Solo puede haber UNA fuente de verdad por tema.**
> 
> Cuando hay conflictos, este documento determina cuál prevalece.

---

## 📊 Jerarquía de Fuentes

### 🔴 Nivel 1: Fuentes Canónicas (Oráculos)

**Si hay conflicto, estos documentos tienen razón.**

| Tema | Fuente Oficial | Documento | Razón |
|------|----------------|-----------|-------|
| **Contrato de Mensajes** | Fuente Única | [PORT_CONTRACTS.md](PORT_CONTRACTS.md) | Define `module`, `port`, `trace_id`, `meta`, `payload` |
| **Flujo de Cierre** | Fuente Única | [TASK_CLOSURE_GOVERNANCE.md](TASK_CLOSURE_GOVERNANCE.md) | Define roles: CLOSER, INFORMER, VERIFIER, OBSERVER |
| **Clasificación Core/Satélite** | Fuente Única | [MODULE_CLASSIFICATION.md](MODULE_CLASSIFICATION.md) | Define qué es esencial vs opcional |
| **Wiring/Flujo Operativo** | Fuente Única | [ARCHITECTURE.md](ARCHITECTURE.md) | Define el flujo end-to-end del sistema |
| **Tipos de Puerto** | Fuente Única | [PORT_TYPES.md](PORT_TYPES.md) | Define separación ejecución/observación |
| **Perfiles de Ejecución** | Fuente Única | [EXECUTION_PROFILES.md](EXECUTION_PROFILES.md) | Define minimal/standard/full |

### 🟠 Nivel 2: Referencia de Módulos

**Documentación específica por módulo.**

| Módulo | Documento | Estado |
|--------|-----------|--------|
| `router.main` | [ROUTER.md](ROUTER.md) | 🔄 En revisión |
| `planner.main` | [PLANNER.md](PLANNER.md) | ✅ Canónico (simplificado) |
| `supervisor.main` | [SUPERVISOR.md](SUPERVISOR.md) | ✅ Canónico |
| `agent.main` | [AGENT.md](AGENT.md) | ✅ Canónico |
| `approval.main` | [APPROVAL.md](APPROVAL.md) | ✅ Canónico |
| `safety.guard.main` | [SAFETY_GUARD.md](SAFETY_GUARD.md) | ✅ Canónico |
| `workers` | [WORKERS.md](WORKERS.md) | 🔄 En revisión |
| `interface.*` | [INTERFACES.md](INTERFACES.md) | 🔄 En revisión |

> **Nota**: ARCHITECTURE.md está en Nivel 1 (Fuentes Canónicas) y se encuentra pendiente de actualización.

### 🟡 Nivel 3: Guías y Sistemas Especializados

**Documentación de subsistemas.**

| Sistema | Documento | Notas |
|---------|-----------|-------|
| IA | [AI_CAPABILITIES.md](AI_CAPABILITIES.md) | Capacidades, no implementación |
| Gamificación | [GAMIFICATION.md](GAMIFICATION.md) | Sistema RPG completo |
| Phase Engine | [PHASE_ENGINE_DESIGN.md](PHASE_ENGINE_DESIGN.md) | Diseño state-driven |
| Verifier | [execution-verifier-design.md](execution-verifier-design.md) | Verificación post-ejecución |
| Office Writer | [OFFICE_WRITER.md](OFFICE_WRITER.md) | Orquestador específico |

### 🟢 Nivel 4: Anexos y Contexto

**Información complementaria.**

| Tipo | Documentos |
|------|------------|
| Historia/Evolución | PROJECT.md, PROJECT_STATUS.md |
| Mejoras Futuras | CONCEPTUAL_IMPROVEMENTS.md, IMPROVEMENTS_GUIDE.md |
| Setup | OLLAMA_SETUP.md, DEVELOPMENT.md |
| Resúmenes | AI_IMPLEMENTATION_SUMMARY.md, PHASE_ENGINE_SUMMARY.md |

---

## ⚖️ Reglas de Resolución de Conflictos

### Regla #1: Contrato vs Todo

**PORT_CONTRACTS.md** define el formato de mensaje.

```
Si otro documento muestra un mensaje diferente:
→ PORT_CONTRACTS.md tiene razón
→ El otro documento debe corregirse
```

### Regla #2: Cierre vs Todo

**TASK_CLOSURE_GOVERNANCE.md** define los roles de cierre.

```
Si un documento dice que X cierra tareas:
→ Verificar contra TASK_CLOSURE_GOVERNANCE.md
→ Solo supervisor.main es CLOSER
```

### Regla #3: Flujo vs Todo

**ARCHITECTURE.md** define el flujo operativo.

```
Flujo canónico:
interface → planner → agent → safety → [approval] → router → workers → [verifier] → supervisor

Si un documento muestra otra cadena:
→ ARCHITECTURE.md tiene razón

> **Nota**: El verifier es opcional. En perfiles minimal/standard puede ser:
> `workers → supervisor` directamente.
```

### Regla #4: Clasificación vs Todo

**MODULE_CLASSIFICATION.md** define qué es Core.

```
Si un perfil de ejecución excluye algo marcado como Core:
→ Verificar si es Core Absoluto o Core Interactivo
→ MODULE_CLASSIFICATION.md tiene razón
```

### Regla #5: Separación Ejecución/Observación

**PORT_TYPES.md** define la separación de flujos.

```
• result.out → Solo para cierre de tareas (supervisor)
• event.out → Para observadores (memory, UI, logs)

Si un documento mezcla result.out con observación:
→ PORT_TYPES.md tiene razón
→ Separar en result.out + event.out
```

---

## 🔄 Estados de Documentos

### Leyenda de Estados

| Símbolo | Estado | Significado |
|---------|--------|-------------|
| ✅ | Canónico | Alineado con fuentes de verdad |
| 🔄 | Corregido | Se aplicaron correcciones quirúrgicas |
| ⚠️ | Revisar | Puede tener inconsistencias menores |
| 📝 | Borrador | Documentación en progreso |
| 🗑️ | Obsoleto | No usar, mantener solo para historia |

### Estado Actual (2026-04-12)

| Documento | Estado | Notas |
|-----------|--------|-------|
| PORT_CONTRACTS.md | ✅ | Fuente de verdad del contrato |
| TASK_CLOSURE_GOVERNANCE.md | ✅ | Fuente de verdad del cierre |
| MODULE_CLASSIFICATION.md | ✅ | Core Absoluto vs Interactivo |
| ARCHITECTURE.md | ⚠️ | Revisar flujo/canales |
| ROUTER.md | 🔄 | En revisión |
| PLANNER.md | ✅ | Simplificado, sin complex workflows |
| SUPERVISOR.md | ✅ | Cierre único documentado |
| AGENT.md | ✅ | Corregido flujo, sin router directo |
| APPROVAL.md | ✅ | Ciclo de aprobaciones |
| SAFETY_GUARD.md | ✅ | Puertos semánticos corregidos |
| WORKERS.md | 🔄 | En revisión |
| INTERFACES.md | 🔄 | En revisión |
| EXECUTION_PROFILES.md | 🔄 | Revisar conteo core/interactivo |

---

## 📋 Checklist de Consistencia

Al crear/editar documentación, verificar:

- [ ] **Contrato**: ¿Los mensajes usan `module`, `port`, `trace_id`, `meta`, `payload`?
- [ ] **Cierre**: ¿Solo supervisor.main cierra tareas?
- [ ] **Flujo**: ¿La cadena termina en supervisor (via verifier)?
- [ ] **Roles**: ¿Workers son informers, no closers?
- [ ] **Core**: ¿Core Absoluto vs Core Interactivo diferenciado?
- [ ] **Nivel**: ¿Ejemplos conceptuales están claramente marcados?

---

## 🎯 Decisiones de Consolidación

### Decisiones Ejecutadas

1. ✅ **AGENT.md**: Quitada conexión directa a router
2. ✅ **PLANNER.md**: Quitados complex workflows, context.in, memory.out
3. ✅ **SAFETY_GUARD.md**: Puertos cambiados a `approved.plan.out`, `blocked.plan.out`
4. ✅ **INTERFACES.md**: Separado formato conceptual vs contrato real

### Decisiones Pendientes (Futuro)

1. **FUSIÓN**: PORT_CONTRACTS.md + CONTRACTS_GUIDE.md → un solo documento
2. **FUSIÓN**: PROJECT.md + PROJECT_STATUS.md → un solo documento de historia
3. **ARCHIVAR**: CONCEPTUAL_IMPROVEMENTS.md → mover a `/docs/roadmap/`
4. **REMOVER**: Duplicados de phase-engine (consolidar en un solo doc)

---

## 🏛️ Estructura Recomendada

```
docs/
├── 📁 00-canonical/              # FUENTES DE VERDAD
│   ├── PORT_CONTRACTS.md         # Contrato de mensajes
│   ├── TASK_CLOSURE_GOVERNANCE.md # Gobierno de cierre
│   ├── MODULE_CLASSIFICATION.md   # Core vs Satélite
│   ├── ARCHITECTURE.md           # Arquitectura general
│   └── EXECUTION_PROFILES.md     # Perfiles
│
├── 📁 01-modules/                # MÓDULOS INDIVIDUALES
│   ├── ROUTER.md
│   ├── PLANNER.md
│   ├── SUPERVISOR.md
│   ├── AGENT.md
│   ├── APPROVAL.md
│   ├── SAFETY_GUARD.md
│   ├── WORKERS.md
│   ├── INTERFACES.md
│   ├── OFFICE_WRITER.md
│   └── ...
│
├── 📁 02-subsystems/             # SUBSISTEMAS
│   ├── AI_CAPABILITIES.md
│   ├── GAMIFICATION.md
│   ├── PHASE_ENGINE_DESIGN.md
│   └── execution-verifier-design.md
│
├── 📁 03-guides/                 # GUÍAS
│   ├── IMPROVEMENTS_GUIDE.md
│   ├── OLLAMA_SETUP.md
│   └── DEVELOPMENT.md
│
└── 📁 04-archive/                # ARCHIVO/HISTORIA
    ├── CONCEPTUAL_IMPROVEMENTS.md
    ├── PROJECT.md
    └── PROJECT_STATUS.md
```

---

<p align="center">
  <b>Última actualización: 2026-04-12</b><br>
  <sub>Jerarquía establecida para consolidación documental</sub>
</p>
