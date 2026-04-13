# Mejoras Conceptuales - blueprint-v0

> **⚠️ DOCUMENTO DE EXPLORACIÓN FUTURA**
> 
> Este documento describe **líneas de evolución posibles** para la arquitectura de blueprint-v0. 
> - NO describe el estado actual del runtime
> - NO es canónico ni vinculante
> - Las ideas aquí presentadas (pub/sub semántico, message broker persistente, CQRS, etc.) son exploraciones conceptuales para futuras iteraciones
> - Para la documentación operativa actual, ver `PORT_CONTRACTS.md`, `TASK_CLOSURE_GOVERNANCE.md` y `DOCUMENTATION_HIERARCHY.md`

---

## Visión Arquitectónica de Próxima Generación

---

## 1. Arquitectura de Mensajes

### 1.1 De Conexiones Estáticas a Pub/Sub Semántico

**Concepto actual**: Blueprint JSON con conexiones punto-a-punto (`moduleA.port → moduleB.port`)

**Mejora conceptual**: Sistema pub/sub basado en tópicos semánticos

```
Actual:
  agent.main:plan.out → router.main:plan.in
  router.main:desktop.action.out → worker-python.main:action.in

Propuesto:
  agent.main publica: "plan.created"
  Suscriptores interesados en "plan.created" reciben el mensaje
  Router se suscribe a "plan.created" y "plan.requires_routing"
```

**Beneficios**:
- Desacoplamiento total entre productores y consumidores
- Módulos pueden aparecer/desaparecer sin reconfigurar el blueprint
- Múltiples consumidores para un mismo evento sin modificar el emisor
- Filtrado por patrones de tópico (`user.*.created`, `system.health.*`)

---

### 1.2 Message Broker con Persistencia

**Concepto actual**: Mensajes directos por stdin/stdout, sin persistencia

**Mejora conceptual**: Capa de mensajería con durabilidad

```
Capas propuestas:
  1. Producer → Queue (con ACK)
  2. Queue (persistida en disco) → Consumer
  3. Dead Letter Queue para mensajes fallidos
  4. Replay de mensajes históricos
```

**Casos de uso habilitados**:
- Recuperación ante crash: al reiniciar, el módulo reconsume mensajes pendientes
- Análisis post-mortem: "¿Qué mensajes procesó el módulo antes de fallar?"
- Procesamiento batch: acumular mensajes y procesar en batch

---

### 1.3 Streaming vs Request/Response

**Concepto actual**: Patrón sincrónico request/response

**Mejora conceptual**: Soporte nativo de streaming

```
IA Actual:
  → Enviar query
  → Esperar 20-45 segundos
  → Recibir respuesta completa

IA Streaming propuesta:
  → Enviar query
  ← Recibir "token_1" inmediatamente
  ← Recibir "token_2" 100ms después
  ← Recibir "token_N" hasta completar
  → UI puede mostrar respuesta progresivamente
```

**Aplicaciones**:
- Streaming de tokens de IA (mejor UX)
- Logs en tiempo real (stdout ya lo hace, pero formalizado)
- Progreso de operaciones largas (búsquedas, análisis)

---

## 2. Gestión de Estado

### 2.1 Event Sourcing

**Concepto actual**: Estado actual guardado en JSON (`session-memory.json`)

**Mejora conceptual**: Event sourcing como fuente de verdad

```
Actual:
  session-memory.json:
    {
      "command_history": ["open chrome", "search file"],
      "recent_applications": ["Chrome", "Terminal"]
    }

Event Sourcing:
  events.log (append-only):
    { type: "command_executed", command: "open chrome", ts: 123 }
    { type: "application_opened", app: "Chrome", ts: 124 }
    { type: "command_executed", command: "search file", ts: 125 }
  
  Estado actual = fold(events, initialState, reducer)
```

**Beneficios**:
- Auditoría completa (¿quién hizo qué y cuándo?)
- Time travel debugging (reproducir estado a las 3:45 PM)
- Proyecciones múltiples (mismo eventos, diferentes vistas)
- Análisis temporal (tendencias de uso)

---

### 2.2 CQRS (Command Query Responsibility Segregation)

**Concepto actual**: Mismo modelo para escritura y lectura

**Mejora conceptual**: Modelos separados

```
Commands (escritura):
  → Ejecutar comando
  → Validar
  → Generar eventos
  → Persistir

Queries (lectura):
  ← Vista optimizada para consulta específica
  ← Memoria semántica pre-calculada
  ← Cache de preferencias del usuario
```

**Aplicación concreta**:
- Commands: `ai.learn`, `memory.store`, `command.execute`
- Queries: `memory.search`, `ai.predict`, `stats.daily_usage`

**Beneficio**: Las consultas complejas no impactan la latencia de comandos.

---

### 2.3 Vector Store Nativo

**Concepto actual**: Memoria semántica con FAISS local

**Mejora conceptual**: Capa de datos vectorial integrada

```
Capacidades:
  - Embeddings automáticos de mensajes del sistema
  - Búsqueda semántica en todo el histórico
  - Clustering de conversaciones por tema
  - Deduplicación semántica ("esto ya se dijo de otra forma")
```

**Integración**:
- Cada mensaje automáticamente indexado
- Búsqueda: "conversaciones similares a esta"
- Contexto automático: "el usuario preguntó algo similar ayer"

---

## 3. Sistema de Módulos

### 3.1 De Procesos a Plugins Sandboxed

**Concepto actual**: Cada módulo es un proceso OS (Node/Python)

**Mejora conceptual**: Runtime sandboxed (WASM o similar)

```
Actual:
  Módulo = Proceso OS completo
  Comunicación = stdin/stdout (pipes del sistema operativo)
  
Propuesto:
  Módulo = Plugin sandboxed
  Comunicación = Canales del runtime (más eficientes)
  Seguridad = Capabilities explícitas (qué puede hacer cada módulo)
```

**Beneficios**:
- Inicio más rápido (no fork de proceso)
- Memoria compartida posible (para datos grandes)
- Límites de recursos estrictos (CPU/memoria por módulo)
- Hot reload sin perder estado

---

### 3.2 Dependency Injection Container

**Concepto actual**: Cada módulo crea sus propias dependencias

**Mejora conceptual**: Container de DI que provee servicios

```
Servicios registrados:
  - logger: Logger estructurado
  - metrics: Sistema de métricas
  - config: Configuración
  - memory: Acceso a memoria semántica
  - ai: Cliente del asistente IA

Módulo declara:
  dependencies: ['logger', 'memory', 'ai']

Runtime inyecta al iniciar el módulo.
```

**Beneficio**: Testing más fácil (mocks inyectables), logging consistente.

---

### 3.3 Lifecycle Hooks Estandarizados

**Concepto actual**: Lifecycle básico (start, message, exit)

**Mejora conceptual**: Hooks granulares

```
Lifecycle completo:
  1. pre_init: Antes de cargar configuración
  2. init: Configuración y setup
  3. post_init: Después de inicializar dependencias
  4. pre_start: Antes de aceptar mensajes
  5. start: Operativo
  6. pre_pause: Guardar estado volátil
  7. pause: Detener procesamiento pero mantener conexiones
  8. resume: Continuar desde pre_pause
  9. pre_stop: Flush de buffers
  10. stop: Cerrar graceful
  11. destroy: Cleanup final
```

**Aplicación**: Migración de módulos entre nodos, upgrades sin downtime.

---

## 4. Capacidades Cognitivas como Servicio

**Filosofía**: La IA no es el cerebro del sistema. Es una herramienta especializada que el sistema invoca cuando necesita capacidades cognitivas: entender lenguaje natural, generar código, analizar patrones. El control siempre permanece en el runtime y los módulos core.

---

### 4.1 Model Router como Servicio

**Concepto actual**: Un modelo (LLaMA) para todo

**Mejora conceptual**: Servicio de routing que selecciona el modelo apropiado según la necesidad del módulo que invoca

```
Módulo del sistema necesita capacidad cognitiva:
  ↓
  Invoca servicio "ai.query" con parámetros
  ↓
  Sistema decide: ¿qué modelo mejor satisface esta necesidad?
  ↓
  - Consulta simple → modelo pequeño (3B, rápido)
  - Generación código → modelo code-specialized
  - Análisis complejo → modelo grande (70B)
  - Sin GPU disponible → fallback a CPU o API cloud
  ↓
  Retorna resultado al módulo invocador
```

**Criterios de selección** (decididos por el sistema, no por la IA):
- Latencia máxima requerida por el módulo
- Complejidad estimada de la tarea
- Recursos disponibles (GPU/CPU/memoria)
- Política de costos (local vs API paga)

**Control**: El módulo decide SI usar IA. El router decide CÓMO (qué modelo). La IA nunca decide qué hacer.
```

---

### 4.2 Asistentes Especializados como Herramientas

**Concepto actual**: Un asistente general intenta hacer todo

**Mejora conceptual**: Especialistas de IA que el sistema invoca para tareas específicas, como cualquier otro worker

```
El sistema mantiene el control:

  agent.main (sistema) recibe: "Auditar proyecto"
  ↓
  agent.main decide: "Esto requiere análisis de código"
  ↓
  agent.main invoca ai.code.analyzer (herramienta IA)
       con contexto específico y formato de salida requerido
  ↓
  ai.code.analyzer genera análisis
  ↓
  agent.main recibe resultado estructurado
  ↓
  agent.main decide próximo paso basado en análisis
  ↓
  Si necesita más info: invoca ai.sysadmin.analyzer
  ↓
  Si es suficiente: emite plan al router para ejecución
```

**Diferencia clave**:
- ❌ Mal: IA decide qué herramientas usar y en qué orden
- ✅ Bien: Sistema decide flujo. IA es la herramienta que ejecuta análisis.

**Especialistas disponibles**:
- `ai.code.analyzer`: Genera análisis estático, sugiere mejoras
- `ai.sysadmin.interpreter`: Traduce lenguaje natural a comandos
- `ai.error.explainer`: Explica errores técnicos
- `ai.intent.parser`: Extrae entidades e intenciones de texto
- `ai.doc.generator`: Genera documentación

**Contrato**: Cada especialista recibe input estructurado, retorna output estructurado. No toma decisiones autónomas.
```

---

### 4.3 Memoria como Servicio Indexado

**Concepto actual**: Memoria de sesión + embeddings manejados por IA

**Mejora conceptual**: Servicio de memoria indexada que cualquier módulo puede consultar, no solo la IA

```
Cualquier módulo puede usar el servicio de memoria:

  memory.store({
    content: "El usuario prefiere Firefox",
    tags: ["preference", "browser"],
    scope: "user"
  })

  memory.search({
    query: "¿Qué navegador le gusta al usuario?",
    semantic: true,
    limit: 5
  })
  ↓
  Retorna resultados ordenados por relevancia
  ↓
  Módulo decide qué hacer con la información
```

**Principio**: La memoria no es "memoria de la IA". Es memoria del sistema que la IA puede usar como input, igual que cualquier otro módulo.

**Jerarquía de retención** (gestionada por el sistema):
  1. Contexto inmediato: Últimos mensajes de conversación activa
  2. Sesión actual: Datos de la sesión de hoy
  3. Memoria de trabajo: Datos recuperados recientemente
  4. Conocimiento persistente: Embeddings indexados
  5. Historial archivado: Datos antiguos, acceso más lento

**La IA como consumidora**: Cuando un módulo invoca a la IA, el sistema automáticamente enriquece el prompt con contexto relevante de la memoria. La IA no gestiona la memoria, la consume.
```

---

## 5. Observabilidad

### 5.1 Distributed Tracing

**Concepto actual**: Logs locales por módulo

**Mejora conceptual**: Trazas distribuidas end-to-end

```
Flujo de un comando:
  [CLI:uuid:span1] → Emitir comando
  [Agent:uuid:span2] → Analizar (parent=span1)
  [Planner:uuid:span3] → Crear plan (parent=span2)
  [Router:uuid:span4] → Enrutar (parent=span3)
  [Worker:uuid:span5] → Ejecutar (parent=span4)

Visualización:
  Timeline mostrando latencia entre cada span
  Identificación de cuellos de botella
  Camino crítico de ejecución
```

**Standard**: OpenTelemetry para compatibilidad con herramientas existentes.

---

### 5.2 SLOs y Error Budgets

**Concepto actual**: Monitoreo básico de health

**Mejora conceptual**: Service Level Objectives

```
SLOs definidos:
  - Disponibilidad: 99.9% (máximo 43 min downtime/mes)
  - Latencia IA p99: < 10 segundos
  - Latencia comandos simples p99: < 500 ms
  - Tasa de error: < 0.1%

Error Budget:
  - Si se excede el SLO de latencia, congelar features nuevas
  - Priorizar optimización hasta recuperar budget

Alertas:
  - Burn rate > 2x: Alerta de page
  - Burn rate > 1x: Alerta de investigar
```

---

### 5.3 Análisis Causal Automático

**Concepto actual**: Debugging manual por logs

**Mejora conceptual**: Sistema de análisis de causas

```
Incidente: "Comandos de IA fallan"
  → Análisis automático:
    - Correlación: Fallos coinciden con alta carga de CPU
    - Causa probable: Timeouts de IA por CPU saturation
    - Acción sugerida: Aumentar timeout o escalar recursos
```

**Técnicas**:
- Correlación temporal entre métricas
- Causalidad probabilística (Bayes)
- Aprendizaje de incidentes pasados

---

## 6. Configuración y Despliegue

### 6.1 Infrastructure as Code

**Concepto actual**: Blueprint JSON estático

**Mejora conceptual**: Configuración programática

```
Blueprint como código:
  system = Blueprint()
    .with_module('agent', version='1.2')
    .with_module('ai-assistant', 
                  model='llama3.2', 
                  gpu='auto',
                  replicas=2)
    .connect('agent:plan.out', 'router:plan.in')
    .with_policy('ai-assistant', 
                 max_memory='2GB',
                 timeout=30)
```

**Beneficios**:
- Composición y reutilización
- Condicionales (si GPU disponible, usar 70B, sino 8B)
- Validación en tiempo de "compilación"
- Templates reutilizables

---

### 6.2 Dynamic Reconfiguration

**Concepto actual**: Configuración estática al inicio

**Mejora conceptual**: Cambios en caliente

```
Operaciones soportadas:
  - Agregar/quitar módulo sin restart
  - Modificar conexiones en runtime
  - Ajustar timeouts de IA on-the-fly
  - Cambiar nivel de logging dinámicamente

Mecanismo:
  1. Nuevo blueprint propuesto
  2. Validación de compatibilidad
  3. Diff calculado
  4. Aplicación gradual (rolling update)
  5. Rollback automático si health check falla
```

---

## 7. Seguridad

### 7.1 Zero Trust Architecture

**Concepto actual**: Seguridad basada en políticas estáticas

**Mejora conceptual**: Nunca confiar, siempre verificar

```
Principios:
  1. Toda comunicación autenticada (módulos tienen identidad)
  2. Autorización por cada mensaje (no solo al inicio)
  3. Mínimo privilegio (módulo solo ve lo que necesita)
  4. Micro-segmentación (módulos aislados por default)

Implementación:
  - Certificados por módulo (mTLS)
  - Capabilities (token que autoriza acción específica)
  - Audit logging de todas las acciones
```

---

### 7.2 Sandboxing por Capabilities

**Concepto actual**: Categorías allow/confirm/block

**Mejora conceptual**: Capabilities granulares

```
Declaración de capabilities:
  ai-assistant:
    - read: memory.semantic
    - write: logs.events
    - execute: ollama.query
    - network: none
    - filesystem: read-only, /tmp

Violación:
  Si el módulo intenta "write: filesystem", denegado.
```

---

## 8. Escalabilidad

### 8.1 Multi-Nodo (Cluster)

**Concepto actual**: Single-node, procesos locales

**Mejora conceptual**: Distribución en cluster

```
Nodo 1 (UI):
  - interface.cli
  - interface.telegram

Nodo 2 (Core):
  - agent
  - router
  - planner

Nodo 3 (Workers):
  - worker-system
  - worker-python
  - worker-browser

Nodo 4 (IA):
  - ai-assistant (con GPU)
  - ai-memory-semantic

Comunicación entre nodos:
  - Message bus distribuido (Redis/RabbitMQ/NATS)
  - Descubrimiento de servicios
  - Load balancing de workers
```

**Habilitado por**: Abstracción del bus de mensajes (no asumir stdin/stdout).

---

### 8.2 Auto-scaling de Workers

**Concepto actual**: Una instancia por worker

**Mejora conceptual**: Pool de workers auto-escalable

```
Metricas de escalado:
  - Queue depth > 10 → Scale up
  - Latencia p99 > 5s → Scale up
  - CPU < 20% por 5 min → Scale down

Límites:
  - Mínimo: 1 instancia por tipo
  - Máximo: 10 instancias por tipo
  - Cooldown: 60 segundos entre escalados
```

---

## 9. Resumen de Transición

### Fase 1: Fundamentos (Mes 1-2)
1. Pub/sub semántico sobre conexiones estáticas
2. Event sourcing para auditoría
3. Distributed tracing básico

### Fase 2: Robustez (Mes 3-4)
1. Message broker con persistencia
2. CQRS para separar lectura/escritura
3. SLOs y error budgets

### Fase 3: Inteligencia (Mes 5-6)
1. Model routing
2. Multi-agent orchestration
3. Memoria jerárquica

### Fase 4: Escalabilidad (Mes 7-8)
1. Abstracción del transporte (preparar para multi-nodo)
2. Auto-scaling
3. Dynamic reconfiguration

---

## 10. Principios Rectores

1. **Event-Driven**: Todo es un evento. Estado es derivado.
2. **Desacoplado**: Módulos no conocen la existencia de otros, solo tópicos.
3. **Observable**: Toda acción trazable, medible, alertable.
4. **Seguro por Default**: Denegar todo, permitir explícitamente.
5. **Declarativo**: La intención es código, no scripts imperativos.
6. **Efímero**: Módulos son descartables. Estado vive fuera de ellos.

---

*Documento conceptual para visión de largo plazo*
