"""

Virtual Numpad Module for Hunt Pro.



Touch-optimized numeric keypad for number input fields.

Automatically appears when numeric fields are tapped and provides

calculator-style input with field validation.

"""



from PySide6.QtWidgets import (

    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, 

    QFrame, QLabel, QApplication, QLineEdit, QSpinBox, QDoubleSpinBox, 

    QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect

)

from PySide6.QtCore import (

    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QRect, 

    QObject, QEvent, QPoint, QSize

)

from PySide6.QtGui import QFont, QFontMetrics, QPalette, QColor, QValidator

from typing import Optional, Union, List, Tuple

import re



from logger import get_logger, LoggableMixin



class NumpadLayout:

    """Numpad layout definitions for different input types."""

    

    STANDARD_KEYS = [

        ['C', 'Â±', '%', 'âŒ«'],

        ['7', '8', '9', 'Ã·'],

        ['4', '5', '6', 'Ã—'],

        ['1', '2', '3', '-'],

        ['0', '.', '=', '+']

    ]

    

    SIMPLE_KEYS = [

        ['âŒ«', 'Â±', 'C'],

        ['7', '8', '9'],

        ['4', '5', '6'],

        ['1', '2', '3'],

        ['0', '.', 'â†µ']

    ]

    

    # Key mappings for special functions

    SPECIAL_KEYS = {

        'C': 'clear',

        'Â±': 'plus_minus',

        '%': 'percent',

        'âŒ«': 'backspace',

        'Ã·': 'divide',

        'Ã—': 'multiply',

        '-': 'subtract',

        '+': 'add',

        '=': 'equals',

        'â†µ': 'enter'

    }



class VirtualNumpad(QWidget, LoggableMixin):

    """Touch-optimized virtual numpad widget."""

    

    # Signals

    number_pressed = Signal(str)

    operation_pressed = Signal(str)

    decimal_pressed = Signal()

    backspace_pressed = Signal()

    clear_pressed = Signal()

    enter_pressed = Signal()

    plus_minus_pressed = Signal()

    numpad_hidden = Signal()

    value_changed = Signal(float)

    

    def __init__(self, parent=None):

        QWidget.__init__(self, parent)

        LoggableMixin.__init__(self)

        

        self.target_widget = None

        self.current_value = "0"

        self.decimal_places = 2

        self.allow_decimal = True

        self.allow_negative = True

        self.min_value = None

        self.max_value = None

        self.simple_mode = False

        

        # Calculator state

        self.calculator_mode = False

        self.stored_value = 0.0

        self.current_operation = None

        self.waiting_for_operand = True

        

        # Numpad dimensions optimized for tablet

        self.numpad_width = 320

        self.numpad_height = 400

        self.button_size = QSize(70, 60)

        

        self.setup_ui()

        self.setup_animations()

        self.apply_styling()

        

        # Auto-hide timer

        self.hide_timer = QTimer()

        self.hide_timer.setSingleShot(True)

        self.hide_timer.timeout.connect(self.hide_numpad)

        

        # Connect signals

        self.number_pressed.connect(self._handle_number_press)

        self.operation_pressed.connect(self._handle_operation_press)

        self.decimal_pressed.connect(self._handle_decimal_press)

        self.backspace_pressed.connect(self._handle_backspace)

        self.clear_pressed.connect(self._handle_clear)

        self.enter_pressed.connect(self._handle_enter)

        self.plus_minus_pressed.connect(self._handle_plus_minus)

        

        self.log_debug("Virtual numpad initialized")

    

    def setup_ui(self):

        """Setup the numpad UI - optimized for touch interaction."""

        self.setFixedSize(self.numpad_width, self.numpad_height)

        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)

        self.setAttribute(Qt.WA_TranslucentBackground)

        

        # Main layout

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(10, 10, 10, 10)

        main_layout.setSpacing(8)

        

        # Numpad container with shadow

        self.numpad_frame = QFrame()

        self.numpad_frame.setObjectName("numpadFrame")

        

        # Add drop shadow

        shadow = QGraphicsDropShadowEffect()

        shadow.setBlurRadius(20)

        shadow.setOffset(0, 5)

        shadow.setColor(QColor(0, 0, 0, 100))

        self.numpad_frame.setGraphicsEffect(shadow)

        

        frame_layout = QVBoxLayout(self.numpad_frame)

        frame_layout.setContentsMargins(15, 15, 15, 15)

        frame_layout.setSpacing(8)

        

        # Display area

        self.create_display(frame_layout)

        

        # Key grid

        self.create_key_grid(frame_layout)

        

        main_layout.addWidget(self.numpad_frame)

    

    def create_display(self, layout):

        """Create the display area showing current value."""

        display_frame = QFrame()

        display_frame.setObjectName("displayFrame")

        display_frame.setFixedHeight(60)

        

        display_layout = QHBoxLayout(display_frame)

        display_layout.setContentsMargins(10, 5, 10, 5)

        

        self.display_label = QLabel("0")

        self.display_label.setObjectName("displayLabel")

        self.display_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.display_label.setFont(QFont("monospace", 18, QFont.Bold))

        

        display_layout.addWidget(self.display_label)

        layout.addWidget(display_frame)

    

    def create_key_grid(self, layout):

        """Create the grid of numpad keys."""

        # Key container

        keys_widget = QWidget()

        self.keys_layout = QGridLayout(keys_widget)

        self.keys_layout.setContentsMargins(0, 0, 0, 0)

        self.keys_layout.setSpacing(4)

        

        # Create keys based on mode

        self.key_buttons = {}

        self.update_key_layout()

        

        layout.addWidget(keys_widget)

    

    def update_key_layout(self):

        """Update the key layout based on current mode."""

        # Clear existing buttons

        for button in self.key_buttons.values():

            self.keys_layout.removeWidget(button)

            button.deleteLater()

        self.key_buttons.clear()

        

        # Choose layout

        if self.simple_mode:

            key_layout = NumpadLayout.SIMPLE_KEYS

        else:

            key_layout = NumpadLayout.STANDARD_KEYS

        

        # Create buttons

        for row, key_row in enumerate(key_layout):

            for col, key_text in enumerate(key_row):

                button = self.create_key_button(key_text)

                self.keys_layout.addWidget(button, row, col)

                self.key_buttons[key_text] = button

    

    def create_key_button(self, key_text: str) -> QPushButton:

        """Create a numpad key button with proper styling and behavior."""

        button = QPushButton(key_text)

        button.setFont(QFont("Arial", 16, QFont.Bold))

        button.setMinimumSize(self.button_size)

        

        # Set object names for styling

        if key_text in NumpadLayout.SPECIAL_KEYS:

            if key_text in ['C', 'âŒ«']:

                button.setObjectName("clearKey")

            elif key_text in ['+', '-', 'Ã—', 'Ã·', '=']:

                button.setObjectName("operatorKey")

            elif key_text in ['Â±', '%']:

                button.setObjectName("functionKey")

            elif key_text == 'â†µ':

                button.setObjectName("enterKey")

        elif key_text == '0':

            button.setObjectName("zeroKey")

            if not self.simple_mode:

                # Make zero key wider in standard mode

                button.setMinimumWidth(self.button_size.width() * 2 + 4)

        elif key_text == '.':

            button.setObjectName("decimalKey")

        else:

            button.setObjectName("numberKey")

        

        # Connect button to appropriate handler

        if key_text in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:

            button.clicked.connect(lambda checked, k=key_text: self.number_pressed.emit(k))

        elif key_text == '.':

            button.clicked.connect(self.decimal_pressed.emit)

        elif key_text == 'âŒ«':

            button.clicked.connect(self.backspace_pressed.emit)

        elif key_text == 'C':

            button.clicked.connect(self.clear_pressed.emit)

        elif key_text == 'â†µ':

            button.clicked.connect(self.enter_pressed.emit)

        elif key_text == 'Â±':

            button.clicked.connect(self.plus_minus_pressed.emit)

        elif key_text in ['+', '-', 'Ã—', 'Ã·', '=', '%']:

            button.clicked.connect(lambda checked, op=key_text: self.operation_pressed.emit(op))

        

        return button

    

    def setup_animations(self):

        """Setup animations for numpad show/hide."""

        self.show_animation = QPropertyAnimation(self, b"geometry")

        self.show_animation.setDuration(300)

        self.show_animation.setEasingCurve(QEasingCurve.OutCubic)

        

        self.hide_animation = QPropertyAnimation(self, b"geometry")

        self.hide_animation.setDuration(250)

        self.hide_animation.setEasingCurve(QEasingCurve.InCubic)

        self.hide_animation.finished.connect(self.hide)

    

    def apply_styling(self):

        """Apply modern styling to the numpad."""

        style = """

        QFrame#numpadFrame {

            background-color: #2a3441;

            border: 2px solid #3d5a8c;

            border-radius: 15px;

        }

        

        QFrame#displayFrame {

            background-color: #1a2332;

            border: 1px solid #3d5a8c;

            border-radius: 8px;

        }

        

        QLabel#displayLabel {

            color: #ffffff;

            background-color: transparent;

            font-size: 18px;

            font-weight: bold;

            padding: 5px;

        }

        

        QPushButton {

            border: 1px solid #4a6ba8;

            border-radius: 8px;

            color: white;

            font-size: 16px;

            font-weight: 600;

            min-height: 50px;

            min-width: 60px;

        }

        

        QPushButton:hover {

            border-width: 2px;

        }

        

        QPushButton:pressed {

            margin-top: 2px;

        }

        

        QPushButton#numberKey {

            background-color: #4a6ba8;

        }

        

        QPushButton#numberKey:hover {

            background-color: #5a7bb8;

        }

        

        QPushButton#zeroKey {

            background-color: #4a6ba8;

        }

        

        QPushButton#decimalKey {

            background-color: #4a6ba8;

        }

        

        QPushButton#operatorKey {

            background-color: #2c5aa0;

        }

        

        QPushButton#operatorKey:hover {

            background-color: #3d6bb0;

        }

        

        QPushButton#functionKey {

            background-color: #5a7bb8;

        }

        

        QPushButton#functionKey:hover {

            background-color: #6a8bc8;

        }

        

        QPushButton#clearKey {

            background-color: #dc3545;

        }

        

        QPushButton#clearKey:hover {

            background-color: #c82333;

        }

        

        QPushButton#enterKey {

            background-color: #28a745;

        }

        

        QPushButton#enterKey:hover {

            background-color: #218838;

        }

        """

        self.setStyleSheet(style)

    

    def configure_for_widget(self, widget: Union[QSpinBox, QDoubleSpinBox]):

        """Configure numpad based on target widget properties."""

        self.target_widget = widget

        

        if isinstance(widget, QSpinBox):

            self.allow_decimal = False

            self.decimal_places = 0

            self.min_value = widget.minimum()

            self.max_value = widget.maximum()

            self.current_value = str(widget.value())

        elif isinstance(widget, QDoubleSpinBox):

            self.allow_decimal = True

            self.decimal_places = widget.decimals()

            self.min_value = widget.minimum()

            self.max_value = widget.maximum()

            self.current_value = f"{widget.value():.{self.decimal_places}f}".rstrip('0').rstrip('.')

        

        # Update display

        self.update_display()

        

        # Enable/disable decimal key

        if '.' in self.key_buttons:

            self.key_buttons['.'].setEnabled(self.allow_decimal)

        

        self.log_debug(f"Configured numpad for {type(widget).__name__}")

    

    def update_display(self):

        """Update the display with current value."""

        display_text = self.current_value

        

        # Format for display

        if self.current_value == "0" or self.current_value == "":

            display_text = "0"

        elif self.allow_decimal and '.' in self.current_value:

            # Show decimals but remove trailing zeros

            display_text = self.current_value.rstrip('0').rstrip('.')

        

        self.display_label.setText(display_text)

    

    def show_for_widget(self, widget: Union[QSpinBox, QDoubleSpinBox]):

        """Show numpad for a specific widget."""

        self.configure_for_widget(widget)

        

        # Position numpad

        self.position_numpad()

        

        # Show with animation

        self.show()

        self.start_show_animation()

        

        # Reset hide timer

        self.hide_timer.start(30000)  # Auto-hide after 30 seconds

        

        self.log_user_action("numpad_shown", {"widget_type": type(widget).__name__})

    

    def position_numpad(self):

        """Position numpad appropriately on screen."""

        if not self.target_widget:

            return

        

        screen = QApplication.primaryScreen().geometry()

        widget_geometry = self.target_widget.geometry()

        widget_global_pos = self.target_widget.mapToGlobal(widget_geometry.topLeft())

        

        # Calculate position

        x = max(0, min(widget_global_pos.x(), screen.width() - self.numpad_width))

        

        # Position to the right of widget if there's space, otherwise to the left

        if widget_global_pos.x() + widget_geometry.width() + self.numpad_width < screen.width():

            x = widget_global_pos.x() + widget_geometry.width() + 10

        else:

            x = max(0, widget_global_pos.x() - self.numpad_width - 10)

        

        # Vertically align with widget

        y = widget_global_pos.y()

        

        # Ensure numpad stays on screen

        y = max(0, min(y, screen.height() - self.numpad_height))

        

        self.move(x, y)

    

    def start_show_animation(self):

        """Start the show animation."""

        current_geometry = self.geometry()

        start_geometry = QRect(current_geometry.x() - 30, current_geometry.y(),

                             current_geometry.width(), current_geometry.height())

        

        self.setGeometry(start_geometry)

        

        self.show_animation.setStartValue(start_geometry)

        self.show_animation.setEndValue(current_geometry)

        self.show_animation.start()

    

    def hide_numpad(self):

        """Hide numpad with animation."""

        current_geometry = self.geometry()

        end_geometry = QRect(current_geometry.x() - 30, current_geometry.y(),

                           current_geometry.width(), current_geometry.height())

        

        self.hide_animation.setStartValue(current_geometry)

        self.hide_animation.setEndValue(end_geometry)

        self.hide_animation.start()

        

        self.numpad_hidden.emit()

        self.log_user_action("numpad_hidden")

    

    def _handle_number_press(self, number: str):

        """Handle number key press."""

        if self.waiting_for_operand or self.current_value == "0":

            self.current_value = number

            self.waiting_for_operand = False

        else:

            if len(self.current_value) < 10:  # Limit length

                self.current_value += number

        

        self.update_display()

        self.apply_to_widget()

        self.hide_timer.start(30000)

        

        self.log_user_action("numpad_number_press", {"number": number})

    

    def _handle_decimal_press(self):

        """Handle decimal point press."""

        if not self.allow_decimal:

            return

        

        if self.waiting_for_operand:

            self.current_value = "0."

            self.waiting_for_operand = False

        elif '.' not in self.current_value:

            self.current_value += '.'

        

        self.update_display()

        self.hide_timer.start(30000)

        

        self.log_user_action("numpad_decimal_press")

    

    def _handle_backspace(self):

        """Handle backspace key."""

        if len(self.current_value) > 1:

            self.current_value = self.current_value[:-1]

        else:

            self.current_value = "0"

            self.waiting_for_operand = True

        

        self.update_display()

        self.apply_to_widget()

        self.hide_timer.start(30000)

        

        self.log_user_action("numpad_backspace")

    

    def _handle_clear(self):

        """Handle clear key."""

        self.current_value = "0"

        self.waiting_for_operand = True

        self.stored_value = 0.0

        self.current_operation = None

        

        self.update_display()

        self.apply_to_widget()

        

        self.log_user_action("numpad_clear")

    

    def _handle_plus_minus(self):

        """Handle plus/minus key to toggle sign."""

        if not self.allow_negative:

            return

        

        if self.current_value != "0":

            if self.current_value.startswith('-'):

                self.current_value = self.current_value[1:]

            else:

                self.current_value = '-' + self.current_value

        

        self.update_display()

        self.apply_to_widget()

        

        self.log_user_action("numpad_plus_minus")

    

    def _handle_operation_press(self, operation: str):

        """Handle operation key press."""

        # Simple operations for basic calculator functionality

        current_float = self.get_current_float()

        

        if operation == '=':

            if self.current_operation and not self.waiting_for_operand:

                result = self.calculate(self.stored_value, current_float, self.current_operation)

                self.current_value = self.format_number(result)

                self.current_operation = None

                self.waiting_for_operand = True

        elif operation == '%':

            # Convert to percentage

            result = current_float / 100

            self.current_value = self.format_number(result)

            self.waiting_for_operand = True

        else:

            # Store operation for later calculation

            if not self.waiting_for_operand and self.current_operation:

                result = self.calculate(self.stored_value, current_float, self.current_operation)

                self.current_value = self.format_number(result)

            

            self.stored_value = self.get_current_float()

            self.current_operation = operation

            self.waiting_for_operand = True

        

        self.update_display()

        self.apply_to_widget()

        

        self.log_user_action("numpad_operation_press", {"operation": operation})

    

    def _handle_enter(self):

        """Handle enter key - apply value and hide."""

        self.apply_to_widget()

        self.hide_numpad()

        

        self.log_user_action("numpad_enter")

    

    def calculate(self, left: float, right: float, operation: str) -> float:

        """Perform calculation between two numbers."""

        try:

            if operation == '+':

                return left + right

            elif operation == '-':

                return left - right

            elif operation == 'Ã—':

                return left * right

            elif operation == 'Ã·':

                return left / right if right != 0 else 0

            else:

                return right

        except (ZeroDivisionError, OverflowError):

            return 0

    

    def get_current_float(self) -> float:

        """Get current value as float."""

        try:

            return float(self.current_value) if self.current_value else 0.0

        except ValueError:

            return 0.0

    

    def format_number(self, value: float) -> str:

        """Format number for display."""

        if self.allow_decimal:

            # Format with appropriate decimal places

            formatted = f"{value:.{self.decimal_places}f}"

            # Remove trailing zeros

            if '.' in formatted:

                formatted = formatted.rstrip('0').rstrip('.')

            return formatted

        else:

            return str(int(value))

    

    def apply_to_widget(self):

        """Apply current value to the target widget."""

        if not self.target_widget:

            return

        

        try:

            value = self.get_current_float()

            

            # Apply min/max constraints

            if self.min_value is not None:

                value = max(value, self.min_value)

            if self.max_value is not None:

                value = min(value, self.max_value)

            

            # Apply to widget

            if isinstance(self.target_widget, QSpinBox):

                self.target_widget.setValue(int(value))

            elif isinstance(self.target_widget, QDoubleSpinBox):

                self.target_widget.setValue(value)

            

            # Update current value with constraints applied

            if isinstance(self.target_widget, QSpinBox):

                self.current_value = str(self.target_widget.value())

            else:

                self.current_value = self.format_number(self.target_widget.value())

            

            self.value_changed.emit(value)

            

        except Exception as e:

            self.log_error("Error applying value to widget", exception=e)

    

    def set_simple_mode(self, simple: bool):

        """Toggle between simple and standard layouts."""

        self.simple_mode = simple

        self.update_key_layout()

        

        # Adjust size for simple mode

        if simple:

            self.numpad_height = 320

        else:

            self.numpad_height = 400

        

        self.setFixedSize(self.numpad_width, self.numpad_height)

    

    def eventFilter(self, obj, event):

        """Event filter to handle outside clicks."""

        if event.type() == QEvent.MouseButtonPress:

            if not self.geometry().contains(event.globalPos()):

                self.hide_numpad()

                return True

        return super().eventFilter(obj, event)





class VirtualNumpadManager(QObject, LoggableMixin):

    """Manager for virtual numpad instances and integration."""

    

    _instance = None

    

    def __init__(self, parent=None):

        QObject.__init__(self, parent)

        LoggableMixin.__init__(self)

        

        self.numpad = None

        self.installed_widgets = set()

        self.event_filters = {}

        

        self.log_debug("Virtual numpad manager initialized")

    

    @classmethod

    def get_instance(cls):

        """Get singleton instance of numpad manager."""

        if cls._instance is None:

            cls._instance = cls()

        return cls._instance

    

    def get_numpad(self) -> VirtualNumpad:

        """Get or create the virtual numpad instance."""

        if self.numpad is None:

            self.numpad = VirtualNumpad()

            self.log_debug("Created new virtual numpad instance")

        return self.numpad

    

    def install_on_widget(self, widget: Union[QSpinBox, QDoubleSpinBox]):

        """Install virtual numpad on a widget."""

        if widget in self.installed_widgets:

            return

        

        # Create event filter for this widget

        event_filter = NumpadEventFilter(widget, self)

        widget.installEventFilter(event_filter)

        

        self.installed_widgets.add(widget)

        self.event_filters[widget] = event_filter

        

        self.log_debug(f"Installed virtual numpad on {type(widget).__name__}")

    

    def remove_from_widget(self, widget: Union[QSpinBox, QDoubleSpinBox]):

        """Remove virtual numpad from a widget."""

        if widget not in self.installed_widgets:

            return

        

        # Remove event filter

        event_filter = self.event_filters.get(widget)

        if event_filter:

            widget.removeEventFilter(event_filter)

            del self.event_filters[widget]

        

        self.installed_widgets.discard(widget)

        self.log_debug(f"Removed virtual numpad from {type(widget).__name__}")

    

    def show_numpad_for_widget(self, widget: Union[QSpinBox, QDoubleSpinBox]):

        """Show virtual numpad for a specific widget."""

        numpad = self.get_numpad()

        numpad.show_for_widget(widget)

    

    def hide_numpad(self):

        """Hide the virtual numpad."""

        if self.numpad:

            self.numpad.hide_numpad()

    

    def is_numpad_visible(self) -> bool:

        """Check if numpad is currently visible."""

        return self.numpad is not None and self.numpad.isVisible()

    

    def set_simple_mode(self, simple: bool):

        """Set simple mode for all future numpad instances."""

        if self.numpad:

            self.numpad.set_simple_mode(simple)





class NumpadEventFilter(QObject):

    """Event filter to detect when numpad should be shown."""

    

    def __init__(self, widget: QWidget, manager: VirtualNumpadManager):

        super().__init__(widget)

        self.widget = widget

        self.manager = manager

        self.logger = get_logger()

    

    def eventFilter(self, obj, event):

        """Filter events to show numpad on focus."""

        if obj == self.widget:

            if event.type() == QEvent.FocusIn:

                # Show numpad when widget gets focus

                QTimer.singleShot(100, lambda: self.manager.show_numpad_for_widget(self.widget))

                self.logger.debug(f"Focus in detected for {type(self.widget).__name__}")

            elif event.type() == QEvent.MouseButtonPress:

                # Also show on mouse press for touch devices

                QTimer.singleShot(50, lambda: self.manager.show_numpad_for_widget(self.widget))

                self.logger.debug(f"Mouse press detected for {type(self.widget).__name__}")

        

        return super().eventFilter(obj, event)





# Convenience functions for global access

def get_numpad_manager() -> VirtualNumpadManager:

    """Get the global numpad manager instance."""

    return VirtualNumpadManager.get_instance()



def install_numpad_on_widget(widget: Union[QSpinBox, QDoubleSpinBox]):

    """Install virtual numpad on a widget."""

    get_numpad_manager().install_on_widget(widget)



def remove_numpad_from_widget(widget: Union[QSpinBox, QDoubleSpinBox]):

    """Remove virtual numpad from a widget."""

    get_numpad_manager().remove_from_widget(widget)



def show_numpad_for_widget(widget: Union[QSpinBox, QDoubleSpinBox]):

    """Show virtual numpad for a widget."""

    get_numpad_manager().show_numpad_for_widget(widget)



def hide_numpad():

    """Hide the virtual numpad."""

    get_numpad_manager().hide_numpad()



def is_numpad_visible() -> bool:

    """Check if virtual numpad is visible."""

    return get_numpad_manager().is_numpad_visible()



def set_numpad_simple_mode(simple: bool):

    """Set simple mode for numpad."""

    get_numpad_manager().set_simple_mode(simple)





# Auto-installation helper

class NumpadAutoInstaller(QObject):

    """Automatically install numpad on widgets as they are created."""

    

    def __init__(self, parent_widget: QWidget):

        super().__init__(parent_widget)

        self.parent_widget = parent_widget

        self.manager = get_numpad_manager()

        self.install_on_children()

    

    def install_on_children(self):

        """Install numpad on all child numeric input widgets."""

        for child in self.parent_widget.findChildren(QSpinBox):

            self.manager.install_on_widget(child)

        

        for child in self.parent_widget.findChildren(QDoubleSpinBox):

            self.manager.install_on_widget(child)





def auto_install_numpad(parent_widget: QWidget):

    """Automatically install numpad on all numeric input widgets in a parent."""

    return NumpadAutoInstaller(parent_widget)





# Input validation helpers

class NumpadValidator:

    """Utility class for input validation in numpad."""

    

    @staticmethod

    def validate_integer(value: str, min_val: int = None, max_val: int = None) -> tuple[bool, int]:

        """Validate integer input."""

        try:

            int_val = int(float(value))

            if min_val is not None and int_val < min_val:

                return False, min_val

            if max_val is not None and int_val > max_val:

                return False, max_val

            return True, int_val

        except (ValueError, OverflowError):

            return False, 0

    

    @staticmethod

    def validate_float(value: str, min_val: float = None, max_val: float = None, 

                      decimals: int = 2) -> tuple[bool, float]:

        """Validate float input."""

        try:

            float_val = float(value)

            # Round to specified decimal places

            float_val = round(float_val, decimals)

            

            if min_val is not None and float_val < min_val:

                return False, min_val

            if max_val is not None and float_val > max_val:

                return False, max_val

            return True, float_val

        except (ValueError, OverflowError):

            return False, 0.0

    

    @staticmethod

    def format_for_display(value: float, decimals: int = 2, remove_trailing_zeros: bool = True) -> str:

        """Format number for display."""

        formatted = f"{value:.{decimals}f}"

        if remove_trailing_zeros and '.' in formatted:

            formatted = formatted.rstrip('0').rstrip('.')

        return formatted
