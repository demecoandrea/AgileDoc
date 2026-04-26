from PyQt6.QtWidgets import QStyle, QTreeView, QAbstractItemView, QHeaderView, QLabel, QApplication, QMenu, QMessageBox
from PyQt6.QtGui import QFileSystemModel, QDrag, QPixmap, QImage
from PyQt6.QtCore import Qt, QDir, QMimeData, QUrl
import os
import fitz  # PyMuPDF!

class SneakPeekWidget(QLabel):
    """Finestra flottante borderless per l'anteprima rapida, configurabile"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("border: 2px solid #4facfe; background-color: #1e1e1e; color: white; padding: 5px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.current_path = ""
        
        self.preview_size_mode = "Media"
        self.dynamic_position = True
        
    def show_preview(self, path, global_pos, screen_rect, main_window_rect):
        self.current_path = path
        ext = os.path.splitext(path)[1].lower()
        
        # --- 1. Calcolo Dimensioni Massime ---
        if self.preview_size_mode == "Fissa":
            max_h = int(main_window_rect.height() * 0.70) # 70% dell'altezza della finestra (lascia 15% sopra e sotto)
            max_w = main_window_rect.right() - global_pos.x() - 40 # Dalla freccia del mouse al bordo destro
            if max_w < 150: max_w = 150 # Limite di sicurezza se il mouse è tutto a destra
        else:
            sizes = {"Piccola": 200, "Media": 400, "Grande": 600}
            max_h = sizes.get(self.preview_size_mode, 400)
            max_w = max_h # Nelle altre modalità il bounding box è un quadrato
            
        # --- 2. Caricamento e Scalatura ---
        if ext in ['.jpg', '.jpeg', '.png']:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(pixmap)
            else:
                self.setText("❌\nImmagine corrotta")
                
        elif ext == '.pdf':
            try:
                doc = fitz.open(path)
                if len(doc) > 0:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=100) # Alzato a 100 DPI per una resa migliore sulle preview grandi
                    
                    fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                    pixmap = QPixmap.fromImage(qimg)
                    pixmap = pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.setPixmap(pixmap)
                else:
                    self.setText("📄\nPDF Vuoto")
            except Exception as e:
                self.setText("❌\nErrore lettura PDF")
        else:
            self.setText("File non supportato")
            
        self.adjustSize()
        
        # --- 3. Calcolo Posizione Intelligente ---
        target_x = global_pos.x() + 20
        
        if self.preview_size_mode == "Fissa":
            # Modalità Fissa: Si allinea al 15% dall'alto della finestra principale
            target_y = main_window_rect.top() + int(main_window_rect.height() * 0.15)
        else:
            # Calcolo basato sulla metà ASSOLUTA dello schermo
            if self.dynamic_position and global_pos.y() > screen_rect.center().y():
                target_y = global_pos.y() - self.height() - 15 # Disegna SOPRA il mouse
            else:
                target_y = global_pos.y() + 15 # Disegna SOTTO il mouse
                
            # Prevenzione fuori-bordo schermo (alto e basso)
            if target_y < screen_rect.top():
                target_y = screen_rect.top() + 10
            elif target_y + self.height() > screen_rect.bottom():
                target_y = screen_rect.bottom() - self.height() - 10
                
        self.move(int(target_x), int(target_y))
        self.show()


class SourcePanelTree(QTreeView):
    def __init__(self, folder_path, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(QDir.rootPath())
        self.setModel(self.file_model)
        
        self.file_model.setNameFilters(['*.pdf', '*.jpg', '*.jpeg', '*.png'])
        self.file_model.setNameFilterDisables(False) 

        root_index = self.file_model.index(folder_path)
        self.setRootIndex(root_index)
        
        self.setColumnHidden(1, False)
        self.setColumnHidden(2, True)
        self.setColumnHidden(3, False)
        self.setHeaderHidden(False) 
        
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)          
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) 
        self.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) 
        self.header().setStretchLastSection(False)

        self.setSortingEnabled(True)
        self.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        
        self.setIndentation(10)      
        self.setStyleSheet("QTreeView { border: none; background-color: transparent; }")

        self.setDragEnabled(True)
        self.setDragDropMode(QTreeView.DragDropMode.DragOnly)
        self.setAcceptDrops(False)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMouseTracking(True) 
        self.sneak_peek = SneakPeekWidget()

    def update_settings(self, size_mode, dynamic_pos):
        self.sneak_peek.preview_size_mode = size_mode
        self.sneak_peek.dynamic_position = dynamic_pos

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            index = self.indexAt(event.pos())
            if index.isValid() and index.column() == 0 and not self.file_model.isDir(index):
                file_path = self.file_model.filePath(index)
                
                # Otteniamo le coordinate assolute
                global_pos = self.viewport().mapToGlobal(event.pos())
                screen_rect = self.screen().availableGeometry()
                main_window_rect = self.window().geometry()
                
                self.sneak_peek.show_preview(file_path, global_pos, screen_rect, main_window_rect)
            else:
                self.sneak_peek.hide()
        else:
            self.sneak_peek.hide()

    def leaveEvent(self, event):
        self.sneak_peek.hide()
        super().leaveEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self.sneak_peek.hide()
        super().keyReleaseEvent(event)

    def startDrag(self, supported_actions):
        self.sneak_peek.hide()
        indexes = self.selectedIndexes()
        if not indexes: return

        urls = []
        for index in indexes:
            if index.column() == 0 and not self.file_model.isDir(index):
                file_path = self.file_model.filePath(index)
                urls.append(QUrl.fromLocalFile(file_path))

        if not urls: return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setUrls(urls) 
        drag.setMimeData(mime_data)
        drag.exec(supported_actions)
    
    def contextMenuEvent(self, event):
        from PyQt6.QtWidgets import QStyle # Assicurati che QStyle sia importato se non lo era
        
        indexes = self.selectedIndexes()
        if not indexes: 
            return
            
        menu = QMenu(self)
        
        # Stile personalizzato che gestisce correttamente l'hover (:selected)
        menu.setStyleSheet("""
            QMenu { background-color: #2a2a2a; border: 1px solid #555; }
            QMenu::item { padding: 5px 25px 5px 25px; color: #ff5555; font-weight: bold; }
            QMenu::item:selected { background-color: #4a4a4a; color: #ff8888; }
        """)
        
        icon_delete = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        action_delete = menu.addAction(icon_delete, "Elimina File dal Disco")
        
        action = menu.exec(self.viewport().mapToGlobal(event.pos()))
        
        if action == action_delete:
            files_to_delete = set()
            for idx in indexes:
                if idx.column() == 0 and not self.file_model.isDir(idx):
                    files_to_delete.add(self.file_model.filePath(idx))
            
            if not files_to_delete: return
            
            reply = QMessageBox.question(
                self, 
                'Conferma Eliminazione Definitiva', 
                f"Sei sicuro di voler eliminare in modo IRREVERSIBILE {len(files_to_delete)} file dal disco?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                for fpath in files_to_delete:
                    try:
                        os.remove(fpath)
                    except Exception as e:
                        print(f"Errore durante l'eliminazione di {fpath}: {e}")
