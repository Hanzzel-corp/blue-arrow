# Blue Arrow

Blue Arrow is an open-source local orchestration framework that lets users control desktop, terminal, browser, system and document actions through Telegram.

It is built around a human-in-the-loop execution model: AI can assist, interpret and plan, but real actions are routed through safety checks, approval flows, workers and execution verification.

## Why it matters

Most automation agents move toward uncontrolled autonomy. Blue Arrow takes the opposite path: the human remains the final decision-maker, while the system provides structured execution, local-first AI integration and verifiable action results.

## Core idea

Blue Arrow connects the following execution chain:

Telegram -> interface.telegram -> agent.main -> planner.main -> safety.guard.main -> approval.main -> router.main -> workers -> supervisor.main -> ui.state.main

## Key features

- Local-first automation
- Telegram control interface
- Human approval before execution
- Safety guard layer
- Modular event-driven architecture
- Desktop, terminal, browser and system workers
- Execution verification with confidence scores
- Optional local AI integration with Ollama/LLaMA
- State-driven architecture migration
- RPG-style Telegram interface

## Use cases

- Control local applications from Telegram
- Execute approved terminal and system actions
- Automate browser workflows
- Generate and write documents through LibreOffice Writer
- Build safer AI-assisted automation flows
- Experiment with local-first human-guided agent systems

## Philosophy

Blue Arrow is not designed to replace the human decision-maker.

The AI acts as an assistant and interpreter. The human remains the final authority. Real actions are checked, routed, approved, executed and verified.

## License

MIT License.
