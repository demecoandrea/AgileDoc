from PyQt6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsRectItem, 
                             QGraphicsPixmapItem, QMenu, QGraphicsItem, QWidget,
                             QVBoxLayout, QHBoxLayout, QPushButton, QApplication, 
                             QMessageBox, QLabel, QFrame, QProgressDialog, QGraphicsDropShadowEffect,
                             QStyle)
from PyQt6.QtGui import (QColor, QBrush, QPen, QPainter, QPixmap, QTransform, QAction, QImageReader, QMouseEvent, QPainterPath, QCursor)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer, QByteArray, QBuffer, QIODevice
import json
import shutil
import uuid
import os
import math
import fitz # PyMuPDF

from editor_toolbar import EditorToolbar
from pdf_annotations import AnnotationFreeTextItem, AnnotationTextBoxItem, AnnotationPathItem

A4_WIDTH = 595.0
A4_HEIGHT = 842.0

# Dimensione fissa degli handle di editing in pixel di schermo.
_HANDLE_PX = 20

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


class PageItem(QGraphicsRectItem):
    def __init__(self, y_offset, is_landscape=False):
        super().__init__()
        self.is_landscape = is_landscape
        self._update_rect()
        self.setPos(0, y_offset)
        self.setBrush(QBrush(Qt.GlobalColor.white))
        
        self.is_selected = False
        self.is_editing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

    def _update_rect(self): 
        w = A4_HEIGHT if self.is_landscape else A4_WIDTH
        h = A4_WIDTH if self.is_landscape else A4_HEIGHT
        self.setRect(0, 0, w, h)
        
    def set_landscape(self, is_landscape): 
        self.is_landscape = is_landscape
        self._update_rect()
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.is_editing: 
            pen = QPen(QColor(255, 215, 0), 5)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())
        elif self.is_selected: 
            pen = QPen(QColor(0, 150, 255), 5)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())
        else: 
            pen = QPen(QColor(100, 100, 100), 1)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())

    def set_editing_mode(self, is_editing):
        self.is_editing = is_editing
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, not is_editing)
        for child in self.childItems():
            if hasattr(child, 'set_editable'): 
                child.set_editable(is_editing)
        self.update() 


class EditableImageItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, parent_page, source_path, orig_pdf_path=None, orig_page_num=None, regulated_path=None, corner_points=None):
        super().__init__()
        
        # Forza il click sull'intero rettangolo ignorando la trasparenza (Fix Firme)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        
        self.original_pixmap = pixmap
        self.parent_page = parent_page
        self.source_path = source_path 
        self.regulated_path = regulated_path 
        self.corner_points = corner_points 
        self.orig_pdf_path = orig_pdf_path
        self.orig_page_num = orig_page_num
        self.is_signature = False 
        self.setParentItem(parent_page)
        
        self.is_editable = False
        self.is_resizing = False
        self.is_rotating = False
        self.hovering_handle = False
        self.hovering_rotate = False
        self.hovering_mode_toggle = False
        self.setAcceptHoverEvents(True) 
        
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.rotation_angle = 0.0
        self.export_mode = "native" if self.orig_pdf_path else "raster"
        
        self.apply_transform(shift_center=False)
        self.set_editable(False) 

    def apply_transform(self, shift_center=True):
        old_center = self.sceneBoundingRect().center() if shift_center else None
        t = QTransform().rotate(self.rotation_angle)
        rotated_pix = self.original_pixmap.transformed(t, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(rotated_pix)
        
        transform = QTransform()
        transform.scale(self.scale_x, self.scale_y)
        self.setTransform(transform)
        
        if shift_center and old_center:
            new_center = self.sceneBoundingRect().center()
            self.moveBy(old_center.x() - new_center.x(), old_center.y() - new_center.y())

    def set_editable(self, editable):
        self.is_editable = editable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, editable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, editable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, editable)
        if not editable: 
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setSelected(False) 
        self.update() 

    def toggle_export_mode(self):
        self.export_mode = "raster" if self.export_mode == "native" else "native"
        self.update()
        if self.scene() and self.scene().views(): 
            self.scene().views()[0].update_toolbars()
            self.scene().views()[0].save_workspace()
            self.scene().views()[0].viewport().update()

    def maximize_in_page(self):
        if not self.parent_page: 
            return
            
        pixmap = self.pixmap()
        margine = 10.0 
        pw = A4_HEIGHT if self.parent_page.is_landscape else A4_WIDTH
        ph = A4_WIDTH if self.parent_page.is_landscape else A4_HEIGHT
        
        max_w = pw - (margine * 2)
        max_h = ph - (margine * 2)
        scala_finale = min(max_w / pixmap.width(), max_h / pixmap.height())
        
        self.scale_x = scala_finale
        self.scale_y = scala_finale
        self.apply_transform(shift_center=False)
        
        ws = pixmap.width() * scala_finale
        hs = pixmap.height() * scala_finale
        self.setPos((pw - ws) / 2, (ph - hs) / 2)

    def reset_modifications(self):
        self.rotation_angle = 0.0
        self.apply_transform(shift_center=False)
        self.maximize_in_page()
        if self.scene() and self.scene().views():
            self.scene().views()[0].save_workspace()

    def contextMenuEvent(self, event):
        if not self.is_editable: 
            return 
            
        if not self.isSelected(): 
            self.scene().clearSelection()
            self.setSelected(True)
            
        selected_items = [item for item in self.scene().selectedItems() if isinstance(item, EditableImageItem)]
        
        menu = QMenu()
        menu.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #4facfe;") 
        
        export_menu = menu.addMenu("📦 Modalità Esportazione")
        action_force_raster = QAction("🗜️ Forza Raster (Comprimi)", export_menu)
        action_force_native = QAction("📄 Forza Nativo (Originale)", export_menu)
        
        def force_mode(m):
            for i in selected_items: 
                i.export_mode = m
            if self.scene() and self.scene().views(): 
                self.scene().views()[0].update_toolbars()
                self.scene().views()[0].save_workspace()
                self.scene().views()[0].viewport().update()
                
        action_force_raster.triggered.connect(lambda: force_mode("raster"))
        action_force_native.triggered.connect(lambda: force_mode("native"))
        export_menu.addAction(action_force_raster)
        export_menu.addAction(action_force_native)
        menu.addSeparator()
        
        action_maximize = QAction("🖼️ Massimizza nella pagina", menu)
        action_maximize.triggered.connect(lambda: [item.maximize_in_page() for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_maximize)
        
        action_reset = QAction("🔄 Reset modifiche", menu)
        action_reset.triggered.connect(lambda: [item.reset_modifications() for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_reset)
        menu.addSeparator() 
        
        action_rot_cw = QAction("↻ Ruota 90° (Tasto D)", menu)
        action_rot_cw.triggered.connect(lambda: [setattr(item, 'rotation_angle', (item.rotation_angle + 90) % 360) or item.apply_transform(shift_center=True) for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_rot_cw)
        
        action_rot_ccw = QAction("↺ Ruota 90° (Tasto S)", menu)
        action_rot_ccw.triggered.connect(lambda: [setattr(item, 'rotation_angle', (item.rotation_angle - 90) % 360) or item.apply_transform(shift_center=True) for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_rot_ccw)
        menu.addSeparator()

        action_advanced = QAction("🔍 Regolazione Avanzata", menu)
        action_advanced.triggered.connect(lambda: self.scene().views()[0].request_advanced_adjustment_for_items(selected_items))
        menu.addAction(action_advanced)
        menu.addSeparator() 
        
        action_delete = QAction("🗑️ Elimina Immagine", menu)
        action_delete.triggered.connect(lambda: [self.scene().removeItem(item) for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_delete)
        
        menu.exec(event.screenPos())

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, widget) 
        if self.is_editable:
            rect = QRectF(self.pixmap().rect())
            if self.isSelected():
                pen = QPen(QColor(0, 150, 255))
                pen.setCosmetic(True) 
                pen.setWidth(2)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawRect(rect)
            else:
                pen = QPen(QColor(180, 180, 180, 180))
                pen.setCosmetic(True)
                pen.setWidth(1)
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawRect(rect)

    def hoverMoveEvent(self, event):
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        is_select_tool = view and getattr(view, 'current_editor_tool', 'select') == "select"
        
        if not self.is_editable or not self.isSelected() or not view:
            super().hoverMoveEvent(event)
            if self.is_editable and is_select_tool:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            self.hovering_handle = False
            self.hovering_rotate = False
            self.hovering_mode_toggle = False
            return
            
        rect = QRectF(self.pixmap().rect())
        
        # Fix Tipi: conversione esplicita a QPointF per evitare crash in .contains()
        epos_vp = view.mapFromScene(self.mapToScene(event.pos()))
        epos_vp_f = QPointF(epos_vp)
        
        tl = view.mapFromScene(self.mapToScene(rect.topLeft()))
        br = view.mapFromScene(self.mapToScene(rect.bottomRight()))
        tc = view.mapFromScene(self.mapToScene(QPointF(rect.center().x(), rect.top())))
        
        H = float(_HANDLE_PX)
        
        in_toggle = QRectF(tl.x(), tl.y(), H, H).contains(epos_vp_f)
        in_resize = QRectF(br.x() - H, br.y() - H, H, H).contains(epos_vp_f)
        in_rotate = QRectF(tc.x() - H/2, tc.y(), H, H).contains(epos_vp_f)

        if in_toggle: 
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.hovering_mode_toggle = True
            self.hovering_handle = False
            self.hovering_rotate = False
        elif in_resize: 
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.hovering_handle = True
            self.hovering_mode_toggle = False
            self.hovering_rotate = False
        elif in_rotate: 
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.hovering_rotate = True
            self.hovering_mode_toggle = False
            self.hovering_handle = False
        else: 
            if is_select_tool:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            self.hovering_handle = False
            self.hovering_rotate = False
            self.hovering_mode_toggle = False
            
        super().hoverMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.is_editable and event.button() == Qt.MouseButton.LeftButton:
            if self.scene() and self.scene().views():
                selected_items = [item for item in self.scene().selectedItems() if isinstance(item, EditableImageItem)]
                if self not in selected_items:
                    selected_items = [self]
                self.scene().views()[0].request_advanced_adjustment_for_items(selected_items)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self.is_editable:
            if self.hovering_mode_toggle: 
                self.toggle_export_mode()
                event.accept()
                return
                
            self.setOpacity(0.6) 
            if self.hovering_handle: 
                self.is_resizing = True
                event.accept()
            elif self.hovering_rotate: 
                self.is_rotating = True
                event.accept()
            else: 
                super().mousePressEvent(event)
        else: 
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            mouse_scene_pos = event.scenePos()
            item_scene_pos = self.scenePos()
            desired_w = mouse_scene_pos.x() - item_scene_pos.x()
            desired_h = mouse_scene_pos.y() - item_scene_pos.y()
            
            if desired_w > 20 and desired_h > 20: 
                pw = self.pixmap().width()
                ph = self.pixmap().height()
                modifiers = QApplication.keyboardModifiers()
                
                if modifiers & Qt.KeyboardModifier.ControlModifier: 
                    scale = max(desired_w / pw, desired_h / ph)
                    self.scale_x = scale
                    self.scale_y = scale
                else: 
                    self.scale_x = desired_w / pw
                    self.scale_y = desired_h / ph
                    
                self.apply_transform(shift_center=False)
                self.update() 
                
        elif getattr(self, 'is_rotating', False):
            center_scene = self.sceneBoundingRect().center()
            mouse_scene = event.scenePos()
            dx = mouse_scene.x() - center_scene.x()
            dy = mouse_scene.y() - center_scene.y()
            
            angle = math.degrees(math.atan2(dy, dx)) + 90 
            if angle < 0: 
                angle += 360
                
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier: 
                angle = round(angle / 90.0) * 90.0
                
            self.rotation_angle = angle
            self.apply_transform(shift_center=True)
            self.update() 
        else: 
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_editable: 
            self.setOpacity(1.0) 
            
        if self.is_resizing: 
            self.is_resizing = False
            event.accept()
        elif getattr(self, 'is_rotating', False): 
            self.is_rotating = False
            event.accept()
        else: 
            super().mouseReleaseEvent(event)
            
        if self.scene() and self.scene().views(): 
            self.scene().views()[0].save_workspace()

    def itemChange(self, change, value):
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged):
            if self.scene() and self.scene().views():
                self.scene().views()[0].viewport().update()
        return super().itemChange(change, value)


class CanvasEditor(QGraphicsView):
    zoom_changed = pyqtSignal(int)
    editing_state_changed = pyqtSignal(bool) 
    page_changed = pyqtSignal(int, int) 
    workspace_changed = pyqtSignal()
    selection_changed = pyqtSignal(list)
    advanced_adjustment_requested = pyqtSignal(list, int)
    advanced_adjustment_for_items_requested = pyqtSignal(list)
    fab_action_requested = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform) 
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) 
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        
        self.pages = []
        self.toolbars = {} 
        self.page_indicators = {} 
        self.page_modes = {} 
        self.page_infos = {} 
        
        self.page_spacing = 50.0
        self.selected_pages = [] 
        self.last_selected_page = None
        self.is_editing_mode = False
        self.active_page = None 
        self.current_zoom = 100 
        self.middle_click_mode = "Strumento Mano (Pan)"
        self.advanced_adjustment_enabled = False
        self._editor_docked = False
        
        self._internal_drag_active = False
        self._drag_start_pos = None
        self._auto_scroll_active = False
        self._auto_scroll_start_pos = None
        self._auto_scroll_current_pos = None
        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.timeout.connect(self._do_auto_scroll)
        
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bg_image = QPixmap(os.path.join(base_dir, "res", "sfondo_agiledoc.jpg"))
        self.splash_pixmap_source = QPixmap(os.path.join(base_dir, "res", "splash_agiledoc.png"))
        
        self.splash_label = QLabel(self)
        self.splash_label.setStyleSheet("background: transparent; border: none;")
        self.splash_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.splash_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.splash_label.hide()
        
        self._pending_deletions = [] 
        self.undo_snackbar = UndoSnackbar(self)
        self.undo_snackbar.undo_requested.connect(self._undo_deletion)
        self.undo_snackbar.dismiss_requested.connect(self._commit_deletion)
        
        self.deletion_timer = QTimer(self)
        self.deletion_timer.setSingleShot(True)
        self.deletion_timer.timeout.connect(self._commit_deletion)
        
        self.toast_timer.timeout.connect(self.undo_snackbar.hide)
        self.setAcceptDrops(True) 
        
        self.drop_indicator = QGraphicsRectItem(-20, 0, A4_WIDTH + 40, 6)
        self.drop_indicator.setBrush(QBrush(QColor(42, 130, 218, 200))) 
        self.drop_indicator.setPen(QPen(Qt.PenStyle.NoPen))
        self.drop_indicator.setZValue(100) 
        self.scene.addItem(self.drop_indicator)
        self.drop_indicator.hide()
        self.current_drop_index = None
        
        self.drag_overlay = QLabel(self)
        self.drag_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay.setStyleSheet("background-color: rgba(0, 120, 215, 210); color: white; font-size: 22px; font-weight: bold; border-radius: 8px; border: 2px solid white;")
        self.drag_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) 
        self.drag_overlay.hide()
        
        self.workspace_dir = os.path.join(base_dir, "temp")
        self.img_dir = os.path.join(self.workspace_dir, "images")
        os.makedirs(self.img_dir, exist_ok=True)
        self.state_file = os.path.join(self.workspace_dir, "canvas_state.json")
        
        self.btn_fab_new = QPushButton("📄", self) 
        self.btn_fab_new.setFixedSize(56, 56) 
        self.btn_fab_new.setCursor(Qt.CursorShape.PointingHandCursor)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 5)
        self.btn_fab_new.setGraphicsEffect(shadow)
        self.btn_fab_new.clicked.connect(self._on_fab_clicked)
        self._update_fab_state()
        
        self.editor_toolbar = EditorToolbar(self)
        self.editor_toolbar.hide()
        self.editor_toolbar.tool_changed.connect(self._on_editor_tool_changed)
        self.editor_toolbar.property_changed.connect(self._on_editor_property_changed)
        self.editor_toolbar.action_requested.connect(self._on_editor_action_requested)

        # Forza l'invio dei dati della firma ORA che il Canvas è in ascolto
        QTimer.singleShot(50, self.editor_toolbar._on_signature_combo_changed)

        self.current_editor_tool = "select"
        self.editor_props = {
            "freetext_border_color": QColor(0,0,0,0),
            "freetext_bg_color": QColor(255,255,255,0),
            "freetext_color": QColor(0,0,0),
            "freetext_font_family": "Helvetica",
            "freetext_font_size": 12,
            "freetext_font_bold": False,
            "freetext_font_italic": False,
            "freetext_font_underline": False,
            
            "textbox_border_color": QColor(0,0,0),
            "textbox_bg_color": QColor(220,220,220),
            "textbox_color": QColor(0,0,0),
            "textbox_font_family": "Helvetica",
            "textbox_font_size": 12,
            "textbox_font_bold": False,
            "textbox_font_italic": False,
            "textbox_font_underline": False,
            "textbox_align_h": "Sinistra",
            "textbox_align_v": "Alto",
            "textbox_wrap": True,
            
            "marker_color": QColor(0,0,0),
            "marker_thickness": 2,
            "highlighter_color": QColor(255,255,0),
            "highlighter_thickness": 10,
            "signature_path": None
        }
        self._current_drawing_path = None
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

    def _on_scene_selection_changed(self):
        if self.is_editing_mode:
            selected_items = self.scene.selectedItems()
            focus_item = self.scene.focusItem()
            effective_items = list(selected_items)
            if focus_item and focus_item not in effective_items:
                effective_items.append(focus_item)
                if focus_item.parentItem() and focus_item.parentItem() not in effective_items:
                    effective_items.append(focus_item.parentItem())

            has_image = any(isinstance(i, EditableImageItem) for i in effective_items)
            if hasattr(self, 'editor_toolbar'):
                self.editor_toolbar.update_selection_state(has_image)
                ann_items = [i for i in effective_items if isinstance(i, (AnnotationFreeTextItem, AnnotationTextBoxItem, AnnotationPathItem, EditableImageItem))]
                
                if len(ann_items) == 1:
                    item = ann_items[0]
                    target_tool = None
                    if isinstance(item, AnnotationFreeTextItem): target_tool = "freetext"
                    elif isinstance(item, AnnotationTextBoxItem): target_tool = "textbox"
                    elif isinstance(item, AnnotationPathItem):
                        target_tool = "highlighter" if item.is_highlighter else "marker"
                    elif isinstance(item, EditableImageItem):
                        target_tool = "select"
                    
                    if target_tool:
                        self.editor_toolbar.set_active_tool(target_tool, silent=True)
                        self.editor_toolbar.set_property_values_from_item(item, target_tool)
                        
                elif len(ann_items) == 0:
                    self.editor_toolbar.set_active_tool(self.current_editor_tool, silent=True)
                else:
                    self.editor_toolbar.set_active_tool("select", silent=True)
        self.viewport().update()

    def _update_cursor_for_tool(self, tool_id):
        # Helper interno per creare un cursore con badge di testo o icona dinamica
        def create_badge_cursor(badge_text, bg_color, is_marker=False, is_chisel=False):
            pix = QPixmap(64, 64)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            hotspot_x, hotspot_y = 0, 0
            center = 32

            if is_marker:
                thickness = self.editor_props.get("marker_thickness", 2)
                m_color = self.editor_props.get("marker_color", QColor(0,0,0))
                visual_size = max(4, thickness * (self.current_zoom / 100.0))
                
                # Disegniamo il Crosshair fisso
                painter.setPen(QPen(QColor(150, 150, 150, 200), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                gap = (visual_size / 2) + 3
                line_len = 6
                painter.drawLine(QPointF(center, center - gap), QPointF(center, center - gap - line_len)) # Su
                painter.drawLine(QPointF(center, center + gap), QPointF(center, center + gap + line_len)) # Giù
                painter.drawLine(QPointF(center - gap, center), QPointF(center - gap - line_len, center)) # Sinistra
                painter.drawLine(QPointF(center + gap, center), QPointF(center + gap + line_len, center)) # Destra

                # Pallino centrale col colore scelto
                rect = QRectF(center - visual_size/2, center - visual_size/2, visual_size, visual_size)
                # Bordo a contrasto per visibilità
                border_color = Qt.GlobalColor.white if m_color.lightness() < 128 else Qt.GlobalColor.black
                painter.setPen(QPen(border_color, 1))
                painter.setBrush(QBrush(m_color))
                painter.drawEllipse(rect)
                hotspot_x, hotspot_y = center, center

            elif is_chisel:
                thickness = self.editor_props.get("highlighter_thickness", 10)
                h_color = self.editor_props.get("highlighter_color", QColor(255, 255, 0))
                visual_w = max(2, thickness * (self.current_zoom / 100.0) * 0.3)
                visual_h = max(10, thickness * (self.current_zoom / 100.0))
                
                rect = QRectF(center - visual_w/2, center - visual_h/2, visual_w, visual_h)
                border_color = Qt.GlobalColor.white if h_color.lightness() < 128 else Qt.GlobalColor.black
                painter.setPen(QPen(border_color, 1))
                
                # Colore pieno nel cursore per visibilità
                c = QColor(h_color)
                c.setAlpha(255)
                painter.setBrush(QBrush(c))
                painter.drawRect(rect)
                hotspot_x, hotspot_y = center, center

            else:
                # Cursore con badge + Freccia
                painter.setPen(QPen(Qt.GlobalColor.white, 2))
                painter.setBrush(QBrush(Qt.GlobalColor.black))
                arrow_poly = QPainterPath()
                arrow_poly.moveTo(0, 0); arrow_poly.lineTo(0, 16); arrow_poly.lineTo(4, 12)
                arrow_poly.lineTo(8, 20); arrow_poly.lineTo(11, 18); arrow_poly.lineTo(7, 11)
                arrow_poly.lineTo(12, 11); arrow_poly.closeSubpath()
                painter.drawPath(arrow_poly)
                
                font = painter.font()
                font.setPixelSize(10); font.setBold(True); painter.setFont(font)
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(badge_text)
                th = fm.height()
                badge_rect = QRectF(12, 18, tw + 6, th + 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(bg_color)))
                painter.drawRoundedRect(badge_rect, 3, 3)
                painter.setPen(QPen(Qt.GlobalColor.white))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
                hotspot_x, hotspot_y = 0, 0
            
            painter.end()
            return QCursor(pix, int(hotspot_x), int(hotspot_y))

        if tool_id == "select":
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif tool_id == "marker":
            c = create_badge_cursor("", "", is_marker=True)
            self.setCursor(c); self.viewport().setCursor(c)
        elif tool_id == "highlighter":
            c = create_badge_cursor("", "", is_chisel=True)
            self.setCursor(c); self.viewport().setCursor(c)
        elif tool_id == "freetext":
            c = create_badge_cursor("+MDS", "#0078d7")
            self.setCursor(c); self.viewport().setCursor(c)
        elif tool_id == "textbox":
            c = create_badge_cursor("+CDT", "#d35400")
            self.setCursor(c); self.viewport().setCursor(c)
        elif tool_id == "signature":
            c = create_badge_cursor("+FIR", "#27ae60")
            self.setCursor(c); self.viewport().setCursor(c)

    def _on_editor_tool_changed(self, tool_id):
        self.current_editor_tool = tool_id
        if tool_id == "select":
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.scene.clearSelection()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            
        self._update_cursor_for_tool(tool_id)

        # FIX BUG ESC: Riprendiamo il focus sul canvas ogni volta che si cambia tool
        self.setFocus()
        
        if hasattr(self, 'editor_toolbar') and self.editor_toolbar.isVisible() and not getattr(self, '_editor_docked', False):
            self.editor_toolbar.adjustSize()
            self.editor_toolbar.move(20, (self.viewport().height() - self.editor_toolbar.height()) // 2)

    def _on_editor_property_changed(self, prop_name, value):
        self.editor_props[prop_name] = value
        
        # Se cambiamo spessore o colore, aggiorniamo il cursore in tempo reale
        # senza sganciare la selezione dell'elemento attivo!
        if ("thickness" in prop_name or "color" in prop_name) and self.current_editor_tool in ["marker", "highlighter"]:
            self._update_cursor_for_tool(self.current_editor_tool)

        selected_items = self.scene.selectedItems()
        focus_item = self.scene.focusItem()
        target_items = set(selected_items)
        if focus_item:
            target_items.add(focus_item)
            if focus_item.parentItem():
                target_items.add(focus_item.parentItem())
        
        if "freetext" in prop_name and target_items:
            for item in target_items:
                if isinstance(item, AnnotationFreeTextItem):
                    if prop_name == "freetext_border_color": item.border_color = value; item.update()
                    elif prop_name == "freetext_bg_color": item.bg_color = value; item.update()
                    elif prop_name == "freetext_color": item.set_text_color(value)
                    elif prop_name == "freetext_font_family": item.set_font_properties(family=value)
                    elif prop_name == "freetext_font_size": item.set_font_properties(size=value)
                    elif prop_name == "freetext_font_bold": item.set_font_properties(bold=value)
                    elif prop_name == "freetext_font_italic": item.set_font_properties(italic=value)
                    elif prop_name == "freetext_font_underline": item.set_font_properties(underline=value)
            self.save_workspace()
            
        if "textbox" in prop_name and target_items:
            for item in target_items:
                if isinstance(item, AnnotationTextBoxItem):
                    if prop_name == "textbox_border_color": item.border_color = value; item.update()
                    elif prop_name == "textbox_bg_color": item.bg_color = value; item.update()
                    elif prop_name == "textbox_color": item.set_text_color(value)
                    elif prop_name == "textbox_font_family": item.set_font_properties(family=value)
                    elif prop_name == "textbox_font_size": item.set_font_properties(size=value)
                    elif prop_name == "textbox_font_bold": item.set_font_properties(bold=value)
                    elif prop_name == "textbox_font_italic": item.set_font_properties(italic=value)
                    elif prop_name == "textbox_font_underline": item.set_font_properties(underline=value)
                    elif prop_name == "textbox_align_h": item.set_font_properties(align_h=value)
                    elif prop_name == "textbox_align_v": item.set_font_properties(align_v=value)
                    elif prop_name == "textbox_wrap": item.set_font_properties(wrap=value)
            self.save_workspace()

        if ("marker" in prop_name or "highlighter" in prop_name) and target_items:
            for item in target_items:
                if isinstance(item, AnnotationPathItem):
                    is_hl = item.is_highlighter
                    if ("marker" in prop_name and not is_hl) or ("highlighter" in prop_name and is_hl):
                        if "color" in prop_name:
                            item.color = value
                        elif "thickness" in prop_name:
                            item.thickness = value
                        item.update_pen()
            self.save_workspace()

    def _on_editor_action_requested(self, action_id):
        if action_id == "advanced_adjustment":
            selected_items = [item for item in self.scene.selectedItems() if isinstance(item, EditableImageItem)]
            if selected_items:
                self.request_advanced_adjustment_for_items(selected_items)

    def _do_auto_scroll(self):
        if not self._auto_scroll_active or not self._auto_scroll_start_pos or not self._auto_scroll_current_pos: 
            return
            
        delta_y = self._auto_scroll_current_pos.y() - self._auto_scroll_start_pos.y()
        deadzone = 15.0 
        if abs(delta_y) > deadzone:
            speed = (abs(delta_y) - deadzone) * 0.15 
            if delta_y < 0: 
                speed = -speed
            v_bar = self.verticalScrollBar()
            v_bar.setValue(int(v_bar.value() + speed))

    def show_toast(self, message):
        self.undo_snackbar.lbl_msg.setText(message)
        self.undo_snackbar.btn_undo.hide()
        self._position_snackbar()
        self.undo_snackbar.show()
        self.toast_timer.stop()
        self.toast_timer.start(3000)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(30, 30, 30))
        if not self.bg_image.isNull():
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            painter.drawPixmap(view_rect, self.bg_image, QRectF(self.bg_image.rect()))
            painter.fillRect(view_rect, QColor(0, 0, 0, 140) if self.pages else QColor(0, 0, 0, 50)) 

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self.is_editing_mode:
            return
        selected = self.scene.selectedItems()
        if not selected:
            return

        painter.save()
        painter.resetTransform()
        H = float(_HANDLE_PX)

        for item in selected:
            if not getattr(item, 'is_editable', False):
                continue
            self._draw_item_overlay(painter, item, H)

        painter.restore()

    def _vp(self, item, pt):
        return QPointF(self.mapFromScene(item.mapToScene(pt)))

    def _draw_item_overlay(self, painter, item, H):
        if isinstance(item, EditableImageItem):
            local_rect = QRectF(item.pixmap().rect())
        elif isinstance(item, AnnotationPathItem):
            local_rect = item.path().boundingRect()
        else:
            local_rect = item.rect()

        tl = self._vp(item, local_rect.topLeft())
        tr = self._vp(item, local_rect.topRight())
        br = self._vp(item, local_rect.bottomRight())
        tc = self._vp(item, QPointF(local_rect.center().x(), local_rect.top()))

        if isinstance(item, AnnotationFreeTextItem):
            label_text = "MDS"
        elif isinstance(item, AnnotationTextBoxItem):
            label_text = "CDT"
        elif isinstance(item, AnnotationPathItem):
            label_text = "EVZ" if getattr(item, 'is_highlighter', False) else "PEN"
        else:
            label_text = "FIR" if getattr(item, 'is_signature', False) else "IMG"

        # Label alto-sinistra
        label_h = H
        label_w = int(H * 1.8)
        lbl_rect = QRectF(tl.x(), tl.y() - label_h - 4, label_w, label_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(50, 50, 50, 210)))
        painter.drawRoundedRect(lbl_rect, 3, 3)
        painter.setPen(QPen(QColor(200, 200, 200)))
        font2 = painter.font()
        font2.setPixelSize(max(1, int(label_h * 0.65)))
        font2.setBold(True)
        painter.setFont(font2)
        painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, label_text)

        # Resize handle
        if isinstance(item, EditableImageItem):
            resize_rect = QRectF(br.x() - H, br.y() - H, H, H)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 150, 255)))
            painter.drawRect(resize_rect)
        elif isinstance(item, AnnotationTextBoxItem) and not isinstance(item, AnnotationFreeTextItem):
            sel_pad = 3
            sel_br_local = item.rect().bottomRight() + QPointF(sel_pad, sel_pad)
            br_tb = self._vp(item, sel_br_local)
            resize_rect = QRectF(br_tb.x() - H, br_tb.y() - H, H, H)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 150, 255)))
            painter.drawRect(resize_rect)

        # Rotate handle & Toggle
        if isinstance(item, EditableImageItem):
            rot_rect = QRectF(tc.x() - H / 2, tc.y(), H, H)
            painter.setBrush(QBrush(QColor(255, 165, 0)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rot_rect, H * 0.15, H * 0.15)
            pen_w = H * 0.12
            painter.setPen(QPen(Qt.GlobalColor.white, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            cx, cy = rot_rect.center().x(), rot_rect.center().y()
            r = H * 0.28
            arc_path = QPainterPath()
            arc_path.moveTo(cx - r, cy)
            arc_path.cubicTo(cx - r, cy - r * 1.6, cx + r, cy - r * 1.6, cx + r, cy)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(arc_path)
            ts = r * 0.55
            painter.drawLine(QPointF(cx + r, cy), QPointF(cx + r - ts, cy - ts))
            painter.drawLine(QPointF(cx + r, cy), QPointF(cx + r + ts, cy - ts))

            toggle_rect = QRectF(tl.x(), tl.y(), H, H)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 150, 255) if item.export_mode == "native" else QColor(100, 100, 100)))
            painter.drawRect(toggle_rect)
            painter.setPen(QPen(Qt.GlobalColor.white))
            font = painter.font()
            font.setPixelSize(max(1, int(H * 0.65)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(toggle_rect, Qt.AlignmentFlag.AlignCenter, "N" if item.export_mode == "native" else "R")

    def _update_splash_screen(self):
        if self.pages or self.splash_pixmap_source.isNull():
            self.splash_label.hide()
            return
            
        vp_w = self.viewport().width()
        vp_h = self.viewport().height()
        if vp_w < 100 or vp_h < 100: 
            return 
            
        max_target_w = vp_w * 0.9
        max_target_h = vp_h * 0.9
        orig_w = self.splash_pixmap_source.width()
        orig_h = self.splash_pixmap_source.height()
        
        final_scale = min(max_target_w / orig_w, max_target_h / orig_h)
        final_w = int(orig_w * final_scale)
        final_h = int(orig_h * final_scale)
        
        if final_w < 10 or final_h < 10: 
            return 
            
        scaled_pixmap = self.splash_pixmap_source.scaled(final_w, final_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.splash_label.setPixmap(scaled_pixmap)
        self.splash_label.adjustSize()
        self.splash_label.move((vp_w - self.splash_label.width()) // 2, (vp_h - self.splash_label.height()) // 2)
        self.splash_label.show()

    def _update_fab_state(self):
        if self.pages:
            self.btn_fab_new.setText("🗑️")
            self.btn_fab_new.setToolTip("Nuovo documento (svuota canvas)\n[SHIFT+click] per saltare la conferma")
            self.btn_fab_new.setStyleSheet(
                "background-color: #7a1a1a; color: white; font-size: 26px; font-weight: bold; "
                "border: none; border-radius: 28px;"
            )
        else:
            self.btn_fab_new.setText("📄")
            self.btn_fab_new.setToolTip("Aggiungi nuova pagina vuota")
            self.btn_fab_new.setStyleSheet(
                "background-color: #0078d7; color: white; font-size: 26px; font-weight: bold; "
                "border: none; border-radius: 28px;"
            )
        self.btn_fab_new.show()

    def _on_fab_clicked(self):
        if not self.pages:
            self.add_page()
        else:
            skip_confirm = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.fab_action_requested.emit(skip_confirm)

    def emit_selection_status(self):
        indices = sorted([self.pages.index(p) + 1 for p in self.selected_pages if p in self.pages])
        self.selection_changed.emit(indices)

    def clear_all(self):
        self._commit_deletion() 
        if self.is_editing_mode: 
            self.set_editing_mode(False)
            
        self.clear_selection()
        self.last_selected_page = None
        
        for page in list(self.pages):
            self.scene.removeItem(page)
            for dict_ref in [self.toolbars, self.page_indicators, self.page_modes, self.page_infos]:
                if page in dict_ref: 
                    dict_ref.pop(page).deleteLater()
                    
        self.pages.clear()
        self.refresh_layout()
        QTimer.singleShot(500, self._cleanup_temp_files)

    def _cleanup_temp_files(self):
        for filename in os.listdir(self.img_dir):
            filepath = os.path.join(self.img_dir, filename)
            try:
                if os.path.isfile(filepath): 
                    os.unlink(filepath)
            except Exception as e: 
                print(f"File bloccato {filepath}: {e}")

    def clear_selection(self):
        for page in self.selected_pages:
            page.is_selected = False
            page.update()
        self.selected_pages.clear()
        self.emit_selection_status()

    def select_single_page(self, page):
        self.clear_selection()
        if page:
            self.selected_pages.append(page)
            page.is_selected = True
            page.update()
            self.emit_selection_status()

    def toggle_page_selection(self, page):
        if page in self.selected_pages:
            self.selected_pages.remove(page)
            page.is_selected = False
        else:
            self.selected_pages.append(page)
            page.is_selected = True
        page.update()
        self.emit_selection_status()
        
    def select_all_pages(self):
        if self.is_editing_mode: 
            return
        self.selected_pages = list(self.pages)
        for p in self.pages:
            p.is_selected = True
            p.update()
        self.emit_selection_status()
            
    def invert_selection(self):
        if self.is_editing_mode: 
            return
        new_sel = []
        for p in self.pages:
            p.is_selected = not p.is_selected
            p.update()
            if p.is_selected: 
                new_sel.append(p)
        self.selected_pages = new_sel
        self.emit_selection_status()

    def refresh_layout(self):
        y_offset = 0.0
        max_w = max([(A4_HEIGHT if p.is_landscape else A4_WIDTH) for p in self.pages], default=A4_WIDTH)
        
        self.drop_indicator.setRect(-20, 0, max_w + 40, 6)
        for page in self.pages:
            w = A4_HEIGHT if page.is_landscape else A4_WIDTH
            h = A4_WIDTH if page.is_landscape else A4_HEIGHT
            page.setPos((max_w - w) / 2.0, y_offset)
            y_offset += h + self.page_spacing
            
        self.update_scene_rect()
        self.update_toolbars()
        self.emit_page_status()
        self.emit_selection_status() 
        self.save_workspace()
        self._update_splash_screen()
        self._update_fab_state()

    def toggle_page_orientation(self, page):
        self._commit_deletion()
        page.set_landscape(not page.is_landscape)
        self.refresh_layout()

    def move_page_up(self, page):
        self._commit_deletion()
        idx = self.pages.index(page)
        if idx > 0:
            self.pages[idx], self.pages[idx-1] = self.pages[idx-1], self.pages[idx]
            self.refresh_layout()
            self.ensureVisible(page)

    def move_page_down(self, page):
        self._commit_deletion()
        idx = self.pages.index(page)
        if idx < len(self.pages) - 1:
            self.pages[idx], self.pages[idx+1] = self.pages[idx+1], self.pages[idx]
            self.refresh_layout()
            self.ensureVisible(page)

    def move_multiple_pages(self, direction_up=True):
        if not self.selected_pages: 
            return
            
        self._commit_deletion()
        sorted_pages = sorted(self.selected_pages, key=lambda p: self.pages.index(p))
        indices = [self.pages.index(p) for p in sorted_pages]
        
        if not (indices[-1] - indices[0] == len(indices) - 1):
            self.show_toast("Spostamento non consentito per selezioni discontinue.")
            return
            
        if direction_up and indices[0] > 0:
            target_idx = indices[0] - 1
            extracted = [self.pages.pop(i) for i in reversed(indices)]
            for p in extracted: 
                self.pages.insert(target_idx, p)
            self.refresh_layout()
            self.ensureVisible(sorted_pages[0])
            
        elif not direction_up and indices[-1] < len(self.pages) - 1:
            target_idx = indices[0] + 1
            extracted = [self.pages.pop(i) for i in reversed(indices)]
            for p in extracted: 
                self.pages.insert(target_idx, p)
            self.refresh_layout()
            self.ensureVisible(sorted_pages[-1])

    def delete_page(self, page):
        if self.is_editing_mode and page == self.active_page: 
            return
            
        self._commit_deletion() 
        self._pending_deletions = []
        idx = self.pages.index(page)
        self._pending_deletions.append((idx, page, self.toolbars.pop(page, None), self.page_indicators.pop(page, None), self.page_modes.pop(page, None), self.page_infos.pop(page, None)))
        self._execute_soft_deletion()

    def delete_selected_pages(self):
        if not self.selected_pages: 
            return
            
        self._commit_deletion() 
        self._pending_deletions = []
        for page in sorted(self.selected_pages, key=lambda p: self.pages.index(p)):
            idx = self.pages.index(page)
            self._pending_deletions.append((idx, page, self.toolbars.pop(page, None), self.page_indicators.pop(page, None), self.page_modes.pop(page, None), self.page_infos.pop(page, None)))
        self._execute_soft_deletion()

    def _execute_soft_deletion(self):
        for idx, page, tb, ind, mode, info in self._pending_deletions:
            self.pages.remove(page)
            page.hide()
            for w in [tb, ind, mode, info]: 
                if w: w.hide()
                
        self.clear_selection()
        self.refresh_layout()
        
        count = len(self._pending_deletions)
        self.undo_snackbar.lbl_msg.setText(f"{count} {'pagina' if count==1 else 'pagine'} {'eliminata' if count==1 else 'eliminate'}.")
        self.undo_snackbar.btn_undo.show()
        self._position_snackbar()
        self.undo_snackbar.show()
        self.deletion_timer.start(7000) 

    def _undo_deletion(self):
        self.deletion_timer.stop()
        self.undo_snackbar.hide()
        if not self._pending_deletions: 
            return
            
        for idx, page, tb, ind, mode, info in self._pending_deletions:
            self.pages.insert(idx, page)
            if tb: self.toolbars[page] = tb
            if ind: self.page_indicators[page] = ind
            if mode: self.page_modes[page] = mode
            if info: self.page_infos[page] = info
            page.show()
            
        self._pending_deletions.clear()
        self.refresh_layout()

    def _commit_deletion(self):
        self.deletion_timer.stop()
        if self.undo_snackbar.isVisible(): 
            self.undo_snackbar.hide()
            
        for idx, page, tb, ind, mode, info in self._pending_deletions:
            self.scene.removeItem(page)
            for w in [tb, ind, mode, info]: 
                if w: w.deleteLater()
                
        self._pending_deletions.clear()

    def _position_snackbar(self):
        sb_w = self.undo_snackbar.sizeHint().width()
        sb_h = self.undo_snackbar.sizeHint().height()
        self.undo_snackbar.setGeometry(25, int(self.viewport().height() - sb_h - 25), sb_w, sb_h)

    def bulk_set_export_mode(self, mode, use_selection=True):
        pages = self.selected_pages if (use_selection and self.selected_pages) else self.pages
        if not pages: 
            return
            
        for p in pages:
            for i in p.childItems():
                if isinstance(i, EditableImageItem): 
                    i.export_mode = mode
                    
        self.update_toolbars()
        self.save_workspace()
        
        m_str = "Nativa" if mode == "native" else "Raster"
        if use_selection and self.selected_pages:
            self.show_toast(f"Modalità {m_str} applicata a {len(pages)} pagine selezionate.")
        else:
            self.show_toast(f"Modalità {m_str} applicata all'intero documento.")

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        
        if key == Qt.Key.Key_Escape:
            if self.is_editing_mode: 
                focus_item = self.scene.focusItem()
                if focus_item and hasattr(focus_item, "textInteractionFlags") and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable):
                    focus_item.clearFocus()
                    event.accept()
                    return
                    
                if self.current_editor_tool != "select":
                    self.editor_toolbar.set_active_tool("select", silent=False)
                    event.accept()
                    return
                    
                self.set_editing_mode(False)
            else: 
                self.clear_selection()
            event.accept()
            return
            
        if self.is_editing_mode:
            focus_item = self.scene.focusItem()
            if focus_item and hasattr(focus_item, "textInteractionFlags") and (focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable):
                super().keyPressEvent(event)
                return

            sel_items = [i for i in self.scene.selectedItems() if isinstance(i, (EditableImageItem, AnnotationFreeTextItem, AnnotationTextBoxItem, AnnotationPathItem))]
            if sel_items:
                if key == Qt.Key.Key_D:
                    for i in sel_items: 
                        if isinstance(i, EditableImageItem):
                            i.rotation_angle = (i.rotation_angle + 90) % 360
                            i.apply_transform(True)
                    self.save_workspace()
                    event.accept()
                    return
                elif key == Qt.Key.Key_S:
                    for i in sel_items: 
                        if isinstance(i, EditableImageItem):
                            i.rotation_angle = (i.rotation_angle - 90) % 360
                            i.apply_transform(True)
                    self.save_workspace()
                    event.accept()
                    return
                elif key == Qt.Key.Key_Delete:
                    for i in sel_items: 
                        self.scene.removeItem(i)
                    self.save_workspace()
                    event.accept()
                    return
                elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                    step = 10 if (modifiers & Qt.KeyboardModifier.ShiftModifier) else 1
                    dx, dy = 0, 0
                    if key == Qt.Key.Key_Left: dx = -step
                    elif key == Qt.Key.Key_Right: dx = step
                    elif key == Qt.Key.Key_Up: dy = -step
                    elif key == Qt.Key.Key_Down: dy = step
                    for i in sel_items:
                        i.moveBy(dx, dy)
                    self.save_workspace()
                    event.accept()
                    return
                    
        if not self.is_editing_mode:
            if key == Qt.Key.Key_A and (modifiers & Qt.KeyboardModifier.ControlModifier):
                if modifiers & Qt.KeyboardModifier.ShiftModifier: 
                    self.invert_selection()
                else: 
                    self.select_all_pages()
                event.accept()
                return
                
            if key == Qt.Key.Key_Delete and self.selected_pages: 
                self.delete_selected_pages()
                event.accept()
                return
                
            if key == Qt.Key.Key_E and len(self.selected_pages) == 1: 
                self.toggle_editing_for_page(self.selected_pages[0])
                event.accept()
                return
                
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                if modifiers & Qt.KeyboardModifier.ControlModifier and self.selected_pages: 
                    self.move_multiple_pages(direction_up=(key == Qt.Key.Key_Up))
                elif len(self.selected_pages) == 1:
                    idx = self.pages.index(self.selected_pages[0])
                    new_idx = idx - 1 if key == Qt.Key.Key_Up else idx + 1
                    if 0 <= new_idx < len(self.pages):
                        p = self.pages[new_idx]
                        self.select_single_page(p)
                        self.last_selected_page = p
                        self.centerOn(p)
                event.accept()
                return
                
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0: 
                self.zoom_in()
            else: 
                self.zoom_out()
            event.accept()
        else: 
            super().wheelEvent(event)

    def contextMenuEvent(self, event):
        if self.is_editing_mode: 
            super().contextMenuEvent(event)
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #4facfe;")
        
        if not self.selected_pages:
            action_empty = menu.addAction("Nessuna pagina selezionata")
            action_empty.setEnabled(False)
            menu.exec(event.globalPos())
            return
            
        export_menu = menu.addMenu("📦 Modalità Esportazione")
        action_force_raster = QAction("🗜️ Forza modalità rasterizzazione", menu)
        action_force_raster.triggered.connect(lambda: self.bulk_set_export_mode("raster", use_selection=True))
        action_force_native = QAction("📄 Forza modalità nativa (originale)", menu)
        action_force_native.triggered.connect(lambda: self.bulk_set_export_mode("native", use_selection=True))
        
        export_menu.addAction(action_force_raster)
        export_menu.addAction(action_force_native)
        menu.addSeparator()
        
        azione_ruota = menu.addAction("🔄 Ruota Pagine (Orizz./Vert.)")
        menu.addSeparator()
        azione_elimina = menu.addAction("🗑️ Elimina Pagine Selezionate")
            
        azione_scelta = menu.exec(event.globalPos())
        
        if azione_scelta == azione_ruota:
            self._commit_deletion()
            for p in self.selected_pages: 
                p.set_landscape(not p.is_landscape)
            self.refresh_layout()
        elif azione_scelta == azione_elimina: 
            self.delete_selected_pages()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if "Mano" in self.middle_click_mode:
                self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
                event.accept()
                fake = QMouseEvent(event.type(), event.position(), event.globalPosition(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
                super().mousePressEvent(fake)
            elif "Auto-Scroll" in self.middle_click_mode:
                self._auto_scroll_active = True
                self._auto_scroll_start_pos = event.position()
                self._auto_scroll_current_pos = event.position()
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                self._auto_scroll_timer.start(16)
                event.accept()
            return
            
        click_pos = self.mapToScene(event.pos())
        item = self.scene.itemAt(click_pos, self.transform())
        
        page_clicked = None
        curr = item
        while curr:
            if isinstance(curr, PageItem):
                page_clicked = curr
                break
            curr = curr.parentItem()
        
        if event.button() == Qt.MouseButton.LeftButton and self.is_editing_mode and self.current_editor_tool != "select":
            if page_clicked == self.active_page:
                is_on_text_item = False
                curr_t = item
                while curr_t and curr_t != self.active_page:
                    if isinstance(curr_t, (AnnotationFreeTextItem, AnnotationTextBoxItem)):
                        is_on_text_item = True
                        break
                    curr_t = curr_t.parentItem()
                    
                if self.current_editor_tool == "freetext":
                    if is_on_text_item:
                        super().mousePressEvent(event)
                        return
                    text_item = AnnotationFreeTextItem(parent_page=self.active_page)
                    text_item.setPos(self.active_page.mapFromScene(click_pos))
                    text_item.bg_color = self.editor_props["freetext_bg_color"]
                    text_item.border_color = self.editor_props["freetext_border_color"]
                    text_item.setDefaultTextColor(self.editor_props["freetext_color"])
                    text_item.set_font_properties(family=self.editor_props["freetext_font_family"], size=self.editor_props["freetext_font_size"], bold=self.editor_props.get("freetext_font_bold", False), italic=self.editor_props.get("freetext_font_italic", False), underline=self.editor_props.get("freetext_font_underline", False))
                    text_item.set_editable(True)
                    self.scene.clearSelection()
                    text_item.setSelected(True)
                    text_item.setFocus()
                    
                    self._on_scene_selection_changed()
                    
                    self.save_workspace()
                    event.accept()
                    return
                elif self.current_editor_tool == "textbox":
                    if is_on_text_item:
                        super().mousePressEvent(event)
                        return
                    rect = QRectF(0, 0, 150, 60)
                    text_item = AnnotationTextBoxItem(rect, parent_page=self.active_page)
                    text_item.setPos(self.active_page.mapFromScene(click_pos))
                    text_item.bg_color = self.editor_props["textbox_bg_color"]
                    text_item.border_color = self.editor_props["textbox_border_color"]
                    text_item.text_item.setDefaultTextColor(self.editor_props["textbox_color"])
                    text_item.set_font_properties(family=self.editor_props["textbox_font_family"], size=self.editor_props["textbox_font_size"], bold=self.editor_props.get("textbox_font_bold", False), italic=self.editor_props.get("textbox_font_italic", False), underline=self.editor_props.get("textbox_font_underline", False), align_h=self.editor_props["textbox_align_h"], align_v=self.editor_props["textbox_align_v"], wrap=self.editor_props["textbox_wrap"])
                    text_item.set_editable(True)
                    self.scene.clearSelection()
                    text_item.setSelected(True)
                    text_item.setFocus()
                    
                    self._on_scene_selection_changed()
                    
                    self.save_workspace()
                    event.accept()
                    return
                elif self.current_editor_tool in ["marker", "highlighter"]:
                    self._current_drawing_path = AnnotationPathItem(parent_page=self.active_page)
                    is_hl = (self.current_editor_tool == "highlighter")
                    self._current_drawing_path.is_highlighter = is_hl
                    self._current_drawing_path.color = self.editor_props[f"{self.current_editor_tool}_color"]
                    self._current_drawing_path.thickness = self.editor_props[f"{self.current_editor_tool}_thickness"]
                    self._current_drawing_path.add_point(self.active_page.mapFromScene(click_pos))
                    self._current_drawing_path.set_editable(True)
                    event.accept()
                    return
                elif self.current_editor_tool == "signature":
                    sig_path = self.editor_props.get("signature_path")
                    sig_scale = self.editor_props.get("signature_scale", 20) / 100.0 
                    
                    if sig_path and os.path.exists(sig_path):
                        # Prima switchiamo lo strumento (cursor diventa Arrow),
                        # poi piazziamo la firma: così Qt registra Arrow come cursore
                        # di sfondo e non il cursore firma.
                        self.editor_toolbar.set_active_tool("select")
                        _page = self.active_page
                        _pos  = click_pos
                        def _place_sig(page=_page, pos=_pos, path=sig_path, scale=sig_scale):
                            sig_item = self.add_image_to_page(path, page, drop_pos=pos)
                            if sig_item:
                                sig_item.is_signature = True
                                sig_item.export_mode = "raster"
                                sig_item.scale_x = scale
                                sig_item.scale_y = scale
                                sig_item.apply_transform(False)
                                lp = page.mapFromScene(pos)
                                ws = sig_item.pixmap().width() * scale
                                hs = sig_item.pixmap().height() * scale
                                sig_item.setPos(lp.x() - ws / 2, lp.y() - hs / 2)
                                self.save_workspace()
                        QTimer.singleShot(50, _place_sig)
                    else:
                        self.show_toast("Nessuna firma configurata o file mancante.")
                    event.accept()
                    return
        
        if event.button() == Qt.MouseButton.RightButton:
            if self.is_editing_mode: 
                super().mousePressEvent(event)
            else: 
                event.accept()
            return
            
        if not self.is_editing_mode and event.button() == Qt.MouseButton.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            if page_clicked:
                if page_clicked in self.selected_pages and not modifiers: 
                    self._internal_drag_active = True
                    self._drag_start_pos = event.pos()
                else:
                    self._internal_drag_active = False
                    if modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_selected_page in self.pages:
                        idx1 = self.pages.index(self.last_selected_page)
                        idx2 = self.pages.index(page_clicked)
                        self.clear_selection()
                        for i in range(min(idx1, idx2), max(idx1, idx2) + 1):
                            p = self.pages[i]
                            self.selected_pages.append(p)
                            p.is_selected = True
                            p.update()
                        self.emit_selection_status()
                    elif modifiers & Qt.KeyboardModifier.ControlModifier: 
                        self.toggle_page_selection(page_clicked)
                        self.last_selected_page = page_clicked
                    else: 
                        self.select_single_page(page_clicked)
                        self.last_selected_page = page_clicked
            else:
                self._internal_drag_active = False
                if not (modifiers & Qt.KeyboardModifier.ControlModifier): 
                    self.clear_selection()
                    self.last_selected_page = None
                    
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.MiddleButton:
            if "Mano" in self.middle_click_mode:
                fake = QMouseEvent(event.type(), event.position(), event.globalPosition(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
                super().mouseMoveEvent(fake)
            elif "Auto-Scroll" in self.middle_click_mode and self._auto_scroll_active: 
                self._auto_scroll_current_pos = event.position()
                event.accept()
            return
            
        if self.is_editing_mode and self._current_drawing_path:
            click_pos = self.mapToScene(event.pos())
            self._current_drawing_path.add_point(self.active_page.mapFromScene(click_pos))
            event.accept()
            return
            
        if self._internal_drag_active and self.selected_pages and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.pos() - self._drag_start_pos).manhattanLength() > 10:
                y_pos = self.mapToScene(event.pos()).y()
                insert_idx = len(self.pages)
                indicator_y = (self.pages[-1].y() + self.pages[-1].boundingRect().height() + 22) if self.pages else 0
                for i, page in enumerate(self.pages):
                    if y_pos < page.y() + (page.boundingRect().height() / 2): 
                        insert_idx = i
                        indicator_y = page.y() - 28
                        break
                self.drop_indicator.setPos(0, indicator_y)
                self.drop_indicator.show()
                self.current_drop_index = insert_idx
                return 
                
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            if "Mano" in self.middle_click_mode: 
                # ---- FIX BUG PANNING: Il Rilascio Fantasma ----
                # Dobbiamo inviare un finto rilascio del tasto sinistro a PyQt
                # altrimenti la view rimane incastrata credendo che stiamo ancora trascinando il foglio!
                fake = QMouseEvent(event.type(), event.position(), event.globalPosition(), 
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers())
                super().mouseReleaseEvent(fake)
                # -----------------------------------------------
                
                if self.is_editing_mode and getattr(self, 'current_editor_tool', 'select') == "select":
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                else:
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
            elif "Auto-Scroll" in self.middle_click_mode: 
                self._auto_scroll_active = False
                self._auto_scroll_timer.stop()
                self.unsetCursor()
            event.accept()
            return
        
        if self.is_editing_mode and self._current_drawing_path:
            self._current_drawing_path = None
            self.save_workspace()
            event.accept()
            return
            
        if event.button() == Qt.MouseButton.LeftButton and self._internal_drag_active:
            self._internal_drag_active = False
            self.drop_indicator.hide()
            
            if self.current_drop_index is not None:
                indices = sorted([self.pages.index(p) for p in self.selected_pages])
                if not (indices[-1] - indices[0] == len(indices) - 1): 
                    self.show_toast("Spostamento non consentito per selezioni discontinue.")
                else:
                    self._commit_deletion()
                    target_idx = self.current_drop_index
                    if target_idx > indices[-1]: 
                        target_idx -= len(indices)
                    extracted = [self.pages.pop(i) for i in reversed(indices)]
                    for p in extracted: 
                        self.pages.insert(target_idx, p)
                    self.refresh_layout()
                    self.ensureVisible(self.selected_pages[0])
                self.current_drop_index = None
                return
                
            click_pos = self.mapToScene(event.pos())
            item = self.scene.itemAt(click_pos, self.transform())
            page_clicked = item if isinstance(item, PageItem) else (item.parent_page if isinstance(item, EditableImageItem) else None)
            
            if page_clicked and not QApplication.keyboardModifiers(): 
                self.select_single_page(page_clicked)
                
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = self.mapToScene(event.pos())
            item = self.scene.itemAt(click_pos, self.transform())
            page_clicked = item if isinstance(item, PageItem) else (item.parent_page if isinstance(item, EditableImageItem) else None)
            
            if page_clicked and (not self.is_editing_mode or self.active_page != page_clicked): 
                self.set_editing_mode(True, target_page=page_clicked)
                event.accept()
                return
                
        super().mouseDoubleClickEvent(event)

    def scrollContentsBy(self, dx, dy): 
        super().scrollContentsBy(dx, dy)
        self.emit_page_status()
        self.update_toolbars()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.emit_page_status()
        self.update_toolbars()
        self._update_splash_screen() 
        if hasattr(self, 'undo_snackbar') and self.undo_snackbar.isVisible(): 
            self._position_snackbar()
        self.btn_fab_new.move(self.viewport().width() - 86, self.viewport().height() - 86)
        if hasattr(self, 'editor_toolbar') and self.editor_toolbar.isVisible() and not self._editor_docked:
            self.editor_toolbar.move(20, (self.viewport().height() - self.editor_toolbar.height()) // 2)

    def update_toolbars(self):
        vp_h = self.viewport().height()
        
        for i, page in enumerate(self.pages):
            tb = self.toolbars.get(page)
            ind = self.page_indicators.get(page)
            pmode = self.page_modes.get(page)
            pinfo = self.page_infos.get(page)
            
            if not all([tb, ind, pmode, pinfo]): 
                continue
            
            child_imgs = [c for c in page.childItems() if isinstance(c, EditableImageItem)]
            if not child_imgs: 
                pmode.set_mode("-")
            else:
                modes = set([c.export_mode for c in child_imgs])
                pmode.set_mode("MIX" if len(modes) > 1 else ("N" if "native" in modes else "R"))

            ind.set_number(i + 1)
            
            if self.is_editing_mode and page != self.active_page:
                for w in [tb, ind, pmode, pinfo]: 
                    w.hide()
                continue
            
            sr = page.sceneBoundingRect()
            v_tl = self.mapFromScene(sr.topLeft())
            v_tr = self.mapFromScene(sr.topRight())
            v_br = self.mapFromScene(sr.bottomRight())
            
            y_min = v_tr.y()
            y_max = v_br.y()
            
            if y_max < 0 or y_min > vp_h:
                for w in [tb, ind, pmode, pinfo]: 
                    w.hide()
                continue
            
            tb.set_editing_state(self.is_editing_mode and page == self.active_page)
            for w in [tb, ind, pmode, pinfo]: 
                w.show()
            
            tb_h = tb.sizeHint().height()
            clamped_y = max(y_min + 10, min((vp_h / 2) - (tb_h / 2), y_max - 10 - tb_h))
            tb.move(int(v_tr.x() + 15), int(clamped_y))
            
            left_total_h = pmode.sizeHint().height() + pinfo.sizeHint().height() + ind.sizeHint().height() + 8
            y_l = clamped_y + (tb_h - left_total_h) / 2
            x_l = v_tl.x() - ind.width() - 15
            
            pmode.move(int(x_l), int(y_l))
            pinfo.move(int(x_l), int(y_l + pmode.sizeHint().height() + 4))
            ind.move(int(x_l), int(y_l + pmode.sizeHint().height() + pinfo.sizeHint().height() + 8))

    def emit_page_status(self):
        if not self.pages: 
            self.page_changed.emit(0, 0)
            return
            
        cp = self.get_centered_page()
        self.page_changed.emit(self.pages.index(cp) + 1 if cp in self.pages else 1, len(self.pages))

    def add_page_at(self, insert_before=None, insert_after=None, index=None, auto_save=True, is_landscape=False):
        self._commit_deletion()
        target_idx = len(self.pages)
        
        if index is not None: 
            target_idx = index
        elif insert_before and insert_before in self.pages: 
            target_idx = self.pages.index(insert_before)
        elif insert_after and insert_after in self.pages: 
            target_idx = self.pages.index(insert_after) + 1
            
        foglio = PageItem(0.0, is_landscape=is_landscape)
        self.scene.addItem(foglio)
        self.pages.insert(target_idx, foglio)
        
        self.toolbars[foglio] = PageToolbar(foglio, self, self)
        self.page_indicators[foglio] = PageNumberIndicator(foglio, self, self)
        self.page_modes[foglio] = PageOutputModeWidget(foglio, self, self)
        self.page_infos[foglio] = PageInfoButton(foglio, self, self)
        
        for w in [self.toolbars[foglio], self.page_indicators[foglio], self.page_modes[foglio], self.page_infos[foglio]]: 
            w.show()
            
        self.refresh_layout()
        self.ensureVisible(foglio)
        return foglio

    def add_page(self, auto_save=True):
        p = self.add_page_at(auto_save=auto_save)
        if not self.is_editing_mode: 
            self.select_single_page(p)
            self.last_selected_page = p
            self.setFocus()
        return p

    def update_scene_rect(self):
        max_w = max([(A4_HEIGHT if p.is_landscape else A4_WIDTH) for p in self.pages], default=A4_WIDTH)
        total_h = sum((A4_WIDTH if p.is_landscape else A4_HEIGHT) + self.page_spacing for p in self.pages)
        self.scene.setSceneRect(-150, -40, max_w + 300, total_h + 80)

    def get_centered_page(self):
        if not self.pages: 
            return None
        vc = self.mapToScene(self.viewport().rect().center())
        return min(self.pages, key=lambda p: abs(p.sceneBoundingRect().center().y() - vc.y()))

    def set_editing_mode(self, active, target_page=None):
        self._commit_deletion() 
        if active:
            target_page = target_page or self.get_centered_page()
            if not target_page: 
                return False
                
            self.clear_selection()
            self.scene.clearSelection()
            self.is_editing_mode = True
            self.active_page = target_page
            
            for p in self.pages: 
                p.set_editing_mode(p == self.active_page)
                p.setOpacity(1.0 if p == self.active_page else 0.3)
                
            if hasattr(self, 'editor_toolbar'):
                self.editor_toolbar.set_active_tool("select")
            
            self.update_toolbars()
            self.editor_toolbar.show()
            if not self._editor_docked:
                self.editor_toolbar.adjustSize()
                self.editor_toolbar.move(20, (self.viewport().height() - self.editor_toolbar.height()) // 2)
            self.ensureVisible(self.active_page, 50, 50)
            self.editing_state_changed.emit(True)
            return True
        else:
            self.is_editing_mode = False
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            if not self._editor_docked:
                self.editor_toolbar.hide()
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            
            for p in self.pages: 
                p.set_editing_mode(False)
                p.setOpacity(1.0)
                
            if self.active_page: 
                self.select_single_page(self.active_page)
                self.last_selected_page = self.active_page
                self.active_page = None
                
            self.update_toolbars()
            self.editing_state_changed.emit(False)
            return False

    def toggle_editing_for_page(self, page): 
        self.set_editing_mode(not (self.is_editing_mode and self.active_page == page), target_page=page) 

    def set_zoom(self, percentage):
        self.current_zoom = max(10, min(percentage, 400))
        tf = QTransform()
        tf.scale(self.current_zoom / 100.0, self.current_zoom / 100.0)
        self.setTransform(tf)
        self.zoom_changed.emit(self.current_zoom)
        self.update_toolbars()

    def zoom_in(self): 
        self.set_zoom(self.current_zoom + 10)
        
    def zoom_out(self): 
        self.set_zoom(self.current_zoom - 10)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): 
            event.accept()
        else: 
            event.ignore()

    def dragMoveEvent(self, event):
        if self.is_editing_mode: 
            event.accept()
            return
            
        modifiers = QApplication.keyboardModifiers()
        dp = self.mapToScene(event.position().toPoint())
        insert_idx = len(self.pages)
        indicator_y = 0.0
        vw = self.viewport().width()
        vh = self.viewport().height()
        
        if self.pages:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                insert_idx = 0
                indicator_y = self.pages[0].y() - 28
                self.drag_overlay.setText("⬆️ INSERISCI ALL'INIZIO ⬆️")
                self.drag_overlay.setGeometry(20, 20, vw - 40, 60)
                self.drag_overlay.show()
            elif modifiers & Qt.KeyboardModifier.ControlModifier:
                insert_idx = len(self.pages)
                indicator_y = self.pages[-1].y() + self.pages[-1].boundingRect().height() + 22
                self.drag_overlay.setText("⬇️ INSERISCI ALLA FINE ⬇️")
                self.drag_overlay.setGeometry(20, vh - 80, vw - 40, 60)
                self.drag_overlay.show()
            else:
                self.drag_overlay.hide()
                for i, page in enumerate(self.pages):
                    if dp.y() < page.y() + (page.boundingRect().height() / 2): 
                        insert_idx = i
                        indicator_y = page.y() - 28
                        break
                else: 
                    insert_idx = len(self.pages)
                    indicator_y = self.pages[-1].y() + self.pages[-1].boundingRect().height() + 22
                    
        self.drop_indicator.setPos(0, indicator_y)
        self.drop_indicator.setVisible(self.drag_overlay.isHidden())
        self.current_drop_index = insert_idx
        event.accept()

    def dragLeaveEvent(self, event): 
        self.drop_indicator.hide()
        self.drag_overlay.hide()
        super().dragLeaveEvent(event)
        
    def _process_dropped_files(self, urls, target_idx=None):
        tasks = []
        image_paths_for_adjustment = []
        steps = 0
        for url in urls:
            fp = url.toLocalFile()
            if not os.path.exists(fp): 
                continue
            ext = os.path.splitext(fp)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png']:
                if self.advanced_adjustment_enabled:
                    image_paths_for_adjustment.append(fp)
                else:
                    tasks.append(('image', fp))
                    steps += 1
            elif ext == '.pdf':
                try: 
                    doc = fitz.open(fp)
                    tasks.append(('pdf', (fp, doc)))
                    steps += len(doc)
                except: 
                    pass

        if image_paths_for_adjustment:
            t_idx = target_idx if target_idx is not None else len(self.pages)
            self.advanced_adjustment_requested.emit(image_paths_for_adjustment, t_idx)
                    
        if steps == 0: 
            return
            
        prog = QProgressDialog("Estrazione pagine in corso...", "Annulla", 0, steps, self)
        prog.setWindowTitle("Importazione File")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300) 
        prog.setValue(0)
        
        added = []
        curr_idx = target_idx if target_idx is not None else len(self.pages)
        curr_step = 0
        
        for ttype, tdata in tasks:
            if prog.wasCanceled(): 
                break
                
            if ttype == 'image':
                p = self.add_page_at(index=curr_idx, auto_save=False)
                added.append(p)
                self.add_image_to_page(tdata, p, center=True, auto_save=False)
                
                if target_idx is not None: 
                    curr_idx += 1
                curr_step += 1
                prog.setValue(curr_step)
                QApplication.processEvents() 
                
            elif ttype == 'pdf':
                fp, doc = tdata
                for pnum in range(len(doc)):
                    if prog.wasCanceled(): 
                        break
                        
                    pdfp = doc.load_page(pnum)
                    pix = pdfp.get_pixmap(dpi=200)
                    lpath = os.path.join(self.img_dir, f"pdf_ext_{uuid.uuid4().hex}.png")
                    pix.save(lpath)
                    
                    p = self.add_page_at(index=curr_idx, auto_save=False, is_landscape=pdfp.rect.width > pdfp.rect.height)
                    added.append(p)
                    self.add_image_to_page(lpath, p, center=True, auto_save=False, orig_pdf_path=fp, orig_page_num=pnum)
                    
                    if target_idx is not None: 
                        curr_idx += 1
                    curr_step += 1
                    prog.setValue(curr_step)
                    QApplication.processEvents() 
                doc.close()
                
        prog.setValue(steps)
        if added: 
            self.clear_selection()
            for p in added:
                self.selected_pages.append(p)
                p.update()
            self.last_selected_page = added[0]
            self.emit_selection_status()
            self.setFocus() 

    def dropEvent(self, event):
        self._commit_deletion()
        self.drop_indicator.hide()
        self.drag_overlay.hide()
        urls = event.mimeData().urls()
        
        if not urls: 
            return
            
        if self.is_editing_mode:
            dp = self.mapToScene(event.position().toPoint())
            if self.active_page.sceneBoundingRect().contains(dp):
                off = 0
                for u in urls:
                    fp = u.toLocalFile()
                    if fp.lower().endswith(('.jpg', '.jpeg', '.png')): 
                        self.add_image_to_page(fp, self.active_page, drop_pos=QPointF(dp.x()+off, dp.y()+off), auto_save=False)
                        off += 30 
        else: 
            self._process_dropped_files(urls, target_idx=self.current_drop_index if self.current_drop_index is not None else len(self.pages))
            
        self.save_workspace()
        event.accept()
    
    def handle_external_image(self, fp):
        self._commit_deletion()
        if not os.path.exists(fp): 
            return

        ext = os.path.splitext(fp)[1] or ".jpg"
        lpath = os.path.join(self.img_dir, f"src_{uuid.uuid4().hex}{ext}")
        shutil.copy2(fp, lpath)
        try:
            os.remove(fp)
        except:
            pass

        if self.advanced_adjustment_enabled:
            self.advanced_adjustment_requested.emit([lpath], len(self.pages))
            return
            
        p = self.add_page(auto_save=False)
        self.add_image_to_page(lpath, p, center=True, auto_save=True)
        self.ensureVisible(p, 50, 50)
        self.select_single_page(p)
        self.last_selected_page = p
        self.setFocus() 

    def add_adjusted_images(self, pairs, target_idx=None):
        self._commit_deletion()
        curr_idx = target_idx if target_idx is not None else len(self.pages)
        added = []
        for regulated_path, source_path, corner_points in pairs:
            if not os.path.exists(regulated_path):
                continue
            
            if self.is_editing_mode and self.active_page:
                self.add_image_to_page(source_path, self.active_page, center=True, auto_save=False, regulated_path=regulated_path, corner_points=corner_points)
            else:
                p = self.add_page_at(index=curr_idx, auto_save=False)
                added.append(p)
                self.add_image_to_page(source_path, p, center=True, auto_save=False, regulated_path=regulated_path, corner_points=corner_points)
                curr_idx += 1
                
        if added:
            self.clear_selection()
            for p in added:
                self.selected_pages.append(p)
                p.update()
            self.last_selected_page = added[0]
            self.emit_selection_status()
            self.setFocus()
        self.save_workspace()

    def update_adjusted_image(self, item, regulated_path, corner_points):
        if os.path.exists(regulated_path):
            rd = QImageReader(regulated_path)
            rd.setAutoTransform(True)
            img = rd.read()
            if not img.isNull():
                item.original_pixmap = QPixmap.fromImage(img)
                item.regulated_path = regulated_path
                item.corner_points = corner_points
                item.apply_transform(shift_center=True)
                self.save_workspace()

    def request_advanced_adjustment_for_items(self, items):
        if not items:
            return
        self.advanced_adjustment_for_items_requested.emit(items)

    def add_image_to_page(self, fp, page, center=False, drop_pos=None, auto_save=True, orig_pdf_path=None, orig_page_num=None, regulated_path=None, corner_points=None):
        if not os.path.exists(fp): 
            return
            
        fdir = os.path.dirname(os.path.abspath(fp))
        tdir = os.path.abspath(self.img_dir)
        
        if fdir == tdir:
            lpath = fp
        else:
            ext = os.path.splitext(fp)[1] or '.jpg'
            lpath = os.path.join(self.img_dir, f"src_{uuid.uuid4().hex}{ext}")
            shutil.copy2(fp, lpath)
            
        display_path = regulated_path if regulated_path and os.path.exists(regulated_path) else lpath
            
        rd = QImageReader(display_path)
        rd.setAutoTransform(True)
        img = rd.read()
        
        if img.isNull(): 
            return
            
        item = EditableImageItem(QPixmap.fromImage(img), page, lpath, orig_pdf_path, orig_page_num, regulated_path, corner_points)
        pw = A4_HEIGHT if page.is_landscape else A4_WIDTH
        ph = A4_WIDTH if page.is_landscape else A4_HEIGHT
        
        scale = min((pw - 20.0) / item.pixmap().width(), (ph - 20.0) / item.pixmap().height())
        item.scale_x = scale
        item.scale_y = scale
        item.apply_transform(False)
        
        ws = item.pixmap().width() * scale
        hs = item.pixmap().height() * scale
        
        if center or not drop_pos: 
            x = (pw - ws) / 2
            y = (ph - hs) / 2
        else: 
            lp = page.mapFromScene(drop_pos)
            x = lp.x() - ws / 2
            y = lp.y() - hs / 2
            
        item.setPos(x, y)
        if self.is_editing_mode and page == self.active_page: 
            item.set_editable(True)
            
        if auto_save: 
            self.save_workspace()
            
        return item

    def save_workspace(self):
        state = {"pages": []}
        for p in self.pages:
            pd = {
                "is_landscape": p.is_landscape, 
                "items": []
            }
            for i in p.childItems():
                if isinstance(i, EditableImageItem):
                    pd["items"].append({
                        "type": "image",
                        "source_path": i.source_path, 
                        "regulated_path": getattr(i, 'regulated_path', None),
                        "corner_points": getattr(i, 'corner_points', None),
                        "orig_pdf_path": i.orig_pdf_path, 
                        "orig_page_num": i.orig_page_num, 
                        "is_signature": getattr(i, 'is_signature', False),
                        "x": i.x(), 
                        "y": i.y(), 
                        "scale_x": i.scale_x, 
                        "scale_y": i.scale_y, 
                        "rotation": i.rotation_angle, 
                        "export_mode": i.export_mode
                    })
                elif isinstance(i, AnnotationFreeTextItem):
                    pd["items"].append({
                        "type": "freetext",
                        "x": i.x(),
                        "y": i.y(),
                        "text": i.toPlainText(),
                        "bg_color": i.bg_color.name(QColor.NameFormat.HexArgb),
                        "border_color": i.border_color.name(QColor.NameFormat.HexArgb),
                        "text_color": i.defaultTextColor().name(QColor.NameFormat.HexArgb),
                        "font_family": i.font().family(),
                        "font_size": i.font().pointSize(),
                        "font_bold": i.font().bold(),
                        "font_italic": i.font().italic(),
                        "font_underline": i.font().underline()
                    })
                elif isinstance(i, AnnotationTextBoxItem):
                    pd["items"].append({
                        "type": "textbox",
                        "x": i.x(),
                        "y": i.y(),
                        "width": i.rect().width(),
                        "height": i.rect().height(),
                        "text": i.text_item.toPlainText(),
                        "bg_color": i.bg_color.name(QColor.NameFormat.HexArgb),
                        "border_color": i.border_color.name(QColor.NameFormat.HexArgb),
                        "text_color": i.text_item.defaultTextColor().name(QColor.NameFormat.HexArgb),
                        "font_family": i.text_item.font().family(),
                        "font_size": i.text_item.font().pointSize(),
                        "font_bold": i.text_item.font().bold(),
                        "font_italic": i.text_item.font().italic(),
                        "font_underline": i.text_item.font().underline(),
                        "align_h": i.align_h,
                        "align_v": i.align_v,
                        "wrap": i.wrap
                    })
                elif isinstance(i, AnnotationPathItem):
                    points = [{"x": pt.x(), "y": pt.y()} for pt in i.points]
                    pd["items"].append({
                        "type": "path",
                        "x": i.x(),
                        "y": i.y(),
                        "color": i.color.name(QColor.NameFormat.HexArgb),
                        "thickness": i.thickness,
                        "is_highlighter": i.is_highlighter,
                        "points": points
                    })
            state["pages"].append(pd)
            
        try:
            with open(self.state_file + ".tmp", "w", encoding="utf-8") as f: 
                json.dump(state, f, indent=4)
            os.replace(self.state_file + ".tmp", self.state_file)
            self.workspace_changed.emit()
        except: 
            pass

    def load_workspace(self):
        if not os.path.exists(self.state_file): 
            return
            
        try:
            with open(self.state_file, "r", encoding="utf-8") as f: 
                state = json.load(f)
                
            for pd in state.get("pages", []):
                p = self.add_page_at(auto_save=False, is_landscape=pd.get("is_landscape", False))
                for id in pd.get("items", []):
                    itype = id.get("type", "image")
                    
                    if itype == "image":
                        source_path = id["source_path"]
                        regulated_path = id.get("regulated_path")
                        corner_points = id.get("corner_points")
                        
                        path_to_load = regulated_path if regulated_path and os.path.exists(regulated_path) else source_path
                        
                        if os.path.exists(path_to_load):
                            rd = QImageReader(path_to_load)
                            rd.setAutoTransform(True)
                            img = rd.read()
                            if not img.isNull():
                                i = EditableImageItem(QPixmap.fromImage(img), p, source_path, id.get("orig_pdf_path"), id.get("orig_page_num"), regulated_path, corner_points)
                                i.rotation_angle = id.get("rotation", 0.0)
                                i.scale_x = id.get("scale_x", 1.0)
                                i.scale_y = id.get("scale_y", 1.0)
                                i.is_signature = id.get("is_signature", False)
                                i.export_mode = id.get("export_mode", "native" if i.orig_pdf_path else "raster")
                                i.apply_transform(False)
                                i.setPos(id.get("x", 0.0), id.get("y", 0.0))
                    elif itype in ["text", "freetext"]:
                        i = AnnotationFreeTextItem(text=id.get("text", ""), parent_page=p)
                        i.setPos(id.get("x", 0.0), id.get("y", 0.0))
                        i.bg_color = QColor(id.get("bg_color", "#00ffffff"))
                        i.border_color = QColor(id.get("border_color", "#00000000"))
                        i.setDefaultTextColor(QColor(id.get("text_color", "#ff000000")))
                        i.set_font_properties(family=id.get("font_family", "Helvetica"), size=id.get("font_size", 12), bold=id.get("font_bold", False), italic=id.get("font_italic", False), underline=id.get("font_underline", False))
                    elif itype == "textbox":
                        w = id.get("width", 150)
                        h = id.get("height", 60)
                        i = AnnotationTextBoxItem(QRectF(0, 0, w, h), parent_page=p)
                        i.setPos(id.get("x", 0.0), id.get("y", 0.0))
                        i.text_item.setPlainText(id.get("text", ""))
                        i.bg_color = QColor(id.get("bg_color", "#dcdcdc"))
                        i.border_color = QColor(id.get("border_color", "#000000"))
                        i.text_item.setDefaultTextColor(QColor(id.get("text_color", "#000000")))
                        i.set_font_properties(family=id.get("font_family", "Helvetica"), size=id.get("font_size", 12), bold=id.get("font_bold", False), italic=id.get("font_italic", False), underline=id.get("font_underline", False), align_h=id.get("align_h", "Sinistra"), align_v=id.get("align_v", "Alto"), wrap=id.get("wrap", True))
                    elif itype == "path":
                        i = AnnotationPathItem(parent_page=p)
                        i.setPos(id.get("x", 0.0), id.get("y", 0.0))
                        i.color = QColor(id.get("color", "#ff000000"))
                        i.thickness = id.get("thickness", 2)
                        i.is_highlighter = id.get("is_highlighter", False)
                        for pt in id.get("points", []):
                            i.add_point(QPointF(pt["x"], pt["y"]))
                            
            self.refresh_layout()
            if self.pages: 
                self.select_single_page(self.pages[0])
                self.last_selected_page = self.pages[0]
        except: 
            pass

    def export_to_pdf(self, file_path, dpi=150, flatten_annotations=True):
        if not self.pages: 
            return False
            
        try:
            out_pdf = fitz.open()
            open_src_docs = {}
            
            for cp in self.pages:
                pw = A4_HEIGHT if cp.is_landscape else A4_WIDTH
                ph = A4_WIDTH if cp.is_landscape else A4_HEIGHT
                
                out_p = out_pdf.new_page(width=pw, height=ph)
                out_p.draw_rect(fitz.Rect(0, 0, pw, ph), color=(1,1,1), fill=(1,1,1))
                
                for item in cp.childItems():
                    if isinstance(item, EditableImageItem):
                        rect = item.sceneBoundingRect()
                        x = rect.x() - cp.scenePos().x()
                        y = rect.y() - cp.scenePos().y()
                        w = rect.width()
                        h = rect.height()
                        fz_rect = fitz.Rect(x, y, x+w, y+h)
                        
                        if item.export_mode == "native":
                            if item.orig_pdf_path and os.path.exists(item.orig_pdf_path):
                                if item.orig_pdf_path not in open_src_docs: 
                                    open_src_docs[item.orig_pdf_path] = fitz.open(item.orig_pdf_path)
                                out_p.show_pdf_page(fz_rect, open_src_docs[item.orig_pdf_path], item.orig_page_num)
                            else: 
                                out_p.insert_image(fz_rect, filename=item.source_path) 
                        else:
                            tw = int((w / 72.0) * dpi)
                            th = int((h / 72.0) * dpi)
                            img = item.pixmap().toImage()
                            if img.width() > tw or img.height() > th: 
                                img = img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                            
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QIODevice.OpenModeFlag.WriteOnly)
                            if img.hasAlphaChannel():
                                img.save(buf, "PNG")
                            else:
                                img.save(buf, "JPEG", quality=85)
                            out_p.insert_image(fz_rect, stream=ba.data())
                    elif isinstance(item, AnnotationFreeTextItem):
                        rect = item.sceneBoundingRect()
                        x = rect.x() - cp.scenePos().x()
                        y = rect.y() - cp.scenePos().y()
                        w = rect.width()
                        h = rect.height()
                        fz_rect = fitz.Rect(x, y, x+w, y+h)
                        
                        if item.bg_color.alpha() > 0 or item.border_color.alpha() > 0:
                            bg_c = (item.bg_color.redF(), item.bg_color.greenF(), item.bg_color.blueF()) if item.bg_color.alpha() > 0 else None
                            bd_c = (item.border_color.redF(), item.border_color.greenF(), item.border_color.blueF()) if item.border_color.alpha() > 0 else None
                            out_p.draw_rect(fz_rect, color=bd_c, fill=bg_c, width=1)
                            
                        tc = (item.defaultTextColor().redF(), item.defaultTextColor().greenF(), item.defaultTextColor().blueF())
                        f_name = "helv"
                        if "Times" in item.font().family(): f_name = "times"
                        elif "Courier" in item.font().family(): f_name = "courier"
                        
                        out_p.insert_textbox(fz_rect, item.toPlainText(), fontname=f_name, fontsize=item.font().pointSize(), color=tc)
                        
                    elif isinstance(item, AnnotationTextBoxItem):
                        rect = item.sceneBoundingRect()
                        x = rect.x() - cp.scenePos().x()
                        y = rect.y() - cp.scenePos().y()
                        w = rect.width()
                        h = rect.height()
                        fz_rect = fitz.Rect(x, y, x+w, y+h)
                        
                        if item.bg_color.alpha() > 0 or item.border_color.alpha() > 0:
                            bg_c = (item.bg_color.redF(), item.bg_color.greenF(), item.bg_color.blueF()) if item.bg_color.alpha() > 0 else None
                            bd_c = (item.border_color.redF(), item.border_color.greenF(), item.border_color.blueF()) if item.border_color.alpha() > 0 else None
                            out_p.draw_rect(fz_rect, color=bd_c, fill=bg_c, width=1)
                            
                        tc = (item.text_item.defaultTextColor().redF(), item.text_item.defaultTextColor().greenF(), item.text_item.defaultTextColor().blueF())
                        f_name = "helv"
                        if "Times" in item.text_item.font().family(): f_name = "times"
                        elif "Courier" in item.text_item.font().family(): f_name = "courier"
                        
                        align_val = 0
                        if item.align_h == "Centro": align_val = 1
                        elif item.align_h == "Destra": align_val = 2
                        
                        text_rect = fitz.Rect(x+2, y+2, x+w-2, y+h-2)
                        
                        out_p.insert_textbox(text_rect, item.text_item.toPlainText(), fontname=f_name, fontsize=item.text_item.font().pointSize(), color=tc, align=align_val)
                        
                    elif isinstance(item, AnnotationPathItem):
                        if len(item.points) < 2: continue
                        pts = []
                        for pt in item.points:
                            scene_pt = item.mapToScene(pt)
                            x = scene_pt.x() - cp.scenePos().x()
                            y = scene_pt.y() - cp.scenePos().y()
                            pts.append((float(x), float(y)))
                            
                        annot = out_p.add_ink_annot([pts])
                        tc = (item.color.redF(), item.color.greenF(), item.color.blueF())
                        annot.set_colors(stroke=tc)
                        annot.set_border(width=item.thickness)
                        if item.is_highlighter:
                            annot.set_opacity(0.5)
                            try: annot.set_blendmode(fitz.PDF_BM_Multiply)
                            except: pass
                        annot.update()
                            
            if flatten_annotations:
                out_pdf.bake()

            out_pdf.save(file_path, garbage=3, deflate=True)
            out_pdf.close()

            for doc in open_src_docs.values(): 
                doc.close()
            return True
            
        except Exception as e: 
            print(f"Errore export PDF: {e}")
            return False