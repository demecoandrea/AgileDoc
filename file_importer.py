import os
import shutil
import uuid
import fitz  # PyMuPDF
from PyQt6.QtWidgets import QProgressDialog, QApplication
from PyQt6.QtCore import Qt

class FileImporter:
    
    @staticmethod
    def handle_external_image(canvas, fp):
        """Gestisce l'importazione di una singola immagine esterna."""
        canvas._commit_deletion()
        if not os.path.exists(fp): 
            return

        ext = os.path.splitext(fp)[1] or ".jpg"
        lpath = os.path.join(canvas.img_dir, f"src_{uuid.uuid4().hex}{ext}")
        shutil.copy2(fp, lpath)
        try:
            os.remove(fp)
        except:
            pass

        if canvas.advanced_adjustment_enabled:
            canvas.advanced_adjustment_requested.emit([lpath], len(canvas.pages))
            return
            
        p = canvas.add_page(auto_save=False)
        canvas.add_image_to_page(lpath, p, center=True, auto_save=True)
        canvas.ensureVisible(p, 50, 50)
        canvas.select_single_page(p)
        canvas.last_selected_page = p
        canvas.setFocus() 

    @staticmethod
    def process_dropped_files(canvas, urls, target_idx=None):
        """Elabora una lista di URL (file trascinati) estraendo immagini e PDF."""
        tasks = []
        image_paths_for_adjustment = []
        steps = 0
        
        # 1. Analisi dei file in ingresso
        for url in urls:
            fp = url.toLocalFile()
            if not os.path.exists(fp): 
                continue
            ext = os.path.splitext(fp)[1].lower()
            
            if ext in ['.jpg', '.jpeg', '.png']:
                if canvas.advanced_adjustment_enabled:
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

        # 2. Gestione regolazione avanzata (se attiva)
        if image_paths_for_adjustment:
            t_idx = target_idx if target_idx is not None else len(canvas.pages)
            canvas.advanced_adjustment_requested.emit(image_paths_for_adjustment, t_idx)
                    
        if steps == 0: 
            return
            
        # 3. Setup della barra di progresso
        prog = QProgressDialog("Estrazione pagine in corso...", "Annulla", 0, steps, canvas)
        prog.setWindowTitle("Importazione File")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(300) 
        prog.setValue(0)
        
        added = []
        curr_idx = target_idx if target_idx is not None else len(canvas.pages)
        curr_step = 0
        
        # 4. Esecuzione dei task (Importazione effettiva)
        for ttype, tdata in tasks:
            if prog.wasCanceled(): 
                break
                
            if ttype == 'image':
                p = canvas.add_page_at(index=curr_idx, auto_save=False)
                added.append(p)
                canvas.add_image_to_page(tdata, p, center=True, auto_save=False)
                
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
                    lpath = os.path.join(canvas.img_dir, f"pdf_ext_{uuid.uuid4().hex}.png")
                    pix.save(lpath)
                    
                    p = canvas.add_page_at(index=curr_idx, auto_save=False, is_landscape=pdfp.rect.width > pdfp.rect.height)
                    added.append(p)
                    canvas.add_image_to_page(lpath, p, center=True, auto_save=False, orig_pdf_path=fp, orig_page_num=pnum)
                    
                    if target_idx is not None: 
                        curr_idx += 1
                    curr_step += 1
                    prog.setValue(curr_step)
                    QApplication.processEvents() 
                doc.close()
                
        prog.setValue(steps)
        
        # 5. Selezione finale delle pagine aggiunte
        if added: 
            canvas.clear_selection()
            for p in added:
                canvas.selected_pages.append(p)
                p.update()
            canvas.last_selected_page = added[0]
            canvas.emit_selection_status()
            canvas.setFocus()
