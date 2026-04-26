from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal

class FilterSettingsDialog(QDialog):
    # Segnale emesso ogni volta che un valore cambia per l'anteprima in tempo reale
    settingsChanged = pyqtSignal(dict)

    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni Filtro")
        self.setFixedWidth(350)
        self.setStyleSheet("background-color: #2a2a2a; color: white; font-family: Segoe UI;")
        
        self.settings = current_settings.copy()
        layout = QVBoxLayout(self)

        # --- SLIDER BLOCK SIZE ---
        layout.addWidget(QLabel("Dimensione Area (Block Size):"))
        self.lbl_block = QLabel(str(self.settings['block_size']))
        self.lbl_block.setStyleSheet("color: #4ade80; font-weight: bold;")
        
        self.slider_block = QSlider(Qt.Orientation.Horizontal)
        self.slider_block.setRange(3, 99) 
        self.slider_block.setValue(self.settings['block_size'])
        self.slider_block.valueChanged.connect(self.update_block)
        
        h_box1 = QHBoxLayout()
        h_box1.addWidget(self.slider_block)
        h_box1.addWidget(self.lbl_block)
        layout.addLayout(h_box1)

        # --- SLIDER CONSTANT C ---
        layout.addWidget(QLabel("Soglia di Pulizia (C):"))
        self.lbl_c = QLabel(str(self.settings['c_value']))
        self.lbl_c.setStyleSheet("color: #4ade80; font-weight: bold;")
        
        self.slider_c = QSlider(Qt.Orientation.Horizontal)
        self.slider_c.setRange(-10, 50)
        self.slider_c.setValue(self.settings['c_value'])
        self.slider_c.valueChanged.connect(self.update_c)
        
        h_box2 = QHBoxLayout()
        h_box2.addWidget(self.slider_c)
        h_box2.addWidget(self.lbl_c)
        layout.addLayout(h_box2)

        layout.addSpacing(20)
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet("background-color: #3a3a3a; padding: 10px; border-radius: 4px;")
        layout.addWidget(btn_close)

    def update_block(self, val):
        if val % 2 == 0: val += 1 # Deve essere dispari
        self.settings['block_size'] = val
        self.lbl_block.setText(str(val))
        self.settingsChanged.emit(self.settings)

    def update_c(self, val):
        self.settings['c_value'] = val
        self.lbl_c.setText(str(val))
        self.settingsChanged.emit(self.settings)
