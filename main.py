"""

Hunt Pro - Professional Hunting Assistant

Main Application Module



A comprehensive hunting assistant application with GPS navigation, ballistics calculations,

game logging, environmental tools, and advanced field equipment integration.

"""



import sys

import os

from pathlib import Path

from typing import Dict, Optional, Any

import importlib

import traceback



from PySide6.QtWidgets import (

    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,

    QTabWidget, QPushButton, QLabel, QStatusBar, QMessageBox,

    QSplashScreen, QSystemTrayIcon, QMenu, QFrame, QScrollArea

)

from PySide6.QtCore import (

    Qt, Signal, QTimer, QThread, QObject, QSettings,

    QPropertyAnimation, QEasingCurve, QRect, QSize

)

from PySide6.QtGui import (

    QFont, QPixmap, QPalette, QColor, QIcon, QAction,

    QPainter, QLinearGradient

)



# Import our modules

from logger import get_logger, setup_logger

from keyboard import VirtualKeyboardManager

from numpad import VirtualNumpadManager



class BaseModule(QWidget):

    """Base class for all Hunt Pro modules."""

    

    # Enhanced signals

    status_message = Signal(str)

    error_occurred = Signal(str, str)  # title, message

    warning_occurred = Signal(str, str)  # title, message

    info_message = Signal(str)

    progress_updated = Signal(int)  # 0-100

    module_ready = Signal()

    

    def __init__(self, parent=None):

        super().__init__(parent)

        self.module_name = self.__class__.__name__.replace('Module', '')

        self.settings = QSettings("HuntPro", f"module_{self.module_name}")

        self.logger = get_logger()

        

        # Module state

        self._initialized = False

        self._error_count = 0

        self._last_error = None

        

        # Setup base UI properties

        self.setMinimumSize(800, 600)

        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

        

        # Initialize error handling

        self.error_occurred.connect(self._handle_error)

    

    def initialize(self) -> bool:

        """Initialize the module. Override in subclasses."""

        try:

            self._initialized = True

            self.logger.info(f"Module {self.module_name} initialized successfully")

            

            # Install virtual inputs after initialization

            QTimer.singleShot(100, self.install_virtual_inputs)

            self.module_ready.emit()

            return True

        except Exception as e:

            self.logger.error(f"Failed to initialize module {self.module_name}", exception=e)

            self.error_occurred.emit("Initialization Error", str(e))

            return False

    

    def install_virtual_inputs(self):

        """Install virtual keyboard and numpad on appropriate widgets."""

        try:

            keyboard_manager = VirtualKeyboardManager.get_instance()

            numpad_manager = VirtualNumpadManager.get_instance()

            

            # Install keyboard on text inputs

            from PySide6.QtWidgets import QLineEdit, QTextEdit

            for widget in self.findChildren(QLineEdit):

                keyboard_manager.install_on_widget(widget)

            for widget in self.findChildren(QTextEdit):

                keyboard_manager.install_on_widget(widget)

                

            # Install numpad on numeric inputs

            from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox

            for widget in self.findChildren(QSpinBox):

                numpad_manager.install_on_widget(widget)

            for widget in self.findChildren(QDoubleSpinBox):

                numpad_manager.install_on_widget(widget)

                

        except Exception as e:

            self.logger.warning(f"Failed to install virtual inputs on {self.module_name}", exception=e)

    

    def cleanup(self):

        """Clean up resources when module is closed."""

        self._initialized = False

        self.logger.info(f"Module {self.module_name} cleaned up")

    

    def get_display_name(self) -> str:

        """Return the display name for this module."""

        return self.module_name

    

    def get_description(self) -> str:

        """Return a description of this module's functionality."""

        return f"{self.module_name} module for Hunt Pro"

    

    def is_initialized(self) -> bool:

        """Check if module is properly initialized."""

        return self._initialized

    

    def _handle_error(self, title: str, message: str):

        """Internal error handler to track error statistics."""

        self._error_count += 1

        self._last_error = f"{title}: {message}"

        self.logger.error(f"Module error in {self.module_name}: {title} - {message}")

    

    def get_last_error(self) -> Optional[str]:

        """Get the last error that occurred in this module."""

        return self._last_error

    

    def save_state(self):

        """Save module state to settings."""

        self.settings.setValue("initialized", self._initialized)

        self.settings.setValue("error_count", self._error_count)

    

    def restore_state(self):

        """Restore module state from settings."""

        self._error_count = self.settings.value("error_count", 0, int)





class ModuleManager(QObject):

    """Enhanced module manager with better error handling and loading."""

    

    # Signals

    module_loaded = Signal(str, object)  # module_name, module_instance

    module_failed = Signal(str, str)     # module_name, error_message

    all_modules_loaded = Signal()

    loading_progress = Signal(int, str)  # progress, status

    

    def __init__(self, parent=None):

        super().__init__(parent)

        self.modules: Dict[str, BaseModule] = {}

        self.failed_modules: Dict[str, str] = {}

        self.logger = get_logger()

        

        # Available modules with metadata

        self.available_modules = {

            'ballistics': {

                'path': 'ballistics.BallisticsModule',

                'display_name': 'ðŸŽ¯ Ballistics',

                'description': 'Advanced ballistics calculator with environmental corrections',

                'icon': 'ðŸŽ¯',

                'priority': 1

            },

            'nav_map': {

                'path': 'nav_map.NavigationModule', 

                'display_name': 'ðŸ—ºï¸ Navigation',

                'description': 'GPS navigation and mapping tools',

                'icon': 'ðŸ—ºï¸',

                'priority': 2

            },

            'game_log': {

                'path': 'game_log.GameLogModule',

                'display_name': 'ðŸ“Š Game Log',

                'description': 'Track hunting activities and harvests',

                'icon': 'ðŸ“Š',

                'priority': 3

            },

            'field_tools': {

                'path': 'field_tools.FieldToolsModule',

                'display_name': 'ðŸ› ï¸ Field Tools',

                'description': 'Environmental calculations and first aid',

                'icon': 'ðŸ› ï¸',

                'priority': 4

            },

            'advanced_tools': {

                'path': 'advanced_tools.AdvancedToolsModule',

                'display_name': 'ðŸ›¡ï¸ Advanced Tools',

                'description': 'RF blocking, night vision, and thermal imaging',

                'icon': 'ðŸ›¡ï¸',

                'priority': 5

            }

        }

        

        # Ensure current directory is in Python path

        current_dir = Path(__file__).parent

        if str(current_dir) not in sys.path:

            sys.path.insert(0, str(current_dir))

    

    def load_module(self, module_name: str, parent: QWidget) -> Optional[BaseModule]:

        """Load a module by name with enhanced error handling."""

        if module_name not in self.available_modules:

            error_msg = f"Module '{module_name}' not found in available modules"

            self.module_failed.emit(module_name, error_msg)

            return None

            

        module_info = self.available_modules[module_name]

        

        try:

            self.logger.info(f"Loading module: {module_name}")

            

            # Parse module path

            module_path, class_name = module_info['path'].rsplit('.', 1)

            

            # Import module

            module = importlib.import_module(module_path)

            module_class = getattr(module, class_name)

            

            # Create instance

            instance = module_class(parent)

            

            # Initialize module

            if instance.initialize():

                self.modules[module_name] = instance

                self.module_loaded.emit(module_name, instance)

                

                # Connect module signals

                instance.status_message.connect(

                    lambda msg, name=module_name: self._relay_status_message(name, msg)

                )

                instance.error_occurred.connect(

                    lambda title, msg, name=module_name: self._relay_error(name, title, msg)

                )

                

                self.logger.info(f"Successfully loaded module: {module_name}")

                return instance

            else:

                error_msg = f"Module '{module_name}' failed to initialize"

                self.failed_modules[module_name] = error_msg

                self.module_failed.emit(module_name, error_msg)

                return None

                

        except ImportError as e:

            error_msg = f"Failed to import module '{module_name}': {str(e)}"

            self.failed_modules[module_name] = error_msg

            self.module_failed.emit(module_name, error_msg)

            self.logger.error(f"Import error for module {module_name}", exception=e)

            return None

        except Exception as e:

            error_msg = f"Error loading module '{module_name}': {str(e)}"

            self.failed_modules[module_name] = error_msg

            self.module_failed.emit(module_name, error_msg)

            self.logger.error(f"Unexpected error loading module {module_name}", exception=e)

            return None

    

    def load_all_modules(self, parent: QWidget) -> Dict[str, BaseModule]:

        """Load all available modules with progress tracking."""

        # Sort modules by priority

        sorted_modules = sorted(

            self.available_modules.items(),

            key=lambda x: x[1]['priority']

        )

        

        total_modules = len(sorted_modules)

        

        for i, (module_name, _) in enumerate(sorted_modules):

            progress = int((i / total_modules) * 100)

            self.loading_progress.emit(progress, f"Loading {module_name}...")

            self.load_module(module_name, parent)

        

        self.loading_progress.emit(100, "All modules loaded")

        self.all_modules_loaded.emit()

        return self.modules.copy()

    

    def get_module(self, module_name: str) -> Optional[BaseModule]:

        """Get a loaded module by name."""

        return self.modules.get(module_name)

    

    def get_module_info(self, module_name: str) -> Optional[Dict]:

        """Get module metadata."""

        return self.available_modules.get(module_name)

    

    def get_failed_modules(self) -> Dict[str, str]:

        """Get list of modules that failed to load."""

        return self.failed_modules.copy()

    

    def _relay_status_message(self, module_name: str, message: str):

        """Relay status messages from modules."""

        self.logger.info(f"[{module_name}] {message}")

    

    def _relay_error(self, module_name: str, title: str, message: str):

        """Relay error messages from modules."""

        self.logger.error(f"[{module_name}] {title}: {message}")





class LoadingScreen(QSplashScreen):

    """Custom loading screen for Hunt Pro."""

    

    def __init__(self):

        super().__init__()

        self.setFixedSize(600, 400)

        

        # Create custom pixmap

        pixmap = QPixmap(600, 400)

        pixmap.fill(QColor("#1a2332"))

        

        painter = QPainter(pixmap)

        painter.setRenderHint(QPainter.Antialiasing)

        

        # Draw gradient background

        gradient = QLinearGradient(0, 0, 0, 400)

        gradient.setColorAt(0, QColor("#2c5aa0"))

        gradient.setColorAt(1, QColor("#1a2332"))

        painter.fillRect(pixmap.rect(), gradient)

        

        # Draw title

        painter.setPen(QColor("white"))

        painter.setFont(QFont("Arial", 24, QFont.Bold))

        painter.drawText(pixmap.rect(), Qt.AlignCenter, "ðŸ¹ Hunt Pro\nProfessional Hunting Assistant")

        

        painter.end()

        

        self.setPixmap(pixmap)

        self.setWindowFlag(Qt.WindowStaysOnTopHint)





class MainWindow(QMainWindow):

    """Modern main application window with enhanced features."""

    

    def __init__(self, parent=None):

        super().__init__(parent)

        self.setWindowTitle("Hunt Pro - Professional Hunting Assistant")

        self.setMinimumSize(1200, 800)

        

        # Application state

        self.settings = QSettings("HuntPro", "HuntPro")

        self.logger = get_logger()

        

        # Initialize virtual input managers

        self.keyboard_manager = VirtualKeyboardManager()

        self.numpad_manager = VirtualNumpadManager()

        

        # Initialize module manager

        self.module_manager = ModuleManager(self)

        self.module_manager.module_loaded.connect(self._on_module_loaded)

        self.module_manager.module_failed.connect(self._on_module_failed)

        self.module_manager.all_modules_loaded.connect(self._on_all_modules_loaded)

        self.module_manager.loading_progress.connect(self._on_loading_progress)

        

        # Setup UI

        self.setup_ui()

        self.apply_theme()

        self.restore_window_state()

        

        # Load modules after UI is ready

        QTimer.singleShot(100, self._load_modules)

        

        # Setup system tray

        self.setup_system_tray()

        

        self.logger.info("Hunt Pro main window initialized")

    

    def setup_ui(self):

        """Set up the modern user interface."""

        central_widget = QWidget()

        self.setCentralWidget(central_widget)

        

        layout = QVBoxLayout(central_widget)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.setSpacing(0)

        

        # Create header

        self.create_header(layout)

        

        # Create main tab widget

        self.tab_widget = QTabWidget()

        self.tab_widget.setTabPosition(QTabWidget.North)

        self.tab_widget.setTabsClosable(False)

        self.tab_widget.setMovable(False)

        layout.addWidget(self.tab_widget)

        

        # Create status bar

        self.status_bar = QStatusBar()

        self.setStatusBar(self.status_bar)

        self.status_bar.showMessage("Starting Hunt Pro...")

    

    def create_header(self, layout):

        """Create application header with title and controls."""

        header = QFrame()

        header.setFixedHeight(80)

        header.setObjectName("header")

        header_layout = QHBoxLayout(header)

        

        # Title

        title_label = QLabel("ðŸ¹ Hunt Pro")

        title_label.setFont(QFont("Arial", 20, QFont.Bold))

        title_label.setObjectName("title")

        header_layout.addWidget(title_label)

        

        header_layout.addStretch()

        

        # Settings button

        settings_btn = QPushButton("âš™ï¸ Settings")

        settings_btn.setObjectName("header_button")

        settings_btn.clicked.connect(self.show_settings)

        header_layout.addWidget(settings_btn)

        

        # About button

        about_btn = QPushButton("â„¹ï¸ About")

        about_btn.setObjectName("header_button")

        about_btn.clicked.connect(self.show_about)

        header_layout.addWidget(about_btn)

        

        layout.addWidget(header)

    

    def setup_system_tray(self):

        """Setup system tray icon and menu."""

        if QSystemTrayIcon.isSystemTrayAvailable():

            self.tray_icon = QSystemTrayIcon(self)

            self.tray_icon.setToolTip("Hunt Pro - Professional Hunting Assistant")

            

            # Create tray menu

            tray_menu = QMenu()

            

            show_action = QAction("Show Hunt Pro", self)

            show_action.triggered.connect(self.show)

            tray_menu.addAction(show_action)

            

            tray_menu.addSeparator()

            

            quit_action = QAction("Quit", self)

            quit_action.triggered.connect(QApplication.quit)

            tray_menu.addAction(quit_action)

            

            self.tray_icon.setContextMenu(tray_menu)

            self.tray_icon.show()

    

    def apply_theme(self):

        """Apply modern dark theme to the application."""

        style = """

        /* Main Window */

        QMainWindow {

            background-color: #1a2332;

            color: white;

        }

        

        /* Header */

        QFrame#header {

            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,

                stop:0 #2c5aa0, stop:1 #1a2332);

            border-bottom: 2px solid #3d5a8c;

        }

        

        QLabel#title {

            color: white;

            font-size: 20px;

            font-weight: bold;

        }

        

        QPushButton#header_button {

            background-color: rgba(255, 255, 255, 0.1);

            border: 1px solid rgba(255, 255, 255, 0.2);

            border-radius: 8px;

            padding: 8px 16px;

            color: white;

            font-size: 14px;

        }

        

        QPushButton#header_button:hover {

            background-color: rgba(255, 255, 255, 0.2);

        }

        

        QPushButton#header_button:pressed {

            background-color: rgba(255, 255, 255, 0.3);

        }

        

        /* Tab Widget */

        QTabWidget {

            background-color: transparent;

        }

        

        QTabWidget::pane {

            border: 2px solid #3d5a8c;

            background-color: #2a3441;

            border-radius: 8px;

            margin-top: 20px;

        }

        

        QTabBar::tab {

            min-width: 160px;

            min-height: 50px;

            padding: 12px 20px;

            margin: 2px;

            background-color: #3d5a8c;

            border: none;

            border-radius: 8px 8px 0 0;

            font-size: 14px;

            font-weight: 600;

            color: white;

        }

        

        QTabBar::tab:selected {

            background-color: #2c5aa0;

            color: white;

        }

        

        QTabBar::tab:hover:!selected {

            background-color: #4a6ba8;

        }

        

        /* Status Bar */

        QStatusBar {

            background-color: #1a2332;

            color: white;

            border-top: 1px solid #3d5a8c;

        }

        """

        

        self.setStyleSheet(style)

    

    def _load_modules(self):

        """Load all modules in the background."""

        self.status_bar.showMessage("Loading modules...")

        self.module_manager.load_all_modules(self)

    

    def _on_module_loaded(self, module_name: str, module_instance: BaseModule):

        """Handle module loaded event."""

        module_info = self.module_manager.get_module_info(module_name)

        if module_info:

            display_name = module_info['display_name']

            icon = module_info.get('icon', 'ðŸ“¦')

            

            self.tab_widget.addTab(module_instance, f"{icon} {display_name}")

            self.logger.info(f"Added tab for module: {module_name}")

    

    def _on_module_failed(self, module_name: str, error_message: str):

        """Handle module failed event."""

        self.logger.error(f"Module {module_name} failed to load: {error_message}")

        self.status_bar.showMessage(f"Failed to load {module_name}: {error_message}", 5000)

    

    def _on_all_modules_loaded(self):

        """Handle all modules loaded event."""

        loaded_count = len(self.module_manager.modules)

        failed_count = len(self.module_manager.failed_modules)

        

        if failed_count > 0:

            self.status_bar.showMessage(f"Loaded {loaded_count} modules ({failed_count} failed)")

        else:

            self.status_bar.showMessage(f"All {loaded_count} modules loaded successfully")

        

        self.logger.info(f"Module loading complete: {loaded_count} loaded, {failed_count} failed")

    

    def _on_loading_progress(self, progress: int, status: str):

        """Handle loading progress updates."""

        self.status_bar.showMessage(f"{status} ({progress}%)")

    

    def show_settings(self):

        """Show application settings dialog."""

        QMessageBox.information(self, "Settings", "Settings dialog coming soon!")

    

    def show_about(self):

        """Show about dialog."""

        about_text = """

        <h2>ðŸ¹ Hunt Pro</h2>

        <p><b>Professional Hunting Assistant</b></p>

        <p>Version 2.0.0 - Touch-Optimized Field Edition</p>

        

        <p>Hunt Pro is a comprehensive hunting companion application featuring:</p>

        <ul>

        <li>ðŸŽ¯ Advanced ballistics calculations</li>

        <li>ðŸ—ºï¸ GPS navigation and mapping</li>

        <li>ðŸ“Š Game logging and tracking</li>

        <li>ðŸ› ï¸ Environmental field tools</li>

        <li>ðŸ›¡ï¸ Advanced tactical equipment</li>

        </ul>

        

        <p>Designed for professional hunters and outdoor enthusiasts.</p>

        """

        

        QMessageBox.about(self, "About Hunt Pro", about_text)

    

    def closeEvent(self, event):

        """Handle window close event."""

        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():

            QMessageBox.information(

                self, "Hunt Pro",

                "Hunt Pro will continue running in the system tray. "

                "Right-click the tray icon to quit."

            )

            self.hide()

            event.ignore()

        else:

            self.save_window_state()

            # Cleanup modules

            for module in self.module_manager.modules.values():

                module.cleanup()

            event.accept()

    

    def save_window_state(self):

        """Save window geometry and state."""

        self.settings.setValue("geometry", self.saveGeometry())

        self.settings.setValue("windowState", self.saveState())

    

    def restore_window_state(self):

        """Restore window geometry and state."""

        geometry = self.settings.value("geometry")

        if geometry:

            self.restoreGeometry(geometry)

            

        state = self.settings.value("windowState")

        if state:

            self.restoreState(state)





def main():

    """Main entry point for Hunt Pro application."""

    

    # Setup logging

    setup_logger("huntpro")

    logger = get_logger()

    

    logger.info("="*60)

    logger.info("ðŸ¹ Hunt Pro - Professional Hunting Assistant")

    logger.info("   Version 2.0.0 - Touch-Optimized Field Edition")

    logger.info("="*60)

    

    # Create application

    app = QApplication(sys.argv)

    app.setApplicationName("Hunt Pro")

    app.setApplicationVersion("2.0.0")

    app.setOrganizationName("HuntPro")

    app.setOrganizationDomain("huntpro.app")

    

    # Show loading screen

    loading_screen = LoadingScreen()

    loading_screen.show()

    app.processEvents()

    

    try:

        # Create main window

        main_window = MainWindow()

        

        # Hide loading screen and show main window

        loading_screen.finish(main_window)

        main_window.show()

        

        logger.info("Hunt Pro application started successfully")

        

        # Run application

        exit_code = app.exec()

        

        logger.info(f"Hunt Pro application exited with code: {exit_code}")

        return exit_code

        

    except Exception as e:

        logger.critical("Critical error starting Hunt Pro", exception=e)

        QMessageBox.critical(None, "Critical Error", 

                           f"Failed to start Hunt Pro:\n{str(e)}\n\nCheck logs for details.")

        return 1





if __name__ == "__main__":

    sys.exit(main())
