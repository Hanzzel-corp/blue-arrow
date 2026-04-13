# Safety Guard Module - Documentación

## 🛡️ Validación de Seguridad

<p align="center">
  <b>Módulo core que valida planes contra reglas de seguridad y políticas de riesgo</b>
</p>

---

## Visión General

`safety.guard.main` es el **gatekeeper de seguridad**. Recibe planes enriquecidos desde `agent.main`, los valida contra reglas de seguridad configuradas, y decide si el plan puede continuar directamente, requiere aprobación, o debe rechazarse.

### Rol en el Sistema

| Característica | Valor |
|----------------|-------|
| **Tipo** | Core - Validación |
| **Autoridad** | Valida y marca para aprobación, no ejecuta |
| **Entrada** | `plan.in` desde `agent.main` |
| **Salida Safe/Risk** | `approved.plan.out` → `router.main` o `approval.main` |
| **Salida Reject** | `blocked.plan.out` (termina flujo) |

---

## Flujo de Validación

```
agent.main ──► safety.guard.main ──► ?
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    [SAFE]      [RISKY]     [DANGEROUS]
       │            │            │
       ▼            ▼            ▼
approved.plan    approved.plan   blocked.plan
      .out          .out (risk)      .out
       │            │            
       ▼            ▼            
   router      approval.main
                 (requiere OK)
                       │
                       ▼
                 router.main
```

---

## Reglas de Seguridad

### Evaluación de Riesgo

```javascript
function evaluateRisk(plan) {
  const riskScore = 0;
  
  // 1. Acciones peligrosas
  if (hasAction(plan, 'delete_file')) riskScore += 50;
  if (hasAction(plan, 'format_drive')) riskScore += 100;
  if (hasAction(plan, 'sudo_command')) riskScore += 40;
  
  // 2. Targets sensibles
  if (targetsSystemDirectory(plan)) riskScore += 30;
  if (targetsUserData(plan)) riskScore += 20;
  
  // 3. Contexto
  if (isFirstTimeAction(plan)) riskScore += 10;
  
  return classifyRisk(riskScore);
}

function classifyRisk(score) {
  if (score >= 80) return { level: 'critical', action: 'reject' };
  if (score >= 50) return { level: 'high', action: 'require_approval' };
  if (score >= 20) return { level: 'medium', action: 'require_approval' };
  return { level: 'low', action: 'allow' };
}
```

### Lista de Acciones Controladas

| Acción | Riesgo Base | Condiciones de Aumento |
|--------|-------------|------------------------|
| `delete_file` | 50 | +30 si es directorio, +20 si no hay backup |
| `sudo_command` | 40 | +30 si modifica sistema |
| `install_package` | 30 | +20 si es fuente no confiable |
| `modify_config` | 25 | +30 si es config de sistema |
| `format_drive` | 100 | Siempre CRÍTICO |
| `open_url` | 5 | +20 si URL es sospechosa |

---

## API y Puertos

### Entrada: `plan.in`

```json
{
  "plan_id": "plan_123",
  "steps": [...],
  "risk_level": "medium",
  "trace_id": "abc-123"
}
```

### Salida: `approved.plan.out` (Safe - riesgo bajo)

```json
{
  "module": "safety.guard.main",
  "port": "approved.plan.out",
  "trace_id": "plan_123_trace",
  "meta": {
    "source": "safety.guard.main",
    "timestamp": "2026-01-01T00:00:00Z"
  },
  "payload": {
    "plan_id": "plan_123",
    "safety_check": {
      "passed": true,
      "risk_level": "low",
      "checked_at": "2026-01-01T00:00:00Z"
    },
    "requires_approval": false,
    "next_module": "router.main"
  }
}
```

### Salida: `approved.plan.out` (Risk - requiere aprobación)

```json
{
  "module": "safety.guard.main",
  "port": "approved.plan.out",
  "trace_id": "plan_123_trace",
  "meta": {...},
  "payload": {
    "plan_id": "plan_123",
    "safety_check": {
      "passed": true,
      "risk_level": "high",
      "reason": "Acción destructiva detectada",
      "risky_actions": ["delete_file"]
    },
    "requires_approval": true,
    "approval_reason": "Eliminación de archivos sin backup",
    "next_module": "approval.main"
  }
}
```

### Salida: `blocked.plan.out` (Dangerous - rechazo)

```json
{
  "module": "safety.guard.main",
  "port": "blocked.plan.out",
  "trace_id": "plan_123_trace",
  "meta": {...},
  "payload": {
    "plan_id": "plan_123",
    "rejected": true,
    "rejection_reason": "Acción crítica no permitida: format_drive",
    "risk_level": "critical",
    "user_message": "❌ Esta acción no está permitida por seguridad",
    "next_module": null
  }
}
```

---

## Configuración

```json
{
  "id": "safety.guard.main",
  "name": "Safety Guard",
  "tier": "core",
  "inputs": ["plan.in", "config.in"],
  "outputs": ["approved.plan.out", "blocked.plan.out", "event.out"],
  "config": {
    "risk_thresholds": {
      "allow": 0,
      "require_approval": 20,
      "reject": 80
    },
    "blocked_actions": ["format_drive", "rm_rf_root"],
    "sensitive_paths": ["/etc", "/usr", "/sys"],
    "require_backup_before_delete": true
  }
}
```

---

## Ejemplos

### Ejemplo 1: Plan Safe

**Entrada**: Abrir firefox

**Evaluación**: `riskScore = 0`

**Salida**:
```json
{
  "safety_check": {"passed": true, "risk_level": "low"},
  "requires_approval": false
}
```

### Ejemplo 2: Plan Risky

**Entrada**: Eliminar archivos de /tmp

**Evaluación**: `riskScore = 50` (delete_file) + 0 (no es sensible)

**Salida**:
```json
{
  "safety_check": {
    "passed": true,
    "risk_level": "high",
    "risky_actions": ["delete_file"]
  },
  "requires_approval": true
}
```

### Ejemplo 3: Plan Dangerous

**Entrada**: Formatear disco

**Evaluación**: `riskScore = 100` → CRÍTICO

**Salida**:
```json
{
  "rejected": true,
  "rejection_reason": "Acción format_drive bloqueada permanentemente"
}
```

---

## Referencias

- **[APPROVAL.md](APPROVAL.md)** - Circuito de aprobaciones
- **[AGENT.md](AGENT.md)** - Enriquecimiento de planes
- **[TASK_CLOSURE_GOVERNANCE.md](TASK_CLOSURE_GOVERNANCE.md)** - Gobierno de roles

---

<p align="center">
  <b>Safety Guard Module v1.0.0</b><br>
  <sub>Validación de seguridad - Core de protección</sub>
</p>
