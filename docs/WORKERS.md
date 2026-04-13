# Workers - Documentación

## ⚙️ Workers Especializados

<p align="center">
  <b>Módulos de ejecución que realizan acciones concretas en el sistema operativo</b>
</p>

---

## Visión General

Los **workers** son módulos Python especializados que ejecutan acciones concretas en el sistema operativo. Son los **informers** del sistema: ejecutan acciones y reportan resultados, pero no cierran tareas.

### Principio Informer

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUJO WORKER                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │ worker.main  │────▶│  result.out  │────▶│  [verifier]  │  │
│  └──────────────┘     └──────────────┘     └──────┬───────┘  │
│                                                     │         │
│                                                     ▼         │
│                                               ┌────────────┐  │
│                                               │ supervisor │  │
│                                               │  (closer)  │  │
│                                               └────────────┘  │
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐  │
│  │ worker.main  │────▶│  event.out   │────▶│  observers   │  │
│  └──────────────┘     └──────────────┘     └──────────────┘  │
│                                                  │           │
│                                                  ▼           │
│                                         ┌────────────────┐   │
│                                         │ memory.log     │   │
│                                         │ ui.state       │   │
│                                         │ ai.learning    │   │
│                                         │ gamification   │   │
│                                         └────────────────┘   │
│                                                              │
│  📌 SEPARACIÓN:                                              │
│  • result.out → Solo para cierre (no UI directa)            │
│  • event.out → Para observadores internos (logs, estado)     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Workers Disponibles

| Worker | Tecnología | Acciones Principales |
|--------|------------|---------------------|
| `worker.python.desktop` | Python + xdotool | Apps, ventanas, terminal visual |
| `worker.python.browser` | Python + Playwright | Navegación web, formularios |
| `worker.python.system` | Python + psutil | Archivos, procesos, métricas |
| `worker.python.terminal` | Python + pexpect | Comandos shell |

---

## Worker Desktop

### Responsabilidades

- Abrir/cerrar aplicaciones
- Control de ventanas (focus, resize, move)
- Captura de pantalla
- Escribir en campos de texto de aplicaciones (no terminal shell)

> **📌 Nota**: Los comandos de terminal shell van a `worker.python.terminal`, no a Desktop.

### Acciones

```python
ACTIONS = {
    'open_application': {
        'params': ['name', 'command'],
        'example': {'name': 'firefox', 'command': 'firefox'}
    },
    'focus_window': {
        'params': ['window_id', 'title_pattern'],
        'example': {'title_pattern': 'Firefox'}
    },
    'write_text_field': {
        'params': ['text', 'window_id', 'field_name'],
        'example': {'text': 'Hello World', 'field_name': 'input'}
    },
    'capture_screen': {
        'params': ['region', 'save_path'],
        'example': {'region': 'full', 'save_path': '/tmp/screenshot.png'}
    }
}
```

### Entrada: `desktop.action.in`

```json
{
  "task_id": "task_123",
  "action": "open_application",
  "params": {"name": "firefox"},
  "trace_id": "abc-123"
}
```

### Salida: `result.out`

```json
{
  "task_id": "task_123",
  "status": "success",
  "result": {
    "opened": true,
    "process_id": 12345,
    "window_id": "0x04200001"
  },
  "_verification": {
    "confidence": 0.95,
    "level": "window_confirmed"
  }
}
```

---

## Worker Browser

### Responsabilidades

- Navegar a URLs
- Rellenar formularios
- Realizar búsquedas
- Capturas de página

### Acciones

```python
ACTIONS = {
    'open_url': {
        'params': ['url', 'wait_for_load'],
        'example': {'url': 'https://github.com'}
    },
    'search': {
        'params': ['query', 'search_engine'],
        'example': {'query': 'python tutorials', 'engine': 'google'}
    },
    'fill_form': {
        'params': ['selector', 'value'],
        'example': {'selector': '#search', 'value': 'query'}
    }
}
```

### Entrada: `browser.action.in`

```json
{
  "task_id": "task_124",
  "action": "open_url",
  "params": {"url": "https://github.com"}
}
```

### Salida: `result.out`

```json
{
  "task_id": "task_124",
  "status": "success",
  "result": {
    "loaded": true,
    "url": "https://github.com",
    "title": "GitHub"
  }
}
```

---

## Worker System

### Responsabilidades

- Búsqueda de archivos
- Información de sistema
- Monitoreo de recursos
- Gestión de procesos

### Acciones

```python
ACTIONS = {
    'search_file': {
        'params': ['pattern', 'directory', 'recursive'],
        'example': {'pattern': '*.py', 'directory': '/home/user'}
    },
    'get_system_info': {
        'params': ['type'],
        'example': {'type': 'cpu|memory|disk'}
    },
    'list_processes': {
        'params': ['filter'],
        'example': {'filter': 'firefox'}
    }
}
```

---

## Worker Terminal

### Responsabilidades

- Ejecutar comandos shell
- Capturar output
- Comandos interactivos

### Acciones

```python
ACTIONS = {
    'terminal.write_command': {
        'params': ['command', 'execute', 'timeout'],
        'example': {'command': 'npm install', 'execute': True}
    },
    'terminal.show_command': {
        'params': ['command'],
        'example': {'command': "echo 'Hola'"}
    }
}
```

> **Nota sobre naming**: El router emite acciones con namespace `terminal.*` para identificar el worker destino. El worker terminal implementa estas acciones con los nombres completos.

---

## Formato de Resultados

### Estructura Base

```json
{
  "module": "worker.python.desktop",
  "port": "result.out",
  "trace_id": "task_123_trace",
  "meta": {
    "worker_type": "desktop",
    "timestamp": "2026-01-01T00:00:00Z"
  },
  "payload": {
    "task_id": "task_123",
    "status": "success|error|partial",
    "result": {
      "...": "datos específicos de la acción"
    },
    "_verification": {
      "confidence": 0.95,
      "level": "window_confirmed|process_detected|signal_confirmed"
    },
    "duration_ms": 3200
  }
}
```

### Niveles de Verificación

| Nivel | Confidence | Señales Requeridas |
|-------|------------|-------------------|
| `window_confirmed` | ≥0.90 | Proceso + Ventana + Foco |
| `window_detected` | ≥0.75 | Proceso + Ventana |
| `process_only` | ≥0.50 | Solo proceso |
| `signal_confirmed` | ≥0.25 | Señal de éxito |

---

## Configuración

### Manifest Worker Desktop

```json
{
  "id": "worker.python.desktop",
  "name": "Desktop Worker",
  "tier": "core",
  "language": "python",
  "entry": "main.py",
  "inputs": ["desktop.action.in"],
  "outputs": ["result.out", "event.out"],
  "config": {
    "tools": ["xdotool", "wmctrl", "psutil"],
    "default_timeout_ms": 30000,
    "verification_enabled": true
  }
}
```

---

## Ejemplos

### Ejemplo 1: Abrir Aplicación

**Entrada**:
```json
{
  "action": "open_application",
  "params": {"name": "firefox"}
}
```

**Ejecución**:
```python
import subprocess
subprocess.Popen(['firefox'])
```

**Salida**:
```json
{
  "status": "success",
  "result": {
    "process_id": 12345,
    "window_id": "0x04200001"
  },
  "_verification": {"confidence": 0.95}
}
```

### Ejemplo 2: Comando Terminal

**Entrada**:
```json
{
  "action": "terminal.write_command",
  "params": {"command": "ls -la", "execute": true}
}
```

**Salida**:
```json
{
  "status": "success",
  "result": {
    "executed": true,
    "return_code": 0,
    "output": "drwxr-xr-x 5 user user ..."
  }
}
```

---

## Referencias

- **[TASK_CLOSURE_GOVERNANCE.md](TASK_CLOSURE_GOVERNANCE.md)** - Rol de Informer
- **[execution-verifier-design.md](execution-verifier-design.md)** - Verificación de resultados
- **[ROUTER.md](ROUTER.md)** - Enrutamiento a workers

---

<p align="center">
  <b>Workers v1.0.0</b><br>
  <sub>Ejecutores de acciones - Core informers</sub>
</p>
