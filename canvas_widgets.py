import os
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QVBoxLayout, QLabel, 
                             QPushButton, QWidget, QGraphicsDropShadowEffect, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

# Importiamo l'elemento immagine per i controlli di tipo (isinstance)
from canvas_items import EditableImageItem

# --- STILE GLOBALE UNIFICATO PER LE TOOLBAR FLOTTANTI ---
UNIFIED_BTN_STYLE = """
    QPushButton, QLabel {
        background-color: #3a3a3a; 
        color: #dddddd; 
        border-radius: 4px; 
        padding: 6px 3px; 
        font-weight: bold; 
        font-size: 14px; 
        border: 1px solid #555555;
    }
    QPushButton:hover { background-color: #505050; border: 1px solid #777777; }
    QPushButton:pressed { background-color: #2a2a2a; }
"""

class UndoSnackbar(QFrame):
    undo_requested = pyqtSignal()
    dismiss_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background-color: #2b2b2b; border-radius: 6px; border: 1px solid #4facfe; }
            QLabel { color: white; font-size: 14px; font-weight: bold; border: none; background: transparent; }
            QPushButton#undoBtn { color: #4facfe; font-weight: bold; background: transparent; border: none; padding: 0 10px; font-size: 14px; }
            QPushButton#undoBtn:hover { text-decoration: underline; color: #73c2fb; }
            QPushButton#closeBtn { color: #888888; font-weight: bold; background: transparent; border: none; font-size: 16px; }
            QPushButton#closeBtn:hover { color: #ffffff; }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 10, 10)
        
        self.lbl_msg = QLabel("Pagine eliminate.")
        layout.addWidget(self.lbl_msg)
        layout.addSpacing(15)
        
        self.btn_undo = QPushButton("ANNULLA", objectName="undoBtn")
        self.btn_undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_undo.clicked.connect(self.undo_requested.emit)
        layout.addWidget(self.btn_undo)
        
        self.btn_close = QPushButton("✕", objectName="closeBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.dismiss_requested.emit)
        layout.addWidget(self.btn_close)
        self.hide()


class PageOutputModeWidget(QWidget):
    def __init__(self, page_item, canvas, parent=None):
        super().__init__(parent)
        self.page_item = page_item
        self.canvas = canvas
        self.setFixedWidth(46)
        self.current_mode = "-"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_mode = QPushButton("N")
        self.btn_mode.setToolTip("Forza modalità per l'intera pagina")
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_mode.clicked.connect(self.toggle_mode)
        layout.addWidget(self.btn_mode)

    def set_mode(self, mode_str):
        self.current_mode = mode_str
        self.btn_mode.setText(mode_str)
        if mode_str == "MIX": 
            self.btn_mode.setStyleSheet(UNIFIED_BTN_STYLE + "QPushButton { color: #ffaa00; font-size: 11px; border: 1px solid #8a6a2c; }")
        else: 
            self.btn_mode.setStyleSheet(UNIFIED_BTN_STYLE)

    def toggle_mode(self):
        items = [i for i in self.page_item.childItems() if isinstance(i, EditableImageItem)]
        if not items: return
        new_mode = "native" if self.current_mode in ["R", "MIX"] else "raster"
        for item in items: 
            item.export_mode = new_mode
        if self.canvas: 
            self.canvas.update_toolbars()
            self.canvas.save_workspace()


class PageInfoButton(QWidget):
    def __init__(self, page_item, canvas, parent=None):
        super().__init__(parent)
        self.page_item = page_item
        self.canvas = canvas
        self.setFixedWidth(46)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_info = QPushButton("ℹ️")
        self.btn_info.setToolTip("Dettagli contenuto e peso pagina")
        self.btn_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_info.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_info.clicked.connect(self.show_page_info)
        layout.addWidget(self.btn_info)

    def show_page_info(self):
        items = [i for i in self.page_item.childItems() if isinstance(i, EditableImageItem)]
        if not items: 
            QMessageBox.information(self, "Info Pagina", "Pagina vuota.")
            return
            
        total_size = 0
        details = []
        for i, item in enumerate(items):
            mode = "Nativo" if item.export_mode == "native" else "Raster"
            if item.orig_pdf_path and os.path.exists(item.orig_pdf_path):
                pdf_size_kb = os.path.getsize(item.orig_pdf_path) / 1024
                total_size += pdf_size_kb
                details.append(f"Oggetto {i+1} [{mode}]:\n   Sorgente PDF Originale (intero file: {pdf_size_kb:.1f} KB)")
            else:
                size_kb = os.path.getsize(item.source_path) / 1024 if os.path.exists(item.source_path) else 0
                total_size += size_kb
                details.append(f"Oggetto {i+1} [{mode}]:\n   Immagine Sorgente: {os.path.basename(item.source_path)} ({size_kb:.1f} KB)")
                
        msg = f"Contenuto Pagina:\n\n" + "\n\n".join(details) + f"\n\n--- \n*Nota: I pesi dei file PDF originali si riferiscono all'intero documento, non alla singola pagina. Verrà incluso solo se settato in Nativo."
        QMessageBox.information(self, "Analisi Pagina", msg)


class PageNumberIndicator(QWidget):
    def __init__(self, page_item, canvas, parent=None):
        super().__init__(parent)
        self.page_item = page_item
        self.canvas = canvas
        self.setFixedWidth(46) 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_number = QLabel("1")
        self.lbl_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_number.setStyleSheet("""
            QLabel {
                background-color: #4a3f12; 
                color: #f2c94c; 
                border-radius: 4px; 
                padding: 6px 3px; 
                font-weight: bold; 
                font-size: 14px; 
                border: 1px solid #8a7522;
            }
        """)
        layout.addWidget(self.lbl_number)
        
    def set_number(self, num): 
        self.lbl_number.setText(str(num))


class PageToolbar(QWidget):
    def __init__(self, page_item, canvas, parent=None):
        super().__init__(parent)
        self.page_item = page_item
        self.canvas = canvas
        self.setFixedWidth(46) 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4) 
        
        self.btn_add_above = QPushButton("📄⬆️")
        self.btn_add_above.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_add_above.clicked.connect(lambda: self.canvas.add_page_at(insert_before=self.page_item))
        
        self.btn_edit = QPushButton("✏️")
        self.set_editing_state(False) 
        self.btn_edit.clicked.connect(lambda: self.canvas.toggle_editing_for_page(self.page_item))
        
        self.btn_rotate = QPushButton("🔄")
        self.btn_rotate.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_rotate.clicked.connect(lambda: self.canvas.toggle_page_orientation(self.page_item))
        
        self.btn_up = QPushButton("▲")
        self.btn_up.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_up.clicked.connect(lambda: self.canvas.move_page_up(self.page_item))
        
        self.btn_down = QPushButton("▼")
        self.btn_down.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_down.clicked.connect(lambda: self.canvas.move_page_down(self.page_item))
        
        self.btn_delete = QPushButton("🗑️")
        self.btn_delete.setStyleSheet(UNIFIED_BTN_STYLE + "QPushButton { background-color: #6a1c1c; } QPushButton:hover { background-color: #cc0000; }")
        self.btn_delete.clicked.connect(lambda: self.canvas.delete_page(self.page_item))
        
        self.btn_add_below = QPushButton("📄⬇️")
        self.btn_add_below.setStyleSheet(UNIFIED_BTN_STYLE)
        self.btn_add_below.clicked.connect(lambda: self.canvas.add_page_at(insert_after=self.page_item))
        
        layout.addWidget(self.btn_add_above)
        layout.addWidget(self.btn_edit)
        layout.addWidget(self.btn_rotate)
        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_delete)
        layout.addWidget(self.btn_add_below)
        layout.addStretch() 

    def set_editing_state(self, is_editing):
        if is_editing: 
            self.btn_edit.setStyleSheet(UNIFIED_BTN_STYLE + "QPushButton { background-color: #ffd700; color: black; border: 2px solid #b8860b; }")
        else: 
            self.btn_edit.setStyleSheet(UNIFIED_BTN_STYLE)
