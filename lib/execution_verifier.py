#!/usr/bin/env python3
"""
Execution Verifier Helper - blueprint-v0

Proporciona funciones para enriquecer resultados con metadatos de verificación.
Mantiene backward compatibility con resultados actuales.
"""

import time
from typing import Dict, Optional, Any
from datetime import datetime


class VerificationBuilder:
    """Builder para construir el objeto _verification en resultados."""

    def __init__(self, action: str, version: str = "1.0"):
        self.action = action
        self.version = version
        self.evidence: Dict[str, Any] = {}
        self.signals = []
        self.limitations = []
        self.warnings = []
        self.start_time = time.time()

    def add_signal(self, name: str, present: bool, weight: float) -> "VerificationBuilder":
        """Agrega una señal de evidencia."""
        contribution = weight if present else 0.0
        self.signals.append({
            "name": name,
            "present": present,
            "weight": weight,
            "contribution": contribution,
        })
        return self

    def add_evidence(self, key: str, value: Any) -> "VerificationBuilder":
        """Agrega evidencia concreta (pid, window_id, etc.)."""
        self.evidence[key] = value
        return self

    def add_limitation(self, limitation: str) -> "VerificationBuilder":
        """Agrega una limitación conocida."""
        self.limitations.append(limitation)
        return self

    def add_warning(self, warning: str) -> "VerificationBuilder":
        """Agrega una advertencia."""
        self.warnings.append(warning)
        return self

    def calculate_confidence(self) -> float:
        """Calcula el confidence score basado en señales."""
        if not self.signals:
            return 0.0

        total_contribution = sum(s["contribution"] for s in self.signals)
        total_weight = sum(s["weight"] for s in self.signals)

        if total_weight == 0:
            return 0.0

        return round(min(1.0, total_contribution / total_weight), 2)

    def determine_level(self) -> str:
        """Determina el nivel de verificación alcanzado."""
        e = self.evidence
        confidence = self.calculate_confidence()

        if confidence >= 0.90:
            if e.get("focus_confirmed") and e.get("window_detected"):
                return "window_confirmed"
            if e.get("window_detected"):
                return "window_detected"
            if e.get("process_detected"):
                return "process_only"
            return "signal_confirmed"

        if confidence >= 0.75:
            if e.get("window_detected"):
                return "window_detected"
            if e.get("process_detected"):
                return "process_only"
            return "signal_detected"

        if confidence >= 0.50:
            if e.get("process_detected"):
                return "process_only"
            return "partial_evidence"

        if confidence >= 0.25:
            return "minimal_evidence"

        return "none"

    def determine_executive_state(self, success: bool = True) -> str:
        """Determina el estado ejecutivo basado en confidence."""
        if not success:
            return "error_confirmed"

        confidence = self.calculate_confidence()

        if confidence >= 0.90:
            return "success_verified"
        if confidence >= 0.75:
            return "success_high_confidence"
        if confidence >= 0.50:
            return "success_partial"
        if confidence >= 0.25:
            return "success_weak"
        return "success_unverified"

    def build_classification(self, action: str, target: Optional[str] = None, success: bool = True) -> Dict:
        """Construye los mensajes de clasificación."""
        executive_state = self.determine_executive_state(success=success)

        messages = {
            "success_verified": {
                "short": f"{action} completado y verificado",
                "detailed": f"{action} de '{target}' confirmado con evidencia completa" if target else f"{action} confirmado con evidencia completa",
                "user_message": f"✅ {target} abierto y verificado correctamente" if target else "✅ Acción completada y verificada",
            },
            "success_high_confidence": {
                "short": f"{action} ejecutado (alta confianza)",
                "detailed": f"{action} de '{target}' con buena evidencia" if target else f"{action} con buena evidencia",
                "user_message": f"✓ {target} abierto (alta confianza)" if target else "✓ Acción ejecutada (alta confianza)",
            },
            "success_partial": {
                "short": f"{action} con verificación parcial",
                "detailed": f"{action} de '{target}' con evidencia limitada" if target else f"{action} con evidencia limitada",
                "user_message": f"⚠ {target} iniciado, verificación parcial" if target else "⚠ Acción iniciada, verificación parcial",
            },
            "success_weak": {
                "short": f"{action} no verificado",
                "detailed": f"{action} de '{target}' sin evidencia suficiente" if target else f"{action} sin evidencia suficiente",
                "user_message": f"? {action} enviado, estado pendiente",
            },
            "success_unverified": {
                "short": f"{action} sin verificación",
                "detailed": f"{action} de '{target}' no pudo ser verificado" if target else f"{action} no pudo ser verificado",
                "user_message": f"⚠ {action} enviado, verificación no disponible",
            },
            "error_confirmed": {
                "short": f"{action} falló",
                "detailed": f"{action} de '{target}' no se completó" if target else f"{action} no se completó",
                "user_message": f"❌ Error en {action}",
            },
        }

        msg = messages.get(executive_state, messages["success_unverified"])

        return {
            "code": executive_state,
            "short": msg["short"],
            "detailed": msg["detailed"],
            "user_message": msg["user_message"],
        }

    def build(self, success: bool = True, target: Optional[str] = None) -> Dict:
        """Construye el objeto _verification completo."""
        elapsed_ms = int((time.time() - self.start_time) * 1000)

        verification = {
            "version": self.version,
            "action": self.action,
            "verified_at": datetime.now().isoformat(),
            "level": self.determine_level(),
            "confidence": self.calculate_confidence(),
            "executive_state": self.determine_executive_state(success),
            "evidence": self.evidence,
            "signals": self.signals,
            "classification": self.build_classification(self.action, target, success=success),
            "limitations": self.limitations if self.limitations else [],
            "warnings": self.warnings if self.warnings else [],
            "verification_time_ms": elapsed_ms,
        }

        return VerificationNormalizer.normalize(verification)


class VerificationNormalizer:
    """Normaliza verificación para garantizar consistencia level/confidence."""

    @staticmethod
    def normalize(verification: Dict) -> Dict:
        """Corrige inconsistencias level/confidence sin recursión."""
        confidence = float(verification.get("confidence", 0) or 0)
        level = verification.get("level", "unknown")
        executive_state = verification.get("executive_state", "unknown")
        evidence = verification.get("evidence", {}) or {}

        is_inconsistent = False
        original_level = level
        original_state = executive_state

        if confidence >= 0.90 and level in {"none", "unknown", "unverified"}:
            is_inconsistent = True
            level = VerificationNormalizer._infer_level_from_evidence(confidence, evidence)

        if confidence < 0.25 and executive_state == "success_verified":
            is_inconsistent = True
            executive_state = "success_weak" if confidence >= 0.10 else "success_unverified"

        minimum_expected_level = VerificationNormalizer._minimum_expected_level(confidence)
        if VerificationNormalizer._level_rank(level) < VerificationNormalizer._level_rank(minimum_expected_level):
            is_inconsistent = True
            level = minimum_expected_level

        verification["confidence"] = round(confidence, 2)
        verification["level"] = level
        verification["executive_state"] = executive_state

        if is_inconsistent:
            verification["_normalized"] = True
            verification["_original_level"] = original_level
            verification["_original_state"] = original_state

        return verification

    @staticmethod
    def _infer_level_from_evidence(confidence: float, evidence: Dict) -> str:
        """Infiere nivel basado en evidencia disponible."""
        if evidence.get("focus_confirmed") and evidence.get("window_detected"):
            return "window_confirmed"
        if evidence.get("window_detected"):
            return "window_detected"
        if evidence.get("process_detected"):
            return "process_only"
        if evidence.get("signal_detected") or evidence.get("output_captured"):
            return "signal_confirmed"
        return "signal_confirmed" if confidence >= 0.90 else "signal_detected"

    @staticmethod
    def _minimum_expected_level(confidence: float) -> str:
        """Devuelve el nivel mínimo coherente para un confidence."""
        if confidence >= 0.90:
            return "signal_confirmed"
        if confidence >= 0.75:
            return "signal_detected"
        if confidence >= 0.50:
            return "partial_evidence"
        if confidence >= 0.25:
            return "minimal_evidence"
        return "none"

    @staticmethod
    def _level_rank(level: str) -> int:
        ranking = {
            "none": 0,
            "minimal_evidence": 1,
            "partial_evidence": 2,
            "signal_detected": 3,
            "process_only": 4,
            "window_detected": 5,
            "signal_confirmed": 6,
            "window_confirmed": 7,
        }
        return ranking.get(level, 0)


def create_verification_builder(action: str) -> VerificationBuilder:
    """Crea un nuevo builder para una acción."""
    return VerificationBuilder(action)


def enrich_result(
    result: Dict,
    action: str,
    success: bool = True,
    target: Optional[str] = None,
    **evidence: Any,
) -> Dict:
    """
    Enriquece un resultado existente con _verification.
    """
    builder = VerificationBuilder(action)

    for key, value in evidence.items():
        builder.add_evidence(key, value)

    if action == "open_application":
        builder.add_signal("process_detected", evidence.get("process_detected", False), 0.20)
        builder.add_signal("window_detected", evidence.get("window_detected", False), 0.30)
        builder.add_signal("target_matched", evidence.get("target_matched", False), 0.25)
        builder.add_signal("focus_confirmed", evidence.get("focus_confirmed", False), 0.15)
        builder.add_signal("window_raised", evidence.get("focus_attempted", False), 0.10)

    elif action == "terminal.write_command":
        builder.add_signal("terminal_exists", evidence.get("window_id") is not None, 0.20)
        builder.add_signal("window_active", evidence.get("window_active", False), 0.25)
        builder.add_signal("command_typed", evidence.get("command_typed", False), 0.20)
        builder.add_signal("command_executed", evidence.get("command_executed", False), 0.25)
        builder.add_signal("output_captured", evidence.get("output_captured", False), 0.10)

    verification = builder.build(success=success, target=target)
    result["_verification"] = verification
    return result


def enrich_success(result: Dict, action: str, target: Optional[str] = None, **evidence: Any) -> Dict:
    """Helper para enriquecer resultado exitoso."""
    return enrich_result(result, action, success=True, target=target, **evidence)


def enrich_error(result: Dict, action: str, error_type: str, **evidence: Any) -> Dict:
    """Helper para enriquecer resultado con error."""
    builder = VerificationBuilder(action)

    for key, value in evidence.items():
        builder.add_evidence(key, value)

    if evidence.get("process_detected"):
        builder.add_signal("process_detected", True, 0.20)

    verification = builder.build(success=False, target=evidence.get("target"))
    verification["error_type"] = error_type

    result["_verification"] = verification
    return result