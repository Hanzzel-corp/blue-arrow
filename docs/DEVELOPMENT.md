# Desarrollo

> **Notas importantes:**
> - Para contratos canónicos, ver `PORT_CONTRACTS.md`, `CONTRACTS_GUIDE.md` y `TASK_CLOSURE_GOVERNANCE.md`
> - Para usar módulos IA locales, seguí también `OLLAMA_SETUP.md` (opcional)

## Setup local

1. Instalar dependencias Node.js:
   - `npm install`
2. Crear entorno Python:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
3. Instalar dependencias Python:
   - `pip install -r requirements.txt`
4. Instalar browser para Playwright:
   - `playwright install chromium`
5. (Opcional) configurar Telegram:
   - `export TELEGRAM_BOT_TOKEN="<token>"`
6. (Opcional) para IA local, seguir `OLLAMA_SETUP.md`
7. Iniciar runtime:
   - `npm start`

## Tests

- Suite completa: `npm run test:all`
- Solo validacion Node: `npm run test:node`
- Solo Python (unittest): `npm run test:py`
- Con pytest instalado (`requirements-dev.txt`): `python3 -m pytest tests/`

## Estructura de un modulo

Cada modulo debe incluir:
- `modules/<nombre>/manifest.json`
- `modules/<nombre>/main.js` o `main.py`

`manifest.json` declara:
- `id`
- `language`
- `entry`
- puertos soportados

## Agregar un nuevo modulo

1. Crear carpeta y `manifest.json`.
2. Implementar entrada (`main.js` o `main.py`).
3. Agregar `id` en `blueprints/system.v0.json -> modules`.
4. Declarar conexiones en `blueprints/system.v0.json -> connections`.
5. Verificar arranque con `npm start`.

## Debug rapido

- Revisar `logs/events.log` para traza de eventos.
- Validar payloads JSON (errores de parseo cortan procesamiento).
- Si falla browser worker:
  - confirmar `playwright` instalado
  - confirmar `playwright install chromium`
- Si falla desktop worker:
  - confirmar `xdotool` y `wmctrl`

## Buenas practicas

- mantener modulos puros por contrato de puertos
- no agregar dependencias cruzadas por import
- versionar contratos de payload cuando cambie semantica
- preferir cambios declarativos en blueprint en lugar de wiring hardcodeado
