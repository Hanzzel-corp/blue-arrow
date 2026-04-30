# AI Capabilities Documentation - Blue Arrow

## 🧠 Capacidades de Inteligencia Artificial

Este documento describe las nuevas capacidades de IA integradas en blueprint-v0.

---

## 📦 Módulos de IA

### 1. `ai.assistant.main` - Asistente Inteligente

**Propósito**: Integración con LLaMA para asistencia conversacional y análisis.

**Capacidades**:
- **Conversación natural** con modelo LLaMA local (vía Ollama)
- **Análisis de intenciones** mejorado con IA
- **Generación de código** automática
- **Explicación de errores** con sugerencias
- **Análisis de proyecto** con sugerencias de mejora

**Acciones disponibles**:

| Acción | Descripción | Parámetros |
|--------|-------------|------------|
| `ai.query` | Consulta general a LLaMA | `prompt`, `system_prompt`, `temperature` |
| `ai.analyze_intent` | Analiza intención del usuario | `text` |
| `ai.generate_code` | Genera código | `description`, `language` |
| `ai.explain_error` | Explica errores | `error`, `context` |
| `ai.analyze_project` | Analiza el proyecto | - |
| `ai.clear_history` | Limpia historial | - |

**Ejemplo de uso**:
```json
{
  "action": "ai.query",
  "params": {
    "prompt": "¿Cómo puedo optimizar este código?",
    "temperature": 0.7
  }
}
```

---

### 2. `ai.memory.semantic.main` - Memoria Semántica

**Propósito**: Almacenar y recuperar información contextual usando embeddings.

**Capacidades**:
- **Búsqueda semántica** de información previa
- **Embeddings** locales (128 dimensiones)
- **Recuperación contextual** para conversaciones
- **Memoria de corto y largo plazo**

**Acciones disponibles**:

| Acción | Descripción | Parámetros |
|--------|-------------|------------|
| `memory.store` | Almacena recuerdo | `content`, `type`, `metadata`, `importance` |
| `memory.search` | Busca recuerdos similares | `query`, `top_k`, `threshold` |
| `memory.context` | Obtiene contexto relevante | `query`, `max_items` |
| `memory.recent` | Recuerdos recientes | `type`, `limit` |
| `memory.forget` | Olvida recuerdo específico | `memory_id` |
| `memory.stats` | Estadísticas de memoria | - |
| `memory.clear` | Limpia toda la memoria | - |

**Ejemplo de uso**:
```json
{
  "action": "memory.store",
  "params": {
    "content": "El usuario prefiere abrir aplicaciones con 'abrir' en lugar de 'ejecutar'",
    "type": "preference",
    "importance": 0.9
  }
}
```

---

### 3. `ai.self.audit.main` - Auto-Análisis

**Propósito**: Análisis automático del código y arquitectura del proyecto.

**Capacidades**:
- **Análisis estático de código** (Python y JavaScript)
- **Verificación de consistencia del blueprint**
- **Detección de issues** (líneas largas, docstrings faltantes, etc.)
- **Score de salud** del proyecto
- **Sugerencias automáticas** de mejora

**Acciones disponibles**:

| Acción | Descripción | Parámetros |
|--------|-------------|------------|
| `audit.run` | Auditoría completa | - |
| `audit.quick` | Auditoría rápida | - |
| `audit.code` | Solo análisis de código | - |
| `audit.architecture` | Solo arquitectura | - |
| `audit.health` | Score de salud | - |

**Tipos de issues detectadas**:
- Funciones sin docstrings
- Líneas >100 caracteres
- `console.log` olvidados
- Errores de sintaxis
- Inconsistencias en blueprint

**Ejemplo de resultado**:
```json
{
  "health_score": 85,
  "total_issues": 12,
  "critical_issues": 0,
  "architecture_consistent": true,
  "suggestions": [
    "Agregar docstrings a 8 funciones",
    "Reformatear 4 líneas largas"
  ]
}
```

---

### 4. `ai.learning.engine.main` - Motor de Aprendizaje

**Propósito**: Aprender de las interacciones y adaptarse al usuario.

**Capacidades**:
- **Aprendizaje de patrones** de uso
- **Predicción de acciones** basada en historial
- **Atajos automáticos** para comandos frecuentes
- **Preferencias del usuario** adaptativas
- **Correcciones aprendidas**

**Acciones disponibles**:

| Acción | Descripción | Parámetros |
|--------|-------------|------------|
| `learn.interaction` | Aprende de interacción | `command`, `action_name`, `result`, `context` |
| `learn.correction` | Aprende de corrección | `original`, `corrected`, `reason` |
| `learn.preference` | Aprende preferencia | `key`, `value`, `confidence` |
| `learn.predict` | Predice mejor acción | `command`, `context` |
| `learn.suggestions` | Sugerencias personalizadas | - |
| `learn.shortcuts` | Atajos aprendidos | - |
| `learn.stats` | Estadísticas de aprendizaje | - |
| `learn.reset` | Resetear aprendizaje | `confirm: "YES_RESET_ALL"` |

**Ejemplo de predicción**:
```json
{
  "success": true,
  "predicted_action": "open_application",
  "confidence": 0.85,
  "based_on": 12,
  "suggested": true
}
```

---

## 🚀 Instalación y Configuración

### Prerrequisitos

1. **Ollama** - Motor de LLaMA local
   ```bash
   # Instalar ollama (Linux)
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Descargar modelo llama3.2
   ollama pull llama3.2
   ```

2. **Dependencias Python**
   ```bash
   pip install -r requirements.txt
   ```

### Configuración

Las variables de entorno opcionales:

```bash
export OLLAMA_MODEL="llama3.2"  # Modelo a usar
export OLLAMA_URL="http://localhost:11434"  # URL de ollama
```

---

## 🔄 Flujo de Integración

```
┌─────────────────┐
│  User Command   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  ai.analyze     │────▶│  ai.memory       │
│   _intent       │     │  (contexto previo)│
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  ai.learning    │────▶│  ai.assistant    │
│   (predicción)  │     │  (si es necesario)│
└────────┬────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐
│   Ejecución     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  ai.learning    │────▶│  ai.memory       │
│   (aprende)     │     │  (almacena)      │
└─────────────────┘     └──────────────────┘
```

---

## 📝 Ejemplos de Uso

### 1. Consultar a la IA

```bash
# Vía interfaz
Pregúntale a la IA: ¿Qué es la arquitectura modular?

# Resultado: Respuesta generada por LLaMA
```

### 2. Análisis de Intención Mejorado

```bash
# Comando ambiguo
Abrir algo para escribir

# IA analiza y determina:
# - Intención: open_application
# - Aplicación sugerida: editor de texto
# - Confianza: 0.85
```

### 3. Memoria Contextual

```bash
# Primera interacción
El usuario: "Prefiero usar Firefox en lugar de Chrome"

# Segunda interacción
Abrir navegador

# IA recuerda y abre Firefox automáticamente
```

### 4. Auto-Corrección

```bash
# Usuario ejecuta
Ejecutar terminal

# Sistema responde
¿Quisiste decir "Abrir terminal"?

# Usuario confirma
Sí

# IA aprende la preferencia por "abrir" vs "ejecutar"
```

### 5. Auditoría Automática

```bash
# Ejecutar auditoría
Auditar proyecto

# Resultado
Health Score: 87/100
Issues encontradas: 5
- 3 funciones sin docstrings
- 2 líneas largas
Sugerencias generadas: 4
```

---

## 📊 Métricas y Observabilidad

Cada módulo de IA emite eventos y métricas:

- **Eventos de aprendizaje**: Cuándo y qué se aprendió
- **Consultas IA**: Tiempos de respuesta, tokens usados
- **Memoria**: Hit rate de recuperación contextual
- **Auditorías**: Health score histórico

Los logs se almacenan en `logs/` con trazabilidad completa.

---

## 🔒 Consideraciones de Seguridad

1. **LLaMA local**: Todo el procesamiento de IA ocurre localmente
2. **Sin datos en la nube**: No se envía información a servicios externos
3. **Memoria privada**: Los datos de aprendizaje son locales
4. **Aprobación explícita**: Acciones críticas requieren aprobación del usuario

---

## 🛠️ Desarrollo y Extensión

### Agregar Nueva Capacidad de IA

1. Crear módulo en `modules/ai-[nombre]/`
2. Implementar `main.py` con interfaz JSON Lines
3. Crear `manifest.json` con puertos y configuración
4. Agregar al blueprint `blueprints/system.v0.json`
5. Documentar en este archivo

### Personalizar Modelo LLaMA

Editar `config` en `manifest.json`:

```json
{
  "config": {
    "model": "codellama",  // O cualquier modelo de ollama
    "temperature": 0.5,
    "max_tokens": 2048
  }
}
```

---

## 📈 Roadmap de IA

### Completado ✅
- [x] Integración LLaMA local
- [x] Memoria semántica con embeddings
- [x] Auto-análisis de proyecto
- [x] Aprendizaje continuo del usuario

### En Desarrollo 🚧
- [ ] Razonamiento multi-paso para tareas complejas
- [ ] Planificación automática de workflows
- [ ] Chat conversacional con memoria de largo plazo
- [ ] Integración con más modelos (Claude, GPT-4, etc.)

### Futuro 🔮
- [ ] Visión por computadora (VLM)
- [ ] Generación automática de código para nuevos módulos
- [ ] Auto-optimización del blueprint
- [ ] Agentes especializados autónomos

---

## 📞 Soporte

Para problemas con capacidades de IA:

1. Verificar que ollama está corriendo: `ollama list`
2. Revisar logs en `logs/events.log`
3. Verificar conectividad: `curl http://localhost:11434`

---

**Versión**: 1.0.0  
**Actualizado**: 2026-04-12  
**Módulos IA**: 5 módulos (assistant, intent, memory.semantic, learning, self.audit)
