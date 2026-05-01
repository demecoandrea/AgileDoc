from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsItem, 
                             QMenu, QApplication, QStyle)
from PyQt6.QtGui import (QColor, QBrush, QPen, QTransform, QAction)
from PyQt6.QtCore import Qt, QRectF, QPointF
import math

# Importiamo le risorse centralizzate
from const_and_resources import Dimensions, Colors, Styles, Strings

class PageItem(QGraphicsRectItem):
    def __init__(self, y_offset, is_landscape=False):
        super().__init__()
        self.is_landscape = is_landscape
        self._update_rect()
        self.setPos(0, y_offset)
        
        self.is_selected = False
        self.is_editing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)

    def _update_rect(self): 
        w = Dimensions.A4_HEIGHT if self.is_landscape else Dimensions.A4_WIDTH
        h = Dimensions.A4_WIDTH if self.is_landscape else Dimensions.A4_HEIGHT
        self.setRect(0, 0, w, h)
        
    def set_landscape(self, is_landscape): 
        self.is_landscape = is_landscape
        self._update_rect()
        self.update()

    def boundingRect(self):
        # Sovrascriviamo il boundingRect per far sì che la scena consideri
        # anche l'area occupata dal bordo esterno spesso quando deve ridisegnare.
        # Aggiungiamo un margine di 8px per contenere comodamente il tratto di selezione.
        margin = 8.0
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def paint(self, painter, option, widget=None):
        # Rimuoviamo la selezione tratteggiata di default di Qt
        option.state &= ~QStyle.StateFlag.State_HasFocus
        
        rect = self.rect()
        
        # 1. Disegna l'area della pagina completamente bianca (nessun bordo)
        painter.fillRect(rect, Qt.GlobalColor.white)
        
        # 2. Disegna un bordino nero sottile esattamente sul perimetro
        pen_bordo = QPen(Colors.BLACK, 1)
        pen_bordo.setCosmetic(True) # Rimane di 1px a qualsiasi livello di zoom
        painter.setPen(pen_bordo)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        
        # 3. Disegna l'indicatore di Selezione o Editing COMPLETAMENTE ALL'ESTERNO
        if self.is_editing or self.is_selected:
            if self.is_editing:
                pen_stato = QPen(Colors.HANDLE_ORANGE, 5)
            else:
                pen_stato = QPen(Colors.SELECTION_BLUE, 5)
            
            pen_stato.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen_stato)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Espandiamo il rettangolo di 3 pixel. 
            # Poiché il tratto è largo 5 (2.5px dentro, 2.5px fuori rispetto alla linea su cui viene disegnato),
            # traslando il tracciato di 3px verso l'esterno evitiamo ogni sovrapposizione
            # con l'area bianca e con il bordino nero.
            painter.drawRect(rect.adjusted(-3, -3, 3, 3))

    def set_editing_mode(self, is_editing):
        self.is_editing = is_editing
        # Se stiamo editando togliamo il clip, così se ridimensioniamo un'immagine
        # e sborda leggermente, possiamo vedere la maniglia comodamente.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, not is_editing)
        for child in self.childItems():
            if hasattr(child, 'set_editable'): 
                child.set_editable(is_editing)
        self.update() 


class EditableImageItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, parent_page, source_path, orig_pdf_path=None, orig_page_num=None, regulated_path=None, corner_points=None):
        super().__init__()
        
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
        pw = Dimensions.A4_HEIGHT if self.parent_page.is_landscape else Dimensions.A4_WIDTH
        ph = Dimensions.A4_WIDTH if self.parent_page.is_landscape else Dimensions.A4_HEIGHT
        
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
        if not self.is_editable: return 
            
        if not self.isSelected(): 
            self.scene().clearSelection()
            self.setSelected(True)
            
        selected_items = [item for item in self.scene().selectedItems() if getattr(item, 'is_editable', False)]
        canvas_view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        
        menu = QMenu()
        menu.setStyleSheet(Styles.MENU_STYLE) 

        if canvas_view:
            action_copy = QAction(Strings.MENU_COPY, menu)
            action_copy.triggered.connect(canvas_view.action_copy)
            menu.addAction(action_copy)
            
            action_paste = QAction(Strings.MENU_PASTE, menu)
            action_paste.setEnabled(len(canvas_view._internal_clipboard) > 0)
            action_paste.triggered.connect(canvas_view.action_paste)
            menu.addAction(action_paste)
            menu.addSeparator()
        
        export_menu = menu.addMenu("📦 Modalità Esportazione")
        action_force_raster = QAction(Strings.MENU_FORCE_RASTER, export_menu)
        action_force_native = QAction(Strings.MENU_FORCE_NATIVE, export_menu)
        
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
        
        action_delete = QAction(Strings.MENU_DELETE, menu)
        action_delete.triggered.connect(lambda: [self.scene().removeItem(item) for item in selected_items] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_delete)
        
        menu.exec(event.screenPos())

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, widget) 
        if self.is_editable:
            rect = QRectF(self.pixmap().rect())
            if self.isSelected():
                pen = QPen(Colors.SELECTION_BLUE)
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
        
        epos_vp = view.mapFromScene(self.mapToScene(event.pos()))
        epos_vp_f = QPointF(epos_vp)
        
        tl = view.mapFromScene(self.mapToScene(rect.topLeft()))
        br = view.mapFromScene(self.mapToScene(rect.bottomRight()))
        tc = view.mapFromScene(self.mapToScene(QPointF(rect.center().x(), rect.top())))
        
        H = float(Dimensions.HANDLE_PX)
        
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
