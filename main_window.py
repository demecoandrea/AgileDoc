import shutil
import os
import json
from version import __version__, APP_NAME
import uuid
import re
import socket 
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QSplitter, QScrollArea, QLineEdit,
                             QFrame, QFileDialog, QMessageBox, QComboBox, QDialog, 
                             QFormLayout, QDialogButtonBox, QCheckBox, QSpinBox, QTextEdit, QSizePolicy)
from PyQt6.QtGui import QPalette, QColor, QAction, QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QTimer, QFileSystemWatcher

from source_panel_tree import SourcePanelTree
from canvas_editor import CanvasEditor
from editor_toolbar import get_custom_colors, set_custom_colors
from api_server import get_local_ip
from help_texts import SHORTCUTS_HTML
from custom_widgets import LabeledToggle


def setup_dark_theme(app):
    app.setStyle("Fusion")
    dark_palette = QPalette()
    base_color = QColor(35, 35, 35)      
    alt_base_color = QColor(25, 25, 25)  
    text_color = QColor(220, 220, 220)   
    accent_color = QColor(42, 130, 218)  

    dark_palette.setColor(QPalette.ColorRole.Window, base_color)
    dark_palette.setColor(QPalette.ColorRole.WindowText, text_color)
    dark_palette.setColor(QPalette.ColorRole.Base, alt_base_color)
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, base_color)
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, text_color)
    dark_palette.setColor(QPalette.ColorRole.Button, base_color)
    dark_palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    dark_palette.setColor(QPalette.ColorRole.Link, accent_color)
    dark_palette.setColor(QPalette.ColorRole.Highlight, accent_color)
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(dark_palette)


# --- NUOVA CLASSE PER LA SELEZIONE AUTOMATICA DEL TESTO ---
class QuickSaveLineEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Il timer a 0ms serve per eseguire la selezione un istante DOPO 
        # che il click del mouse ha posizionato il cursore, altrimenti la annullerebbe.
        QTimer.singleShot(0, self.selectAll)
# ----------------------------------------------------------


class ScannerSelectionDialog(QDialog):
    def __init__(self, current_method, current_id, current_loop, res_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Scanner")
        self.resize(450, 220)
        self.res_dir = res_dir
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.combo_method = QComboBox()
        self.combo_method.addItems(["TWAIN", "WIA"])
        self.combo_method.setCurrentText(current_method if current_method else "TWAIN")
        self.combo_method.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555;")
        self.combo_method.currentTextChanged.connect(self.refresh_list)
        
        self.combo_scanners = QComboBox()
        self.combo_scanners.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555;")
        
        form.addRow("Tecnologia:", self.combo_method)
        form.addRow("Scanner:", self.combo_scanners)
        layout.addLayout(form)
        
        layout.addSpacing(10)
        
        self.chk_scanner_loop = QCheckBox("Proponi una nuova scansione al termine della precedente")
        self.chk_scanner_loop.setChecked(current_loop)
        layout.addWidget(self.chk_scanner_loop)
        
        layout.addSpacing(5)
        
        self.btn_refresh = QPushButton("🔄 Aggiorna Lista Scanner")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_list)
        layout.addWidget(self.btn_refresh)
        
        layout.addStretch()
        
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
        self.selected_id_to_restore = current_id
        self.refresh_list()
        
    def refresh_list(self):
        self.combo_scanners.clear()
        method = self.combo_method.currentText()
        try:
            from scanner_handler import get_available_scanners
            lista = get_available_scanners(method=method, res_dir=self.res_dir)
            for scanner_id, name in lista:
                self.combo_scanners.addItem(name, scanner_id)
                if scanner_id == self.selected_id_to_restore:
                    self.combo_scanners.setCurrentIndex(self.combo_scanners.count() - 1)
            
            if not lista:
                self.combo_scanners.addItem("Nessuno scanner trovato", None)
                
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile recuperare la lista:\n{e}")
        finally:
            self.selected_id_to_restore = None 
            
    def get_selection(self):
        return self.combo_method.currentText(), self.combo_scanners.currentData(), self.combo_scanners.currentText(), self.chk_scanner_loop.isChecked()


class SettingsDialog(QDialog):
    def __init__(self, current_size, current_dynamic, current_port, current_hub_name, current_middle_click, current_flatten=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Impostazioni AgileDoc")
        self.resize(480, 280)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_size = QComboBox()
        self.combo_size.addItems(["Piccola", "Media", "Grande", "Fissa"])
        self.combo_size.setCurrentText(current_size)
        self.combo_size.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555;")

        self.chk_dynamic = QCheckBox("Adatta la posizione dell'anteprima per non coprire il mouse")
        self.chk_dynamic.setChecked(current_dynamic)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(current_port)
        self.spin_port.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555;")

        self.txt_hub_name = QLineEdit(current_hub_name)
        self.txt_hub_name.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555; border-radius: 3px;")

        self.combo_middle = QComboBox()
        self.combo_middle.addItems(["Strumento Mano (Pan)", "Auto-Scroll (Base)"])
        self.combo_middle.setCurrentText(current_middle_click)
        self.combo_middle.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #555;")

        self.chk_flatten = QCheckBox("Appiattisci annotazioni (PDF non modificabile)")
        self.chk_flatten.setChecked(current_flatten)

        form.addRow("Nome Computer (Hub):", self.txt_hub_name)
        form.addRow("Porta Server Android:", self.spin_port)
        form.addRow("", QLabel("")) 
        form.addRow("Azione Tasto Centrale:", self.combo_middle)
        form.addRow("Dimensione Sneak Peek:", self.combo_size)
        form.addRow("", self.chk_dynamic)
        form.addRow("", self.chk_flatten)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return (self.combo_size.currentText(), self.chk_dynamic.isChecked(), 
                self.spin_port.value(), self.txt_hub_name.text().strip(), 
                self.combo_middle.currentText(), self.chk_flatten.isChecked())


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scorciatoie da Tastiera e Mouse")
        self.resize(500, 450)
        
        layout = QVBoxLayout(self)
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        text_area.setStyleSheet("background-color: #2a2a2a; color: #ddd; font-size: 13px; border: none;")
        
        text_area.setHtml(SHORTCUTS_HTML)
        layout.addWidget(text_area)
        
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class CollapsibleFolder(QWidget):
    request_removal = pyqtSignal(QWidget)
    toggled = pyqtSignal() 

    def __init__(self, folder_path, is_collapsed=False, title_prefix="📁", parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.is_collapsed = is_collapsed 
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.header_frame = QFrame()
        self.header_frame.setStyleSheet("background-color: #2a2a2a; border-bottom: 1px solid #3a3a3a;")
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(5, 2, 5, 2)
        header_layout.setSpacing(2)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setFixedWidth(20)
        self.btn_toggle.setStyleSheet("color: white; font-weight: bold; border: none; background: transparent;")
        self.btn_toggle.clicked.connect(self.toggle_collapse)
        header_layout.addWidget(self.btn_toggle)

        nome_cartella_breve = os.path.basename(folder_path)
        if not nome_cartella_breve: nome_cartella_breve = folder_path 
        
        self.lbl_title = QLabel(f"{title_prefix} {nome_cartella_breve}")
        self.lbl_title.setStyleSheet("font-weight: bold; border: none; color: #dddddd;")
        self.lbl_title.setToolTip(folder_path) 
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        header_layout.addWidget(self.lbl_title, stretch=1)

        self.btn_open = QPushButton("📂↗️")
        self.btn_open.setFixedWidth(24)
        self.btn_open.setToolTip("Apri cartella in Esplora File di Windows")
        self.btn_open.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        self.btn_open.clicked.connect(self.open_in_explorer)
        header_layout.addWidget(self.btn_open)

        self.btn_remove = QPushButton("✕")
        self.btn_remove.setFixedWidth(20)
        self.btn_remove.setStyleSheet("color: #ff4444; font-weight: bold; border: none; background: transparent;")
        self.btn_remove.clicked.connect(self.emit_removal_request)
        header_layout.addWidget(self.btn_remove)

        self.main_layout.addWidget(self.header_frame)

        self.body_widget = QWidget()
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tree_view = SourcePanelTree(folder_path)
        self.tree_view.setMinimumHeight(150)
        
        body_layout.addWidget(self.tree_view)
        self.main_layout.addWidget(self.body_widget)

        if self.is_collapsed:
            self.body_widget.setVisible(False)
            self.btn_toggle.setText("▶")
        else:
            self.body_widget.setVisible(True)
            self.btn_toggle.setText("▼")

    def toggle_collapse(self):
        if self.is_collapsed:
            self.body_widget.setVisible(True)
            self.btn_toggle.setText("▼")
            self.is_collapsed = False
        else:
            self.body_widget.setVisible(False)
            self.btn_toggle.setText("▶")
            self.is_collapsed = True
        self.toggled.emit()

    def emit_removal_request(self):
        self.request_removal.emit(self)

    def open_in_explorer(self):
        if os.path.exists(self.folder_path):
            os.startfile(self.folder_path)


class MainWindow(QMainWindow):
    server_settings_changed = pyqtSignal(int, str) 
    window_closed = pyqtSignal() 
    full_exit_requested = pyqtSignal() 

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Gestione Documenti Medici - {APP_NAME} v{__version__}")
        self.resize(1100, 750)
        
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.conf_dir = os.path.join(self.base_dir, "conf")
        self.res_dir = os.path.join(self.base_dir, "res")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        
        os.makedirs(self.conf_dir, exist_ok=True)
        os.makedirs(self.res_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.config_file = os.path.join(self.conf_dir, "agiledoc_config.json")
        self.setWindowIcon(QIcon(os.path.join(self.res_dir, "agiledoc_icon.ico")))
        
        self.current_page_idx = 0
        self.quick_save_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
        self.is_document_dirty = False
        
        self.sneak_peek_size = "Media"
        self.sneak_peek_dynamic = True
        self.server_port = 5000
        self.hub_name = socket.gethostname() 
        self.middle_click_mode = "Strumento Mano (Pan)"
        
        self.scanner_method = "TWAIN"
        self.selected_scanner_id = None
        self.selected_scanner_name = None
        self.scanner_loop_enabled = False

        self.pdf_flatten_annotations = True 
        
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.directoryChanged.connect(self.validate_quick_filename)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4) 
        main_layout.addWidget(self.splitter)

        self.setup_source_panel() 
        self.setup_preview_area() 
        
        self.create_menu_bar()

        self.splitter.setSizes([250, 750])
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3) 

        self.load_config() 
        self.update_quick_folder_ui()
        self.generate_default_filename()
        self.update_server_status_ui()

    def create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        
        nuovo_doc_action = QAction("📄 Nuovo Documento Vuoto", self)
        nuovo_doc_action.setShortcut("Ctrl+Shift+N")
        nuovo_doc_action.triggered.connect(self.action_new_document)
        file_menu.addAction(nuovo_doc_action)
        
        file_menu.addSeparator()
        
        salva_rapido_action = QAction("💾 Salvataggio Rapido PDF", self)
        salva_rapido_action.setShortcut("Ctrl+S")
        salva_rapido_action.triggered.connect(self.action_quick_save)
        file_menu.addAction(salva_rapido_action)
        
        esporta_action = QAction("🗂️ Salva PDF con Nome...", self)
        esporta_action.setShortcut("Ctrl+E")
        esporta_action.triggered.connect(self.action_export_pdf_as)
        file_menu.addAction(esporta_action)
        
        file_menu.addSeparator()
        esci_action = QAction("Chiudi Finestra", self)
        esci_action.setToolTip("Chiude la visuale (AgileDoc rimane nel System Tray)")
        esci_action.setShortcut("Ctrl+Q")
        esci_action.triggered.connect(self.close)
        file_menu.addAction(esci_action)

        esci_tutto_action = QAction("🚪 Chiudi completamente AgileDoc", self)
        esci_tutto_action.setToolTip("Spegne il server e chiude l'applicazione del tutto")
        esci_tutto_action.triggered.connect(self.full_exit_requested.emit)
        file_menu.addAction(esci_tutto_action)

        modifica_menu = menubar.addMenu("Modifica")
        
        nuova_pagina_action = QAction("📄 Nuova Pagina Vuota", self)
        nuova_pagina_action.setShortcut("Ctrl+N")
        nuova_pagina_action.triggered.connect(lambda: self.canvas.add_page())
        modifica_menu.addAction(nuova_pagina_action)
        
        incolla_action = QAction("📋 Incolla dagli Appunti", self)
        incolla_action.setShortcut("Ctrl+V")
        incolla_action.triggered.connect(self.action_paste_from_clipboard)
        modifica_menu.addAction(incolla_action)
        
        scanner_action = QAction("🖨️ Acquisisci da Scanner", self)
        scanner_action.triggered.connect(self.action_acquire_scanner)
        modifica_menu.addAction(scanner_action)
        
        modifica_menu.addSeparator()
        
        sel_tutto_action = QAction("Seleziona Tutto", self)
        sel_tutto_action.setShortcut("Ctrl+A")
        sel_tutto_action.triggered.connect(self.canvas.select_all_pages)
        modifica_menu.addAction(sel_tutto_action)
        
        inv_sel_action = QAction("Inverti Selezione", self)
        inv_sel_action.setShortcut("Ctrl+Shift+A")
        inv_sel_action.triggered.connect(self.canvas.invert_selection)
        modifica_menu.addAction(inv_sel_action)

        modifica_menu.addSeparator()
        
        export_mode_menu = modifica_menu.addMenu("📦 Modalità Esportazione")
        action_force_raster = QAction("🗜️ Forza modalità rasterizzazione", self)
        action_force_raster.triggered.connect(lambda: self.canvas.bulk_set_export_mode("raster", use_selection=True))
        action_force_native = QAction("📄 Forza modalità nativa (originale)", self)
        action_force_native.triggered.connect(lambda: self.canvas.bulk_set_export_mode("native", use_selection=True))
        export_mode_menu.addAction(action_force_raster)
        export_mode_menu.addAction(action_force_native)

        visualizza_menu = menubar.addMenu("Visualizza")
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(lambda: self.canvas.zoom_in())
        visualizza_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(lambda: self.canvas.zoom_out())
        visualizza_menu.addAction(zoom_out_action)

        strumenti_menu = menubar.addMenu("Strumenti")
        impostazioni_action = QAction("⚙️ Impostazioni", self)
        impostazioni_action.triggered.connect(self.open_settings)
        strumenti_menu.addAction(impostazioni_action)
        
        shortcuts_action = QAction("⌨️ Scorciatoie da Tastiera", self)
        shortcuts_action.triggered.connect(self.open_shortcuts)
        strumenti_menu.addAction(shortcuts_action)

    def setup_source_panel(self):
        source_widget = QWidget()
        source_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        source_widget.setMinimumWidth(200)
        
        source_layout = QVBoxLayout(source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(2)

        action_buttons_frame = QFrame()
        action_buttons_layout = QVBoxLayout(action_buttons_frame)
        action_buttons_layout.setContentsMargins(2, 2, 2, 2)
        action_buttons_layout.setSpacing(2)

        scanner_layout = QHBoxLayout()
        scanner_layout.setSpacing(2)
        
        self.btn_scanner = QPushButton("🖨️ SCANNER")
        self.btn_scanner.setStyleSheet("font-weight: bold; padding: 5px;")
        self.btn_scanner.clicked.connect(self.action_acquire_scanner)
        
        self.btn_scanner_settings = QPushButton("⚙️")
        self.btn_scanner_settings.setFixedWidth(35)
        self.btn_scanner_settings.setToolTip("Configura Scanner")
        self.btn_scanner_settings.clicked.connect(self.action_configure_scanner)
        
        scanner_layout.addWidget(self.btn_scanner, stretch=1)
        scanner_layout.addWidget(self.btn_scanner_settings)
        action_buttons_layout.addLayout(scanner_layout)
        
        self.btn_appunti = QPushButton("📋 INCOLLA DAGLI APPUNTI")
        self.btn_appunti.clicked.connect(self.action_paste_from_clipboard)
        
        self.btn_vuota = QPushButton("📄 NUOVA PAGINA VUOTA")
        self.btn_vuota.clicked.connect(lambda: self.canvas.add_page())
        
        action_buttons_layout.addWidget(self.btn_appunti)
        action_buttons_layout.addWidget(self.btn_vuota)
        source_layout.addWidget(action_buttons_frame)

        source_layout.addSpacing(10)

        header_cartelle_layout = QHBoxLayout()
        header_cartelle_layout.setContentsMargins(5, 0, 5, 0)
        lbl_sezione = QLabel("SORGENTI FILE")
        lbl_sezione.setStyleSheet("color: #aaaaaa; font-size: 11px; font-weight: bold;")
        header_cartelle_layout.addWidget(lbl_sezione)
        
        header_cartelle_layout.addStretch()
        
        self.btn_add_folder = QPushButton("➕ Aggiungi")
        self.btn_add_folder.setFixedWidth(80)
        self.btn_add_folder.setStyleSheet("font-size: 11px; padding: 2px;")
        self.btn_add_folder.clicked.connect(self.action_add_folder)
        header_cartelle_layout.addWidget(self.btn_add_folder)
        
        source_layout.addLayout(header_cartelle_layout)

        self.folders_scroll_area = QScrollArea()
        self.folders_scroll_area.setWidgetResizable(True)
        self.folders_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.folders_scroll_area.setStyleSheet("background-color: transparent;")

        self.folders_container_widget = QWidget()
        self.folders_container_widget.setStyleSheet("background-color: transparent;")
        self.folders_container_layout = QVBoxLayout(self.folders_container_widget)
        self.folders_container_layout.setContentsMargins(0, 0, 0, 0)
        self.folders_container_layout.setSpacing(2) 
        self.folders_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.folders_scroll_area.setWidget(self.folders_container_widget)
        source_layout.addWidget(self.folders_scroll_area)

        self.lbl_server_status = QLabel("")
        self.lbl_server_status.setWordWrap(True)
        self.lbl_server_status.setMinimumHeight(45)
        self.lbl_server_status.setStyleSheet("""
            background-color: #1e3d23; color: #4ade80; 
            padding: 8px; border-radius: 4px; font-weight: bold; font-size: 11px;
        """)
        self.lbl_server_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source_layout.addWidget(self.lbl_server_status)

        self.splitter.addWidget(source_widget)

    def setup_preview_area(self):
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        
        top_toolbar_frame = QFrame()
        top_toolbar_frame.setStyleSheet("background-color: #2a2a2a; border-bottom: 1px solid #1a1a1a;")
        top_layout = QHBoxLayout(top_toolbar_frame)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)

        # --- LEFT: Advanced adjustment toggle ---
        self.toggle_advanced = LabeledToggle("Regolazione avanzata")
        top_layout.addWidget(self.toggle_advanced)

        top_layout.addStretch()

        # --- CENTER: Quick save group ---
        lbl_dest = QLabel("Destinazione:")
        lbl_dest.setStyleSheet("color: #aaaaaa; font-weight: bold; font-size: 11px;")
        top_layout.addWidget(lbl_dest)

        self.btn_quick_folder = QPushButton()
        self.btn_quick_folder.setToolTip("Clicca per cambiare la cartella di salvataggio rapido")
        self.btn_quick_folder.setStyleSheet("text-align: left; padding: 4px 8px; background-color: #333333; border: 1px solid #444; border-radius: 3px;")
        self.btn_quick_folder.setMinimumWidth(150)
        self.btn_quick_folder.clicked.connect(self.action_choose_quick_folder)
        top_layout.addWidget(self.btn_quick_folder)

        self.txt_quick_filename = QuickSaveLineEdit()
        self.txt_quick_filename.setMinimumWidth(180)
        self.txt_quick_filename.setStyleSheet("padding: 4px; border: 1px solid #555; border-radius: 3px;")
        self.txt_quick_filename.textChanged.connect(self.validate_quick_filename)
        top_layout.addWidget(self.txt_quick_filename)

        self.btn_name_warning = QPushButton("⚠️")
        self.btn_name_warning.setToolTip("File già esistente! Clicca per generare un nuovo numero progressivo.")
        self.btn_name_warning.setStyleSheet("color: #ffaa00; font-weight: bold; background: transparent; border: none; font-size: 16px;")
        self.btn_name_warning.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_name_warning.clicked.connect(self.bump_filename_counter)
        self.btn_name_warning.hide()
        top_layout.addWidget(self.btn_name_warning)

        self.btn_quick_save = QPushButton("💾 Salva Rapido")
        self.btn_quick_save.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold; padding: 5px 15px; border-radius: 3px;")
        self.btn_quick_save.clicked.connect(self.action_quick_save)
        top_layout.addWidget(self.btn_quick_save)

        self.lbl_save_status = QLabel("✔️ Salvato!")
        self.lbl_save_status.setStyleSheet("color: #4ade80; font-weight: bold;")
        self.lbl_save_status.hide()
        top_layout.addWidget(self.lbl_save_status)

        top_layout.addStretch()

        # --- RIGHT: PDF quality ---
        lbl_qualita = QLabel("Qualità PDF:")
        top_layout.addWidget(lbl_qualita)

        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["Alta (300 DPI)", "Media (150 DPI)", "Bassa (96 DPI)"])
        self.combo_quality.setStyleSheet("padding: 3px; background-color: #3a3a3a; border: 1px solid #4a4a4a; border-radius: 3px;")
        self.combo_quality.currentIndexChanged.connect(self.save_config)
        top_layout.addWidget(self.combo_quality)

        preview_layout.addWidget(top_toolbar_frame)
        
        self.canvas = CanvasEditor()
        self.canvas.workspace_dir = self.temp_dir
        self.canvas.img_dir = os.path.join(self.canvas.workspace_dir, "images")
        self.canvas.state_file = os.path.join(self.canvas.workspace_dir, "canvas_state.json")
        os.makedirs(self.canvas.img_dir, exist_ok=True)
        
        # Canvas area with optional docked editor panel
        canvas_area = QWidget()
        canvas_area_layout = QHBoxLayout(canvas_area)
        canvas_area_layout.setContentsMargins(0, 0, 0, 0)
        canvas_area_layout.setSpacing(0)
        
        self.docked_editor_container = QScrollArea()
        self.docked_editor_container.setWidgetResizable(True)
        self.docked_editor_container.setFixedWidth(236)
        self.docked_editor_container.setFrameShape(QFrame.Shape.NoFrame)
        self.docked_editor_container.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.docked_editor_container.setStyleSheet(
            "QScrollArea { background-color: #2b2b2b; border: none; border-right: 1px solid #4facfe; }")
        self.docked_editor_container.hide()
        
        canvas_area_layout.addWidget(self.docked_editor_container)
        canvas_area_layout.addWidget(self.canvas, stretch=1)
        
        preview_layout.addWidget(canvas_area, stretch=1)
        
        bottom_toolbar_frame = QFrame()
        bottom_toolbar_frame.setStyleSheet("background-color: #2a2a2a; border-top: 1px solid #1a1a1a;")
        bottom_layout = QHBoxLayout(bottom_toolbar_frame)
        bottom_layout.setContentsMargins(10, 5, 10, 5)
        
        btn_nav_style = "QPushButton { background-color: #333; border: 1px solid #555; border-radius: 3px; padding: 4px 10px; font-weight: bold; } QPushButton:hover { background-color: #444; }"
        
        self.txt_selection_info = QLineEdit()
        self.txt_selection_info.setReadOnly(True)
        self.txt_selection_info.setStyleSheet("background-color: transparent; border: none; color: #4facfe; font-weight: bold;")
        self.txt_selection_info.setFixedWidth(250) 
        self.txt_selection_info.setText("")
        bottom_layout.addWidget(self.txt_selection_info)
        
        bottom_layout.addStretch() 
        
        self.btn_nav_first = QPushButton("|<")
        self.btn_nav_first.setStyleSheet(btn_nav_style)
        self.btn_nav_first.clicked.connect(self.nav_first)
        
        self.btn_nav_prev = QPushButton("<")
        self.btn_nav_prev.setStyleSheet(btn_nav_style)
        self.btn_nav_prev.clicked.connect(self.nav_prev)
        
        self.lbl_page_indicator = QLabel("Pagina 0 / 0")
        self.lbl_page_indicator.setMinimumWidth(80)
        self.lbl_page_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page_indicator.setStyleSheet("color: #dddddd; font-weight: bold;")
        
        self.btn_nav_next = QPushButton(">")
        self.btn_nav_next.setStyleSheet(btn_nav_style)
        self.btn_nav_next.clicked.connect(self.nav_next)
        
        self.btn_nav_last = QPushButton(">|")
        self.btn_nav_last.setStyleSheet(btn_nav_style)
        self.btn_nav_last.clicked.connect(self.nav_last)
        
        bottom_layout.addWidget(self.btn_nav_first)
        bottom_layout.addWidget(self.btn_nav_prev)
        bottom_layout.addWidget(self.lbl_page_indicator)
        bottom_layout.addWidget(self.btn_nav_next)
        bottom_layout.addWidget(self.btn_nav_last)
        
        bottom_layout.addStretch() 
        
        self.btn_zoom_out = QPushButton("➖")
        self.btn_zoom_out.setFixedWidth(30)
        self.btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        
        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_zoom.setFixedWidth(40)
        
        self.btn_zoom_in = QPushButton("➕")
        self.btn_zoom_in.setFixedWidth(30)
        self.btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        
        bottom_layout.addWidget(self.btn_zoom_out)
        bottom_layout.addWidget(self.lbl_zoom)
        bottom_layout.addWidget(self.btn_zoom_in)

        preview_layout.addWidget(bottom_toolbar_frame)
        self.splitter.addWidget(preview_widget)
        
        self.canvas.zoom_changed.connect(self.handle_zoom_ui_update)
        self.canvas.page_changed.connect(self.update_navigation_ui)
        self.canvas.workspace_changed.connect(self.mark_document_dirty)
        self.canvas.selection_changed.connect(self.update_selection_ui)
        self.canvas.fab_action_requested.connect(self._on_fab_clear_requested)
        self.canvas.advanced_adjustment_requested.connect(self.open_advanced_adjustment)
        self.canvas.advanced_adjustment_for_items_requested.connect(self.open_advanced_adjustment_for_items)
        self.toggle_advanced.toggled.connect(lambda checked: setattr(self.canvas, 'advanced_adjustment_enabled', checked))
        self.canvas.editor_toolbar.dock_mode_toggled.connect(self._handle_editor_dock_toggle)
        self.canvas.editing_state_changed.connect(self._handle_editing_state_for_dock)
        
        self.canvas.load_workspace()

    def update_server_status_ui(self):
        local_ip = get_local_ip()
        self.lbl_server_status.setText(f"🖥️ {self.hub_name}\n📡 http://{local_ip}:{self.server_port}")

    def open_settings(self):
        dialog = SettingsDialog(self.sneak_peek_size, self.sneak_peek_dynamic, self.server_port, self.hub_name, self.middle_click_mode, self.pdf_flatten_annotations, self)
        if dialog.exec():
            new_size, new_dynamic, new_port, new_hub_name, new_middle, new_flatten = dialog.get_data()
            if not new_hub_name: new_hub_name = socket.gethostname()
            if new_port != self.server_port or new_hub_name != self.hub_name:
                self.server_port, self.hub_name = new_port, new_hub_name
                self.server_settings_changed.emit(new_port, new_hub_name)
            self.sneak_peek_size, self.sneak_peek_dynamic, self.middle_click_mode = new_size, new_dynamic, new_middle
            self.pdf_flatten_annotations = new_flatten
            self.canvas.middle_click_mode = new_middle
            self.propagate_sneak_peek_settings(); self.save_config(); self.update_server_status_ui()

    def open_shortcuts(self):
        dialog = ShortcutsDialog(self)
        dialog.exec()

    def propagate_sneak_peek_settings(self):
        for i in range(self.folders_container_layout.count()):
            widget = self.folders_container_layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleFolder): widget.tree_view.update_settings(self.sneak_peek_size, self.sneak_peek_dynamic)

    def action_configure_scanner(self):
        dialog = ScannerSelectionDialog(self.scanner_method, self.selected_scanner_id, self.scanner_loop_enabled, self.res_dir, self)
        if dialog.exec():
            method, scanner_id, scanner_name, loop_enabled = dialog.get_selection()
            if scanner_id:
                self.scanner_method, self.selected_scanner_id, self.selected_scanner_name, self.scanner_loop_enabled = method, scanner_id, scanner_name, loop_enabled
                self.save_config(); self.canvas.show_toast(f"Scanner impostato: {scanner_name}")

    def action_acquire_scanner(self):
        if not self.selected_scanner_id:
            QMessageBox.information(self, "Scanner non configurato", "Seleziona prima uno scanner cliccando sull'icona dell'ingranaggio ⚙️.")
            return
        try:
            from scanner_handler import scan_pages
            while True:
                scanned_files = scan_pages(self.selected_scanner_id, self.scanner_method, self.res_dir, self.canvas.img_dir)
                if scanned_files:
                    self.canvas._commit_deletion()
                    added_pages = []
                    for filepath in scanned_files:
                        nuova_pagina = self.canvas.add_page(auto_save=False)
                        added_pages.append(nuova_pagina)
                        self.canvas.add_image_to_page(filepath, nuova_pagina, center=True, auto_save=False)
                    if added_pages:
                        self.canvas.clear_selection()
                        for p in added_pages:
                            self.canvas.selected_pages.append(p); p.is_selected = True; p.update()
                        self.canvas.last_selected_page = added_pages[0]; self.canvas.emit_selection_status(); self.canvas.setFocus()
                    self.canvas.save_workspace()
                else: break 
                
                if self.scanner_loop_enabled:
                    reply = QMessageBox.question(self, "Scansione Multipla", "Acquisizione completata.\n\nVuoi posizionare un altro foglio e scansionare ancora?",
                                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
                    if reply != QMessageBox.StandardButton.Yes: break
                else: break 
        except Exception as e:
            QMessageBox.warning(self, "Errore Scanner", f"Impossibile completare la scansione:\n{e}")

    def _on_fab_clear_requested(self, skip_confirm):
        if skip_confirm:
            self.canvas.clear_all()
            self.is_document_dirty = False
        else:
            self.action_new_document()

    def action_new_document(self):
        if self.is_document_dirty and self.canvas.pages:
            reply = QMessageBox.question(self, 'Modifiche non esportate', "Il documento attuale presenta modifiche non salvate in PDF.\nIniziando un nuovo documento, andranno perse.\n\nVuoi procedere comunque?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes: return
        
        self.canvas.clear_all()
        self.is_document_dirty = False
        # Rimosso il reset del testo di self.txt_quick_filename per permettere 
        # all'utente di mantenere il nome del paziente corrente.

    def mark_document_dirty(self): self.is_document_dirty = True

    def update_quick_folder_ui(self):
        display_text = self.quick_save_folder
        if len(display_text) > 35: display_text = "..." + display_text[-32:]
        self.btn_quick_folder.setText(f"📁 {display_text}")
        dirs = self.file_watcher.directories()
        if dirs: self.file_watcher.removePaths(dirs)
        if os.path.exists(self.quick_save_folder): self.file_watcher.addPath(self.quick_save_folder)
        self.validate_quick_filename()

    def action_choose_quick_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona Cartella di Destinazione Rapida", self.quick_save_folder)
        if path: self.quick_save_folder = path; self.update_quick_folder_ui(); self.save_config()

    def get_date_string(self):
        mesi_it = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
        oggi = datetime.now()
        return f"{oggi.day:02d}-{mesi_it[oggi.month - 1]}-{oggi.year}"

    def generate_default_filename(self):
        base_name = f"Doc_{self.get_date_string()}"
        counter = 1
        while True:
            test_name = f"{base_name}_{counter:02d}.pdf"
            if not os.path.exists(os.path.join(self.quick_save_folder, test_name)):
                self.txt_quick_filename.setText(test_name); break
            counter += 1

    def validate_quick_filename(self, *args):
        filename = self.txt_quick_filename.text().strip()
        if not filename.lower().endswith(".pdf"): filename += ".pdf"
        if os.path.exists(os.path.join(self.quick_save_folder, filename)):
            self.txt_quick_filename.setStyleSheet("padding: 4px; border: 2px solid #cc0000; border-radius: 3px; background-color: #4a1c1c;")
            self.btn_name_warning.show()
        else:
            self.txt_quick_filename.setStyleSheet("padding: 4px; border: 1px solid #555; border-radius: 3px;")
            self.btn_name_warning.hide()

    def bump_filename_counter(self):
        filename = self.txt_quick_filename.text().strip()
        match = re.search(r'_(\d+)\.pdf$', filename, re.IGNORECASE)
        if match:
            base, counter = filename[:match.start()], int(match.group(1))
            while True:
                counter += 1; new_name = f"{base}_{counter:02d}.pdf"
                if not os.path.exists(os.path.join(self.quick_save_folder, new_name)):
                    self.txt_quick_filename.setText(new_name); break
        else:
            self.txt_quick_filename.setText(f"{filename.replace('.pdf', '')}_01.pdf")
            self.bump_filename_counter()

    def get_selected_dpi(self):
        idx = self.combo_quality.currentIndex()
        return 300 if idx == 0 else 150 if idx == 1 else 96

    def action_quick_save(self):
        if not self.canvas.pages: return
        if self.canvas.is_editing_mode: self.canvas.set_editing_mode(False)
        if not self.btn_name_warning.isHidden(): self.bump_filename_counter()
        filename = self.txt_quick_filename.text().strip()
        if not filename.lower().endswith(".pdf"): filename += ".pdf"
        if self.canvas.export_to_pdf(os.path.join(self.quick_save_folder, filename), dpi=self.get_selected_dpi(), flatten_annotations=self.pdf_flatten_annotations):
            self.is_document_dirty = False; self.lbl_save_status.show()
            QTimer.singleShot(3000, self.lbl_save_status.hide); self.bump_filename_counter()
        else: QMessageBox.critical(self, "Errore", "Si è verificato un errore durante la generazione del PDF.")

    def action_export_pdf_as(self):
        if not self.canvas.pages: return
        if self.canvas.is_editing_mode: self.canvas.set_editing_mode(False)
        file_path, _ = QFileDialog.getSaveFileName(self, "Salva con Nome", os.path.join(self.quick_save_folder, self.txt_quick_filename.text()), "File PDF (*.pdf)")
        if file_path:
            if self.canvas.export_to_pdf(file_path, dpi=self.get_selected_dpi(), flatten_annotations=self.pdf_flatten_annotations):
                self.is_document_dirty = False 
                QMessageBox.information(self, "Successo", f"Fascicolo esportato correttamente!\n\nPosizione: {file_path}\nDimensione: {os.path.getsize(file_path)/(1024*1024):.2f} MB")
            else: QMessageBox.critical(self, "Errore", "Errore durante la generazione del PDF.")

    def update_navigation_ui(self, corrente, totale):
        self.current_page_idx = corrente - 1
        self.lbl_page_indicator.setText(f"Pagina {corrente} / {totale}")
        # btn_fab_new è sempre visibile; _update_fab_state() aggiorna icona e comportamento
        
    def update_selection_ui(self, selected_indices):
        if not selected_indices: self.txt_selection_info.setText("")
        else: self.txt_selection_info.setText(f"Pagine selezionate: {len(selected_indices)} (pag. {', '.join(map(str, selected_indices))})"); self.txt_selection_info.setCursorPosition(0) 

    def go_to_page(self, index):
        if not self.canvas.pages: return
        page = self.canvas.pages[max(0, min(index, len(self.canvas.pages) - 1))]
        if not self.canvas.is_editing_mode: self.canvas.select_single_page(page)
        self.canvas.centerOn(page)

    def nav_first(self): self.go_to_page(0)
    def nav_prev(self): self.go_to_page(self.current_page_idx - 1)
    def nav_next(self): self.go_to_page(self.current_page_idx + 1)
    def nav_last(self): self.go_to_page(len(self.canvas.pages) - 1)

    def handle_zoom_ui_update(self, percentage): self.lbl_zoom.setText(f"{percentage}%"); self.save_config()

    def open_advanced_adjustment(self, image_paths, target_idx):
        """Opens PopupRegolazioneAvanzata for new images (Case 1)."""
        from document_scanner_pro import PopupRegolazioneAvanzata
        # Facciamo una copia delle sorgenti nella cartella temp/images prima di passarle al popup
        temp_src_paths = []
        for path in image_paths:
            ext = os.path.splitext(path)[1] or ".jpg"
            lpath = os.path.join(self.canvas.img_dir, f"src_{uuid.uuid4().hex}{ext}")
            shutil.copy2(path, lpath)
            temp_src_paths.append(lpath)
            
        dialog = PopupRegolazioneAvanzata(temp_src_paths, temp_dir=self.canvas.img_dir, conf_dir=self.conf_dir, is_editing_existing=False, parent=self)
        if dialog.exec() and hasattr(dialog, 'final_pairs'):
            self.canvas.add_adjusted_images(dialog.final_pairs, target_idx)

    def open_advanced_adjustment_for_items(self, items):
        """Opens PopupRegolazioneAvanzata on one or more already-placed images (Case 2)."""
        from document_scanner_pro import PopupRegolazioneAvanzata
        
        source_paths = []
        existing_corners = {}
        valid_items = []
        
        for i, item in enumerate(items):
            if os.path.exists(item.source_path):
                source_paths.append(item.source_path)
                if hasattr(item, 'corner_points') and item.corner_points:
                    existing_corners[i] = item.corner_points
                valid_items.append(item)
        
        if not source_paths:
            return
            
        dialog = PopupRegolazioneAvanzata(source_paths, temp_dir=self.canvas.img_dir, conf_dir=self.conf_dir, is_editing_existing=True, parent=self, existing_corners=existing_corners)
        if dialog.exec() and hasattr(dialog, 'final_pairs'):
            for i, pair in enumerate(dialog.final_pairs):
                new_reg_path, _, new_pts = pair
                if i < len(valid_items):
                    self.canvas.update_adjusted_image(valid_items[i], new_reg_path, new_pts)

    def action_paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard.mimeData().hasImage():
            image = clipboard.image()
            # Salvataggio immediato in temp come "src_"
            path = os.path.join(self.canvas.img_dir, f"src_clipboard_{uuid.uuid4().hex}.png")
            image.save(path, "PNG")
            if self.toggle_advanced.isChecked():
                # Passiamo il file appena creato in temp
                self.open_advanced_adjustment([path], len(self.canvas.pages))
            else:
                nuova_pagina = self.canvas.add_page(auto_save=False)
                # Se regolazione avanzata è OFF, usiamo direttamente la sorgente
                self.canvas.add_image_to_page(path, nuova_pagina, center=True, auto_save=True)
                self.canvas.select_single_page(nuova_pagina)
        else:
            QMessageBox.warning(self, "Appunti vuoti", "Non c'è nessuna immagine negli appunti.")

    def load_config(self):
        folders_to_load, quality_idx, editor_docked = [], 1, False
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f); folders_to_load = data.get("folders", []); quality_idx = data.get("pdf_quality_index", 1); saved_zoom = data.get("zoom_level", 60)
                    self.quick_save_folder = data.get("quick_save_folder", os.path.join(os.path.expanduser('~'), 'Downloads'))
                    self.sneak_peek_size, self.sneak_peek_dynamic = data.get("sneak_peek_size", "Media"), data.get("sneak_peek_dynamic", True)
                    self.server_port, self.hub_name = data.get("server_port", 5000), data.get("hub_name", socket.gethostname())
                    self.middle_click_mode = data.get("middle_click_mode", "Strumento Mano (Pan)")
                    self.scanner_method, self.selected_scanner_id, self.selected_scanner_name = data.get("scanner_method", "TWAIN"), data.get("scanner_id", None), data.get("scanner_name", None)
                    self.scanner_loop_enabled = data.get("scanner_loop_enabled", False)
                    self.pdf_flatten_annotations = data.get("pdf_flatten_annotations", True)
                    editor_docked = data.get("editor_docked", False)
                    if "geometry" in data: self.restoreGeometry(QByteArray.fromHex(data["geometry"].encode('ascii')))
                    if "window_state" in data: self.restoreState(QByteArray.fromHex(data["window_state"].encode('ascii')))
                    if "splitter_state" in data: self.splitter.restoreState(QByteArray.fromHex(data["splitter_state"].encode('ascii')))
                    if "advanced_adjustment_enabled" in data: self.toggle_advanced.setChecked(data["advanced_adjustment_enabled"])
                    if "custom_colors" in data: set_custom_colors(data["custom_colors"])
            except Exception: pass

        self.combo_quality.setCurrentIndex(quality_idx if quality_idx <= 2 else 1)
        try: self.canvas.set_zoom(saved_zoom)
        except: pass
        self.canvas.middle_click_mode = self.middle_click_mode
        self.canvas.advanced_adjustment_enabled = self.toggle_advanced.isChecked()
        
        if editor_docked:
            self._handle_editor_dock_toggle(True)

        if not folders_to_load: folders_to_load = [{"path": os.path.join(os.path.expanduser('~'), 'Downloads'), "collapsed": False}]
        for f_data in folders_to_load:
            if os.path.exists(f_data.get("path")): self.add_folder_view(f_data.get("path"), title_prefix="📥" if "Downloads" in f_data.get("path") else "📁", is_collapsed=f_data.get("collapsed", False))

    def save_config(self):
        if not hasattr(self, 'canvas') or not hasattr(self, 'splitter'): return
        folders_data = [{"path": self.folders_container_layout.itemAt(i).widget().folder_path, "collapsed": self.folders_container_layout.itemAt(i).widget().is_collapsed} for i in range(self.folders_container_layout.count()) if isinstance(self.folders_container_layout.itemAt(i).widget(), CollapsibleFolder)]
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f: data = json.load(f)
            except Exception: pass
        data.update({"folders": folders_data, "pdf_quality_index": self.combo_quality.currentIndex(), "zoom_level": self.canvas.current_zoom, "quick_save_folder": self.quick_save_folder, "sneak_peek_size": self.sneak_peek_size, "sneak_peek_dynamic": self.sneak_peek_dynamic, "server_port": self.server_port, "hub_name": self.hub_name, "middle_click_mode": self.middle_click_mode, "scanner_method": self.scanner_method, "scanner_id": self.selected_scanner_id, "scanner_name": self.selected_scanner_name, "scanner_loop_enabled": self.scanner_loop_enabled, "pdf_flatten_annotations": self.pdf_flatten_annotations, "advanced_adjustment_enabled": self.toggle_advanced.isChecked(), "editor_docked": getattr(self.canvas, '_editor_docked', False), "custom_colors": get_custom_colors(), "geometry": self.saveGeometry().toHex().data().decode('ascii'), "window_state": self.saveState().toHex().data().decode('ascii'), "splitter_state": self.splitter.saveState().toHex().data().decode('ascii')})
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
        except Exception: pass

    def add_folder_view(self, path, title_prefix="📁", is_collapsed=False):
        if not path or not os.path.exists(path): return
        for i in range(self.folders_container_layout.count()):
            if isinstance(self.folders_container_layout.itemAt(i).widget(), CollapsibleFolder) and self.folders_container_layout.itemAt(i).widget().folder_path == path: return
        new_folder_widget = CollapsibleFolder(path, is_collapsed=is_collapsed, title_prefix=title_prefix)
        new_folder_widget.request_removal.connect(self.action_remove_folder); new_folder_widget.toggled.connect(self.save_config) 
        new_folder_widget.tree_view.update_settings(self.sneak_peek_size, self.sneak_peek_dynamic)
        self.folders_container_layout.addWidget(new_folder_widget); self.save_config()

    def action_add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona Cartella da monitorare")
        if path: self.add_folder_view(path)

    def action_remove_folder(self, folder_widget):
        if QMessageBox.question(self, 'Conferma', f"Vuoi rimuovere la vista sulla cartella?\n\n{folder_widget.folder_path}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.folders_container_layout.removeWidget(folder_widget); folder_widget.deleteLater(); self.save_config()

    def closeEvent(self, event): self.save_config(); super().closeEvent(event); self.window_closed.emit()

    def _handle_editor_dock_toggle(self, docked):
        """Handles switching between docked and floating editor toolbar."""
        toolbar = self.canvas.editor_toolbar
        self.canvas._editor_docked = docked
        toolbar.set_dock_mode(docked)
        
        if docked:
            toolbar.setParent(None)
            self.docked_editor_container.setWidget(toolbar)
            toolbar.show()
            self.docked_editor_container.setVisible(self.canvas.is_editing_mode)
        else:
            self.docked_editor_container.takeWidget()
            toolbar.setParent(self.canvas)
            self.docked_editor_container.hide()
            if self.canvas.is_editing_mode:
                toolbar.show()
                toolbar.adjustSize()
                toolbar.move(20, (self.canvas.viewport().height() - toolbar.height()) // 2)
            else:
                toolbar.hide()
        self.save_config()

    def _handle_editing_state_for_dock(self, is_editing):
        """Shows/hides the docked editor container when editing mode changes."""
        if getattr(self.canvas, '_editor_docked', False):
            self.docked_editor_container.setVisible(is_editing)
