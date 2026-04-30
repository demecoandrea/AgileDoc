import os
import json
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QColor, QImageReader, QPixmap

from pdf_annotations import AnnotationFreeTextItem, AnnotationTextBoxItem, AnnotationPathItem
from canvas_items import EditableImageItem

class WorkspaceManager:
    @staticmethod
    def serialize_item(item):
        """Converte un oggetto grafico della scena in un dizionario (JSON-friendly)"""
        data = {"type": None}
        
        if isinstance(item, EditableImageItem):
            data.update({
                "type": "image",
                "source_path": item.source_path,
                "regulated_path": getattr(item, 'regulated_path', None),
                "corner_points": getattr(item, 'corner_points', None),
                "orig_pdf_path": item.orig_pdf_path,
                "orig_page_num": item.orig_page_num,
                "is_signature": getattr(item, 'is_signature', False),
                "x": item.x(),
                "y": item.y(),
                "scale_x": item.scale_x,
                "scale_y": item.scale_y,
                "rotation": item.rotation_angle,
                "export_mode": item.export_mode
            })
        elif isinstance(item, AnnotationFreeTextItem):
            data.update({
                "type": "freetext",
                "x": item.x(), "y": item.y(),
                "text": item.toPlainText(),
                "bg_color": item.bg_color.name(QColor.NameFormat.HexArgb),
                "border_color": item.border_color.name(QColor.NameFormat.HexArgb),
                "text_color": item.defaultTextColor().name(QColor.NameFormat.HexArgb),
                "font_family": item.font().family(),
                "font_size": item.font().pointSize(),
                "font_bold": item.font().bold(),
                "font_italic": item.font().italic(),
                "font_underline": item.font().underline()
            })
        elif isinstance(item, AnnotationTextBoxItem):
            data.update({
                "type": "textbox",
                "x": item.x(), "y": item.y(),
                "width": item.rect().width(), "height": item.rect().height(),
                "text": item.text_item.toPlainText(),
                "bg_color": item.bg_color.name(QColor.NameFormat.HexArgb),
                "border_color": item.border_color.name(QColor.NameFormat.HexArgb),
                "text_color": item.text_item.defaultTextColor().name(QColor.NameFormat.HexArgb),
                "font_family": item.text_item.font().family(),
                "font_size": item.text_item.font().pointSize(),
                "font_bold": item.text_item.font().bold(),
                "font_italic": item.text_item.font().italic(),
                "font_underline": item.text_item.font().underline(),
                "align_h": item.align_h, "align_v": item.align_v, "wrap": item.wrap
            })
        elif isinstance(item, AnnotationPathItem):
            data.update({
                "type": "path",
                "x": item.x(), "y": item.y(),
                "color": item.color.name(QColor.NameFormat.HexArgb),
                "thickness": item.thickness,
                "is_highlighter": item.is_highlighter,
                "points": [{"x": pt.x(), "y": pt.y()} for pt in item.points]
            })
            
        return data

    @staticmethod
    def deserialize_item(data, page, offset_x=0.0, offset_y=0.0):
        """Converte un dizionario salvato in un oggetto grafico sulla scena"""
        itype = data.get("type", "image") # Default di sicurezza
        new_x = data.get("x", 0.0) + offset_x
        new_y = data.get("y", 0.0) + offset_y
        
        if itype == "image":
            source_path = data.get("source_path")
            regulated_path = data.get("regulated_path")
            corner_points = data.get("corner_points")
            
            path_to_load = regulated_path if regulated_path and os.path.exists(regulated_path) else source_path
            
            if path_to_load and os.path.exists(path_to_load):
                rd = QImageReader(path_to_load)
                rd.setAutoTransform(True)
                img = rd.read()
                if not img.isNull():
                    i = EditableImageItem(QPixmap.fromImage(img), page, source_path, data.get("orig_pdf_path"), data.get("orig_page_num"), regulated_path, corner_points)
                    i.rotation_angle = data.get("rotation", 0.0)
                    i.scale_x = data.get("scale_x", 1.0)
                    i.scale_y = data.get("scale_y", 1.0)
                    i.is_signature = data.get("is_signature", False)
                    i.export_mode = data.get("export_mode", "native" if i.orig_pdf_path else "raster")
                    i.apply_transform(False)
                    i.setPos(new_x, new_y)
                    return i
                    
        elif itype in ["freetext", "text"]: # text è per compatibilità con vecchi salvataggi
            i = AnnotationFreeTextItem(text=data.get("text", ""), parent_page=page)
            i.setPos(new_x, new_y)
            i.bg_color = QColor(data.get("bg_color", "#00ffffff"))
            i.border_color = QColor(data.get("border_color", "#00000000"))
            i.setDefaultTextColor(QColor(data.get("text_color", "#ff000000")))
            i.set_font_properties(
                family=data.get("font_family", "Helvetica"), 
                size=data.get("font_size", 12), 
                bold=data.get("font_bold", False), 
                italic=data.get("font_italic", False), 
                underline=data.get("font_underline", False)
            )
            return i
            
        elif itype == "textbox":
            w = data.get("width", 150)
            h = data.get("height", 60)
            i = AnnotationTextBoxItem(QRectF(0, 0, w, h), parent_page=page)
            i.setPos(new_x, new_y)
            i.text_item.setPlainText(data.get("text", ""))
            i.bg_color = QColor(data.get("bg_color", "#dcdcdc"))
            i.border_color = QColor(data.get("border_color", "#000000"))
            i.text_item.setDefaultTextColor(QColor(data.get("text_color", "#000000")))
            i.set_font_properties(
                family=data.get("font_family", "Helvetica"), 
                size=data.get("font_size", 12), 
                bold=data.get("font_bold", False), 
                italic=data.get("font_italic", False), 
                underline=data.get("font_underline", False), 
                align_h=data.get("align_h", "Sinistra"), 
                align_v=data.get("align_v", "Alto"), 
                wrap=data.get("wrap", True)
            )
            return i
            
        elif itype == "path":
            i = AnnotationPathItem(parent_page=page)
            i.setPos(new_x, new_y)
            i.color = QColor(data.get("color", "#ff000000"))
            i.thickness = data.get("thickness", 2)
            i.is_highlighter = data.get("is_highlighter", False)
            for pt in data.get("points", []):
                i.add_point(QPointF(pt["x"], pt["y"]))
            i.update_pen()
            return i
            
        return None

    @staticmethod
    def save_to_file(pages, file_path):
        """Estrae i dati dalle pagine e salva il file JSON"""
        state = {"pages": []}
        for p in pages:
            pd = {"is_landscape": p.is_landscape, "items": []}
            for item in p.childItems():
                item_data = WorkspaceManager.serialize_item(item)
                if item_data.get("type"): # Salviamo solo se il tipo è riconosciuto
                    pd["items"].append(item_data)
            state["pages"].append(pd)
            
        try:
            with open(file_path + ".tmp", "w", encoding="utf-8") as f: 
                json.dump(state, f, indent=4)
            os.replace(file_path + ".tmp", file_path)
            return True
        except Exception as e:
            print(f"Errore salvataggio workspace: {e}")
            return False

    @staticmethod
    def load_from_file(file_path):
        """Legge il file JSON e restituisce il dizionario di stato"""
        if not os.path.exists(file_path): 
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception as e:
            print(f"Errore caricamento workspace: {e}")
            return None
