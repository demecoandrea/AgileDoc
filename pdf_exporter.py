import os
import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, QByteArray, QBuffer, QIODevice

from pdf_annotations import AnnotationFreeTextItem, AnnotationTextBoxItem, AnnotationPathItem
from canvas_items import EditableImageItem
from const_and_resources import Dimensions

class PdfExporter:
    @staticmethod
    def export(pages, file_path, dpi=150, flatten_annotations=True):
        """
        Esporta una lista di PageItem in un file PDF.
        """
        if not pages: 
            return False
            
        try:
            out_pdf = fitz.open()
            open_src_docs = {}
            
            for cp in pages:
                pw = Dimensions.A4_HEIGHT if cp.is_landscape else Dimensions.A4_WIDTH
                ph = Dimensions.A4_WIDTH if cp.is_landscape else Dimensions.A4_HEIGHT
                
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
