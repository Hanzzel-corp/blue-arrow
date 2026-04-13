"""
Semantic Memory System - Memoria con embeddings para recuperación contextual
Sistema de memoria semántica que permite al agente recordar y aprender de interacciones previas.
"""

import json
import sys
import os
import hashlib
import math
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Any

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None
    print("WARN: numpy not available, using fallback embeddings", file=sys.stderr)

MODULE_ID = "ai.memory.semantic.main"


def safe_iso_now() -> str:
    return datetime.now().isoformat()


def generate_trace_id() -> str:
    return f"aims_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = CURRENT_DIR
MODULES_DIR = os.path.dirname(MODULE_DIR)
PROJECT_ROOT = os.path.dirname(MODULES_DIR)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from logger import StructuredLogger  # type: ignore[reportMissingImports]
except ModuleNotFoundError:
    class StructuredLogger:
        def __init__(self, name):
            self.name = name

        def info(self, msg):
            print(f"INFO: {msg}", file=sys.stderr)

        def error(self, msg):
            print(f"ERROR: {msg}", file=sys.stderr)

        def warning(self, msg):
            print(f"WARN: {msg}", file=sys.stderr)


logger = StructuredLogger(MODULE_ID)


def build_top_meta(meta: Optional[Dict] = None) -> Dict:
    base = {
        "source": "internal",
        "timestamp": safe_iso_now(),
        "module": MODULE_ID
    }
    if isinstance(meta, dict):
        base.update(meta)
    return base


def emit(port: str, payload: Optional[Dict] = None):
    """Emite mensaje JSON Lines a stdout."""
    payload = payload or {}
    trace_id = payload.get("trace_id") or generate_trace_id()
    meta = build_top_meta(payload.get("meta"))

    clean_payload = {
        k: v for k, v in payload.items()
        if k not in ("trace_id", "meta")
    }

    msg = {
        "module": MODULE_ID,
        "port": port,
        "trace_id": trace_id,
        "meta": meta,
        "payload": clean_payload
    }
    print(json.dumps(msg, ensure_ascii=False), flush=True)


def emit_result(task_id: str, status: str, result: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    """Emite resultado estandarizado."""
    emit("result.out", {
        "task_id": task_id,
        "status": status,
        "result": result,
        "meta": meta or {},
        "trace_id": trace_id or generate_trace_id()
    })


def emit_guaranteed_result(task_id: str, status: str, result: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    try:
        emit_result(task_id, status, result, meta, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Error emitiendo result.out: {e}")
        fallback = {
            "module": MODULE_ID,
            "port": "result.out",
            "trace_id": trace_id or generate_trace_id(),
            "meta": build_top_meta(meta),
            "payload": {
                "task_id": task_id,
                "status": "error",
                "result": {
                    "success": False,
                    "error": "emit_result_failed",
                    "detail": str(e),
                    "original_status": status
                }
            }
        }
        print(json.dumps(fallback, ensure_ascii=False), flush=True)


class SimpleEmbedding:
    """Generador simple de embeddings basado en hash/frecuencia."""

    def __init__(self, dim: int = 128):
        self.dim = dim

    def encode(self, text: str) -> List[float]:
        """Genera embedding simple sin dependencias externas."""
        if HAS_NUMPY:
            return self._encode_numpy(text)
        return self._encode_fallback(text)

    def _encode_numpy(self, text: str) -> List[float]:
        """Versión con numpy."""
        words = (text or "").lower().split()
        vector = np.zeros(self.dim)

        for i, word in enumerate(words):
            word_hash = hashlib.md5(word.encode("utf-8")).hexdigest()
            for j in range(min(8, self.dim)):
                idx = (i * 8 + j) % self.dim
                vector[idx] += int(word_hash[j * 2:j * 2 + 2], 16) / 255.0

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        return vector.tolist()

    def _encode_fallback(self, text: str) -> List[float]:
        """Versión sin numpy usando solo Python nativo."""
        words = (text or "").lower().split()
        vector = [0.0] * self.dim

        for i, word in enumerate(words):
            word_hash = hashlib.md5(word.encode("utf-8")).hexdigest()
            for j in range(min(8, self.dim)):
                idx = (i * 8 + j) % self.dim
                vector[idx] += int(word_hash[j * 2:j * 2 + 2], 16) / 255.0

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]

        return vector

    def similarity(self, v1: Sequence[float], v2: Sequence[float]) -> float:
        """Calcula similitud coseno entre dos vectores."""
        norm1 = math.sqrt(sum(x * x for x in v1))
        norm2 = math.sqrt(sum(x * x for x in v2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        dot = sum(x * y for x, y in zip(v1, v2))
        return dot / (norm1 * norm2)


class SemanticMemory:
    """Sistema de memoria semántica con embeddings."""

    def __init__(self, memory_path: str = "logs/semantic-memory.json"):
        self.memory_path = os.path.join(PROJECT_ROOT, memory_path)
        self.embedding = SimpleEmbedding(dim=128)
        self.memories: List[Dict] = []
        self.load_memory()

    def load_memory(self):
        """Carga memoria desde disco."""
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memories = data.get("memories", [])

                    for m in self.memories:
                        if "embedding" in m:
                            m["_vector"] = (
                                np.array(m["embedding"], dtype=float)
                                if HAS_NUMPY else
                                list(m["embedding"])
                            )

                logger.info(f"Memoria cargada: {len(self.memories)} recuerdos")
            except Exception as e:
                logger.error(f"Error cargando memoria: {e}")

    def save_memory(self):
        """Guarda memoria a disco."""
        try:
            memory_dir = os.path.dirname(self.memory_path)
            if memory_dir:
                os.makedirs(memory_dir, exist_ok=True)

            serializable_memories = []
            for m in self.memories:
                sm = m.copy()
                if "_vector" in sm:
                    if HAS_NUMPY and hasattr(sm["_vector"], "tolist"):
                        sm["embedding"] = sm["_vector"].tolist()
                    else:
                        sm["embedding"] = list(sm["_vector"])
                    del sm["_vector"]

                serializable_memories.append(sm)

            with open(self.memory_path, "w", encoding="utf-8") as f:
                json.dump({
                    "memories": serializable_memories,
                    "updated_at": safe_iso_now(),
                    "count": len(serializable_memories)
                }, f, indent=2, ensure_ascii=False)

            logger.info(f"Memoria guardada: {len(self.memories)} recuerdos")
        except Exception as e:
            logger.error(f"Error guardando memoria: {e}")

    def _public_memory(self, memory: Dict) -> Dict:
        return {
            "id": memory.get("id"),
            "content": memory.get("content"),
            "type": memory.get("type"),
            "metadata": memory.get("metadata", {}),
            "importance": memory.get("importance", 1.0),
            "timestamp": memory.get("timestamp"),
            "access_count": memory.get("access_count", 0)
        }

    def store(
        self,
        content: str,
        memory_type: str = "interaction",
        metadata: Optional[Dict] = None,
        importance: float = 1.0
    ) -> str:
        """Almacena un nuevo recuerdo."""
        content = (content or "").strip()
        if not content:
            raise ValueError("content vacío")

        vector = self.embedding.encode(content)

        memory_id = hashlib.md5(
            f"{content}{safe_iso_now()}".encode("utf-8")
        ).hexdigest()[:12]

        memory = {
            "id": memory_id,
            "content": content,
            "type": memory_type,
            "metadata": metadata or {},
            "importance": importance,
            "timestamp": safe_iso_now(),
            "access_count": 0,
            "_vector": np.array(vector, dtype=float) if HAS_NUMPY else list(vector),
            "embedding": list(vector)
        }

        self.memories.append(memory)

        if len(self.memories) > 1000:
            self.memories.sort(
                key=lambda m: (
                    m.get("importance", 1.0),
                    m.get("access_count", 0),
                    datetime.fromisoformat(m["timestamp"]).timestamp()
                ),
                reverse=True
            )
            self.memories = self.memories[:800]

        self.save_memory()
        return memory_id

    def search(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict]:
        """Busca recuerdos similares a la query."""
        if not self.memories:
            return []

        query = (query or "").strip()
        if not query:
            return []

        query_vector = self.embedding.encode(query)

        results = []
        for memory in self.memories:
            if "_vector" not in memory:
                embedding = memory.get("embedding", [])
                memory["_vector"] = (
                    np.array(embedding, dtype=float)
                    if HAS_NUMPY else
                    list(embedding)
                )

            similarity = self.embedding.similarity(query_vector, memory["_vector"])

            if similarity >= threshold:
                results.append({
                    "id": memory["id"],
                    "content": memory["content"],
                    "type": memory["type"],
                    "similarity": float(similarity),
                    "metadata": memory.get("metadata", {}),
                    "timestamp": memory["timestamp"],
                    "importance": memory.get("importance", 1.0)
                })

                memory["access_count"] = memory.get("access_count", 0) + 1

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def get_context(self, query: str, max_items: int = 3) -> str:
        """Obtiene contexto relevante como texto."""
        memories = self.search(query, top_k=max_items, threshold=0.2)

        if not memories:
            return ""

        context_parts = []
        for m in memories:
            context_parts.append(f"- {m['content'][:200]}")

        return "\n".join(context_parts)

    def get_recent(self, memory_type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Obtiene recuerdos recientes."""
        filtered = self.memories
        if memory_type:
            filtered = [m for m in filtered if m.get("type") == memory_type]

        sorted_memories = sorted(
            filtered,
            key=lambda m: datetime.fromisoformat(m["timestamp"]),
            reverse=True
        )

        return [self._public_memory(m) for m in sorted_memories[:limit]]

    def forget(self, memory_id: str) -> bool:
        """Elimina un recuerdo específico."""
        original_len = len(self.memories)
        self.memories = [m for m in self.memories if m.get("id") != memory_id]

        if len(self.memories) < original_len:
            self.save_memory()
            return True

        return False

    def stats(self) -> Dict:
        """Devuelve estadísticas de memoria."""
        type_counts: Dict[str, int] = {}
        total_access = 0

        for m in self.memories:
            memory_type = m.get("type", "unknown")
            type_counts[memory_type] = type_counts.get(memory_type, 0) + 1
            total_access += m.get("access_count", 0)

        return {
            "total_memories": len(self.memories),
            "types": type_counts,
            "total_access_count": total_access,
            "embedding_dim": self.embedding.dim
        }

    def clear(self) -> int:
        """Limpia toda la memoria."""
        count = len(self.memories)
        self.memories = []
        self.save_memory()
        return count


memory = SemanticMemory()


def extract_task_id(payload: Dict, meta: Dict) -> str:
    return (
        payload.get("task_id")
        or payload.get("plan_id")
        or meta.get("task_id")
        or meta.get("plan_id")
        or f"memory_{int(datetime.now().timestamp())}"
    )


def handle_action(payload: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    action = payload.get("action")
    params = payload.get("params", {}) or {}
    meta = meta or {}
    task_id = extract_task_id(payload, meta)

    try:
        if action == "memory.store":
            memory_id = memory.store(
                content=params.get("content", ""),
                memory_type=params.get("memory_type", "interaction"),
                metadata=params.get("metadata", {}),
                importance=float(params.get("importance", 1.0))
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "memory_id": memory_id,
                "message": "Memoria almacenada"
            }, meta, trace_id=trace_id)

        elif action == "memory.search":
            results = memory.search(
                query=params.get("query", ""),
                top_k=int(params.get("top_k", 5)),
                threshold=float(params.get("threshold", 0.3))
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "results": results
            }, meta, trace_id=trace_id)

        elif action == "memory.context":
            context = memory.get_context(
                query=params.get("query", ""),
                max_items=int(params.get("max_items", 3))
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "context": context
            }, meta, trace_id=trace_id)

        elif action == "memory.recent":
            recent = memory.get_recent(
                memory_type=params.get("memory_type"),
                limit=int(params.get("limit", 10))
            )
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "recent": recent
            }, meta, trace_id=trace_id)

        elif action == "memory.forget":
            forgotten = memory.forget(params.get("memory_id", ""))
            emit_guaranteed_result(task_id, "success", {
                "success": forgotten,
                "forgotten": forgotten
            }, meta, trace_id=trace_id)

        elif action == "memory.stats":
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "stats": memory.stats()
            }, meta, trace_id=trace_id)

        elif action == "memory.clear":
            removed = memory.clear()
            emit_guaranteed_result(task_id, "success", {
                "success": True,
                "removed": removed
            }, meta, trace_id=trace_id)

        else:
            emit_guaranteed_result(task_id, "error", {
                "success": False,
                "error": f"Acción no soportada: {action}"
            }, meta, trace_id=trace_id)

    except Exception as e:
        logger.error(f"Error procesando acción {action}: {e}")
        emit_guaranteed_result(task_id, "error", {
            "success": False,
            "error": str(e)
        }, meta, trace_id=trace_id)


def handle_query(payload: Dict, meta: Optional[Dict] = None, trace_id: Optional[str] = None):
    meta = meta or {}
    task_id = extract_task_id(payload, meta)

    try:
        emit_guaranteed_result(task_id, "success", {
            "success": True,
            "stats": memory.stats(),
            "recent": memory.get_recent(limit=5)
        }, meta, trace_id=trace_id)
    except Exception as e:
        logger.error(f"Error procesando query: {e}")
        emit_guaranteed_result(task_id, "error", {
            "success": False,
            "error": str(e)
        }, meta, trace_id=trace_id)


def main():
    logger.info(f"Semantic Memory Module iniciado - {MODULE_ID}")

    emit("event.out", {
        "level": "info",
        "type": "semantic_memory_ready",
        "module": MODULE_ID,
        "trace_id": generate_trace_id()
    })

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
            port = msg.get("port")
            payload = msg.get("payload", {}) or {}
            top_meta = msg.get("meta", {}) or {}
            payload_meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
            meta = {**top_meta, **payload_meta}
            trace_id = msg.get("trace_id") or payload.get("trace_id") or generate_trace_id()

            if port == "action.in":
                handle_action(payload, meta=meta, trace_id=trace_id)
            elif port == "query.in":
                handle_query(payload, meta=meta, trace_id=trace_id)

        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido: {e}")
            emit("event.out", {
                "level": "error",
                "type": "semantic_memory_invalid_json",
                "error": str(e),
                "trace_id": generate_trace_id()
            })
        except Exception as e:
            logger.error(f"Error leyendo mensaje: {e}")
            emit("event.out", {
                "level": "error",
                "type": "semantic_memory_error",
                "error": str(e),
                "trace_id": generate_trace_id()
            })


if __name__ == "__main__":
    main()
