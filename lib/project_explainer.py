#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except Exception:
    tomllib = None


SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "coverage",
    "target",
    "out",
    "bin",
    "obj",
    ".cache",
    ".pytest_cache",
}

AUXILIARY_DIRS = {
    "tools",
    "scripts",
    "script",
    "analysis",
    "analisis",
    "tmp",
    "temp",
    "bench",
    "benchmarks",
    "tests",
    "test",
}

AUXILIARY_FILENAMES = {
    "project_explainer.py",
    "analyze.py",
    "analysis.py",
    "inspect.py",
    "scanner.py",
    "audit.py",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".php", ".rb",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".json", ".toml", ".yaml", ".yml",
    ".md", ".txt", ".html", ".css", ".scss", ".xml", ".sh", ".log"
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".php", ".rb",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".sh"
}

EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/React",
    ".jsx": "JavaScript/React",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".html": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
}

STRONG_AI_KEYWORDS = {
    "openai",
    "anthropic",
    "langchain",
    "llama",
    "ollama",
    "transformers",
    "torch",
    "tensorflow",
    "keras",
    "huggingface",
    "sentence_transformers",
    "embeddings",
    "faiss",
    "chromadb",
    "pinecone",
    "weaviate",
    "rag",
    "llm",
    "machine learning",
    "deep learning",
    "neural network",
    "copilot",
}

WEAK_AI_KEYWORDS = {
    "agent",
    "agents",
    "memory",
    "planner",
    "model",
    "intent",
}

FRAMEWORK_HINTS = {
    "react": "React",
    "next": "Next.js",
    "next.js": "Next.js",
    "express": "Express",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "electron": "Electron",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "nestjs": "NestJS",
    "playwright": "Playwright",
    "selenium": "Selenium",
    "discord.js": "Discord Bot",
    "telegraf": "Telegram Bot",
    "python-telegram-bot": "Telegram Bot",
    "aiogram": "Telegram Bot",
}


def safe_read_text(path: Path, limit: int = 200_000) -> str:
    try:
        data = path.read_bytes()
        if len(data) > limit:
            data = data[:limit]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def is_hidden_or_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def is_auxiliary_path(root: Path, path: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except Exception:
        rel = path

    if path.name.lower() in AUXILIARY_FILENAMES:
        return True

    return any(part.lower() in AUXILIARY_DIRS for part in rel.parts)


def iter_project_files(root: Path):
    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        if is_hidden_or_skipped(current_path):
            continue

        for fname in files:
            path = current_path / fname
            if is_hidden_or_skipped(path):
                continue
            yield path


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_toml_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or tomllib is None:
        return None
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def top_lines(text: str, max_lines: int = 10) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:max_lines]


def normalize_dep_name(dep: str) -> str:
    dep = dep.strip()
    dep = re.split(r"[<>=~! \[\];]", dep, maxsplit=1)[0].strip()
    return dep


def detect_name(root: Path, package_json: dict[str, Any] | None, pyproject: dict[str, Any] | None) -> str:
    if package_json and isinstance(package_json.get("name"), str):
        return package_json["name"]

    if pyproject:
        project = pyproject.get("project")
        if isinstance(project, dict) and isinstance(project.get("name"), str):
            return project["name"]

        poetry = pyproject.get("tool", {}).get("poetry", {})
        if isinstance(poetry, dict) and isinstance(poetry.get("name"), str):
            return poetry["name"]

    return root.name


def detect_description(
    readme_text: str,
    package_json: dict[str, Any] | None,
    pyproject: dict[str, Any] | None,
    name: str
) -> str:
    if package_json and isinstance(package_json.get("description"), str) and package_json["description"].strip():
        return package_json["description"].strip()

    if pyproject:
        project = pyproject.get("project")
        if isinstance(project, dict) and isinstance(project.get("description"), str):
            desc = project["description"].strip()
            if desc:
                return desc

        poetry = pyproject.get("tool", {}).get("poetry", {})
        if isinstance(poetry, dict) and isinstance(poetry.get("description"), str):
            desc = poetry["description"].strip()
            if desc:
                return desc

    if readme_text:
        for line in top_lines(readme_text, 30):
            if line.startswith("#"):
                continue
            if len(line) >= 30:
                return line

    return f"Proyecto llamado {name}."


def detect_file_stats(root: Path) -> tuple[Counter, list[Path]]:
    ext_counter: Counter = Counter()
    files: list[Path] = []

    for path in iter_project_files(root):
        if is_auxiliary_path(root, path):
            continue
        files.append(path)
        ext_counter[path.suffix.lower()] += 1

    return ext_counter, files


def detect_primary_language(ext_counter: Counter) -> str:
    language_counter: Counter = Counter()

    for ext, count in ext_counter.items():
        lang = EXTENSION_TO_LANGUAGE.get(ext)
        if lang:
            language_counter[lang] += count

    if not language_counter:
        return "No determinado"

    return language_counter.most_common(1)[0][0]


def collect_dependencies(root: Path) -> dict[str, list[str]]:
    deps: dict[str, list[str]] = defaultdict(list)

    package_json = load_json_if_exists(root / "package.json")
    if package_json:
        for section in ("dependencies", "devDependencies", "peerDependencies"):
            block = package_json.get(section, {})
            if isinstance(block, dict):
                deps["node"].extend(block.keys())

    pyproject = load_toml_if_exists(root / "pyproject.toml")
    if pyproject:
        project = pyproject.get("project", {})
        if isinstance(project, dict):
            for item in project.get("dependencies", []) or []:
                deps["python"].append(normalize_dep_name(str(item)))

        poetry = pyproject.get("tool", {}).get("poetry", {})
        if isinstance(poetry, dict):
            poetry_deps = poetry.get("dependencies", {})
            if isinstance(poetry_deps, dict):
                deps["python"].extend(poetry_deps.keys())

    requirements = root / "requirements.txt"
    if requirements.exists():
        for line in requirements.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            deps["python"].append(normalize_dep_name(line))

    cargo = root / "Cargo.toml"
    if cargo.exists() and tomllib is not None:
        data = load_toml_if_exists(cargo) or {}
        for section in ("dependencies", "dev-dependencies"):
            block = data.get(section, {})
            if isinstance(block, dict):
                deps["rust"].extend(block.keys())

    return {k: sorted(set(v), key=str.lower) for k, v in deps.items()}


def detect_frameworks(deps: dict[str, list[str]], files: list[Path]) -> list[str]:
    found = set()
    dep_set = {d.lower() for group in deps.values() for d in group}

    for dep, label in FRAMEWORK_HINTS.items():
        if dep in dep_set:
            found.add(label)

    file_names = {p.name.lower() for p in files}
    if "manage.py" in file_names:
        found.add("Django")
    if "main.py" in file_names and any("telegram" in p.as_posix().lower() for p in files):
        found.add("Telegram Bot")

    return sorted(found)


def load_readme(root: Path) -> str:
    for candidate in ("README.md", "readme.md", "README.txt", "README"):
        p = root / candidate
        if p.exists():
            return safe_read_text(p)
    return ""


def load_blueprint(root: Path) -> dict[str, Any] | None:
    return load_json_if_exists(root / "blueprints" / "system.v0.json")


def find_manifest_paths(root: Path) -> list[Path]:
    modules_root = root / "modules"
    if not modules_root.exists():
        return []

    out: list[Path] = []
    for current_root, dirs, files in os.walk(modules_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if fname == "manifest.json":
                out.append(Path(current_root) / fname)
    return sorted(out)


def load_manifests(root: Path) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for manifest_path in find_manifest_paths(root):
        data = load_json_if_exists(manifest_path)
        if not data:
            continue
        module_id = data.get("id")
        if isinstance(module_id, str):
            manifests[module_id] = {
                "manifest_path": str(manifest_path.relative_to(root)),
                "entry": data.get("entry"),
                "inputs": data.get("inputs") if isinstance(data.get("inputs"), list) else [],
                "outputs": data.get("outputs") if isinstance(data.get("outputs"), list) else [],
                "raw": data,
            }
    return manifests


def classify_module_role(module_id: str, manifest: dict[str, Any]) -> str:
    mid = module_id.lower()

    exact_rules: list[tuple[str, list[str]]] = [
        ("Menú UI", ["telegram.menu", "system.menu", "memory.menu", ".menu."]),
        ("Router / orquestación", ["router."]),
        ("Supervisor", ["supervisor."]),
        ("Seguridad / safety", ["safety.", "guard."]),
        ("Aprobación", ["approval."]),
        ("Memoria / logs", ["memory.", ".log."]),
        ("Auditoría", ["audit."]),
        ("Intención / análisis", ["intent.", "analysis."]),
        ("Interfaz", ["interface.", "telegram-interface"]),
        ("Worker de ejecución", ["worker."]),
        ("Agente / planificación", ["agent."]),
    ]

    for role, needles in exact_rules:
        if any(n in mid for n in needles):
            return role

    haystack = " ".join([
        str(manifest.get("entry") or ""),
        " ".join(str(x) for x in (manifest.get("inputs") or [])),
        " ".join(str(x) for x in (manifest.get("outputs") or [])),
    ]).lower()

    fallback_rules: list[tuple[str, list[str]]] = [
        ("Menú UI", ["menu"]),
        ("Router / orquestación", ["router"]),
        ("Supervisor", ["supervisor"]),
        ("Seguridad / safety", ["safety", "guard"]),
        ("Aprobación", ["approval"]),
        ("Memoria / logs", ["memory", "log"]),
        ("Auditoría", ["audit"]),
        ("Intención / análisis", ["intent", "analysis"]),
        ("Interfaz", ["interface", "telegram", "cli", "webui"]),
        ("Worker de ejecución", ["worker", "desktop", "browser", "system"]),
        ("Agente / planificación", ["agent", "plan"]),
    ]

    for role, tokens in fallback_rules:
        if any(token in haystack for token in tokens):
            return role

    return "Módulo general"


def group_modules_by_role(manifests: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for module_id, manifest in manifests.items():
        grouped[classify_module_role(module_id, manifest)].append(module_id)

    return {role: sorted(ids) for role, ids in sorted(grouped.items(), key=lambda kv: kv[0])}


def infer_structure(root: Path, files: list[Path]) -> list[str]:
    top_level = defaultdict(int)
    for f in files:
        rel = f.relative_to(root)
        if len(rel.parts) >= 2:
            top_level[rel.parts[0]] += 1

    ordered = sorted(top_level.items(), key=lambda x: (-x[1], x[0]))
    return [f"{name} ({count} archivos)" for name, count in ordered[:10]]


def weak_signal_allowed(root: Path, path: Path) -> bool:
    rel = path.relative_to(root).as_posix().lower()

    if path.suffix.lower() not in CODE_EXTENSIONS:
        return False
    if rel.endswith("manifest.json"):
        return False
    if "project_status" in rel:
        return False
    if "/telegram-menu/" in rel or "/system-menu/" in rel or "/memory-menu/" in rel:
        return False
    if "/project-audit/" in rel:
        return False
    if "/telegram-interface/" in rel:
        return False
    if "/memory-log/" in rel:
        return False
    if "/worker-system/" in rel:
        return False
    if "/approval/" in rel:
        return False

    return True


def detect_ai_usage(root: Path, deps: dict[str, list[str]], files: list[Path], readme_text: str) -> dict[str, Any]:
    strong_evidence: list[str] = []
    weak_evidence: list[str] = []

    dep_set = {d.lower() for group in deps.values() for d in group}

    for dep in sorted(dep_set):
        for kw in STRONG_AI_KEYWORDS:
            if kw in dep:
                strong_evidence.append(f"Dependencia relacionada con IA: {dep}")
                break

    if readme_text:
        lower = readme_text.lower()
        for kw in sorted(STRONG_AI_KEYWORDS):
            if kw in lower:
                strong_evidence.append(f"README menciona: {kw}")

    checked = 0
    weak_checked = 0

    for path in files:
        if checked >= 120:
            break
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        text = safe_read_text(path, limit=40_000).lower()
        checked += 1

        matched_strong = False
        for kw in (
            "openai", "anthropic", "langchain", "ollama", "transformers",
            "torch", "tensorflow", "huggingface", "llm", "embeddings",
            "rag", "faiss", "chromadb", "pinecone", "weaviate"
        ):
            if kw in text:
                strong_evidence.append(f"Archivo {path.relative_to(root)} contiene: {kw}")
                matched_strong = True
                break

        if matched_strong:
            continue

        if weak_checked >= 40 or not weak_signal_allowed(root, path):
            continue

        weak_checked += 1
        for kw in WEAK_AI_KEYWORDS:
            if kw in text:
                weak_evidence.append(f"Archivo {path.relative_to(root)} contiene término genérico: {kw}")
                break

    strong_evidence = list(dict.fromkeys(strong_evidence))[:12]
    weak_evidence = list(dict.fromkeys(weak_evidence))[:6]

    uses_ai = len(strong_evidence) > 0
    if len(strong_evidence) >= 3:
        confidence = "alta"
    elif len(strong_evidence) >= 1:
        confidence = "media"
    else:
        confidence = "baja"

    if not uses_ai:
        weak_evidence = []
        note = "No se encontraron dependencias ni señales fuertes de IA real en el proyecto."
    else:
        note = None

    return {
        "uses_ai": uses_ai,
        "confidence": confidence,
        "evidence": strong_evidence,
        "weak_signals": weak_evidence,
        "note": note,
    }


def split_endpoint(endpoint: str) -> tuple[str | None, str | None]:
    parts = str(endpoint or "").split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], None
    return None, None


def build_architecture_description(
    blueprint: dict[str, Any] | None,
    manifests: dict[str, dict[str, Any]],
    frameworks: list[str],
) -> str:
    if not blueprint or not manifests:
        return ""

    module_ids = {m.lower() for m in manifests.keys()}

    has_interface = any("interface" in m for m in module_ids)
    has_agent = any("agent" in m for m in module_ids)
    has_safety = any("safety" in m or "guard" in m for m in module_ids)
    has_approval = any("approval" in m for m in module_ids)
    has_router = any("router" in m for m in module_ids)
    has_worker = any("worker" in m for m in module_ids)
    has_supervisor = any("supervisor" in m for m in module_ids)
    has_memory = any("memory" in m or "log" in m for m in module_ids)
    has_audit = any("audit" in m for m in module_ids)
    has_telegram = any("telegram" in m for m in module_ids) or ("Telegram Bot" in frameworks)

    subject = "Sistema modular"
    if has_telegram:
        subject = "Sistema modular orientado a recibir comandos desde interfaces como Telegram"
    elif has_interface:
        subject = "Sistema modular orientado a recibir comandos desde distintas interfaces"

    clauses = []
    if has_agent:
        clauses.append("procesarlos en un agente o planificador")
    if has_safety:
        clauses.append("validarlos con una capa de safety")
    if has_approval:
        clauses.append("aplicar aprobación manual cuando hace falta")
    if has_router:
        clauses.append("enrutarlos hacia distintos módulos")
    if has_worker:
        clauses.append("ejecutar acciones en desktop, sistema o navegador")
    if has_supervisor:
        clauses.append("supervisar el estado de las tareas")
    if has_memory:
        clauses.append("registrar memoria operativa y eventos")
    if has_audit:
        clauses.append("auditar la arquitectura y las conexiones")

    if not clauses:
        return "Sistema modular basado en componentes conectados por puertos."

    if len(clauses) == 1:
        return f"{subject}, diseñado para {clauses[0]}."

    return f"{subject}, diseñado para {', '.join(clauses[:-1])} y {clauses[-1]}."


def summarize_architecture(
    blueprint: dict[str, Any] | None,
    manifests: dict[str, dict[str, Any]],
    frameworks: list[str],
) -> dict[str, Any]:
    if not blueprint:
        return {
            "modules_count": 0,
            "connections_count": 0,
            "roles": {},
            "flow_summary": "No se encontró blueprint de arquitectura.",
            "key_flows": [],
        }

    modules = blueprint.get("modules", []) if isinstance(blueprint.get("modules"), list) else []
    connections = blueprint.get("connections", []) if isinstance(blueprint.get("connections"), list) else []
    roles = group_modules_by_role(manifests)
    flow_summary = build_architecture_description(blueprint, manifests, frameworks)

    key_flows = []
    interesting_pairs = [
        ("interface", "agent"),
        ("interface", "router"),
        ("agent", "safety"),
        ("safety", "approval"),
        ("safety", "router"),
        ("approval", "router"),
        ("approval", "supervisor"),
        ("router", "worker"),
        ("worker", "interface"),
        ("worker", "supervisor"),
        ("audit", "interface"),
    ]

    for conn in connections:
        from_ep = conn.get("from")
        to_ep = conn.get("to")
        if not isinstance(from_ep, str) or not isinstance(to_ep, str):
            continue

        from_mod, _ = split_endpoint(from_ep)
        to_mod, _ = split_endpoint(to_ep)
        if not from_mod or not to_mod:
            continue

        low_from = from_mod.lower()
        low_to = to_mod.lower()

        for a, b in interesting_pairs:
            if a in low_from and b in low_to:
                key_flows.append(f"{from_ep} -> {to_ep}")
                break

    return {
        "modules_count": len(modules),
        "connections_count": len(connections),
        "roles": roles,
        "flow_summary": flow_summary,
        "key_flows": list(dict.fromkeys(key_flows))[:12],
    }


def detect_project_type(
    deps: dict[str, list[str]],
    files: list[Path],
    readme_text: str,
    blueprint: dict[str, Any] | None,
    manifests: dict[str, dict[str, Any]],
) -> str:
    dep_set = {d.lower() for group in deps.values() for d in group}
    file_names = {p.name.lower() for p in files}
    readme_lower = readme_text.lower()

    if blueprint and manifests:
        module_ids = set(manifests.keys())
        if any("router" in m for m in module_ids) and any("worker" in m for m in module_ids):
            return "Orquestador modular / sistema de automatización por eventos"

    if {"electron"} & dep_set:
        return "Aplicación de escritorio"
    if {"react", "next", "vue", "nuxt"} & dep_set:
        if {"express", "fastapi", "flask", "django", "nestjs"} & dep_set:
            return "Aplicación web full stack"
        return "Frontend web"
    if {"express", "fastapi", "flask", "django", "nestjs"} & dep_set:
        return "Backend / API"
    if "docker-compose.yml" in file_names or "docker-compose.yaml" in file_names:
        return "Sistema multi-servicio"
    if "package.json" in file_names and "bin" in file_names:
        return "CLI / herramienta"
    if "telegram" in readme_lower or "bot" in readme_lower or {"telegraf", "aiogram", "python-telegram-bot"} & dep_set:
        return "Bot / automatización"

    return "Proyecto de software"


def summarize_idea(
    name: str,
    description: str,
    project_type: str,
    primary_language: str,
    frameworks: list[str],
    ai_usage: dict[str, Any],
    architecture: dict[str, Any],
) -> str:
    parts = [
        f"{name} parece ser un {project_type.lower()} hecho principalmente en {primary_language.lower()}."
    ]

    if frameworks:
        parts.append(f"Integra {', '.join(frameworks[:4])}.")

    flow_summary = architecture.get("flow_summary", "")
    if flow_summary and architecture.get("modules_count", 0) > 0:
        parts.append(flow_summary)
    elif description:
        parts.append(f"Su idea principal sería: {description}")

    if ai_usage["uses_ai"]:
        parts.append("Hay evidencia concreta de integración de IA.")
    else:
        parts.append("No muestra evidencia fuerte de IA como núcleo; se comporta más como una arquitectura modular de automatización.")

    return " ".join(parts)


def analyze_project(root: Path) -> dict[str, Any]:
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"La ruta no existe o no es carpeta: {root}")

    ext_counter, files = detect_file_stats(root)
    package_json = load_json_if_exists(root / "package.json")
    pyproject = load_toml_if_exists(root / "pyproject.toml")
    readme_text = load_readme(root)
    blueprint = load_blueprint(root)
    manifests = load_manifests(root)

    name = detect_name(root, package_json, pyproject)
    description = detect_description(readme_text, package_json, pyproject, name)
    dependencies = collect_dependencies(root)
    primary_language = detect_primary_language(ext_counter)
    frameworks = detect_frameworks(dependencies, files)
    architecture = summarize_architecture(blueprint, manifests, frameworks)
    project_type = detect_project_type(dependencies, files, readme_text, blueprint, manifests)
    ai_usage = detect_ai_usage(root, dependencies, files, readme_text)
    structure = infer_structure(root, files)

    if description == f"Proyecto llamado {name}." and architecture.get("flow_summary"):
        description = architecture["flow_summary"]

    top_extensions = [
        {"extension": ext or "[sin extensión]", "count": count}
        for ext, count in ext_counter.most_common(10)
    ]

    report = {
        "project_name": name,
        "description": description,
        "idea_summary": summarize_idea(
            name=name,
            description=description,
            project_type=project_type,
            primary_language=primary_language,
            frameworks=frameworks,
            ai_usage=ai_usage,
            architecture=architecture,
        ),
        "project_type": project_type,
        "primary_language": primary_language,
        "frameworks": frameworks,
        "dependencies": dependencies,
        "structure": structure,
        "top_extensions": top_extensions,
        "architecture": architecture,
        "manifests_found": len(manifests),
        "ai_usage": ai_usage,
        "file_count": len(files),
        "root": str(root.resolve()),
    }
    return report


def render_human(report: dict[str, Any]) -> str:
    lines = []
    lines.append("=== EXPLICADOR DE PROYECTO ===")
    lines.append(f"Nombre: {report['project_name']}")
    lines.append(f"Ruta: {report['root']}")
    lines.append(f"Tipo: {report['project_type']}")
    lines.append(f"Lenguaje principal: {report['primary_language']}")
    lines.append(f"Archivos analizados: {report['file_count']}")
    lines.append(f"Manifests detectados: {report['manifests_found']}")
    lines.append("")

    lines.append("De qué se trata:")
    lines.append(report["description"])
    lines.append("")

    lines.append("Resumen tipo idea:")
    lines.append(report["idea_summary"])
    lines.append("")

    arch = report.get("architecture", {})
    if arch.get("modules_count", 0) > 0:
        lines.append("Arquitectura:")
        lines.append(f"- Módulos declarados en blueprint: {arch.get('modules_count', 0)}")
        lines.append(f"- Conexiones declaradas: {arch.get('connections_count', 0)}")
        lines.append(f"- Flujo inferido: {arch.get('flow_summary', 'No disponible')}")
        lines.append("")

    roles = arch.get("roles", {})
    if roles:
        lines.append("Roles de módulos:")
        for role, modules in roles.items():
            shown = ", ".join(modules[:6])
            extra = "" if len(modules) <= 6 else f" (+{len(modules) - 6} más)"
            lines.append(f"- {role}: {shown}{extra}")
        lines.append("")

    if arch.get("key_flows"):
        lines.append("Flujos clave detectados:")
        for item in arch["key_flows"][:10]:
            lines.append(f"- {item}")
        lines.append("")

    if report["frameworks"]:
        lines.append("Tecnologías detectadas:")
        for item in report["frameworks"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("Estructura principal:")
    for item in report["structure"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("Extensiones más comunes:")
    for item in report["top_extensions"]:
        lines.append(f"- {item['extension']}: {item['count']}")
    lines.append("")

    ai = report["ai_usage"]
    lines.append(f"¿Usa IA?: {'Sí' if ai['uses_ai'] else 'No evidente'}")
    lines.append(f"Confianza: {ai['confidence']}")

    if ai["evidence"]:
        lines.append("Evidencia fuerte:")
        for ev in ai["evidence"]:
            lines.append(f"- {ev}")

    if ai.get("weak_signals"):
        lines.append("Señales débiles:")
        for ev in ai["weak_signals"]:
            lines.append(f"- {ev}")

    if ai.get("note"):
        lines.append(f"Nota: {ai['note']}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Explica de qué trata un proyecto de software.")
    parser.add_argument("path", nargs="?", default=".", help="Ruta del proyecto")
    parser.add_argument("--json", action="store_true", help="Salida en JSON")
    args = parser.parse_args()

    try:
        root = Path(args.path).resolve()
        report = analyze_project(root)

        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_human(report))

        return 0
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())