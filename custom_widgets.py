from PyQt6.QtWidgets import QPushButton, QWidget, QHBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPainter, QColor, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QRectF

from const_and_resources import Colors

class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_checked = False

    def isChecked(self):
        return self._is_checked

    def setChecked(self, checked):
        self._is_checked = checked
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_checked = not self._is_checked
            self.toggled.emit(self._is_checked)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(0, 0, self.width(), self.height())
        
        if self._is_checked:
            p.setBrush(QColor(Colors.HEX_SUCCESS)) 
        else:
            p.setBrush(QColor(Colors.HEX_BORDER)) 
            
        p.drawRoundedRect(rect, self.height() / 2, self.height() / 2)
        p.setBrush(Colors.WHITE)
        
        if self._is_checked:
            p.drawEllipse(int(self.width() - self.height() + 2), 2, int(self.height() - 4), int(self.height() - 4))
        else:
            p.drawEllipse(2, 2, int(self.height() - 4), int(self.height() - 4))


class LabeledToggle(QFrame):
    toggled = pyqtSignal(bool)

    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            LabeledToggle {{
                background-color: {Colors.HEX_BTN_BG}; 
                border-radius: 4px; 
                border: 1px solid {Colors.HEX_BORDER};
            }}
        """)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(5)
        
        self.toggle = ToggleSwitch()
        self.toggle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.label = QLabel(label_text)
        
        font = self.label.font()
        font.setBold(True)
        fm = QFontMetrics(font)
        max_width = fm.horizontalAdvance(label_text) + 2
        self.label.setMinimumWidth(max_width)
        
        self.label.setStyleSheet("color: #dddddd; border: none; background: transparent; font-weight: normal;")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        layout.addWidget(self.toggle)
        layout.addWidget(self.label)
        
    def _update_label_style(self, is_checked):
        if is_checked:
            self.label.setStyleSheet("color: #dddddd; border: none; background: transparent; font-weight: bold;")
        else:
            self.label.setStyleSheet("color: #dddddd; border: none; background: transparent; font-weight: normal;")

    def isChecked(self):
        return self.toggle.isChecked()
        
    def setChecked(self, checked):
        self.toggle.setChecked(checked)
        self._update_label_style(checked)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = not self.toggle.isChecked()
            self.toggle.setChecked(new_state)
            self._update_label_style(new_state)
            self.toggled.emit(new_state)
            super().mouseReleaseEvent(event)


class SegmentedControl(QWidget):
    selectionChanged = pyqtSignal(int)

    def __init__(self, options, label_text=None, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if label_text:
            self.lbl = QLabel(label_text.upper())
            self.lbl.setStyleSheet("color: #aaaaaa; font-weight: bold; font-size: 11px; margin-right: 8px;")
            layout.addWidget(self.lbl)

        self.buttons = []
        self._currentIndex = 0
        
        self.base_style = f"""
            QPushButton {{ 
                background-color: {Colors.HEX_BTN_BG}; 
                color: #888; 
                border: 1px solid {Colors.HEX_BORDER}; 
                padding: 6px 12px; 
                font-size: 11px; 
                font-weight: bold;
                border-radius: 0px;
            }}
            QPushButton:hover {{ background-color: {Colors.HEX_BTN_HOVER}; }}
        """
        self.active_style = f"background-color: {Colors.HEX_WARNING}; color: #222; border: 1px solid #8a7522;"
        
        for i, text in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            style = self.base_style
            if i == 0:
                style += "QPushButton { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }"
            if i == len(options) - 1:
                style += "QPushButton { border-top-right-radius: 4px; border-bottom-right-radius: 4px; }"
                
            btn.setStyleSheet(style)
            btn.clicked.connect(lambda checked, idx=i: self.setCurrentIndex(idx))
            layout.addWidget(btn)
            self.buttons.append(btn)
            
        self.update_selection()

    def setCurrentIndex(self, index):
        if 0 <= index < len(self.buttons):
            if self._currentIndex != index:
                self._currentIndex = index
                self.update_selection()
                self.selectionChanged.emit(index)

    def currentIndex(self):
        return self._currentIndex

    def update_selection(self):
        for i, btn in enumerate(self.buttons):
            btn.blockSignals(True)
            btn.setChecked(i == self._currentIndex)
            
            style = self.base_style
            if i == 0: style += "QPushButton { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }"
            if i == len(self.buttons)-1: style += "QPushButton { border-top-right-radius: 4px; border-bottom-right-radius: 4px; }"
            
            if i == self._currentIndex:
                style += "QPushButton { " + self.active_style + " }"
                style += f"QPushButton:hover {{ background-color: {Colors.HEX_WARNING}; }}"
            
            btn.setStyleSheet(style)
            btn.blockSignals(False)
