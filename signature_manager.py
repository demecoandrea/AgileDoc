import os
import json
import uuid
import shutil
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QListWidget, QListWidgetItem, QFileDialog,
                             QMessageBox, QSpinBox, QFormLayout, QDialogButtonBox, QLineEdit, QWidget, QLabel)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QImage, QPainterPath, QTransform
from PyQt6.QtCore import Qt, QSize, QPointF

# Importiamo le risorse centralizzate
from const_and_resources import Colors

class SignatureDrawDialog(QDialog):
    """Finestra per disegnare la firma a mano libera in Alta Qualità Vettoriale."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Disegna Firma")
        self.setFixedSize(600, 400)
        self.setStyleSheet(f"background-color: {Colors.HEX_BG_DIALOG}; color: white;")
        
        layout = QVBoxLayout(self)
        
        # --- Toolbar Spessore Tratto ---
        thick_layout = QHBoxLayout()
        thick_layout.addWidget(QLabel("Tratto:"))
        
        self.btn_thin = QPushButton("Sottile")
        self.btn_med = QPushButton("Medio")
        self.btn_thick = QPushButton("Spesso")
        
        self.pen_thickness = 3 # Default Medio
        self.buttons = [self.btn_thin, self.btn_med, self.btn_thick]
        
        for idx, b in enumerate(self.buttons):
            b.setCheckable(True)
            b.setStyleSheet(f"""
                QPushButton {{ background-color: {Colors.HEX_BTN_BG}; padding: 5px 15px; border-radius: 4px; }}
                QPushButton:checked {{ background-color: {Colors.HEX_ACCENT}; font-weight: bold; border: 1px solid white; }}
            """)
            b.clicked.connect(lambda checked, btn=b, i=idx: self._set_thickness(btn, i))
            thick_layout.addWidget(b)
        
        thick_layout.addStretch()
        layout.addLayout(thick_layout)
        self.btn_med.setChecked(True)
        
        # --- Canvas di Disegno ---
        self.label = QWidget()
        self.label.setStyleSheet(f"background-color: white; border: 2px solid {Colors.HEX_ACCENT};")
        self.label.setCursor(Qt.CursorShape.CrossCursor)
        layout.addWidget(self.label, stretch=1)
        
        self.path = QPainterPath()
        self.last_point = None
        
        self.label.mousePressEvent = self._mouse_press
        self.label.mouseMoveEvent = self._mouse_move
        self.label.mouseReleaseEvent = self._mouse_release
        self.label.paintEvent = self._paint_pad
        
        # --- Tasti Azione ---
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Resetta")
        self.btn_clear.setStyleSheet(f"background-color: {Colors.HEX_BORDER}; padding: 8px;")
        self.btn_clear.clicked.connect(self._clear)
        
        self.btn_ok = QPushButton("Salva Disegno")
        self.btn_ok.setStyleSheet(f"background-color: {Colors.HEX_ACCENT}; font-weight: bold; padding: 8px;")
        self.btn_ok.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)

    def _set_thickness(self, clicked_btn, index):
        for b in self.buttons: b.setChecked(b == clicked_btn)
        if index == 0: self.pen_thickness = 1
        elif index == 1: self.pen_thickness = 3
        elif index == 2: self.pen_thickness = 6

    def _clear(self):
        self.path = QPainterPath()
        self.label.update()

    def _mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_point = event.position()
            self.path.moveTo(self.last_point)

    def _mouse_move(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.last_point:
            current_point = event.position()
            
            mid_point = QPointF((self.last_point.x() + current_point.x()) / 2.0,
                                (self.last_point.y() + current_point.y()) / 2.0)
            
            self.path.quadTo(self.last_point, mid_point)
            
            self.last_point = current_point
            self.label.update()

    def _mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.last_point:
            self.path.lineTo(self.last_point)
            self.label.update()
            self.last_point = None

    def _paint_pad(self, event):
        painter = QPainter(self.label)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Colors.BLACK, self.pen_thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(self.path)

    def get_transparent_image(self):
        """Genera un'immagine trasparente 4x più grande per massima definizione."""
        if self.path.isEmpty(): return None
        
        scale_factor = 4.0 
        bbox = self.path.boundingRect()
        margin = 10
        render_rect = bbox.adjusted(-margin, -margin, margin, margin)
        
        target_w = int(render_rect.width() * scale_factor)
        target_h = int(render_rect.height() * scale_factor)
        
        img = QImage(target_w, target_h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        transform = QTransform()
        transform.scale(scale_factor, scale_factor)
        transform.translate(-render_rect.topLeft().x(), -render_rect.topLeft().y())
        painter.setTransform(transform)
        
        painter.setPen(QPen(Colors.BLACK, self.pen_thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(self.path)
        painter.end()
        
        return img


class SignaturePropertiesDialog(QDialog):
    def __init__(self, name="", scale=20, is_new=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proprietà Firma")
        self.setStyleSheet(f"background-color: {Colors.HEX_BG_DIALOG}; color: white;")
        self.delete_requested = False
        layout = QFormLayout(self)
        self.name_input = QLineEdit(name)
        self.scale_input = QSpinBox()
        self.scale_input.setRange(1, 200)
        self.scale_input.setValue(scale)
        self.scale_input.setSuffix(" %")
        layout.addRow("Nome:", self.name_input)
        layout.addRow("Scala:", self.scale_input)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        if not is_new:
            self.btn_delete = QPushButton("🗑️ Elimina")
            self.btn_delete.setStyleSheet(f"background-color: {Colors.HEX_DANGER};")
            self.btn_delete.clicked.connect(self._handle_delete)
            layout.addRow(self.btn_delete)
        layout.addRow(self.buttons)
    def _handle_delete(self):
        if QMessageBox.question(self, 'Conferma', 'Eliminare?') == QMessageBox.StandardButton.Yes:
            self.delete_requested = True
            self.accept()
    def get_data(self): return self.name_input.text(), self.scale_input.value()


class SignatureManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestione Firme")
        self.resize(600, 450)
        self.setStyleSheet(f"background-color: {Colors.HEX_BG_DIALOG}; color: white;")
        self.selected_sig_id = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.sig_dir = os.path.join(self.base_dir, "signatures")
        self.conf_dir = os.path.join(self.base_dir, "conf")
        self.json_path = os.path.join(self.conf_dir, "signatures.json")
        os.makedirs(self.sig_dir, exist_ok=True)
        os.makedirs(self.conf_dir, exist_ok=True)
        self.signatures = {}
        self.load_data()
        
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setIconSize(QSize(120, 100))
        self.list_widget.setSpacing(10)
        self.list_widget.itemSelectionChanged.connect(self._update_ui_state)
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_draw = QPushButton("🖊️ Disegna Firma")
        self.btn_add = QPushButton("📁 Importa")
        self.btn_edit = QPushButton("✏️ Modifica")
        self.btn_select = QPushButton("✅ SCEGLI")
        
        for b in [self.btn_draw, self.btn_add, self.btn_edit]:
            b.setStyleSheet(f"background-color: {Colors.HEX_BTN_BG}; padding: 8px;")
            btn_layout.addWidget(b)
        self.btn_select.setStyleSheet(f"background-color: {Colors.HEX_ACCENT}; font-weight: bold; padding: 8px;")
        btn_layout.addWidget(self.btn_select)
        layout.addLayout(btn_layout)
        
        self.btn_draw.clicked.connect(self.draw_signature)
        self.btn_add.clicked.connect(self.import_signature)
        self.btn_edit.clicked.connect(self.edit_signature)
        self.btn_select.clicked.connect(self.confirm_selection)
        
        self.refresh_list()
        self._update_ui_state()

    def _update_ui_state(self):
        has_sel = len(self.list_widget.selectedItems()) > 0
        self.btn_edit.setEnabled(has_sel)
        self.btn_select.setEnabled(has_sel)

    def load_data(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f: self.signatures = json.load(f)
            except: self.signatures = {}

    def save_data(self):
        with open(self.json_path, "w", encoding="utf-8") as f: json.dump(self.signatures, f, indent=4)

    def refresh_list(self):
        self.list_widget.clear()
        for sid, data in self.signatures.items():
            path = os.path.join(self.sig_dir, data['filename'])
            if not os.path.exists(path): continue
            thumb = QPixmap(120, 100)
            thumb.fill(Qt.GlobalColor.white)
            p = QPainter(thumb)
            sig_px = QPixmap(path).scaled(100, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((120-sig_px.width())//2, (100-sig_px.height())//2, sig_px)
            p.end()
            item = QListWidgetItem(QIcon(thumb), f"{data['name']}\n({data['scale']}%)")
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self.list_widget.addItem(item)

    def draw_signature(self):
        draw_dialog = SignatureDrawDialog(self)
        if draw_dialog.exec():
            img = draw_dialog.get_transparent_image()
            if img:
                prop_dialog = SignaturePropertiesDialog("Nuova Firma", 20, is_new=True, parent=self)
                if prop_dialog.exec():
                    name, scale = prop_dialog.get_data()
                    sid = uuid.uuid4().hex
                    fname = f"draw_{sid}.png"
                    img.save(os.path.join(self.sig_dir, fname), "PNG")
                    self.signatures[sid] = {"name": name, "filename": fname, "scale": scale}
                    self.save_data()
                    self.refresh_list()

    def import_signature(self):
        f, _ = QFileDialog.getOpenFileName(self, "Importa", "", "Images (*.png *.jpg *.jpeg)")
        if f:
            d = SignaturePropertiesDialog("Nuova Firma", 20, is_new=True, parent=self)
            if d.exec():
                name, scale = d.get_data()
                sid = uuid.uuid4().hex
                fname = f"sig_{sid}{os.path.splitext(f)[1]}"
                shutil.copy2(f, os.path.join(self.sig_dir, fname))
                self.signatures[sid] = {"name": name, "filename": fname, "scale": scale}
                self.save_data(); self.refresh_list()

    def edit_signature(self):
        sel = self.list_widget.selectedItems()
        if not sel: return
        sid = sel[0].data(Qt.ItemDataRole.UserRole)
        data = self.signatures[sid]
        d = SignaturePropertiesDialog(data['name'], data['scale'], is_new=False, parent=self)
        if d.exec():
            if d.delete_requested:
                data = self.signatures.pop(sid)
                os.remove(os.path.join(self.sig_dir, data['filename']))
            else:
                name, scale = d.get_data()
                self.signatures[sid].update({"name": name, "scale": scale})
            self.save_data(); self.refresh_list(); self._update_ui_state()

    def confirm_selection(self):
        sel = self.list_widget.selectedItems()
        if sel:
            self.selected_sig_id = sel[0].data(Qt.ItemDataRole.UserRole)
            self.accept()
