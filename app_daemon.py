import sys
import os
import json
import winreg
from version import __version__, APP_NAME
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction, QCursor

from main_window import MainWindow, setup_dark_theme
from api_server import LocalServerThread

class AgileDocDaemon:
    def __init__(self, app, is_autostart=False):
        self.app = app
        self.is_autostart = is_autostart 

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.conf_dir = os.path.join(self.base_dir, "conf")
        self.res_dir = os.path.join(self.base_dir, "res")
        
        os.makedirs(self.conf_dir, exist_ok=True)
        os.makedirs(self.res_dir, exist_ok=True)

        self.icon_path = os.path.join(self.res_dir, "agiledoc_icon.ico")
        self.app.setWindowIcon(QIcon(self.icon_path)) 
        
        self.config_file = os.path.join(self.conf_dir, "agiledoc_config.json")
        self.load_daemon_config()
        # ---------------------------------
        
        self.main_window = MainWindow()
        self.main_window.server_settings_changed.connect(self.restart_server)
        self.main_window.window_closed.connect(self.on_main_window_closed)
        self.main_window.full_exit_requested.connect(self.quit_app)

        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(QIcon(self.icon_path))
        self.tray_icon.setToolTip("AgileDoc - In background")

        self.tray_menu = QMenu()

        self.title_action = QAction(f"✨ {APP_NAME} v{__version__}", self.tray_menu)
        self.title_action.setDisabled(True) 
        self.tray_menu.addAction(self.title_action)
        
        self.tray_menu.addSeparator()

        self.action_show = QAction("Mostra Interfaccia Principale", self.tray_menu)
        font = self.action_show.font()
        font.setBold(True)
        self.action_show.setFont(font)
        self.action_show.triggered.connect(self.show_main_window)
        self.tray_menu.addAction(self.action_show)

        self.tray_menu.addSeparator()

        self.settings_menu = self.tray_menu.addMenu("⚙️ Impostazioni Demone")
        
        self.action_startup = QAction("Lancia AgileDoc all'avvio di Windows", self.settings_menu)
        self.action_startup.setCheckable(True)
        self.action_startup.setChecked(self.check_startup_registry())
        self.action_startup.triggered.connect(self.toggle_startup)
        self.settings_menu.addAction(self.action_startup)
        
        self.settings_menu.addSeparator()

        self.action_auto_show_manual = QAction("Mostra interfaccia all'avvio MANUALE", self.settings_menu)
        self.action_auto_show_manual.setCheckable(True)
        self.action_auto_show_manual.setChecked(self.auto_show_manual)
        self.action_auto_show_manual.triggered.connect(self.save_daemon_config)
        self.settings_menu.addAction(self.action_auto_show_manual)
        
        self.action_auto_show_auto = QAction("Mostra interfaccia all'avvio AUTOMATICO", self.settings_menu)
        self.action_auto_show_auto.setCheckable(True)
        self.action_auto_show_auto.setChecked(self.auto_show_auto)
        self.action_auto_show_auto.triggered.connect(self.save_daemon_config)
        self.settings_menu.addAction(self.action_auto_show_auto)
        
        self.settings_menu.addSeparator()

        self.action_quit_on_close = QAction("Termina app chiudendo l'interfaccia (X)", self.settings_menu)
        self.action_quit_on_close.setCheckable(True)
        self.action_quit_on_close.setChecked(self.quit_on_close)
        self.action_quit_on_close.triggered.connect(self.save_daemon_config)
        self.settings_menu.addAction(self.action_quit_on_close)

        self.tray_menu.addSeparator()

        self.action_quit = QAction("Esci da AgileDoc", self.tray_menu)
        self.action_quit.triggered.connect(self.quit_app)
        self.tray_menu.addAction(self.action_quit)

        # NOTA: Abbiamo rimosso setContextMenu per gestire l'apertura manualmente e fixare la posizione
        self.tray_icon.activated.connect(self.tray_activated)
        self.tray_icon.show()

        self.server_thread = None
        self.start_server(self.main_window.server_port, self.main_window.hub_name)
        
        if self.is_autostart:
            if self.auto_show_auto: self.show_main_window()
        else:
            if self.auto_show_manual: self.show_main_window()

    def load_daemon_config(self):
        self.auto_show_manual = True   
        self.auto_show_auto = False    
        self.quit_on_close = False     
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.auto_show_manual = data.get("auto_show_manual", True)
                    self.auto_show_auto = data.get("auto_show_auto", False)
                    self.quit_on_close = data.get("quit_on_close", False)
            except Exception:
                pass

    def save_daemon_config(self):
        data = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception: pass
                
        data["auto_show_manual"] = self.action_auto_show_manual.isChecked()
        data["auto_show_auto"] = self.action_auto_show_auto.isChecked()
        data["quit_on_close"] = self.action_quit_on_close.isChecked()
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception: pass

    def start_server(self, port, hub_name):
        self.server_thread = LocalServerThread(port=port, hub_name=hub_name)
        self.server_thread.image_received.connect(self.main_window.canvas.handle_external_image)
        self.server_thread.open_ui_requested.connect(self.show_main_window)
        self.server_thread.quicksave_requested.connect(self.main_window.action_quick_save)
        self.server_thread.start()

    def restart_server(self, new_port, new_hub_name):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait()
        self.start_server(new_port, new_hub_name)
        self.main_window.update_server_status_ui()

    def tray_activated(self, reason):
        # FIX POSIZIONAMENTO MENU: Intercettiamo il click destro (Context)
        if reason == QSystemTrayIcon.ActivationReason.Context:
            pos = QCursor.pos()
            # Alziamo il menu di 25 pixel (puoi aggiustare questo valore se serve)
            pos.setY(pos.y() - 25) 
            self.tray_menu.popup(pos)
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main_window()

    def show_main_window(self):
        self.main_window.show()
        self.main_window.activateWindow()
        self.main_window.raise_()

    def on_main_window_closed(self):
        if self.action_quit_on_close.isChecked():
            self.quit_app()

    def check_startup_registry(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "AgileDoc")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False

    def toggle_startup(self, checked):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if checked:
                command = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --autostart'
                winreg.SetValueEx(key, "AgileDoc", 0, winreg.REG_SZ, command)
                self.tray_icon.showMessage("Avvio Automatico", "AgileDoc si avvierà con Windows in background.", QSystemTrayIcon.MessageIcon.Information, 2000)
            else:
                winreg.DeleteValue(key, "AgileDoc")
                self.tray_icon.showMessage("Avvio Automatico", "Avvio automatico disabilitato.", QSystemTrayIcon.MessageIcon.Information, 2000)
            winreg.CloseKey(key)
        except Exception as e:
            QMessageBox.critical(None, "Errore di Sistema", f"Impossibile modificare il registro di Windows:\n{e}")

    def quit_app(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait()
        self.app.quit()


if __name__ == "__main__":
    is_autostart = "--autostart" in sys.argv
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) 
    setup_dark_theme(app)
    daemon = AgileDocDaemon(app, is_autostart=is_autostart)
    sys.exit(app.exec())
