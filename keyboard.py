"""
Virtual Keyboard Module for Hunt Pro.
Touch-optimized on-screen keyboard for text input fields.
Automatically appears when text fields are tapped and provides
field-appropriate keyboard layouts.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, 
    QFrame, QLabel, QApplication, QLineEdit, QTextEdit, QSpacerItem, 
    QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QRect, 
    QObject, QEvent, QPoint, QSize
)
from PySide6.QtGui import QFont, QFontMetrics, QPalette, QColor, QCursor
from typing import Optional, Dict, List, Callable, Union
import string
from logger import get_logger, LoggableMixin
class KeyboardLayout:
    """Keyboard layout definitions for different input types."""

    SHIFT_KEY = "Shift"
    BACKSPACE_KEY = "Backspace"
    ENTER_KEY = "Enter"
    LANGUAGE_KEY = "Lang"

    QWERTY_LETTERS = [
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
        [SHIFT_KEY, 'z', 'x', 'c', 'v', 'b', 'n', 'm', BACKSPACE_KEY]
    ]
    QWERTY_LETTERS_UPPER = [
        ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
        ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
        [SHIFT_KEY, 'Z', 'X', 'C', 'V', 'B', 'N', 'M', BACKSPACE_KEY]
    ]
    NUMBERS_SYMBOLS = [
        ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
        ['-', '/', ':', ';', '(', ')', '$', '&', '@', '"'],
        ['#+=', '.', ',', '?', '!', "'", BACKSPACE_KEY]
    ]
    SYMBOLS_EXTRA = [
        ['[', ']', '{', '}', '#', '%', '^', '*', '+', '='],
        ['_', '\', '|', '~', '<', '>', 'EUR', 'GBP', 'JPY', '*'],
        ['123', '.', ',', '?', '!', "'", BACKSPACE_KEY]
    ]
    # Bottom row for all layouts
    BOTTOM_ROW_LETTERS = ['123', LANGUAGE_KEY, ' ', '.', ENTER_KEY]
    BOTTOM_ROW_NUMBERS = ['ABC', LANGUAGE_KEY, ' ', '.', ENTER_KEY]
    BOTTOM_ROW_SYMBOLS = ['123', LANGUAGE_KEY, ' ', '.', ENTER_KEY]

class VirtualKeyboard(QWidget, LoggableMixin):
    """Touch-optimized virtual keyboard widget."""
    # Signals
    key_pressed = Signal(str)
    text_changed = Signal(str)
    enter_pressed = Signal()
    backspace_pressed = Signal()
    keyboard_hidden = Signal()
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        LoggableMixin.__init__(self)
        self.current_layout = "letters"
        self.shift_active = False
        self.caps_lock = False
        self.target_widget = None
        self.original_text = ""
        # Keyboard dimensions optimized for tablet
        self.keyboard_width = 800
        self.keyboard_height = 320
        self.key_size = QSize(70, 60)
        self.setup_ui()
        self.setup_animations()
        self.apply_styling()
        # Auto-hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_keyboard)
        # Connect signals
        self.key_pressed.connect(self._handle_key_press)
        self.backspace_pressed.connect(self._handle_backspace)
        self.enter_pressed.connect(self._handle_enter)
        self.log_debug("Virtual keyboard initialized")
    def setup_ui(self):
        """Setup the keyboard UI - optimized for touch interaction."""
        self.setFixedSize(self.keyboard_width, self.keyboard_height)
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)
        # Keyboard container with shadow
        self.keyboard_frame = QFrame()
        self.keyboard_frame.setObjectName("keyboardFrame")
        # Add drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.keyboard_frame.setGraphicsEffect(shadow)
        keyboard_layout = QVBoxLayout(self.keyboard_frame)
        keyboard_layout.setContentsMargins(15, 15, 15, 15)
        keyboard_layout.setSpacing(6)
        # Create key rows
        self.key_rows = []
        self.key_buttons = {}
        # Create 4 rows (3 main + 1 bottom)
        for i in range(4):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            self.key_rows.append({
                'widget': row_widget,
                'layout': row_layout,
                'buttons': []
            })
            keyboard_layout.addWidget(row_widget)
        main_layout.addWidget(self.keyboard_frame)
        # Initial layout
        self.update_layout()
    def setup_animations(self):
        """Setup animations for keyboard show/hide."""
        self.show_animation = QPropertyAnimation(self, b"geometry")
        self.show_animation.setDuration(300)
        self.show_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.hide_animation = QPropertyAnimation(self, b"geometry")
        self.hide_animation.setDuration(250)
        self.hide_animation.setEasingCurve(QEasingCurve.InCubic)
        self.hide_animation.finished.connect(self.hide)
    def apply_styling(self):
        """Apply modern styling to the keyboard."""
        style = """
        QFrame#keyboardFrame {
            background-color: #2a3441;
            border: 2px solid #3d5a8c;
            border-radius: 15px;
        }
        QPushButton {
            background-color: #3d5a8c;
            border: 1px solid #4a6ba8;
            border-radius: 8px;
            color: white;
            font-size: 16px;
            font-weight: 600;
            min-height: 50px;
            min-width: 60px;
        }
        QPushButton:hover {
            background-color: #4a6ba8;
            border-color: #5a7bb8;
        }
        QPushButton:pressed {
            background-color: #2c5aa0;
            margin-top: 2px;
        }
        QPushButton#specialKey {
            background-color: #5a7bb8;
            color: white;
        }
        QPushButton#specialKey:hover {
            background-color: #6a8bc8;
        }
        QPushButton#spaceKey {
            background-color: #4a6ba8;
            min-width: 200px;
        }
        QPushButton#enterKey {
            background-color: #2c5aa0;
            color: white;
        }
        QPushButton#deleteKey {
            background-color: #dc3545;
            color: white;
        }
        QPushButton#deleteKey:hover {
            background-color: #c82333;
        }
        """
        self.setStyleSheet(style)
    def create_key_button(self, key_text: str, key_value: str = None) -> QPushButton:
        """Create a keyboard key button with proper styling and behavior."""
        if key_value is None:
            key_value = key_text
        button = QPushButton(key_text)
        button.setFont(QFont("Arial", 14, QFont.Medium))
        button.setMinimumSize(self.key_size)
        # Set object names for styling
        if key_text in [
            KeyboardLayout.SHIFT_KEY,
            KeyboardLayout.BACKSPACE_KEY,
            KeyboardLayout.ENTER_KEY,
            '123',
            'ABC',
            '#+=',
            KeyboardLayout.LANGUAGE_KEY
        ]:
            button.setObjectName("specialKey")
        elif key_text == ' ':
            button.setObjectName("spaceKey")
        elif key_text == KeyboardLayout.ENTER_KEY:
            button.setObjectName("enterKey")
        elif key_text == KeyboardLayout.BACKSPACE_KEY:
            button.setObjectName("deleteKey")
        # Connect button to handler
        if key_text == KeyboardLayout.BACKSPACE_KEY:
            button.clicked.connect(self.backspace_pressed.emit)
        elif key_text == KeyboardLayout.ENTER_KEY:
            button.clicked.connect(self.enter_pressed.emit)
        elif key_text == KeyboardLayout.SHIFT_KEY:
            button.clicked.connect(self.toggle_shift)
        elif key_text == '123':
            button.clicked.connect(lambda: self.switch_layout("numbers"))
        elif key_text == 'ABC':
            button.clicked.connect(lambda: self.switch_layout("letters"))
        elif key_text == '#+=':
            button.clicked.connect(lambda: self.switch_layout("symbols"))
        elif key_text == KeyboardLayout.LANGUAGE_KEY:
            button.clicked.connect(self.show_language_options)
        else:
            button.clicked.connect(lambda checked, k=key_value: self.key_pressed.emit(k))
        return button
    def update_layout(self):
        """Update the keyboard layout based on current mode."""
        # Clear existing buttons
        for row_info in self.key_rows:
            for button in row_info['buttons']:
                row_info['layout'].removeWidget(button)
                button.deleteLater()
            row_info['buttons'].clear()
        # Get current layout
        if self.current_layout == "letters":
            if self.shift_active or self.caps_lock:
                main_rows = KeyboardLayout.QWERTY_LETTERS_UPPER
            else:
                main_rows = KeyboardLayout.QWERTY_LETTERS
            bottom_row = KeyboardLayout.BOTTOM_ROW_LETTERS
        elif self.current_layout == "numbers":
            main_rows = KeyboardLayout.NUMBERS_SYMBOLS
            bottom_row = KeyboardLayout.BOTTOM_ROW_NUMBERS
        else:  # symbols
            main_rows = KeyboardLayout.SYMBOLS_EXTRA
            bottom_row = KeyboardLayout.BOTTOM_ROW_SYMBOLS
        # Create main rows
        for i, row_keys in enumerate(main_rows):
            row_info = self.key_rows[i]
            # Add left spacer for alignment
            if i == 1:  # Middle row
                spacer = QSpacerItem(35, 1, QSizePolicy.Fixed, QSizePolicy.Minimum)
                row_info['layout'].addItem(spacer)
            for key_text in row_keys:
                button = self.create_key_button(key_text)
                row_info['layout'].addWidget(button)
                row_info['buttons'].append(button)
            # Add right spacer
            if i == 1:
                spacer = QSpacerItem(35, 1, QSizePolicy.Fixed, QSizePolicy.Minimum)
                row_info['layout'].addItem(spacer)
        # Create bottom row
        bottom_row_info = self.key_rows[3]
        for key_text in bottom_row:
            if key_text == ' ':
                # Special handling for space bar
                button = self.create_key_button('Space', ' ')
                button.setMinimumWidth(200)
            else:
                button = self.create_key_button(key_text)
            bottom_row_info['layout'].addWidget(button)
            bottom_row_info['buttons'].append(button)
        self.log_debug(f"Updated keyboard layout: {self.current_layout}")
    def switch_layout(self, layout: str):
        """Switch to a different keyboard layout."""
        self.current_layout = layout
        self.shift_active = False
        self.caps_lock = False
        self.update_layout()
        self.log_user_action("keyboard_layout_switch", {"layout": layout})
    def toggle_shift(self):
        """Toggle shift/caps lock."""
        if self.shift_active:
            self.caps_lock = not self.caps_lock
            self.shift_active = self.caps_lock
        else:
            self.shift_active = True
            self.caps_lock = False
        self.update_layout()
        self.log_user_action("keyboard_shift_toggle", {
            "shift_active": self.shift_active,
            "caps_lock": self.caps_lock
        })
    def show_language_options(self):
        """Show language/locale options (placeholder)."""
        self.log_user_action("keyboard_language_requested")
        # TODO: Implement language switching
        pass
    def show_for_widget(self, widget: QWidget):
        """Show keyboard for a specific widget."""
        self.target_widget = widget
        if isinstance(widget, (QLineEdit, QTextEdit)):
            self.original_text = widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()
        # Position keyboard
        self.position_keyboard()
        # Show with animation
        self.show()
        self.start_show_animation()
        # Reset hide timer
        self.hide_timer.start(30000)  # Auto-hide after 30 seconds
        self.log_user_action("keyboard_shown", {"widget_type": type(widget).__name__})
    def position_keyboard(self):
        """Position keyboard appropriately on screen."""
        if not self.target_widget:
            return
        screen = QApplication.primaryScreen().geometry()
        widget_geometry = self.target_widget.geometry()
        widget_global_pos = self.target_widget.mapToGlobal(widget_geometry.topLeft())
        # Calculate position
        x = max(0, min(widget_global_pos.x(), screen.width() - self.keyboard_width))
        # Position above widget if it's in bottom half, below if in top half
        if widget_global_pos.y() > screen.height() // 2:
            y = widget_global_pos.y() - self.keyboard_height - 10
        else:
            y = widget_global_pos.y() + widget_geometry.height() + 10
        # Ensure keyboard stays on screen
        y = max(0, min(y, screen.height() - self.keyboard_height))
        self.move(x, y)
    def start_show_animation(self):
        """Start the show animation."""
        current_geometry = self.geometry()
        start_geometry = QRect(current_geometry.x(), current_geometry.y() + 50,
                             current_geometry.width(), current_geometry.height())
        self.setGeometry(start_geometry)
        self.show_animation.setStartValue(start_geometry)
        self.show_animation.setEndValue(current_geometry)
        self.show_animation.start()
    def hide_keyboard(self):
        """Hide keyboard with animation."""
        current_geometry = self.geometry()
        end_geometry = QRect(current_geometry.x(), current_geometry.y() + 50,
                           current_geometry.width(), current_geometry.height())
        self.hide_animation.setStartValue(current_geometry)
        self.hide_animation.setEndValue(end_geometry)
        self.hide_animation.start()
        self.keyboard_hidden.emit()
        self.log_user_action("keyboard_hidden")
    def _handle_key_press(self, key: str):
        """Handle key press and send to target widget."""
        if not self.target_widget:
            return
        if isinstance(self.target_widget, QLineEdit):
            cursor_pos = self.target_widget.cursorPosition()
            current_text = self.target_widget.text()
            new_text = current_text[:cursor_pos] + key + current_text[cursor_pos:]
            self.target_widget.setText(new_text)
            self.target_widget.setCursorPosition(cursor_pos + 1)
        elif isinstance(self.target_widget, QTextEdit):
            cursor = self.target_widget.textCursor()
            cursor.insertText(key)
        # Auto-disable shift after character (unless caps lock)
        if self.shift_active and not self.caps_lock:
            self.shift_active = False
            self.update_layout()
        # Reset hide timer
        self.hide_timer.start(30000)
        self.log_user_action("keyboard_key_press", {"key": key})
    def _handle_backspace(self):
        """Handle backspace key."""
        if not self.target_widget:
            return
        if isinstance(self.target_widget, QLineEdit):
            cursor_pos = self.target_widget.cursorPosition()
            if cursor_pos > 0:
                current_text = self.target_widget.text()
                new_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                self.target_widget.setText(new_text)
                self.target_widget.setCursorPosition(cursor_pos - 1)
        elif isinstance(self.target_widget, QTextEdit):
            cursor = self.target_widget.textCursor()
            cursor.deletePreviousChar()
        self.hide_timer.start(30000)
        self.log_user_action("keyboard_backspace")
    def _handle_enter(self):
        """Handle enter key."""
        if not self.target_widget:
            return
        if isinstance(self.target_widget, QLineEdit):
            self.target_widget.returnPressed.emit()
            self.hide_keyboard()
        elif isinstance(self.target_widget, QTextEdit):
            cursor = self.target_widget.textCursor()
            cursor.insertText('\n')
        self.log_user_action("keyboard_enter")
    def eventFilter(self, obj, event):
        """Event filter to handle outside clicks."""
        if event.type() == QEvent.MouseButtonPress:
            if not self.geometry().contains(event.globalPos()):
                self.hide_keyboard()
                return True
        return super().eventFilter(obj, event)
class VirtualKeyboardManager(QObject, LoggableMixin):
    """Manager for virtual keyboard instances and integration."""
    _instance = None
    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        LoggableMixin.__init__(self)
        self.keyboard = None
        self.installed_widgets = set()
        self.event_filters = {}
        self.log_debug("Virtual keyboard manager initialized")
    @classmethod
    def get_instance(cls):
        """Get singleton instance of keyboard manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    def get_keyboard(self) -> VirtualKeyboard:
        """Get or create the virtual keyboard instance."""
        if self.keyboard is None:
            self.keyboard = VirtualKeyboard()
            self.log_debug("Created new virtual keyboard instance")
        return self.keyboard
    def install_on_widget(self, widget: Union[QLineEdit, QTextEdit]):
        """Install virtual keyboard on a widget."""
        if widget in self.installed_widgets:
            return
        # Create event filter for this widget
        event_filter = KeyboardEventFilter(widget, self)
        widget.installEventFilter(event_filter)
        self.installed_widgets.add(widget)
        self.event_filters[widget] = event_filter
        self.log_debug(f"Installed virtual keyboard on {type(widget).__name__}")
    def remove_from_widget(self, widget: Union[QLineEdit, QTextEdit]):
        """Remove virtual keyboard from a widget."""
        if widget not in self.installed_widgets:
            return
        # Remove event filter
        event_filter = self.event_filters.get(widget)
        if event_filter:
            widget.removeEventFilter(event_filter)
            del self.event_filters[widget]
        self.installed_widgets.discard(widget)
        self.log_debug(f"Removed virtual keyboard from {type(widget).__name__}")
    def show_keyboard_for_widget(self, widget: Union[QLineEdit, QTextEdit]):
        """Show virtual keyboard for a specific widget."""
        keyboard = self.get_keyboard()
        keyboard.show_for_widget(widget)
    def hide_keyboard(self):
        """Hide the virtual keyboard."""
        if self.keyboard:
            self.keyboard.hide_keyboard()
    def is_keyboard_visible(self) -> bool:
        """Check if keyboard is currently visible."""
        return self.keyboard is not None and self.keyboard.isVisible()
class KeyboardEventFilter(QObject):
    """Event filter to detect when keyboard should be shown."""
    def __init__(self, widget: QWidget, manager: VirtualKeyboardManager):
        super().__init__(widget)
        self.widget = widget
        self.manager = manager
        self.logger = get_logger()
    def eventFilter(self, obj, event):
        """Filter events to show keyboard on focus."""
        if obj == self.widget:
            if event.type() == QEvent.FocusIn:
                # Show keyboard when widget gets focus
                QTimer.singleShot(100, lambda: self.manager.show_keyboard_for_widget(self.widget))
                self.logger.debug(f"Focus in detected for {type(self.widget).__name__}")
            elif event.type() == QEvent.MouseButtonPress:
                # Also show on mouse press for touch devices
                QTimer.singleShot(50, lambda: self.manager.show_keyboard_for_widget(self.widget))
                self.logger.debug(f"Mouse press detected for {type(self.widget).__name__}")
        return super().eventFilter(obj, event)
# Convenience functions for global access
def get_keyboard_manager() -> VirtualKeyboardManager:
    """Get the global keyboard manager instance."""
    return VirtualKeyboardManager.get_instance()
def install_keyboard_on_widget(widget: Union[QLineEdit, QTextEdit]):
    """Install virtual keyboard on a widget."""
    get_keyboard_manager().install_on_widget(widget)
def remove_keyboard_from_widget(widget: Union[QLineEdit, QTextEdit]):
    """Remove virtual keyboard from a widget."""
    get_keyboard_manager().remove_from_widget(widget)
def show_keyboard_for_widget(widget: Union[QLineEdit, QTextEdit]):
    """Show virtual keyboard for a widget."""
    get_keyboard_manager().show_keyboard_for_widget(widget)
def hide_keyboard():
    """Hide the virtual keyboard."""
    get_keyboard_manager().hide_keyboard()
def is_keyboard_visible() -> bool:
    """Check if virtual keyboard is visible."""
    return get_keyboard_manager().is_keyboard_visible()
# Auto-installation helper
class KeyboardAutoInstaller(QObject):
    """Automatically install keyboard on widgets as they are created."""
    def __init__(self, parent_widget: QWidget):
        super().__init__(parent_widget)
        self.parent_widget = parent_widget
        self.manager = get_keyboard_manager()
        self.installed_on_children()
    def installed_on_children(self):
        """Install keyboard on all child text input widgets."""
        for child in self.parent_widget.findChildren(QLineEdit):
            self.manager.install_on_widget(child)
        for child in self.parent_widget.findChildren(QTextEdit):
            self.manager.install_on_widget(child)
def auto_install_keyboard(parent_widget: QWidget):
    """Automatically install keyboard on all text input widgets in a parent."""
    return KeyboardAutoInstaller(parent_widget)
