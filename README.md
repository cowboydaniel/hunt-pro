# Hunt Pro

Hunt Pro is a PySide6 desktop assistant designed to support hunters with modern field tools such as navigation, ballistics, and logging utilities. The application organizes each capability into modular dashboards that share a consistent interface built on the `BaseModule` widget defined in `main.py`.

## Features

- **Modular architecture** – Each feature is implemented as a QWidget-based module that inherits shared behavior such as settings management, virtual input installation, and status reporting.
- **Ballistics calculator** – Advanced drag modelling, ammunition databases, and environmental corrections for precision shooting, implemented in `ballistics.py`.
- **Navigation mapping** – GPS-aware map visualization, tracking, and waypoint planning (see `nav_map.py`).
- **Game logging** – Structured harvest logging, tagging, and analytics tools (see `game_log.py`).
- **Virtual inputs** – On-screen keyboard and numpad managers for touch-friendly deployments (`keyboard.py` and `numpad.py`).
- **Robust logging** – Centralized logging utilities exposed via `logger.py`.

## Requirements

- Python 3.10 or newer
- PySide6 and PySide6-Charts

Install the Python dependencies with:

```bash
pip install -r requirements.txt
```

> **Note:** A `requirements.txt` file is not bundled yet. Install at least `PySide6` and `PySide6-Addons` packages before running the application.

## Running Hunt Pro

Run the main entry point with:

```bash
python -m hunt_pro
```

or launch the explicit script:

```bash
python main.py
```

Both commands initialize the Qt application, load modules, and display the main window with tabbed access to every tool.

## Development

- Modules should inherit from `BaseModule` in `main.py` to gain shared lifecycle handling and virtual input setup.
- Use the logging helpers in `logger.py` rather than the standard library to ensure consistent formatting and destinations.
- UI additions should favor PySide6 layouts and widgets that support both mouse and touch interactions.

## License

See [LICENSE](LICENSE) for licensing details.

## Roadmap

Planned improvements are tracked in [ROADMAP](ROADMAP).
