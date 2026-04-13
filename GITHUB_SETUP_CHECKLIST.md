# Checklist: Preparación para GitHub

> Lista de verificación para publicar `blue-arrow` como repositorio público en GitHub.
>
> **Nota:** El repositorio público se llama `blue-arrow`, pero el nombre interno del proyecto sigue siendo `blueprint-v0`.

---

## 🔴 Crítico (Bloqueante)

| # | Item | Estado | Acción |
|---|------|--------|--------|
| 1 | **Crear `.gitignore` correcto** | ❌ FALTA | Ignorar `.env`, `.venv/`, `node_modules/`, `logs/`, `__pycache__/`, archivos temporales y estado local |
| 2 | **Revisión de secretos y archivos sensibles** | ❌ FALTA | Verificar que no se suban tokens, credenciales, `.env`, logs, archivos locales o datos privados |
| 3 | **Archivo LICENSE completo** | ❌ FALTA | Crear `LICENSE` con el texto íntegro de MIT License |
| 4 | **README.md revisado** | ⚠️ VERIFICAR | Confirmar que el README refleje el estado actual del proyecto sin exagerar capacidades |
| 5 | **package.json completo** | ⚠️ INCOMPLETO | Agregar: `description`, `author`, `license`, `repository`, `keywords` |
| 6 | **Inicializar repositorio Git después de limpiar el proyecto** | ❌ FALTA | Recién después de preparar `.gitignore`, revisar secretos y validar archivos base |

---

## 🟡 Importante (Recomendado)

| # | Item | Estado | Acción |
|---|------|--------|--------|
| 7 | **`.env.example`** | ❌ FALTA | Crear archivo de ejemplo con variables necesarias, sin valores reales |
| 8 | **CONTRIBUTING.md** | ❌ FALTA | Guía para contribuidores (puede ser simple) |
| 9 | **Issue Templates** | ❌ FALTA | Crear `.github/ISSUE_TEMPLATE/bug_report.md` y `feature_request.md` |
| 10 | **Pull Request Template** | ❌ FALTA | Crear `.github/pull_request_template.md` |
| 11 | **README.md - badges** | ⚠️ VERIFICAR | Revisar si los badges genéricos necesitan update post-publicación |
| 12 | **requirements.txt / constraints** | ⚠️ EVALUAR | Definir si querés versiones fijas, rangos o constraints separadas |
| 13 | **pyproject.toml metadata** | ⚠️ RECOMENDADO | Completar `[project]` si querés metadata Python más formal |

---

## 🟢 Opcional (Nice to have)

| # | Item | Estado | Acción |
|---|------|--------|--------|
| 14 | **GitHub Actions CI** | ❌ FALTA | Workflow básico para tests: `.github/workflows/ci.yml` |
| 15 | **CODE_OF_CONDUCT.md** | ❌ FALTA | Código de conducta estándar |
| 16 | **SECURITY.md** | ❌ FALTA | Política de seguridad / reporte de vulnerabilidades |
| 17 | **CHANGELOG.md** | ❌ FALTA | Historial de cambios/versiones |
| 18 | **screenshots / demo** | ⚠️ EVALUAR | GIFs o imágenes de la UI Telegram para ilustrar el README |

---

## 📋 Orden Recomendado de Preparación

1. Crear `.gitignore`
2. Revisar secretos / archivos sensibles
3. Crear `LICENSE`
4. Revisar `README.md`
5. Completar `package.json`
6. Crear `.env.example`
7. Inicializar Git
8. Hacer commit inicial
9. Crear repo en GitHub
10. Agregar remote y hacer push

---

## 📦 `.gitignore` mínimo recomendado

Crear archivo `.gitignore`:

```gitignore
# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Python
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/

# Environment / secrets
.env
.env.*
!.env.example

# Logs / runtime state
logs/
*.log

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/

# Temporary / build
dist/
build/
tmp/
temp/
```

---

## 🔐 Revisión de Secretos Antes de Publicar

Verificar que NO se suba:

- `.env` y archivos de entorno
- Tokens de Telegram u otros tokens de API
- Credenciales de Ollama o endpoints privados
- Archivos en `logs/` o logs de ejecución
- Archivos de sesión / memoria local
- Rutas absolutas personales
- Archivos temporales del sistema o del editor

**Chequeos útiles:**

```bash
# Buscar tokens o variables sensibles
grep -R "TELEGRAM_BOT_TOKEN" .
grep -R "OLLAMA" .
grep -R "SECRET" .
grep -R "PASSWORD" .

# Ver qué se subiría
git status
git add -n .
```

---

## 📋 Acciones Rápidas (Copy/Paste)

### 1. Crear `.gitignore`

```bash
cat > .gitignore <<'EOF'
# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Python
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/

# Environment / secrets
.env
.env.*
!.env.example

# Logs / runtime state
logs/
*.log

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/

# Temporary / build
dist/
build/
tmp/
temp/
EOF
```

### 2. Crear `.env.example`

```bash
cat > .env.example <<'EOF'
TELEGRAM_BOT_TOKEN=
BOOTSTRAP_PROFILE=full
LOG_LEVEL=info
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
EOF
```

### 3. Crear LICENSE (MIT)

Crear archivo `LICENSE` con el texto completo de la licencia MIT. Ver plantilla en:
https://choosealicense.com/licenses/mit/

### 4. Completar `package.json`

Agregar al `package.json` existente:

```json
{
  "name": "blueprint-v0",
  "version": "1.0.0",
  "description": "Modular orchestration system with state-driven migration, local AI integration, and execution verification",
  "type": "module",
  "author": "[Tu Nombre] <[tu@email.com]>",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/Hanzzel-corp/blue-arrow.git"
  },
  "keywords": [
    "automation",
    "orchestration",
    "modular-architecture",
    "llama",
    "ollama",
    "telegram-bot",
    "state-machine",
    "gamification"
  ],
  "scripts": {
    "...": "... (scripts existentes)"
  }
}
```

### 5. Completar `pyproject.toml` (opcional/recomendado)

Agregar al inicio del archivo:

```toml
[project]
name = "blueprint-v0"
version = "1.0.0"
description = "Modular orchestration system with state-driven migration and local AI integration"
readme = "README.md"
license = {text = "MIT"}
authors = [
    {name = "[Tu Nombre]", email = "[tu@email.com]"}
]
requires-python = ">=3.11"

[project.urls]
Homepage = "https://github.com/Hanzzel-corp/blue-arrow"
Documentation = "https://github.com/Hanzzel-corp/blue-arrow/tree/main/docs"
```

### 6. Inicializar Git (después de preparar todo)

```bash
cd /home/jarvis0001/blue-arrow
git init
git add .
git commit -m "Initial commit: Blueprint v0 - Modular orchestration system"
```

---

## ✅ Post-Publicación en GitHub

Después de crear el repo en GitHub:

```bash
# Agregar remote
git remote add origin https://github.com/Hanzzel-corp/blue-arrow.git

# Push inicial
git branch -M main
git push -u origin main
```

---

## 📊 Resumen

| Categoría | Completados | Faltantes |
|-----------|-------------|-----------|
| 🔴 Crítico | 0/6 | 6 |
| 🟡 Importante | 0/7 | 7 |
| 🟢 Opcional | 0/5 | 5 |
| **Total** | **0/18** | **18** |

**Estado actual:** ❌ No listo para publicar

**Acciones mínimas para publicar:** Completar los 6 items críticos (🔴).
