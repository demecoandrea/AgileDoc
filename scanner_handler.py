import os
import uuid
import subprocess
import glob
from PyQt6.QtGui import QImage

def get_available_scanners(method="TWAIN", res_dir="res"):
    scanners = []
    
    if method == "TWAIN":
        bridge_path = os.path.join(res_dir, "ADMSimpleTwainBridge.exe")
        if not os.path.exists(bridge_path):
            raise Exception(f"Bridge TWAIN non trovato in: {bridge_path}")
        
        try:
            result = subprocess.run([bridge_path, "--list"], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            
            for line in lines:
                name = line.strip()
                if name:
                    scanners.append((name, name))
                    
        except subprocess.CalledProcessError as e:
            raise Exception(f"Errore interrogazione TWAIN: {e.stderr}")
            
    elif method == "WIA":
        try:
            import win32com.client
            manager = win32com.client.Dispatch("WIA.DeviceManager")
            
            for info in manager.DeviceInfos:
                if info.Type == 1:
                    name = "Scanner Sconosciuto"
                    for prop in info.Properties:
                        if prop.Name == "Name":
                            name = prop.Value
                            break
                    scanners.append((info.DeviceID, name))
                    
        except ImportError:
            raise Exception("Libreria 'pywin32' non installata. Esegui: pip install pywin32")
        except Exception as e:
            raise Exception(f"Errore inizializzazione WIA: {e}")
            
    return scanners


def scan_pages(scanner_id, method="TWAIN", res_dir="res", temp_dir="temp"):
    target_dir = temp_dir 
    os.makedirs(target_dir, exist_ok=True)
    
    scanned_bmps = []
    
    if method == "TWAIN":
        bridge_path = os.path.join(res_dir, "ADMSimpleTwainBridge.exe")
        if not os.path.exists(bridge_path):
            raise Exception(f"Bridge TWAIN non trovato in: {bridge_path}")
        
        try:
            subprocess.run([bridge_path, "--scan", scanner_id, target_dir], check=True)
            scanned_bmps = glob.glob(os.path.join(target_dir, "*.bmp"))
        except subprocess.CalledProcessError as e:
            print(f"Acquisizione TWAIN annullata o fallita: {e}")
            return []
            
    elif method == "WIA":
        try:
            import win32com.client
            manager = win32com.client.Dispatch("WIA.DeviceManager")
            
            device_info = None
            for info in manager.DeviceInfos:
                if info.DeviceID == scanner_id:
                    device_info = info
                    break
                    
            if not device_info:
                raise Exception("Scanner WIA non trovato o disconnesso.")
            
            device = device_info.Connect()
            item = device.Items[1] 
            
            wiaFormatBMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"
            dialog = win32com.client.Dispatch("WIA.CommonDialog")
            
            image = dialog.ShowTransfer(item, wiaFormatBMP, False)
            
            if image is not None:
                bmp_filepath = os.path.join(target_dir, f"scan_{uuid.uuid4().hex}.bmp")
                if os.path.exists(bmp_filepath):
                    os.remove(bmp_filepath)
                image.SaveFile(bmp_filepath)
                scanned_bmps.append(bmp_filepath)
                
        except Exception as e:
            error_msg = str(e)
            if "80210015" in error_msg or "80210064" in error_msg:
                return []
            raise Exception(f"Errore hardware WIA: {error_msg}")

    final_jpgs = []
    for bmp_path in scanned_bmps:
        jpg_filename = f"scan_converted_{uuid.uuid4().hex}.jpg"
        jpg_path = os.path.join(target_dir, jpg_filename)
        
        qimg = QImage(bmp_path)
        if not qimg.isNull():
            qimg.save(jpg_path, "JPG", 85)
            final_jpgs.append(jpg_path)
            
        try:
            os.remove(bmp_path)
        except Exception as e:
            print(f"Attenzione: Impossibile eliminare BMP temporaneo {bmp_path}: {e}")
            
    return final_jpgs
