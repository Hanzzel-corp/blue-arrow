#!/usr/bin/env python3
"""
Sistema de idempotencia y deduplicación para blueprint-v0.

Previene efectos duplicados cuando:
- Un mensaje se re-entrega (reconexión de módulo)
- Un worker se reinicia y re-procesa
- Un timeout hace reintentar
"""

import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional


class IdempotencyChecker:
    """
    Checker de idempotencia con ventana deslizante.

    Usa task_id como clave primaria + fingerprint del payload
    para detectar duplicados exactos.
    """

    def __init__(self, window_seconds: int = 300, max_entries: int = 10000):
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        # OrderedDict para LRU: {key: timestamp}
        self.seen = OrderedDict()
        self.persistence_path = Path("logs/idempotency.jsonl")

    def _make_key(self, task_id: str, action: str, params: dict) -> str:
        """
        Crea clave única para detectar duplicados.

        task_id: Identificador de la tarea (debe venir del upstream)
        action: Nombre de la acción
        params: Parámetros de la acción (se hashea)
        """
        # Normalizar params para hash consistente
        params_normalized = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_normalized.encode()).hexdigest()[:16]

        return f"{task_id}:{action}:{params_hash}"

    def check(self, task_id: str, action: str, params: dict) -> tuple[bool, str]:
        """
        Verifica si esta acción ya fue procesada.

        Returns:
            (is_duplicate, key)
            is_duplicate: True si ya se procesó (rechazar)
            key: La clave usada (para logging/debug)
        """
        key = self._make_key(task_id, action, params)
        now = time.time()

        # Limpiar entradas antiguas
        self._cleanup(now)

        if key in self.seen:
            # Actualizar orden para LRU
            self.seen.move_to_end(key)
            return True, key

        # Registrar nueva acción
        self.seen[key] = {
            'timestamp': now,
            'action': action,
            'task_id': task_id
        }

        # Evitar crecimiento ilimitado
        if len(self.seen) > self.max_entries:
            self.seen.popitem(last=False)

        return False, key

    def _cleanup(self, now: float):
        """Elimina entradas más viejas que la ventana."""
        cutoff = now - self.window_seconds
        expired = [
            key for key, data in self.seen.items()
            if data['timestamp'] < cutoff
        ]
        for key in expired:
            del self.seen[key]

    def persist(self):
        """Persiste estado actual (para recovery)."""
        with open(self.persistence_path, 'a') as f:
            for key, data in self.seen.items():
                f.write(json.dumps({
                    'key': key,
                    'timestamp': data['timestamp'],
                    'action': data['action'],
                    'task_id': data['task_id']
                }) + '\n')


class WorkerIdempotency:
    """
    Helper para workers: ejecuta acción solo si no es duplicado.

    Patrón de uso:
        with WorkerIdempotency(execution_id) as guard:
            if guard.should_execute():
                result = do_action()
                guard.commit(result)
            else:
                return guard.previous_result()
    """

    def __init__(self, checker: IdempotencyChecker, task_id: str, action: str, params: dict):
        self.checker = checker
        self.task_id = task_id
        self.action = action
        self.params = params
        self.is_duplicate = False
        self.key = None
        self.result = None

    def should_execute(self) -> bool:
        """True si debe ejecutar, False si es duplicado."""
        self.is_duplicate, self.key = self.checker.check(
            self.task_id, self.action, self.params
        )
        return not self.is_duplicate

    def mark_duplicate(self):
        """Fuerza marcado como duplicado (para casos especiales)."""
        self.is_duplicate = True


class ActionFingerprint:
    """
    Genera fingerprint único para una acción con efecto real.

    Incluye:
    - task_id (del flujo)
    - action (nombre)
    - params normalizados
    - timestamp de inicio (ventana)
    """

    @staticmethod
    def generate(task_id: str, action: str, params: dict, timestamp: Optional[float] = None) -> str:
        """Genera fingerprint único."""
        data = {
            'task_id': task_id,
            'action': action,
            'params': ActionFingerprint._normalize_params(params),
            'timestamp': timestamp or time.time()
        }
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode()).hexdigest()[:24]

    @staticmethod
    def _normalize_params(params: dict) -> dict:
        """Normaliza params para comparación consistente."""
        # Eliminar campos volátiles que no afectan el efecto
        volatile = ['_trace_id', '_meta', 'timestamp', 'request_id']
        cleaned = {k: v for k, v in params.items() if k not in volatile}
        return cleaned


# Singleton global
checker = IdempotencyChecker()


def check_idempotent(task_id: str, action: str, params: dict) -> tuple[bool, str]:
    """
    Función global para verificar idempotencia.

    Uso en workers:
        is_dup, key = check_idempotent(task_id, 'open_app', {'name': 'firefox'})
        if is_dup:
            return {'status': 'success', 'result': 'already_executed', 'dedupe_key': key}
        # ... ejecutar ...
    """
    return checker.check(task_id, action, params)
