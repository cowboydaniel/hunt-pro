# Hunt Pro

Hunt Pro is a PySide6 desktop assistant designed to support hunters with modern field tools such as navigation, ballistics, and logging utilities. The application organizes each capability into modular dashboards that share a consistent interface built on the `BaseModule` widget defined in `main.py`.

## Features

- **Modular architecture** – Each feature is implemented as a QWidget-based module that inherits shared behavior such as settings management, virtual input installation, and status reporting.
- **Ballistics calculator** – Advanced drag modelling, ammunition databases, and environmental corrections for precision shooting, implemented in `ballistics.py`.
- **Navigation mapping** – GPS-aware map visualization, tracking, and waypoint planning (see `nav_map.py`).
- **Game logging** – Structured harvest logging, tagging, and analytics tools (see `game_log.py`).
- **Virtual inputs** – On-screen keyboard and numpad managers for touch-friendly deployments (`keyboard.py` and `numpad.py`).
- **Robust logging** – Centralized logging utilities exposed via `logger.py`.

## Environment Setup

### Supported Platforms

- **Operating systems:** Windows 10/11, macOS 12+, and modern Linux distributions with X11 or Wayland support.
- **Python:** 3.10 through 3.12 (64-bit builds recommended).

### Baseline Hardware

- Quad-core CPU (Intel i5/Ryzen 5 class or better).
- 8 GB RAM minimum (16 GB recommended when running additional mapping utilities).
- 2 GB of available disk space for application assets, caches, and map tiles.
- A GPU that supports OpenGL 3.3 for optimal PySide6 rendering.

### Recommended Workflow

1. **Create a virtual environment** to isolate dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

2. **Install dependencies**. A `requirements.txt` lock file is still pending, so install the essential packages manually:

   ```bash
   pip install --upgrade pip
   pip install PySide6 PySide6-Addons PySide6-Charts
   ```

3. **Install developer tooling** to use the shared linting and formatting baselines:

   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Verify Qt compatibility** by running a simple sanity check:

   ```bash
   python -c "from PySide6.QtWidgets import QApplication; QApplication([])"
   ```

   The command should exit without errors, confirming that the Qt platform plugins are available.

5. **Install optional tools** such as `pytest` for running the existing tests.

When deploying to field hardware such as rugged tablets, ensure the device firmware enables the GPU acceleration needed by PySide6 and that location services are accessible for navigation features.

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
