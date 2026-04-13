#!/usr/bin/env python3
"""
System Ontology - Definición canónica del sistema
Ontología: estudio de la realidad/naturaleza de las cosas

Define:
- Qué existe en el sistema (entidades canónicas)
- Cómo se relacionan (relaciones semánticas)
- Qué alias/nombres acepta cada cosa
- Roles y responsabilidades
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Callable
from enum import Enum, auto
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class EntityType(Enum):
    """Tipos de entidades en el sistema"""
    CORE_MODULE = auto()      # Módulo esencial (router, agent, supervisor)
    SATELLITE_MODULE = auto() # Módulo opcional (gamification, guide)
    WORKER = auto()           # Worker de ejecución (python, node)
    RUNTIME_COMPONENT = auto() # Componente del runtime (bus, registry)
    LIBRARY = auto()          # Biblioteca compartida
    INTERFACE = auto()         # Punto de entrada (telegram, hud)
    AI_SERVICE = auto()       # Servicio de IA


class Plane(Enum):
    """Los 3 planos de existencia del sistema"""
    PHYSICAL = "physical"    # Archivos, carpetas, disco
    LOGICAL = "logical"      # Módulos, roles, tiers, ontología
    OPERATIONAL = "operational"  # Procesos, mensajes, estado


class PortStatus(Enum):
    """Estado de un puerto en el contrato"""
    ACTIVE = "active"           # En uso actualmente
    RESERVED = "reserved"       # Reservado para crecimiento futuro
    OBSOLETE = "obsolete"       # Obsoleto, mantenido por compatibilidad
    MISDEFINED = "misdefined"   # Mal definido, necesita corrección


@dataclass
class CanonicalEntity:
    """
    Entidad canónica del sistema
    - Un único nombre canónico (fuente de verdad)
    - Múltiples alias válidos
    - Rol definido
    - Ubicación semántica
    - Clasificación de puertos (reservados, obsoletos, mal definidos)
    """
    canonical_id: str                    # ID único (ej: "router.main")
    entity_type: EntityType
    name: str                            # Nombre humano
    aliases: Set[str] = field(default_factory=set)  # nombres alternativos válidos
    directory_name: str = ""             # nombre en disco (ej: "router-main")
    role: str = ""                       # rol semántico
    tier: str = "satellite"              # core/satellite
    inputs: Set[str] = field(default_factory=set)
    outputs: Set[str] = field(default_factory=set)
    dependencies: Set[str] = field(default_factory=set)
    description: str = ""
    
    # Clasificación de puertos para análisis de coherencia
    reserved_inputs: Set[str] = field(default_factory=set)   # Inputs reservados para futuro
    reserved_outputs: Set[str] = field(default_factory=set)  # Outputs reservados para futuro
    obsolete_inputs: Set[str] = field(default_factory=set)   # Inputs obsoletos
    obsolete_outputs: Set[str] = field(default_factory=set)  # Outputs obsoletos
    
    def matches(self, identifier: str) -> bool:
        """Verifica si un identificador refiere a esta entidad"""
        identifier = identifier.lower().replace("-", ".")
        canonical = self.canonical_id.lower()
        aliases_lower = {a.lower().replace("-", ".") for a in self.aliases}
        
        return identifier == canonical or identifier in aliases_lower
    
    def get_all_names(self) -> Set[str]:
        """Retorna todos los nombres válidos para esta entidad"""
        return {self.canonical_id} | self.aliases | {self.directory_name}


class SystemOntology:
    """
    Tabla de realidad del sistema
    Define quién es quién, cómo se llama, dónde vive, qué rol tiene
    """
    
    def __init__(self):
        self.entities: Dict[str, CanonicalEntity] = {}  # canonical_id -> entity
        self._alias_index: Dict[str, str] = {}  # alias -> canonical_id
        self._directory_index: Dict[str, str] = {}  # dir_name -> canonical_id
        self._by_tier: Dict[str, Set[str]] = {"core": set(), "satellite": set()}
        self._by_role: Dict[str, Set[str]] = {}
        
        self._initialize_core_ontology()
    
    def _initialize_core_ontology(self):
        """Define la ontología canónica del sistema"""
        
        core_definitions = [
            # === RUNTIME CORE ===
            CanonicalEntity(
                canonical_id="router.main",
                entity_type=EntityType.CORE_MODULE,
                name="Message Router",
                aliases={"router", "message-router", "router-main"},
                directory_name="router",
                role="message_routing",
                tier="core",
                inputs={"plan.in", "event.in", "command.in", "result.in"},
                outputs={"plan.out", "event.out", "command.out", "result.out"},
                reserved_inputs={"command.in", "result.in", "event.in"},
                reserved_outputs={"plan.out", "command.out", "result.out"},
                description="Rutea mensajes entre módulos según blueprint"
            ),
            
            CanonicalEntity(
                canonical_id="agent.main",
                entity_type=EntityType.CORE_MODULE,
                name="Agent Core",
                aliases={"agent", "agent-core", "agent-main"},
                directory_name="agent",
                role="intent_processing",
                tier="core",
                inputs={"intent.in", "command.in", "memory.in"},
                outputs={"plan.out", "command.out", "memory.out"},
                reserved_inputs={"intent.in", "memory.in"},  # intent.in: recibir intenciones directas; memory.in: contexto externo
                reserved_outputs={"command.out", "memory.out"},  # command.out: comandos directos; memory.out: persistir estado
                description="Procesa intenciones y genera planes"
            ),
            
            CanonicalEntity(
                canonical_id="supervisor.main",
                entity_type=EntityType.CORE_MODULE,
                name="Task Supervisor",
                aliases={"supervisor", "task-supervisor", "supervisor-main"},
                directory_name="supervisor",
                role="task_lifecycle",
                tier="core",
                inputs={"plan.in", "result.in", "event.in", "approval.in"},
                outputs={"command.out", "event.out", "status.out"},
                reserved_inputs={"approval.in"},
                reserved_outputs={"command.out", "status.out"},
                description="Gestiona ciclo de vida de tareas y timeouts"
            ),
            
            CanonicalEntity(
                canonical_id="planner.main",
                entity_type=EntityType.CORE_MODULE,
                name="Plan Generator",
                aliases={"planner", "plan-generator", "planner-main", "planner.main"},
                directory_name="planner",
                role="plan_generation",
                tier="core",
                inputs={"intent.in", "context.in"},
                outputs={"plan.out", "event.out"},
                reserved_inputs={"context.in", "intent.in"},
                description="Genera planes ejecutables desde intenciones"
            ),
            
            CanonicalEntity(
                canonical_id="safety-guard.main",
                entity_type=EntityType.CORE_MODULE,
                name="Safety Guard",
                aliases={"safety", "safety-guard", "safety-guard-main", "safety.guard.main"},
                directory_name="safety-guard",
                role="safety_validation",
                tier="core",
                inputs={"plan.in", "command.in"},
                outputs={"blocked.plan.out", "approved.plan.out", "event.out"},
                reserved_inputs={"command.in"},
                description="Valida seguridad de planes y comandos"
            ),
            
            CanonicalEntity(
                canonical_id="approval.main",
                entity_type=EntityType.CORE_MODULE,
                name="Approval Manager",
                aliases={"approval", "approval-manager", "approval-main"},
                directory_name="approval",
                role="human_approval",
                tier="core",
                inputs={"blocked.plan.in", "ui.response.in", "signal.in"},
                outputs={"approved.plan.out", "event.out", "ui.request.out", "signal.out"},
                reserved_inputs={"ui.response.in", "signal.in"},
                reserved_outputs={"ui.request.out"},
                description="Gestiona flujos de aprobación humana"
            ),
            
            # === WORKERS ===
            CanonicalEntity(
                canonical_id="worker.python.desktop",
                entity_type=EntityType.WORKER,
                name="Desktop Worker (Python)",
                aliases={"desktop-worker", "worker-desktop", "worker.python.desktop"},
                directory_name="worker-python",
                role="desktop_automation",
                tier="satellite",
                inputs={"command.in"},
                outputs={"result.out", "event.out"},
                reserved_inputs={"command.in"},
                description="Automatización de interfaz de escritorio via Python"
            ),

            CanonicalEntity(
                canonical_id="worker.python.system",
                entity_type=EntityType.WORKER,
                name="System Worker (Python)",
                aliases={"system-worker", "worker-system", "worker.python.system"},
                directory_name="worker-system",
                role="system_commands",
                tier="satellite",
                inputs={"command.in"},
                outputs={"result.out", "event.out"},
                reserved_inputs={"command.in"},
                description="Ejecución de comandos del sistema via Python"
            ),

            CanonicalEntity(
                canonical_id="worker.python.browser",
                entity_type=EntityType.WORKER,
                name="Browser Worker (Python)",
                aliases={"browser-worker", "worker-browser", "worker.python.browser"},
                directory_name="worker-browser",
                role="browser_automation",
                tier="satellite",
                inputs={"command.in"},
                outputs={"result.out", "event.out"},
                reserved_inputs={"command.in"},
                description="Automatización de navegador via Python"
            ),

            CanonicalEntity(
                canonical_id="worker.python.terminal",
                entity_type=EntityType.WORKER,
                name="Terminal Worker (Python)",
                aliases={"python-terminal", "terminal-worker", "worker-terminal"},
                directory_name="worker.python.terminal",
                role="terminal_execution",
                tier="satellite",
                inputs={"command.in"},
                outputs={"result.out", "event.out"},
                reserved_inputs={"command.in"},
                description="Ejecución de comandos en terminal via Python"
            ),

            # === AI SERVICES ===
            CanonicalEntity(
                canonical_id="ai-assistant.main",
                entity_type=EntityType.AI_SERVICE,
                name="AI Assistant",
                aliases={"ai-assistant", "assistant", "ai", "ai.assistant.main"},
                directory_name="ai-assistant",
                role="llm_inference",
                tier="satellite",
                inputs={"prompt.in", "context.in"},
                outputs={"response.out", "result.out"},
                reserved_inputs={"context.in", "prompt.in"},
                reserved_outputs={"response.out"},
                description="Interfaz con LLM para generación de texto"
            ),

            CanonicalEntity(
                canonical_id="ai-intent.main",
                entity_type=EntityType.AI_SERVICE,
                name="Intent Parser",
                aliases={"ai-intent", "intent-parser", "intent", "ai.intent.main"},
                directory_name="ai-intent",
                role="intent_classification",
                tier="satellite",
                inputs={"text.in", "context.in"},
                outputs={"intent.out", "confidence.out"},
                reserved_inputs={"text.in", "context.in"},
                reserved_outputs={"confidence.out", "intent.out"},
                description="Clasifica intenciones desde texto natural"
            ),

            CanonicalEntity(
                canonical_id="ai-learning-engine.main",
                entity_type=EntityType.AI_SERVICE,
                name="Learning Engine",
                aliases={"ai-learning", "learning-engine", "learning", "ai.learning.engine.main"},
                directory_name="ai-learning-engine",
                role="pattern_learning",
                tier="satellite",
                inputs={"feedback.in", "result.in", "event.in"},
                outputs={"pattern.out", "model.out"},
                reserved_inputs={"result.in", "event.in", "feedback.in"},
                reserved_outputs={"model.out", "pattern.out"},
                description="Aprende patrones desde feedback"
            ),

            CanonicalEntity(
                canonical_id="ai-memory-semantic.main",
                entity_type=EntityType.AI_SERVICE,
                name="Semantic Memory",
                aliases={"ai-memory", "semantic-memory", "memory", "ai.memory.semantic.main"},
                directory_name="ai-memory-semantic",
                role="vector_storage",
                tier="satellite",
                inputs={"store.in", "query.in", "context.in"},
                outputs={"recall.out", "similar.out"},
                reserved_inputs={"context.in", "store.in", "query.in"},
                reserved_outputs={"similar.out", "recall.out"},
                description="Almacenamiento y recuperación semántica"
            ),

            CanonicalEntity(
                canonical_id="ai-self-audit.main",
                entity_type=EntityType.AI_SERVICE,
                name="Self Audit",
                aliases={"ai-audit", "self-audit", "audit", "ai.self.audit.main"},
                directory_name="ai-self-audit",
                role="self_reflection",
                tier="satellite",
                inputs={"event.in", "log.in"},
                outputs={"insight.out", "alert.out"},
                reserved_inputs={"event.in", "log.in"},
                reserved_outputs={"alert.out", "insight.out"},
                description="Auditoría automática del sistema"
            ),
            
            # === INTERFACES ===
            CanonicalEntity(
                canonical_id="telegram.main",
                entity_type=EntityType.INTERFACE,
                name="Telegram Interface",
                aliases={"telegram", "telegram-bot", "tg", "interface.telegram", "telegram.main"},
                directory_name="telegram-interface",
                role="user_interface",
                tier="satellite",
                inputs={"command.in", "response.in"},
                outputs={"intent.out", "ui.request.out"},
                reserved_inputs={"command.in"},
                reserved_outputs={"intent.out", "ui.request.out"},
                description="Interfaz de usuario via Telegram"
            ),

            CanonicalEntity(
                canonical_id="telegram-menu.main",
                entity_type=EntityType.INTERFACE,
                name="Telegram Menu",
                aliases={"telegram-menu", "tg-menu", "menu", "telegram.menu.main"},
                directory_name="telegram-menu",
                role="menu_interface",
                tier="satellite",
                inputs={"ui.response.in", "command.in"},
                outputs={"ui.request.out", "event.out"},
                reserved_inputs={"ui.response.in", "command.in"},
                reserved_outputs={"ui.request.out", "event.out"},
                description="Sistema de menús para Telegram"
            ),

            CanonicalEntity(
                canonical_id="telegram-hud.main",
                entity_type=EntityType.INTERFACE,
                name="Telegram HUD",
                aliases={"telegram-hud", "tg-hud", "hud", "telegram.hud.main"},
                directory_name="telegram-hud",
                role="status_display",
                tier="satellite",
                inputs={"status.in", "event.in"},
                outputs={"display.out"},
                reserved_inputs={"status.in", "event.in"},
                reserved_outputs={"display.out"},
                description="Heads-up display via Telegram"
            ),

            # === MEMORY & MENUS ===
            CanonicalEntity(
                canonical_id="memory-menu.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Memory Menu",
                aliases={"memory-menu", "mem-menu", "memory.menu.main"},
                directory_name="memory-menu",
                role="memory_interface",
                tier="satellite",
                inputs={"ui.response.in", "memory.in"},
                outputs={"ui.request.out", "memory.out"},
                reserved_inputs={"ui.response.in", "memory.in"},
                reserved_outputs={"ui.request.out", "memory.out"},
                description="Interfaz de menú para gestión de memoria"
            ),

            CanonicalEntity(
                canonical_id="apps-menu.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Apps Menu",
                aliases={"apps-menu", "app-menu", "apps.menu.main"},
                directory_name="apps-menu",
                role="app_interface",
                tier="satellite",
                inputs={"ui.response.in", "app.in"},
                outputs={"ui.request.out", "app.out"},
                reserved_inputs={"ui.response.in", "app.in"},
                reserved_outputs={"app.out", "ui.request.out"},
                description="Interfaz de menú para aplicaciones"
            ),

            CanonicalEntity(
                canonical_id="apps-session.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Apps Session",
                aliases={"apps-session", "session-manager", "apps.session.main"},
                directory_name="apps-session",
                role="session_management",
                tier="satellite",
                inputs={"app.in", "command.in"},
                outputs={"app.out", "event.out"},
                reserved_inputs={"app.in", "command.in"},
                reserved_outputs={"app.out"},
                description="Gestión de sesiones de aplicaciones"
            ),

            # === SYSTEM ===
            CanonicalEntity(
                canonical_id="system-menu.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="System Menu",
                aliases={"system-menu", "sys-menu", "system.menu.main"},
                directory_name="system-menu",
                role="system_interface",
                tier="satellite",
                inputs={"ui.response.in", "system.in"},
                outputs={"ui.request.out", "system.out"},
                reserved_inputs={"ui.response.in", "system.in"},
                reserved_outputs={"ui.request.out", "system.out"},
                description="Interfaz de menú para sistema"
            ),

            CanonicalEntity(
                canonical_id="guide.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="System Guide",
                aliases={"guide", "help", "system-guide"},
                directory_name="guide",
                role="documentation",
                tier="satellite",
                inputs={"query.in", "context.in"},
                outputs={"response.out", "ui.request.out"},
                reserved_inputs={"query.in"},
                reserved_outputs={"ui.request.out"},
                description="Guía interactiva del sistema"
            ),

            CanonicalEntity(
                canonical_id="project-audit.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Project Audit",
                aliases={"project-audit", "audit", "project-check", "project.audit.main"},
                directory_name="project-audit",
                role="project_analysis",
                tier="satellite",
                inputs={"project.in", "command.in"},
                outputs={"report.out", "event.out"},
                reserved_inputs={"command.in", "project.in"},
                reserved_outputs={"report.out"},
                description="Auditoría de proyectos"
            ),

            CanonicalEntity(
                canonical_id="interface.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Generic Interface",
                aliases={"interface", "generic-interface"},
                directory_name="interface",
                role="generic_io",
                tier="satellite",
                inputs={"command.in", "response.in", "ui.response.in"},
                outputs={"command.out"},
                reserved_inputs={"command.in", "ui.response.in"},  # Reservados para expansión de interfaz
                description="Interfaz genérica de comando"
            ),

            # === GAMIFICATION ===
            CanonicalEntity(
                canonical_id="gamification.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Gamification",
                aliases={"gamification", "game", "rewards"},
                directory_name="gamification",
                role="user_engagement",
                tier="satellite",
                inputs={"event.in", "achievement.in"},
                outputs={"reward.out", "badge.out"},
                reserved_inputs={"event.in", "achievement.in"},
                reserved_outputs={"reward.out", "badge.out"},
                description="Sistema de gamificación y recompensas"
            ),

            CanonicalEntity(
                canonical_id="verifier.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Contract Verifier",
                aliases={"verifier", "contract-verifier", "verifier.engine.main"},
                directory_name="verifier-engine",
                role="contract_validation",
                tier="satellite",
                inputs={"message.in", "schema.in"},
                outputs={"validation.out", "error.out"},
                reserved_inputs={"message.in", "schema.in"},
                reserved_outputs={"validation.out", "error.out"},
                description="Verificación de contratos de mensajes"
            ),
            
            # === DIAGNOSTIC (nuevos) ===
            CanonicalEntity(
                canonical_id="diagnostic.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="System Diagnostic",
                aliases={"diagnostic", "health-check", "system-check"},
                directory_name="diagnostic.main",
                role="system_health",
                tier="satellite",
                inputs={"event.in", "command.in", "result.in", "signal.in"},
                outputs={"event.out", "result.out"},
                description="Diagnóstico de salud del sistema"
            ),

            CanonicalEntity(
                canonical_id="chaos.tester",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Chaos Tester",
                aliases={"chaos", "chaos-tester", "tester"},
                directory_name="chaos.tester",
                role="chaos_engineering",
                tier="satellite",
                inputs={"command.in", "signal.in"},
                outputs={"event.out", "result.out", "command.out"},
                description="Testing activo y chaos engineering"
            ),

            # === ENTIDADES BLUEPRINT ESPECÍFICAS ===
            # (nombres alternativos usados en blueprint)
            CanonicalEntity(
                canonical_id="planner",
                entity_type=EntityType.CORE_MODULE,
                name="Planner (short name)",
                aliases={"planner", "planner-main"},
                directory_name="planner",
                role="plan_generation",
                tier="core",
                inputs={"intent.in", "context.in"},
                outputs={"plan.out", "event.out"},
                description="Alias corto para planner.main"
            ),

            CanonicalEntity(
                canonical_id="interface.telegram",
                entity_type=EntityType.INTERFACE,
                name="Telegram Interface (alt)",
                aliases={"interface.telegram", "telegram.interface"},
                directory_name="telegram-interface",
                role="user_interface",
                tier="satellite",
                inputs={"command.in", "response.in"},
                outputs={"intent.out", "ui.request.out"},
                reserved_inputs={"command.in"},
                reserved_outputs={"intent.out", "ui.request.out"},
                description="Alias de telegram.main para blueprint"
            ),

            CanonicalEntity(
                canonical_id="memory.log.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Memory Logger",
                aliases={"memory-log", "log-main", "memory.log"},
                directory_name="memory-log",
                role="logging",
                tier="satellite",
                inputs={"event.in", "log.in"},
                outputs={"log.out", "event.out"},
                reserved_inputs={"log.in"},
                reserved_outputs={"event.out", "log.out"},
                description="Logging de memoria"
            ),

            CanonicalEntity(
                canonical_id="coherence.analyzer",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Coherence Analyzer",
                aliases={"coherence", "coherence-analyzer"},
                directory_name="coherence.analyzer",
                role="coherence_analysis",
                tier="satellite",
                inputs={"command.in", "signal.in"},
                outputs={"event.out", "result.out", "report.out"},
                description="Análisis de coherencia entre planos"
            ),

            CanonicalEntity(
                canonical_id="ui.state.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="UI State Manager",
                aliases={"ui.state.main", "ui-state", "state"},
                directory_name="ui-state",
                role="state_management",
                tier="satellite",
                inputs={"event.in", "callback.in", "app.context.in", "state.in"},
                outputs={"event.out", "ui.state.out", "ui.render.request.out", "context.out"},
                reserved_inputs={"event.in", "callback.in", "app.context.in", "state.in"},
                reserved_outputs={"event.out", "ui.state.out", "ui.render.request.out", "context.out"},
                description="Gestión de estado de UI"
            ),

            CanonicalEntity(
                canonical_id="plan.runner.main",
                entity_type=EntityType.CORE_MODULE,
                name="Plan Runner",
                aliases={"plan.runner.main", "plan-runner", "runner"},
                directory_name="plan-runner",
                role="plan_execution",
                tier="core",
                inputs={"command.in", "memory.query.in", "event.in"},
                outputs={"command.out", "memory.query.out", "event.out", "ui.response.out"},
                reserved_inputs={"command.in", "memory.query.in", "event.in"},
                reserved_outputs={"command.out", "memory.query.out", "event.out", "ui.response.out"},
                description="Ejecución de planes"
            ),

            CanonicalEntity(
                canonical_id="phase.engine.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Phase Engine",
                aliases={"phase.engine.main", "phase-engine", "phase"},
                directory_name="phase-engine",
                role="phase_management",
                tier="satellite",
                inputs={"signal.in"},
                outputs={"signal.out", "command.out", "state.out", "plan.in", "event.out"},
                reserved_outputs={"plan.in"},
                description="Gestión de fases de ejecución"
            ),

            CanonicalEntity(
                canonical_id="verifier.engine.main",
                entity_type=EntityType.SATELLITE_MODULE,
                name="Verifier Engine",
                aliases={"verifier.engine.main", "verifier-engine", "verifier"},
                directory_name="verifier-engine",
                role="result_verification",
                tier="satellite",
                inputs={"result.in", "event.in"},
                outputs={"result.out", "verification.out", "event.out"},
                reserved_inputs={"event.in"},
                description="Verificación de resultados de workers"
            ),
        ]
        
        for entity in core_definitions:
            self._register_entity(entity)
    
    def _register_entity(self, entity: CanonicalEntity):
        """Registra una entidad en los índices"""
        self.entities[entity.canonical_id] = entity
        
        # Índice por tier
        self._by_tier[entity.tier].add(entity.canonical_id)
        
        # Índice por rol
        if entity.role:
            if entity.role not in self._by_role:
                self._by_role[entity.role] = set()
            self._by_role[entity.role].add(entity.canonical_id)
        
        # Índice de alias
        for alias in entity.aliases:
            self._alias_index[alias.lower()] = entity.canonical_id
        
        # Índice de directorio
        if entity.directory_name:
            self._directory_index[entity.directory_name] = entity.canonical_id
    
    def resolve(self, identifier: str) -> Optional[CanonicalEntity]:
        """
        Resuelve cualquier identificador a la entidad canónica
        Acepta: canonical_id, alias, directory_name
        """
        identifier = identifier.lower().strip()
        identifier_normalized = identifier.replace("-", ".")
        
        # Direct match
        if identifier_normalized in self.entities:
            return self.entities[identifier_normalized]
        
        # Alias match
        if identifier in self._alias_index:
            canonical_id = self._alias_index[identifier]
            return self.entities.get(canonical_id)
        
        # Directory match
        if identifier in self._directory_index:
            canonical_id = self._directory_index[identifier]
            return self.entities.get(canonical_id)
        
        # Try with hyphens
        if identifier.replace(".", "-") in self._directory_index:
            canonical_id = self._directory_index[identifier.replace(".", "-")]
            return self.entities.get(canonical_id)
        
        return None
    
    def get_by_tier(self, tier: str) -> List[CanonicalEntity]:
        """Retorna todas las entidades de un tier"""
        ids = self._by_tier.get(tier, set())
        return [self.entities[i] for i in ids if i in self.entities]
    
    def get_by_role(self, role: str) -> List[CanonicalEntity]:
        """Retorna todas las entidades con un rol"""
        ids = self._by_role.get(role, set())
        return [self.entities[i] for i in ids if i in self.entities]
    
    def get_all_canonical_ids(self) -> Set[str]:
        """Retorna todos los IDs canónicos"""
        return set(self.entities.keys())
    
    def validate_identifier(self, identifier: str) -> Dict:
        """Valida un identificador y reporta su estado en la ontología"""
        entity = self.resolve(identifier)
        
        if entity:
            return {
                "valid": True,
                "canonical_id": entity.canonical_id,
                "type": entity.entity_type.name,
                "tier": entity.tier,
                "role": entity.role,
                "aliases": list(entity.aliases),
                "directory": entity.directory_name
            }
        else:
            return {
                "valid": False,
                "identifier": identifier,
                "error": "Unknown entity - not in ontology",
                "suggestions": self._find_similar(identifier)
            }
    
    def _find_similar(self, identifier: str, max_suggestions: int = 3) -> List[str]:
        """Encuentra entidades similares para sugerencias"""
        identifier = identifier.lower()
        scores = []
        
        for canonical_id, entity in self.entities.items():
            # Simple string similarity
            names = [canonical_id] + list(entity.aliases) + [entity.directory_name]
            for name in names:
                # Common substring
                common = set(identifier) & set(name.lower())
                score = len(common) / max(len(identifier), len(name))
                scores.append((score, canonical_id))
        
        # Get top suggestions
        scores.sort(reverse=True)
        seen = set()
        suggestions = []
        for score, canonical_id in scores:
            if canonical_id not in seen and score > 0.3:
                seen.add(canonical_id)
                suggestions.append(canonical_id)
                if len(suggestions) >= max_suggestions:
                    break
        
        return suggestions
    
    def export_ontology(self) -> Dict:
        """Exporta la ontología completa como diccionario"""
        return {
            "entities": {
                k: {
                    "canonical_id": v.canonical_id,
                    "name": v.name,
                    "type": v.entity_type.name,
                    "aliases": list(v.aliases),
                    "directory_name": v.directory_name,
                    "role": v.role,
                    "tier": v.tier,
                    "inputs": list(v.inputs),
                    "outputs": list(v.outputs),
                    "description": v.description
                }
                for k, v in self.entities.items()
            },
            "tiers": {k: list(v) for k, v in self._by_tier.items()},
            "roles": {k: list(v) for k, v in self._by_role.items()},
            "indices": {
                "aliases": self._alias_index,
                "directories": self._directory_index
            }
        }
    
    def save_to_file(self, path: str):
        """Guarda la ontología a archivo JSON"""
        data = self.export_ontology()
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


# Singleton global
_ontology = None

def get_ontology() -> SystemOntology:
    """Retorna la ontología del sistema (singleton)"""
    global _ontology
    if _ontology is None:
        _ontology = SystemOntology()
    return _ontology


if __name__ == "__main__":
    # Test
    ont = get_ontology()
    
    print("=== ONTOLOGY TEST ===\n")
    
    # Test resolution
    test_ids = ["router.main", "router", "router-main", "supervisor", "unknown-module"]
    for test_id in test_ids:
        result = ont.validate_identifier(test_id)
        print(f"'{test_id}':")
        if result["valid"]:
            print(f"  ✓ Canonical: {result['canonical_id']}")
            print(f"  ✓ Type: {result['type']}, Tier: {result['tier']}")
            print(f"  ✓ Aliases: {result['aliases'][:3]}")
        else:
            print(f"  ✗ {result['error']}")
            print(f"  → Sugerencias: {result['suggestions']}")
        print()
    
    # Export
    ont.save_to_file(os.path.join(PROJECT_ROOT, "logs", "system_ontology.json"))
    print(f"✓ Ontología exportada a logs/system_ontology.json")
    print(f"✓ Total entidades: {len(ont.entities)}")
    print(f"✓ Core modules: {len(ont.get_by_tier('core'))}")
    print(f"✓ Satellite modules: {len(ont.get_by_tier('satellite'))}")
