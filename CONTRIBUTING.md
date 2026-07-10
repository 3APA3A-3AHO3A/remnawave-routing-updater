# Contributing

Thanks for your interest in improving **Remnawave Routing Auto Updater**! It's a small project, so the process is light.

## Project layout

The code is a Python package under `routing_updater/`, split by responsibility:

| File | Responsibility |
| --- | --- |
| `config.py` | Reads all settings from the environment / `.env` |
| `logger.py` | Shared logger |
| `rules.py` | Pure response-rule logic (no network, no files) |
| `templating.py` | Load / stamp / encode / save the routing template |
| `remnawave.py` | The only code that talks to the Remnawave API |
| `core.py` | Orchestrates one update cycle |
| `runtime.py` | Signal handling and interruptible sleep |
| `__main__.py` | Entry point (`python -m routing_updater`) |

Tests live in `tests/`. The guiding rule: keep pure logic (in `rules.py` and `core.apply_changes`) free of network and file access, so it stays trivial to test.

## Development setup

```bash
git clone https://github.com/3APA3A-3AHO3A/remnawave-routing-updater.git
cd remnawave-routing-updater
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"             # installs the app + ruff + pytest
```

## Before opening a pull request

Run the same checks CI runs:

```bash
ruff check .      # lint + import order
pytest -q         # tests
```

Keep changes focused and add a test where it makes sense. Match the existing style — `ruff` will point out anything off. Log messages are in English to match the rest of the project.

## Reporting bugs

Open an issue with your Remnawave version, the relevant log lines, and steps to reproduce.
