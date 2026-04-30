from PyQt6.QtGui import (QCursor, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath)
from PyQt6.QtCore import Qt, QRectF, QPointF

def create_tool_cursor(tool_id, editor_props, current_zoom):
    """
    Fabbrica e restituisce un QCursor personalizzato in base al tool selezionato.
    Se il tool è 'select', restituisce il cursore freccia standard.
    """
    if tool_id == "select":
        return Qt.CursorShape.ArrowCursor

    # 1. Mappatura delle proprietà in base al tool
    badge_text = ""
    bg_color = ""
    is_marker = False
    is_chisel = False

    if tool_id == "marker":
        is_marker = True
    elif tool_id == "highlighter":
        is_chisel = True
    elif tool_id == "freetext":
        badge_text = "+MDS"
        bg_color = "#0078d7"
    elif tool_id == "textbox":
        badge_text = "+CDT"
        bg_color = "#d35400"
    elif tool_id == "signature":
        badge_text = "+FIR"
        bg_color = "#27ae60"
    else:
        # Fallback di sicurezza se arriva un tool_id sconosciuto
        return Qt.CursorShape.ArrowCursor

    # 2. Setup del Canvas per disegnare il cursore
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    hotspot_x, hotspot_y = 0, 0
    center = 32

    # 3. Disegno specifico del cursore
    if is_marker:
        thickness = editor_props.get("marker_thickness", 2)
        m_color = editor_props.get("marker_color", QColor(0,0,0))
        visual_size = max(4, thickness * (current_zoom / 100.0))
        
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
        border_color = Qt.GlobalColor.white if m_color.lightness() < 128 else Qt.GlobalColor.black
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(m_color))
        painter.drawEllipse(rect)
        hotspot_x, hotspot_y = center, center

    elif is_chisel:
        thickness = editor_props.get("highlighter_thickness", 10)
        h_color = editor_props.get("highlighter_color", QColor(255, 255, 0))
        visual_w = max(2, thickness * (current_zoom / 100.0) * 0.3)
        visual_h = max(10, thickness * (current_zoom / 100.0))
        
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
        # Cursore standard con badge + Freccia
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.black))
        arrow_poly = QPainterPath()
        arrow_poly.moveTo(0, 0); arrow_poly.lineTo(0, 16); arrow_poly.lineTo(4, 12)
        arrow_poly.lineTo(8, 20); arrow_poly.lineTo(11, 18); arrow_poly.lineTo(7, 11)
        arrow_poly.lineTo(12, 11); arrow_poly.closeSubpath()
        painter.drawPath(arrow_poly)
        
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
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