import os
import cv2
import json
import numpy as np
import queue
import uuid
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QGraphicsView, QGraphicsScene, QGraphicsItem,
                             QSplitter, QApplication, QWidget, QFrame, QSizePolicy)
from PyQt6.QtGui import QPainter, QPixmap, QImage, QPen, QBrush, QColor, QPolygonF
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPointF, QRectF, QTimer, QByteArray

# Importa il nostro widget personalizzato!
from custom_widgets import LabeledToggle, SegmentedControl
from filter_dialog import FilterSettingsDialog

GLOBAL_YOLO_MODEL = None
ENABLE_ACTIVE_LEARNING = True



# --- THREAD 1: PREPARAZIONE IMMAGINI (Producer) ---
# Legge, applica il padding, salva su disco e passa i dati alla coda
class PrepWorker(QThread):
    # Segnale: idx, path_temp, padding_info (pad_x, pad_y, w, h)
    image_ready = pyqtSignal(int, str, dict)
    finished_all = pyqtSignal()

    def __init__(self, image_paths, temp_dir, yolo_queue):
        super().__init__()
        self.image_paths = image_paths
        self.temp_dir = temp_dir
        self.yolo_queue = yolo_queue
        self.active = True

    def run(self):
        for i, src_path in enumerate(self.image_paths):
            if not self.active: break
            
            img = cv2.imread(src_path)
            if img is None:
                continue

            h, w = img.shape[:2]
            pad_y = int(h * 0.20)
            pad_x = int(w * 0.20)
            
            # Applica Padding
            cv_image = cv2.copyMakeBorder(img, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=[128, 128, 128])
            new_h, new_w = cv_image.shape[:2]

            out_path = os.path.join(self.temp_dir, f"prep_{i}.jpg")
            cv2.imwrite(out_path, cv_image)

            pad_info = {'pad_x': pad_x, 'pad_y': pad_y, 'new_w': new_w, 'new_h': new_h}
            
            # Segnala alla UI che l'immagine è pronta da visualizzare
            self.image_ready.emit(i, out_path, pad_info)
            # Inserisce il task nella coda per YOLO
            self.yolo_queue.put((i, out_path))

        self.finished_all.emit()


# --- THREAD 2: INFERENZA YOLO (Consumer) ---
# Legge dalla coda, carica il modello (se serve), analizza e restituisce i punti
class YoloWorker(QThread):
    progress = pyqtSignal(int, int) # Rilevamento in corso... (corrente, totale)
    result_ready = pyqtSignal(int, list) # idx, punti [se vuota = fallito]
    finished_all = pyqtSignal()

    def __init__(self, yolo_queue, total_images, res_dir):
        super().__init__()
        self.yolo_queue = yolo_queue
        self.total_images = total_images
        self.res_dir = res_dir
        self.active = True

    def run(self):
        global GLOBAL_YOLO_MODEL
        if GLOBAL_YOLO_MODEL is None:
            import onnxruntime as ort
            model_path = os.path.join(self.res_dir, "best.onnx")
            if os.path.exists(model_path):
                try:
                    # Carichiamo il modello ONNX invece di quello PyTorch
                    GLOBAL_YOLO_MODEL = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
                except Exception as e:
                    print(f"Errore caricamento modello ONNX: {e}")
                    self.finished_all.emit()
                    return
            else:
                print(f"Modello ONNX non trovato in {model_path}")
                self.finished_all.emit()
                return

        processed = 0
        input_name = GLOBAL_YOLO_MODEL.get_inputs()[0].name
        
        # Dimensione input attesa dal modello
        input_shape = GLOBAL_YOLO_MODEL.get_inputs()[0].shape
        # Se il modello ha input dinamici (es. ['batch', 3, 'height', 'width']), 
        # proviamo a usare 1280 come fallback se non è specificato nel modello esportato
        input_h = input_shape[2] if isinstance(input_shape[2], int) else 1280
        input_w = input_shape[3] if isinstance(input_shape[3], int) else 1280

        while self.active:
            try:
                idx, path = self.yolo_queue.get(timeout=0.5)
            except queue.Empty:
                if processed >= self.total_images:
                    break
                continue
            
            points = []
            try:
                img = cv2.imread(path)
                if img is not None:
                    orig_h, orig_w = img.shape[:2]
                    
                    # Pre-processing per ONNX
                    img_resized = cv2.resize(img, (input_w, input_h))
                    img_input = img_resized.transpose(2, 0, 1) # HWC -> CHW
                    img_input = np.expand_dims(img_input, axis=0).astype(np.float32) / 255.0
                    
                    # Run Inference
                    outputs = GLOBAL_YOLO_MODEL.run(None, {input_name: img_input})
                    
                    # Post-processing per YOLOv8 Keypoints (output tipico: [1, 51, 8400] o simile)
                    output = outputs[0][0] # [N_features, 8400]
                    
                    conf_scores = output[4]
                    best_idx = np.argmax(conf_scores)
                    if conf_scores[best_idx] > 0.25:
                        # Estraiamo i 4 punti (8 coordinate totali a partire dall'indice 5)
                        kpts = output[5:, best_idx]
                        raw_points = []
                        for i in range(0, 12, 3): # 4 punti * (x, y, conf) = 12 valori
                            px = kpts[i] * (orig_w / input_w)
                            py = kpts[i+1] * (orig_h / input_h)
                            raw_points.append((float(px), float(py)))
                        
                        if len(raw_points) >= 4:
                            points = raw_points[:4]
            except Exception as e:
                print(f"Errore ONNX su img {idx}: {e}")

            self.result_ready.emit(idx, points)
            processed += 1
            self.progress.emit(processed, self.total_images)

        self.finished_all.emit()


# --- MIRINO TRASCINABILE ---
class DraggableCorner(QGraphicsItem):
    def __init__(self, color, callback):
        super().__init__()
        self.color = color
        self.callback = callback 
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True) 
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.hitbox_size = 30.0 

    def boundingRect(self):
        return QRectF(-self.hitbox_size/2, -self.hitbox_size/2, self.hitbox_size, self.hitbox_size)

    def paint(self, painter, option, widget=None):
        c = QPointF(0, 0)
        painter.setBrush(QBrush(QColor(0, 255, 0, 40)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.boundingRect())
        
        painter.setPen(QPen(self.color, 2))
        l = 15 
        painter.drawLine(QPointF(c.x() - l, c.y()), QPointF(c.x() + l, c.y()))
        painter.drawLine(QPointF(c.x(), c.y() - l), QPointF(c.x(), c.y() + l))
        
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawPoint(c)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.callback:
                self.callback()
        return value 


# --- POPUP PRINCIPALE ---
class PopupRegolazioneAvanzata(QDialog):
    def __init__(self, image_paths, temp_dir, conf_dir, is_editing_existing=False, parent=None, existing_corners=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        
        self.image_paths = image_paths
        self.temp_dir = temp_dir
        self.conf_dir = conf_dir
        self.base_dir = os.path.dirname(conf_dir)
        self.res_dir  = os.path.join(self.base_dir, "res")
        self.yolo_dir = os.path.join(self.base_dir, "yolo_active_learning")
        self.is_editing_existing = is_editing_existing
        self.total_images = len(image_paths)
        self.current_idx = 0
        
        # Strutture dati centralizzate
        self.padded_data = {}    # {idx: {"path": str, "info": dict}}
        self.default_points = {} # {idx: [(x,y), ...]}
        self.yolo_points = {}    # {idx: [(x,y), ...]}
        self.user_points = {}    # {idx: [(x,y), ...]}
        self.user_modified = set() # Set di indici modificati manualmente

        if existing_corners:
            for idx, pts in existing_corners.items():
                if pts:
                    self.user_points[idx] = pts
                    self.user_modified.add(idx)

        self.cv_image = None
        self.corners = []
        self.filter_settings = {'block_size': 21, 'c_value': 15}
        
        self.spinner_timer = QTimer(self)
        self.spinner_timer.timeout.connect(self.animate_spinner)
        self.spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

        self.config_file = os.path.join(self.conf_dir, "scanner_pro_config.json")

        # --- DEFINIZIONE ALTEZZE DEI BOTTONI DELLE TOOLBAR ---
        self.L2_HEIGHT = 27  # Toolbar sotto i pannelli (sinistra/destra)
        self.L1_HEIGHT = 30  # Barra generale in basso (Navigazione + Azioni)

        self.setup_ui()
        self.load_config() 
        self.start_background_workers()

    def showEvent(self, event):
        super().showEvent(event)
        # Forza lo splitter a 50/50 appena la finestra è visibile e ha le dimensioni finali
        w = self.width()
        self.splitter.setSizes([w // 2, w // 2])
        QTimer.singleShot(50, self.fit_both_views)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        # Impediamo all'utente di ridimensionare i pannelli manualmente 
        # dato che vogliamo un layout fisso 50/50
        self.splitter.setChildrenCollapsible(False)
        self.splitter.splitterMoved.connect(lambda: self.splitter.setSizes([self.width()//2, self.width()//2]))
        
        # STILE CORNICE E BOTTONI
        frame_style = "QFrame#ImageFrame { border: 3px solid #3a3a3a; border-radius: 4px; background-color: #1a1a1a; }"
        btn_style = "QPushButton { background-color: #3a3a3a; color: white; border-radius: 4px; padding: 6px 15px; font-weight: bold; border: 1px solid #555; height: 20px; } QPushButton:hover { background-color: #505050; } QPushButton:disabled { background-color: #222; color: #555; }"

        # --- SINISTRA ---
        self.left_frame = QFrame(objectName="ImageFrame")
        self.left_frame.setStyleSheet(frame_style)
        left_layout = QVBoxLayout(self.left_frame)
        left_layout.setContentsMargins(2, 2, 2, 2)
        left_layout.setSpacing(0)

        self.left_view = QGraphicsView()
        self.left_scene = QGraphicsScene()
        self.left_view.setScene(self.left_scene)
        self.left_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.left_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.left_view.setStyleSheet("background-color: #222222; border: none;")
        self.left_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.left_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.left_view.viewport().installEventFilter(self)
        
        left_layout.addWidget(self.left_view)
        
        left_controls_wrapper = QWidget()
        left_bottom_bar = QHBoxLayout(left_controls_wrapper)
        left_bottom_bar.setContentsMargins(5, 6, 5, 5)
        left_bottom_bar.setSpacing(8)
        left_bottom_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_reset = QPushButton("🔄 Reimposta Rilevamento")
        self.btn_reset.setToolTip("Riavvia l'AI per questa immagine")
        self.btn_reset.setStyleSheet(btn_style)
        self.btn_reset.setFixedHeight(self.L2_HEIGHT)
        self.btn_reset.clicked.connect(self.reset_to_yolo)
        
        self.btn_reset_corners = QPushButton("📐 Reset Angoli")
        self.btn_reset_corners.setStyleSheet(btn_style)
        self.btn_reset_corners.setFixedHeight(self.L2_HEIGHT)
        self.btn_reset_corners.clicked.connect(self.reset_to_corners)
        
        self.btn_rot_ccw = QPushButton("↺ 90°")
        self.btn_rot_ccw.setStyleSheet(btn_style)
        self.btn_rot_ccw.setFixedHeight(self.L2_HEIGHT)
        self.btn_rot_ccw.clicked.connect(lambda: self.rotate_image(-90))
        
        self.btn_rot_cw = QPushButton("90° ↻")
        self.btn_rot_cw.setStyleSheet(btn_style)
        self.btn_rot_cw.setFixedHeight(self.L2_HEIGHT)
        self.btn_rot_cw.clicked.connect(lambda: self.rotate_image(90))
        
        left_bottom_bar.addWidget(self.btn_reset)
        left_bottom_bar.addWidget(self.btn_reset_corners)
        left_bottom_bar.addWidget(self.btn_rot_ccw)
        left_bottom_bar.addWidget(self.btn_rot_cw)
        left_layout.addWidget(left_controls_wrapper)
        
        self.splitter.addWidget(self.left_frame)

        # --- DESTRA ---
        self.right_frame = QFrame(objectName="ImageFrame")
        self.right_frame.setStyleSheet(frame_style)
        right_layout = QVBoxLayout(self.right_frame)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(0)

        self.right_view = QGraphicsView()
        self.right_scene = QGraphicsScene()
        self.right_view.setScene(self.right_scene)
        self.right_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.right_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.right_view.setStyleSheet("background-color: #222222; border: none;")
        self.right_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.right_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.right_pixmap_item = self.right_scene.addPixmap(QPixmap())
        right_layout.addWidget(self.right_view)

        right_controls_wrapper = QWidget()
        right_bottom_bar = QHBoxLayout(right_controls_wrapper)
        right_bottom_bar.setContentsMargins(5, 6, 5, 5)
        right_bottom_bar.setSpacing(15)
        right_bottom_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ratio_group = SegmentedControl(
            options=["Originale", "A4 (Standard)", "Dinamica"],
            label_text="PROPORZIONE:"
        )
        self.ratio_group.setFixedHeight(self.L2_HEIGHT)
        self.ratio_group.selectionChanged.connect(self.update_preview)
        
        self.chk_filters = LabeledToggle("Migliora Leggibilità")
        self.chk_filters.setFixedHeight(self.L2_HEIGHT)
        self.chk_filters.toggled.connect(self.update_preview)

        self.btn_filter_settings = QPushButton("⚙")
        self.btn_filter_settings.setFixedSize(self.L2_HEIGHT, self.L2_HEIGHT)
        self.btn_filter_settings.setToolTip("Impostazioni Filtro")
        self.btn_filter_settings.setStyleSheet(btn_style + "QPushButton { padding: 0px; font-size: 18px; }")
        self.btn_filter_settings.clicked.connect(self.open_filter_settings)

        right_bottom_bar.addWidget(self.ratio_group)
        right_bottom_bar.addWidget(self.chk_filters)
        right_bottom_bar.addWidget(self.btn_filter_settings)
        right_layout.addWidget(right_controls_wrapper)

        self.splitter.addWidget(self.right_frame)
        layout.addWidget(self.splitter, stretch=1)

        # --- BARRA DI NAVIGAZIONE GLOBALE ---
        bottom_nav_container = QWidget()
        bottom_nav_layout = QHBoxLayout(bottom_nav_container)
        bottom_nav_layout.setContentsMargins(0, 0, 5, 0)

        # Usiamo 3 sezioni per centrare il gruppo di navigazione perfettamente
        left_spacer = QWidget()
        left_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bottom_nav_layout.addWidget(left_spacer)

        # Gruppo Navigazione (CENTRATO)
        nav_group = QWidget()
        nav_layout = QHBoxLayout(nav_group)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(10)

        self.btn_prev = QPushButton("◀ Precedente")
        self.btn_prev.setEnabled(False)
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_prev.setFixedHeight(self.L1_HEIGHT)
        self.btn_prev.clicked.connect(self.prev_image)
        
        self.lbl_page_counter = QLabel("1 / 1")
        self.lbl_page_counter.setStyleSheet("color: #f2c94c; font-weight: bold; font-size: 15px; min-width: 80px;")
        self.lbl_page_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_next = QPushButton("Successiva ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet(btn_style)
        self.btn_next.setFixedHeight(self.L1_HEIGHT)
        self.btn_next.clicked.connect(self.next_image)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_page_counter)
        nav_layout.addWidget(self.btn_next)
        bottom_nav_layout.addWidget(nav_group)

        # Gruppo Azioni (A DESTRA)
        actions_wrapper = QWidget()
        actions_wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        actions_layout = QHBoxLayout(actions_wrapper)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.setStyleSheet(btn_style + "QPushButton { background-color: #6a1a1a; border: 1px solid #8a2a2a; } QPushButton:hover { background-color: #8a2a2a; }")
        self.btn_cancel.setFixedHeight(self.L1_HEIGHT)
        self.btn_cancel.clicked.connect(self.reject_changes)

        self.btn_done = QPushButton(f"Rilevamento... (0/{self.total_images})")
        self.btn_done.setEnabled(False)
        self.btn_done.setStyleSheet(btn_style + "QPushButton { background-color: #1a6a1a; border: 1px solid #2a8a2a; } QPushButton:hover { background-color: #2a8a2a; }")
        self.btn_done.setFixedHeight(self.L1_HEIGHT)
        self.btn_done.clicked.connect(self.accept_changes)

        actions_layout.addWidget(self.btn_cancel)
        actions_layout.addWidget(self.btn_done)
        bottom_nav_layout.addWidget(actions_wrapper)

        layout.addWidget(bottom_nav_container)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            if self.btn_prev.isEnabled(): self.prev_image()
        elif event.key() == Qt.Key.Key_Right:
            if self.btn_next.isEnabled(): self.next_image()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, source, event):
        if source == self.left_view.viewport() and event.type() == event.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                self.reset_to_corners()
                return True
        return super().eventFilter(source, event)

    def reset_to_corners(self):
        if self.current_idx in self.default_points:
            self.user_modified.add(self.current_idx)
            self.draw_interactive_points(self.default_points[self.current_idx])

    def rotate_image(self, angle):
        path = self.image_paths[self.current_idx]
        img = cv2.imread(path)
        if img is None: return
        h, w = img.shape[:2]
        if hasattr(self, 'corners') and len(self.corners) == 4:
            old_pts = [(c.pos().x(), c.pos().y()) for c in self.corners]
        elif self.current_idx in self.user_points:
            old_pts = self.user_points[self.current_idx]
        elif self.current_idx in self.yolo_points:
            old_pts = self.yolo_points[self.current_idx]
        else:
            old_pts = self.default_points[self.current_idx]

        if angle == 90: rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle == -90: rotated = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else: return

        cv2.imwrite(path, rotated)
        new_h, new_w = rotated.shape[:2]
        info = self.padded_data[self.current_idx]["info"]
        curr_padded_w, curr_padded_h = info['new_w'], info['new_h']
        
        new_pts = []
        for x, y in old_pts:
            if angle == 90: nx, ny = curr_padded_h - y, x
            else: nx, ny = y, curr_padded_w - x
            new_pts.append((nx, ny))
            
        self.user_points[self.current_idx] = new_pts
        self.user_modified.add(self.current_idx)
        if self.current_idx in self.yolo_points: del self.yolo_points[self.current_idx]
        
        pad_y, pad_x = int(new_h * 0.20), int(new_w * 0.20)
        cv_padded = cv2.copyMakeBorder(rotated, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=[128, 128, 128])
        padded_h, padded_w = cv_padded.shape[:2]
        prep_path = os.path.join(self.temp_dir, f"prep_{self.current_idx}_{uuid.uuid4().hex[:6]}.jpg")
        cv2.imwrite(prep_path, cv_padded)
        
        self.padded_data[self.current_idx] = {"path": prep_path, "info": {'pad_x': pad_x, 'pad_y': pad_y, 'new_w': padded_w, 'new_h': padded_h}}
        self.default_points[self.current_idx] = [(pad_x, pad_y), (padded_w - pad_x, pad_y), (padded_w - pad_x, padded_h - pad_y), (pad_x, padded_h - pad_y)]
        self.display_image(self.current_idx)
        self.update_reset_button_state()
        self.refresh_done_button()

    def start_background_workers(self):
        self.yolo_queue = queue.Queue()
        self.prep_worker = PrepWorker(self.image_paths, self.temp_dir, self.yolo_queue)
        self.prep_worker.image_ready.connect(self.on_image_prepared)
        self.prep_worker.finished_all.connect(self.on_preparation_finished)
        self.yolo_worker = YoloWorker(self.yolo_queue, self.total_images, self.res_dir)
        self.yolo_worker.progress.connect(self.on_yolo_progress)
        self.yolo_worker.result_ready.connect(self.on_yolo_result)
        self.yolo_worker.finished_all.connect(self.on_yolo_finished)
        self.spinner_timer.start(100)
        self.prep_worker.start()
        self.yolo_worker.start()

    def animate_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_frames)
        if self.current_idx not in self.yolo_points and self.current_idx not in self.user_points:
            self.btn_reset.setText(f"{self.spinner_frames[self.spinner_idx]} Rilevamento in corso...")

    def update_window_title(self):
        txt_immagini = "immagine" if self.total_images == 1 else "immagini"
        self.setWindowTitle(f"Regolazione Avanzata Documento ({self.total_images} {txt_immagini})")
        if hasattr(self, 'lbl_page_counter'):
            self.lbl_page_counter.setText(f"{self.current_idx + 1} / {self.total_images}")

    def on_image_prepared(self, idx, path, info):
        self.padded_data[idx] = {"path": path, "info": info}
        pad_x, pad_y, new_w, new_h = info['pad_x'], info['pad_y'], info['new_w'], info['new_h']
        self.default_points[idx] = [(pad_x, pad_y), (new_w - pad_x, pad_y), (new_w - pad_x, new_h - pad_y), (pad_x, new_h - pad_y)]
        if idx == 0: self.display_image(0)
        self.update_navigation_buttons()

    def on_preparation_finished(self):
        self.update_navigation_buttons()

    def on_yolo_progress(self, current, total):
        display_current = min(current, total)
        if not self.btn_done.isEnabled():
            self.btn_done.setText(f"Rilevamento... ({display_current}/{total})")
        else:
            self.btn_done.setText("Fine Regolazione")

    def on_yolo_result(self, idx, points):
        if points:
            pts_array = np.array(points, dtype="float32")
            rect = self.order_points(pts_array)
            self.yolo_points[idx] = [(float(p[0]), float(p[1])) for p in rect]
        else:
            self.yolo_points[idx] = self.default_points[idx]
        if idx == self.current_idx:
            self.update_reset_button_state()
            if idx not in self.user_modified:
                self.draw_interactive_points(self.yolo_points[idx])
        self.refresh_done_button()

    def on_yolo_finished(self):
        self.refresh_done_button()

    def refresh_done_button(self):
        ready_count = len(set(list(self.yolo_points.keys()) + list(self.user_points.keys())))
        if ready_count >= self.total_images:
            self.btn_done.setText("Fine Regolazione")
            self.btn_done.setEnabled(True)
            self.spinner_timer.stop()
        else:
            self.btn_done.setText(f"Rilevamento... ({ready_count}/{self.total_images})")

    def update_navigation_buttons(self):
        self.btn_prev.setEnabled(self.current_idx > 0)
        next_is_ready = (self.current_idx + 1) in self.padded_data
        self.btn_next.setEnabled(self.current_idx < self.total_images - 1 and next_is_ready)

    def update_reset_button_state(self):
        if self.current_idx in self.padded_data:
            self.btn_reset.setEnabled(True)
            self.btn_reset.setText("🔄 Reimposta Rilevamento")
        else:
            self.btn_reset.setEnabled(False)

    def reset_to_yolo(self):
        if self.current_idx in self.padded_data:
            path = self.padded_data[self.current_idx]["path"]
            self.user_modified.discard(self.current_idx)
            if self.current_idx in self.user_points: del self.user_points[self.current_idx]
            if self.current_idx in self.yolo_points: del self.yolo_points[self.current_idx]
            self.btn_reset.setEnabled(False)
            self.btn_reset.setText("⏳ Rilevamento...")
            self.yolo_queue.put((self.current_idx, path))
            if not self.yolo_worker.isRunning(): self.yolo_worker.start()

    def display_image(self, index):
        self.current_idx = index
        self.update_window_title()
        self.update_navigation_buttons()
        self.update_reset_button_state()
        path = self.padded_data[index]["path"]
        self.cv_image = cv2.imread(path)
        rgb_img = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_img.shape
        qt_img = QImage(rgb_img.data, w, h, ch * w, QImage.Format.Format_RGB888)
        if not hasattr(self, 'pixmap_item'): self.pixmap_item = self.left_scene.addPixmap(QPixmap.fromImage(qt_img))
        else: self.pixmap_item.setPixmap(QPixmap.fromImage(qt_img))
        self.left_scene.setSceneRect(QRectF(self.pixmap_item.pixmap().rect()))
        pts_to_draw = self.user_points.get(index) or self.yolo_points.get(index) or self.default_points[index]
        self.draw_interactive_points(pts_to_draw)

    def draw_interactive_points(self, points):
        for item in self.left_scene.items():
            if isinstance(item, DraggableCorner) or (isinstance(item, QGraphicsItem) and item.zValue() == 1):
                self.left_scene.removeItem(item)
        self.corners = []
        pen = QPen(QColor(0, 170, 255, 200), 1)
        pen.setCosmetic(True)
        self.polygon_item = self.left_scene.addPolygon(QPolygonF(), pen)
        self.polygon_item.setZValue(1) 
        for x, y in points:
            corner = DraggableCorner(color=QColor(0, 255, 0), callback=self.on_corner_moved)
            corner.setPos(x, y) 
            corner.setZValue(2) 
            self.left_scene.addItem(corner)
            self.corners.append(corner)
        self.on_corner_moved(user_action=False)
        self.left_view.fitInView(self.left_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def on_corner_moved(self, user_action=True):
        if not hasattr(self, 'polygon_item') or len(self.corners) < 4: return
        if user_action: self.user_modified.add(self.current_idx)
        poly = QPolygonF([c.pos() for c in self.corners])
        self.polygon_item.setPolygon(poly)
        self.update_preview()

    def order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect

    def open_filter_settings(self):
        dialog = FilterSettingsDialog(self.filter_settings, self)
        dialog.settingsChanged.connect(self.on_filter_settings_changed)
        dialog.exec()

    def on_filter_settings_changed(self, new_settings):
        self.filter_settings = new_settings
        if self.chk_filters.isChecked(): self.update_preview()

    def get_optimal_dimensions_with_mode(self, rect, mode):
        (tl, tr, br, bl) = rect
        width_bottom, width_top = np.linalg.norm(br - bl), np.linalg.norm(tr - tl)
        maxWidth = max(int(width_bottom), int(width_top))
        height_right, height_left = np.linalg.norm(tr - br), np.linalg.norm(tl - bl)
        maxHeight = max(int(height_right), int(height_left))
        
        if mode == 0: # Originale
            return maxWidth, maxHeight
        elif mode == 1: # A4
            if maxHeight >= maxWidth * 0.7: return maxWidth, int(maxWidth * 1.4142)
            else: return maxWidth, int(maxWidth / 1.4142)
        elif mode == 2: # Dinamica
            minWidth = min(width_bottom, width_top)
            if minWidth > 0 and maxWidth > minWidth:
                stretch_factor = min(maxWidth / minWidth, 1.8)
                return maxWidth, int(maxHeight * stretch_factor)
            return maxWidth, maxHeight
        else: return maxWidth, maxHeight

    def update_preview(self):
        if self.cv_image is None or len(self.corners) < 4: return
        pts = np.array([[c.x(), c.y()] for c in self.corners], dtype="float32")
        rect = self.order_points(pts)
        mode = self.ratio_group.currentIndex()
        maxWidth, maxHeight = self.get_optimal_dimensions_with_mode(rect, mode)
        dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(self.cv_image, M, (maxWidth, maxHeight))
        if self.chk_filters.isChecked():
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            warped = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, self.filter_settings['block_size'], self.filter_settings['c_value'])
            warped = cv2.cvtColor(warped, cv2.COLOR_GRAY2RGB)
        else: warped = cv2.cvtColor(warped, cv2.COLOR_BGR2RGB)
        h, w, ch = warped.shape
        # Fix per costruttore QImage in PyQt6 (non accetta keyword arguments per i dati)
        qt_img = QImage(warped.data, w, h, ch * w, QImage.Format.Format_RGB888)
        # Fix per QImage data pointer lifetime
        self._qt_img_preview = qt_img 
        pixmap = QPixmap.fromImage(qt_img)
        self.right_pixmap_item.setPixmap(pixmap)
        self.right_scene.setSceneRect(QRectF(pixmap.rect()))
        self.right_view.fitInView(self.right_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def save_current_corners(self):
        if len(self.corners) == 4 and self.current_idx in self.user_modified:
            self.user_points[self.current_idx] = [(c.x(), c.y()) for c in self.corners]

    def next_image(self):
        self.save_current_corners()
        if self.current_idx < self.total_images - 1: self.display_image(self.current_idx + 1)

    def prev_image(self):
        self.save_current_corners()
        if self.current_idx > 0: self.display_image(self.current_idx - 1)

    def accept_changes(self):
        self.save_current_corners()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.btn_done.setText("Elaborazione finale in corso...")
        self.setEnabled(False)
        QApplication.processEvents()
        self.final_pairs = []
        current_ratio_mode = self.ratio_group.currentIndex()
        for idx in range(self.total_images):
            path = self.padded_data[idx]["path"]
            img = cv2.imread(path)
            pts = self.user_points.get(idx) or self.yolo_points.get(idx) or self.default_points[idx]
            pts_array = np.array(pts, dtype="float32")
            rect = self.order_points(pts_array)
            maxWidth, maxHeight = self.get_optimal_dimensions_with_mode(rect, current_ratio_mode)
            dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
            if self.chk_filters.isChecked():
                gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
                warped = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, self.filter_settings['block_size'], self.filter_settings['c_value'])
            orig_src_path = self.image_paths[idx]
            base_name = os.path.splitext(os.path.basename(orig_src_path))[0]
            if base_name.startswith("src_"): out_name = base_name.replace("src_", "reg_") + ".jpg"
            else: out_name = f"reg_{uuid.uuid4().hex}.jpg"
            out_path = os.path.join(self.temp_dir, out_name)
            cv2.imwrite(out_path, warped)
            self.final_pairs.append((out_path, orig_src_path, pts))
        QApplication.restoreOverrideCursor()
        self.save_config(); self.accept()

    def reject_changes(self): self.save_config(); self.reject()

    def closeEvent(self, event):
        if hasattr(self, 'prep_worker'): self.prep_worker.active = False; self.prep_worker.quit(); self.prep_worker.wait()
        if hasattr(self, 'yolo_worker'): self.yolo_worker.active = False; self.yolo_worker.quit(); self.yolo_worker.wait()
        self.save_config(); super().closeEvent(event)

    def load_config(self):
        self.resize(1200, 850)
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if "geometry" in data: self.restoreGeometry(QByteArray.fromHex(data["geometry"].encode('ascii')))
                    if "filters_enabled" in data: self.chk_filters.setChecked(data["filters_enabled"])
                    if "ratio_mode" in data: self.ratio_group.setCurrentIndex(data["ratio_mode"])
            except: pass

    def save_config(self):
        os.makedirs(self.conf_dir, exist_ok=True)
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f: data = json.load(f)
            except: pass
        data.update({"geometry": self.saveGeometry().toHex().data().decode('ascii'), "filters_enabled": self.chk_filters.isChecked(), "ratio_mode": self.ratio_group.currentIndex()})
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(data, f)
        except: pass

    def resizeEvent(self, event): super().resizeEvent(event); self.fit_both_views()
    def fit_both_views(self):
        if hasattr(self, 'left_view'): self.left_view.fitInView(self.left_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if hasattr(self, 'right_pixmap_item') and self.right_pixmap_item.pixmap() and not self.right_pixmap_item.pixmap().isNull(): self.right_view.fitInView(self.right_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
