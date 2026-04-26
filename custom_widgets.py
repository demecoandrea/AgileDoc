from PyQt6.QtWidgets import QPushButton, QWidget, QHBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QRectF

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
            p.setBrush(QColor("#4ade80")) # Verde
        else:
            p.setBrush(QColor("#555555")) # Grigio
            
        p.drawRoundedRect(rect, self.height() / 2, self.height() / 2)
        p.setBrush(QColor("#ffffff"))
        
        if self._is_checked:
            p.drawEllipse(int(self.width() - self.height() + 2), 2, int(self.height() - 4), int(self.height() - 4))
        else:
            p.drawEllipse(2, 2, int(self.height() - 4), int(self.height() - 4))


class LabeledToggle(QFrame):
    toggled = pyqtSignal(bool)

    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            LabeledToggle {
                background-color: #3a3a3a; 
                border-radius: 4px; 
                border: 1px solid #555555;
            }
        """)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(5)
        
        self.toggle = ToggleSwitch()
        self.toggle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.label = QLabel(label_text)
        
        # Calcoliamo la larghezza del testo in grassetto per evitare ridimensionamenti
        font = self.label.font()
        font.setBold(True)
        fm = QFontMetrics(font)
        max_width = fm.horizontalAdvance(label_text) + 2
        self.label.setMinimumWidth(max_width)
        
        # Partiamo con lo stile normale di default
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
    """
    Un widget generico che presenta un gruppo di bottoni a segmenti.
    Emette 'selectionChanged(int)' quando cambia l'indice selezionato.
    """
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
        
        self.base_style = """
            QPushButton { 
                background-color: #333333; 
                color: #888; 
                border: 1px solid #555; 
                padding: 6px 12px; 
                font-size: 11px; 
                font-weight: bold;
                border-radius: 0px;
            }
            QPushButton:hover { background-color: #404040; }
        """
        self.active_style = "background-color: #f2c94c; color: #222; border: 1px solid #8a7522;"
        
        for i, text in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Applichiamo bordi arrotondati solo agli estremi
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
                # Manteniamo il colore giallo anche al passaggio del mouse se il bottone è attivo
                style += "QPushButton:hover { background-color: #f2c94c; }"
            
            btn.setStyleSheet(style)
            btn.blockSignals(False)
