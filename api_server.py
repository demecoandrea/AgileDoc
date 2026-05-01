import socket
import os
import uuid
from flask import Flask, request, jsonify
from werkzeug.serving import make_server
from PyQt6.QtCore import QThread, pyqtSignal

from const_and_resources import AppInfo

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class LocalServerThread(QThread):
    image_received = pyqtSignal(str)
    open_ui_requested = pyqtSignal()     
    quicksave_requested = pyqtSignal()   

    def __init__(self, port=5000, hub_name=f"{AppInfo.NAME} Hub"):
        super().__init__()
        self.port = port
        self.hub_name = hub_name
        self.app = Flask(__name__)
        self.server = None
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.workspace_dir = os.path.join(base_dir, "temp", "images")
        os.makedirs(self.workspace_dir, exist_ok=True)
        
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/ping', methods=['GET'])
        def ping():
            return jsonify({
                "status": "ok", 
                "message": f"{AppInfo.NAME} Server in ascolto!",
                "hub_name": self.hub_name
            })

        @self.app.route('/upload', methods=['POST'])
        def upload():
            if 'file' not in request.files:
                return jsonify({"error": "Nessun file ricevuto"}), 400
            
            file = request.files['file']
            ext = os.path.splitext(file.filename)[1]
            if not ext: ext = ".jpg"
            
            filename = f"ricevuto_{uuid.uuid4().hex}{ext}"
            path = os.path.join(self.workspace_dir, filename)
            file.save(path) 
            
            self.image_received.emit(path)
            return jsonify({"status": "success"})

        @self.app.route('/open_ui', methods=['GET', 'POST'])
        def open_ui():
            self.open_ui_requested.emit()
            return jsonify({"status": "success", "message": "Interfaccia richiamata"})

        @self.app.route('/quicksave', methods=['GET', 'POST'])
        def quicksave():
            self.quicksave_requested.emit()
            return jsonify({"status": "success", "message": "Salvataggio rapido avviato in background"})

    def run(self):
        try:
            self.server = make_server('0.0.0.0', self.port, self.app)
            self.server.serve_forever()
        except OSError as e:
            print(f"Errore avvio server porta {self.port}: {e}")

    def stop(self):
        if self.server:
            self.server.shutdown()
