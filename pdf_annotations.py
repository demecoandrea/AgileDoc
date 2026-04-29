from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsPathItem, QGraphicsItem, QGraphicsRectItem, QApplication, QMenu, QStyle
from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QPainterPath, QAction, QPainterPathStroker
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer

# Dimensione fissa degli handle in pixel di schermo — deve corrispondere a _HANDLE_PX in canvas_editor.py
_HANDLE_PX = 20

class AnnotationTextBoxItem(QGraphicsRectItem):
    def __init__(self, rect, parent_page=None):
        super().__init__(rect)
        self.parent_page = parent_page
        if parent_page:
            self.setParentItem(parent_page)
            
        self.bg_color = QColor(220, 220, 220, 255)
        self.border_color = QColor(0, 0, 0, 255)
        self.default_text_color = QColor(0, 0, 0)
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.setAcceptHoverEvents(True)
        
        class ChildText(QGraphicsTextItem):
            def focusOutEvent(self_, event):
                super().focusOutEvent(event)
                QTimer.singleShot(0, self_._deferred_focus_out)

            def _deferred_focus_out(self_):
                from editor_toolbar import EditorToolbar
                app = QApplication.instance()
                if app:
                    fw = app.focusWidget()
                    while fw:
                        if isinstance(fw, EditorToolbar):
                            return  
                        fw = fw.parentWidget()
                cursor = self_.textCursor()
                cursor.clearSelection()
                self_.setTextCursor(cursor)
                self_.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
                if self_.parentItem():
                    self_.parentItem().setSelected(False)
                testo = self_.toPlainText().strip()
                if not testo or testo == "Inserisci testo...":
                    if self_.scene() and self_.parentItem():
                        self_.scene().removeItem(self_.parentItem())
                elif self_.scene() and self_.scene().views():
                    self_.scene().views()[0].save_workspace()

            def mouseDoubleClickEvent(self_, event):
                if self_.parentItem() and self_.parentItem().is_editable:
                    self_.parentItem().start_editing()
                super().mouseDoubleClickEvent(event)
        
        self.text_item = ChildText("Inserisci testo...", self)
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.text_item.setDefaultTextColor(self.default_text_color)
        font = QFont("Helvetica", 12)
        self.text_item.setFont(font)
        
        self.is_editable = False
        self.is_resizing = False
        self.hovering_handle = False
        
        self.align_h = "Sinistra"
        self.align_v = "Alto"
        self.wrap = True
        
        self._update_text_layout()

    def start_editing(self):
        self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.text_item.setFocus()
        if self.text_item.toPlainText() == "Inserisci testo...":
            self.text_item.setPlainText("")

    def _update_text_layout(self):
        rect = self.rect()
        if self.wrap:
            self.text_item.setTextWidth(rect.width())
        else:
            self.text_item.setTextWidth(-1)
            
        doc = self.text_item.document()
        opt = doc.defaultTextOption()
        if self.align_h == "Centro":
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        elif self.align_h == "Destra":
            opt.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            opt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        doc.setDefaultTextOption(opt)
        
        doc_height = doc.size().height()
        if self.align_v == "Centro":
            y = max(0, (rect.height() - doc_height) / 2)
        elif self.align_v == "Basso":
            y = max(0, rect.height() - doc_height)
        else:
            y = 0
            
        self.text_item.setPos(0, y)

    def set_editable(self, editable):
        self.is_editable = editable
        if not editable:
            self.setSelected(False)
            self.text_item.clearFocus()
            self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        else:
            self.text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.update()

    def itemChange(self, change, value):
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged):
            scene = self.scene()
            if scene and scene.views():
                scene.views()[0].viewport().update()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        rect = self.rect()
        
        painter.save()
        if self.bg_color.alpha() > 0:
            painter.setBrush(QBrush(self.bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)
            
        if self.border_color.alpha() > 0:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self.border_color, 1))
            painter.drawRect(rect)
        painter.restore()
            
        if self.is_editable and self.isSelected():
            painter.save()
            sel_pad = 3
            sel_rect = rect.adjusted(-sel_pad, -sel_pad, sel_pad, sel_pad)
            pen = QPen(QColor(0, 150, 255))
            pen.setCosmetic(True)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sel_rect)
            painter.restore()

    def boundingRect(self):
        br = super().boundingRect()
        pad = 5
        return br.adjusted(-pad, -pad, pad, pad)

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
            return
            
        rect = self.rect()
        sel_pad = 3
        sel_rect = rect.adjusted(-sel_pad, -sel_pad, sel_pad, sel_pad)
        
        # Hit test impeccabile in coordinate schermo (risolve i bug di scala)
        epos_vp = view.mapFromScene(self.mapToScene(event.pos()))
        epos_vp_f = QPointF(epos_vp) # <-- CONVERSIONE FIX
        br = view.mapFromScene(self.mapToScene(sel_rect.bottomRight()))
        H = float(_HANDLE_PX)
        
        in_resize = not isinstance(self, AnnotationFreeTextItem) and QRectF(br.x() - H, br.y() - H, H, H).contains(epos_vp_f)
        
        if in_resize:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            self.hovering_handle = True
        else:
            if is_select_tool:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            self.hovering_handle = False
            
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.is_editable and self.hovering_handle:
            self.is_resizing = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_resizing:
            epos = event.pos()
            desired_w = max(50, epos.x() - self.rect().x())
            desired_h = max(30, epos.y() - self.rect().y())
            self.setRect(self.rect().x(), self.rect().y(), desired_w, desired_h)
            self._update_text_layout()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_resizing:
            self.is_resizing = False
            if self.scene() and self.scene().views():
                self.scene().views()[0].save_workspace()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
        if self.is_editable and self.scene() and self.scene().views():
            self.scene().views()[0].save_workspace()

    def mouseDoubleClickEvent(self, event):
        if self.is_editable:
            self.start_editing()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if not self.is_editable: return
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)
            
        menu = QMenu()
        menu.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #4facfe;")
        
        canvas_view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if canvas_view:
            action_copy = QAction("📄 Copia", menu)
            action_copy.triggered.connect(canvas_view.action_copy)
            menu.addAction(action_copy)
            
            action_paste = QAction("📋 Incolla", menu)
            action_paste.setEnabled(len(canvas_view._internal_clipboard) > 0)
            action_paste.triggered.connect(canvas_view.action_paste)
            menu.addAction(action_paste)
            menu.addSeparator()

        action_delete = QAction("🗑️ Elimina Elemento", menu)
        action_delete.triggered.connect(lambda: [self.scene().removeItem(item) for item in self.scene().selectedItems()] and (self.scene().views()[0].save_workspace() if self.scene() and self.scene().views() else None))
        menu.addAction(action_delete)
        menu.exec(event.screenPos())

    def set_font_properties(self, family=None, size=None, bold=None, italic=None, underline=None, align_h=None, align_v=None, wrap=None):
        font = self.text_item.font()
        if family is not None: font.setFamily(family)
        if size is not None: font.setPointSize(size)
        if bold is not None: font.setBold(bold)
        if italic is not None: font.setItalic(italic)
        if underline is not None: font.setUnderline(underline)
        self.text_item.setFont(font)
        
        cursor = self.text_item.textCursor()
        cursor.select(cursor.SelectionType.Document)
        fmt = cursor.charFormat()
        fmt.setFont(font)
        cursor.setCharFormat(fmt)
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        
        if align_h is not None: self.align_h = align_h
        if align_v is not None: self.align_v = align_v
        if wrap is not None: self.wrap = wrap
        
        self._update_text_layout()
            
        if self.scene() and self.scene().views():
            self.scene().views()[0].save_workspace()

    def set_text_color(self, color):
        self.default_text_color = color
        self.text_item.setDefaultTextColor(color)
        cursor = self.text_item.textCursor()
        cursor.select(cursor.SelectionType.Document)
        fmt = cursor.charFormat()
        fmt.setForeground(color)
        cursor.setCharFormat(fmt)
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        self.update()
        if self.scene() and self.scene().views():
            self.scene().views()[0].save_workspace()

    def setFocus(self):
        self.start_editing()

class AnnotationFreeTextItem(AnnotationTextBoxItem):
    def __init__(self, text="Inserisci testo...", parent_page=None):
        super().__init__(QRectF(0, 0, 100, 30), parent_page)
        self.bg_color = QColor(255, 255, 255, 0)
        self.border_color = QColor(0, 0, 0, 0)
        self.wrap = False
        self.text_item.document().setDocumentMargin(0)
        self.text_item.setPlainText(text)
        self.text_item.document().contentsChanged.connect(self._auto_resize)
        self._auto_resize()

    def _update_text_layout(self):
        self.text_item.setTextWidth(-1)
        self.text_item.setPos(2, 2)

    def _auto_resize(self):
        margin = 2
        br = self.text_item.boundingRect()
        self.setRect(0, 0, br.width() + 2*margin, br.height() + 2*margin)
        self.text_item.setPos(margin, margin)
        self.update()

    def toPlainText(self):
        return self.text_item.toPlainText()

    def setPlainText(self, text):
        self.text_item.setPlainText(text)
        self._auto_resize()

    def font(self):
        return self.text_item.font()

    def setFont(self, font):
        self.text_item.setFont(font)
        self._auto_resize()

    def setDefaultTextColor(self, color):
        self.set_text_color(color)

    def defaultTextColor(self):
        return self.default_text_color

    def textCursor(self):
        return self.text_item.textCursor()

    def setTextCursor(self, cursor):
        self.text_item.setTextCursor(cursor)


class AnnotationPathItem(QGraphicsPathItem):
    def __init__(self, parent_page=None):
        super().__init__()
        self.parent_page = parent_page
        if parent_page:
            self.setParentItem(parent_page)
            
        self.color = QColor(255, 255, 0)
        self.thickness = 10
        self.is_highlighter = True
        
        self.points = [] 
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
        self.is_editable = False
        self.setAcceptHoverEvents(True)
        
    def shape(self):
        path = self.path()
        if path.isEmpty():
            return super().shape()
            
        # Calcoliamo la traccia "stroked"
        stroker = QPainterPathStroker()
        stroker.setWidth(max(20, self.thickness))
        if self.is_highlighter:
            stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        else:
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        stroked_path = stroker.createStroke(path)
        
        # Se selezionato, l'area cliccabile è l'intero rettangolo (evita crash ricorsione)
        if self.is_editable and self.isSelected():
            rect_path = QPainterPath()
            rect_path.addRect(stroked_path.boundingRect())
            return rect_path
            
        return stroked_path
        
    def add_point(self, point):
        self.points.append(point)
        if len(self.points) < 2: return
        
        path = QPainterPath()
        path.moveTo(self.points[0])
        for i in range(1, len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i+1]
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            path.quadTo(p1, mid)
            
        path.lineTo(self.points[-1])
        self.setPath(path)
        self.update_pen()

    def update_pen(self):
        pen = QPen(self.color, self.thickness)
        
        # Simula la punta a scalpello per l'evidenziatore
        if self.is_highlighter:
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            self.setOpacity(0.5)
        else:
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.setOpacity(1.0)
            
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def set_editable(self, editable):
        self.is_editable = editable
        if not editable:
            self.setSelected(False)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        else:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.update()

    def hoverMoveEvent(self, event):
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        is_select_tool = view and getattr(view, 'current_editor_tool', 'select') == "select"
        
        if self.is_editable and is_select_tool:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def itemChange(self, change, value):
        if change in (QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged):
            scene = self.scene()
            if scene and scene.views():
                scene.views()[0].viewport().update()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, widget)
        if self.is_editable and self.isSelected():
            rect = self.boundingRect()
            pen = QPen(QColor(0, 150, 255))
            pen.setCosmetic(True)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)
            
    def _delete_selected(self):
        scene = self.scene()
        if not scene: return
        views = scene.views()
        for item in scene.selectedItems():
            scene.removeItem(item)
        if views:
            views[0].save_workspace()

    def contextMenuEvent(self, event):
        if not self.is_editable:
            return
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)
            
        menu = QMenu()
        menu.setStyleSheet("background-color: #2a2a2a; color: white; border: 1px solid #4facfe;")
        
        canvas_view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if canvas_view:
            action_copy = QAction("📄 Copia", menu)
            action_copy.triggered.connect(canvas_view.action_copy)
            menu.addAction(action_copy)
            
            action_paste = QAction("📋 Incolla", menu)
            action_paste.setEnabled(len(canvas_view._internal_clipboard) > 0)
            action_paste.triggered.connect(canvas_view.action_paste)
            menu.addAction(action_paste)
            menu.addSeparator()
        
        action_delete = QAction("🗑️ Elimina Disegno", menu)
        action_delete.triggered.connect(self._delete_selected)
        menu.addAction(action_delete)
        
        menu.exec(event.screenPos())

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.is_editable and self.scene() and self.scene().views():
            self.scene().views()[0].save_workspace()
