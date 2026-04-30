# Development

> 🌐 [Versión en Español → DEVELOPMENT.md](DEVELOPMENT.md)

> **Important notes:**
> - For canonical contracts, see `PORT_CONTRACTS.md`, `CONTRACTS_GUIDE.md` and `TASK_CLOSURE_GOVERNANCE.md`
> - To use local AI modules, also follow `OLLAMA_SETUP.md` (optional)

## Local Setup

1. Install Node.js dependencies:
   ```bash
   npm install
   ```

2. Create Python environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install browser for Playwright:
   ```bash
   playwright install chromium
   ```

5. (Optional) Configure Telegram:
   ```bash
   export TELEGRAM_BOT_TOKEN="<token>"
   ```

6. (Optional) For local AI, follow `OLLAMA_SETUP.md`

7. Start runtime:
   ```bash
   npm start
   ```

## Tests

- Full suite: `npm run test:all`
- Node only validation: `npm run test:node`
- Python only (unittest): `npm run test:py`
- With pytest installed (`requirements-dev.txt`): `python3 -m pytest tests/`

## Module Structure

Each module must include:
- `modules/<name>/manifest.json`
- `modules/<name>/main.js` or `main.py`

`manifest.json` declares:
- `id` - Unique module identifier
- `language` - node or python
- `entry` - Main file (main.js or main.py)
- Supported ports

## Adding a New Module

1. Create folder and `manifest.json`:
   ```json
   {
     "id": "module.name",
     "name": "My Module",
     "version": "1.0.0",
     "language": "node",
     "entry": "main.js",
     "tier": "satellite",
     "priority": "medium",
     "inputs": ["command.in", "event.in"],
     "outputs": ["result.out", "event.out"]
   }
   ```

2. Implement entry (`main.js` or `main.py`)

3. Add `id` in `blueprints/system.v0.json -> modules`

4. Declare connections in `blueprints/system.v0.json -> connections`

5. Verify startup with `npm start`

## Quick Debug

- Check `logs/events.log` for event traces
- Validate JSON payloads (parse errors cut processing)
- If browser worker fails:
  - confirm `playwright` is installed
  - confirm `playwright install chromium` was run
- If desktop worker fails:
  - confirm `xdotool` and `wmctrl` are installed

## Best Practices

- Keep modules pure through port contracts
- Don't add cross-dependencies via imports
- Version payload contracts when semantics change
- Prefer declarative changes in blueprint over hardcoded wiring

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token for interface |
| `BOOTSTRAP_PROFILE` | No | Profile: minimal, standard, full (default: full) |
| `LOG_LEVEL` | No | Log level: error, warn, info, debug, trace |
| `OLLAMA_HOST` | No | Ollama URL for local AI (default: http://localhost:11434) |

## Troubleshooting

### Common Issues

**Module won't start:**
- Check `manifest.json` syntax
- Verify `entry` file exists and is executable
- Check `logs/events.log` for errors

**Telegram bot not responding:**
- Verify `TELEGRAM_BOT_TOKEN` is set correctly
- Check bot is added to a chat and has permissions
- Look for "Unauthorized" errors in logs

**AI modules not working:**
- Confirm Ollama is running: `curl http://localhost:11434/api/tags`
- Check `OLLAMA_HOST` environment variable
- Verify model is pulled: `ollama pull llama3.2`

**Playwright browser issues:**
- Run `playwright install chromium` after pip install
- Check system dependencies for Chromium

## Development Workflow

1. Make changes to module code
2. Run `npm run check:node` or `npm run check:py` for syntax validation
3. Test with `npm run test:all`
4. Run `npm run health` to verify system health
5. Commit changes with descriptive messages

---

For architecture details, see [ARCHITECTURE_EN.md](ARCHITECTURE_EN.md)
