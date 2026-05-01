from PyQt6.QtGui import QColor

class AppInfo:
    NAME = "AgileDoc"
    VERSION = "1.0beta"

class Dimensions:
    A4_WIDTH = 595.0
    A4_HEIGHT = 842.0
    HANDLE_PX = 20
    
    # Altezze barre
    L1_HEIGHT = 30
    L2_HEIGHT = 27

class Colors:
    # --- Colori Base (QColor) ---
    BG_DARK = QColor(30, 30, 30)
    BG_PANEL = QColor(42, 42, 42)
    SELECTION_BLUE = QColor(0, 150, 255)
    SELECTION_GHOST = QColor(100, 150, 255, 180)
    HIGHLIGHT_YELLOW = QColor(255, 255, 0)
    HANDLE_ORANGE = QColor(255, 165, 0)
    DROP_INDICATOR = QColor(42, 130, 218, 200)
    
    # Colori Tema Scuro (Fusion Palette)
    THEME_BASE = QColor(35, 35, 35)      
    THEME_ALT_BASE = QColor(25, 25, 25)  
    THEME_TEXT = QColor(220, 220, 220)   
    THEME_ACCENT = QColor(42, 130, 218)
    
    # --- Colori per Editor e Annotazioni (QColor) ---
    TEXT_DEFAULT_BG = QColor(220, 220, 220)
    FREETEXT_DEFAULT_BG = QColor(255, 255, 255, 0) # Trasparente
    BLACK = QColor(0, 0, 0)
    WHITE = QColor(255, 255, 255)
    TRANSPARENT = QColor(0, 0, 0, 0)
    
    # --- Colori HEX per Fogli di Stile (CSS) ---
    HEX_ACCENT = "#4facfe"
    HEX_SUCCESS = "#4ade80"
    HEX_WARNING = "#ffaa00"
    HEX_DANGER = "#ff4444"
    HEX_DANGER_HOVER = "#cc0000"
    HEX_BG_DARK = "#1a1a1a"
    HEX_BG_LIGHTER = "#2a2a2a"
    HEX_BG_DIALOG = "#2b2b2b"
    HEX_BTN_BG = "#3a3a3a"
    HEX_BTN_HOVER = "#505050"
    HEX_BORDER = "#555555"

class Styles:
    # --- Stili Globali ---
    UNIFIED_BTN_STYLE = f"""
        QPushButton, QLabel {{
            background-color: {Colors.HEX_BTN_BG}; 
            color: #dddddd; 
            border-radius: 4px; 
            padding: 6px 3px; 
            font-weight: bold; 
            font-size: 14px; 
            border: 1px solid {Colors.HEX_BORDER};
        }}
        QPushButton:hover {{ background-color: {Colors.HEX_BTN_HOVER}; border: 1px solid #777777; }}
        QPushButton:pressed {{ background-color: {Colors.HEX_BG_LIGHTER}; }}
    """

    SCANNER_BTN_STYLE = f"""
        QPushButton {{ 
            background-color: {Colors.HEX_BTN_BG}; 
            color: white; 
            border-radius: 4px; 
            padding: 6px 15px; 
            font-weight: bold; 
            border: 1px solid {Colors.HEX_BORDER}; 
            height: 20px; 
        }} 
        QPushButton:hover {{ background-color: {Colors.HEX_BTN_HOVER}; }} 
        QPushButton:disabled {{ background-color: #222; color: #555; }}
    """

    FRAME_STYLE = f"QFrame#ImageFrame {{ border: 3px solid {Colors.HEX_BTN_BG}; border-radius: 4px; background-color: {Colors.HEX_BG_DARK}; }}"

    TOOLBAR_STYLE = f"""
        QFrame {{
            background-color: {Colors.HEX_BG_DIALOG};
            border-radius: 6px;
            border: 1px solid {Colors.HEX_ACCENT};
        }}
        QPushButton {{
            background-color: {Colors.HEX_BTN_BG};
            color: #ddd;
            border: 1px solid {Colors.HEX_BORDER};
            border-radius: 4px;
            padding: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {Colors.HEX_BTN_HOVER}; border: 1px solid #777; }}
        QPushButton:checked {{ background-color: #0078d7; color: white; border: 1px solid #005a9e; }}
        QPushButton:disabled {{ background-color: #222; color: #555; border: 1px solid #333; }}
        QLabel {{ background: transparent; border: none; font-size: 11px; color: #ccc; }}
        QComboBox, QSpinBox {{
            background-color: {Colors.HEX_BTN_BG};
            border: 1px solid {Colors.HEX_BORDER};
            border-radius: 3px;
            padding: 2px;
            color: white;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.HEX_BTN_BG};
            color: white;
            selection-background-color: #0078d7;
        }}
        QSlider::groove:horizontal {{ border: 1px solid {Colors.HEX_BORDER}; height: 4px; background: {Colors.HEX_BTN_BG}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background: #ddd; border: 1px solid #888; width: 12px; margin: -4px 0; border-radius: 6px; }}
        QSlider::handle:horizontal:hover {{ background: #fff; }}
        QWidget#subgroup {{ background: transparent; border: none; }}
    """
    
    MENU_STYLE = f"""
        background-color: {Colors.HEX_BG_LIGHTER}; 
        color: white; 
        border: 1px solid {Colors.HEX_ACCENT};
    """

class Strings:
    # --- Testi Ricorrenti e UI ---
    MENU_COPY = "📄 Copia"
    MENU_PASTE = "📋 Incolla"
    MENU_DELETE = "🗑️ Elimina Elemento"
    MENU_FORCE_RASTER = "🗜️ Forza modalità rasterizzazione"
    MENU_FORCE_NATIVE = "📄 Forza modalità nativa (originale)"
    DEFAULT_TEXTBOX_TEXT = "Inserisci testo..."
    
class HelpTexts:
    SHORTCUTS_HTML = """
    <h3 style="color: #4facfe;">Navigazione e Selezione</h3>
    <ul>
        <li><b>Click Sinistro:</b> Seleziona una singola pagina.</li>
        <li><b>Ctrl + Click Sinistro:</b> Aggiungi/Rimuovi la pagina dalla selezione (Multiselezione).</li>
        <li><b>Shift + Click Sinistro:</b> Seleziona tutte le pagine tra l'ultima cliccata e quella corrente.</li>
        <li><b>Ctrl + A:</b> Seleziona tutte le pagine.</li>
        <li><b>Ctrl + Shift + A:</b> Inverti la selezione attuale.</li>
        <li><b>ESC:</b> Deseleziona tutto (o esci dalla modalità Editing).</li>
    </ul>
    <h3 style="color: #4facfe;">Gestione Pagine</h3>
    <ul>
        <li><b>Freccia SU / GIÙ:</b> (Con 1 pagina selezionata) Scorri tra le pagine.</li>
        <li><b>Ctrl + Freccia SU / GIÙ:</b> Sposta fisicamente la pagina in alto o in basso.</li>
        <li><b>CANC:</b> Elimina la pagina selezionata (o tutte le pagine selezionate).</li>
        <li><b>E:</b> Attiva/Disattiva la modalità Editing per la pagina selezionata.</li>
    </ul>
    <h3 style="color: #4facfe;">Modalità Editing e Varie</h3>
    <ul>
        <li><b>Ctrl + Rotellina Mouse:</b> Zoom In / Zoom Out.</li>
        <li><b>Drag & Drop (Normale):</b> Inserisce i fogli nel punto esatto indicato dalla barra blu.</li>
        <li><b>Shift + Drag & Drop:</b> Forza l'inserimento all'INIZIO del documento.</li>
        <li><b>Ctrl + Drag & Drop:</b> Forza l'inserimento alla FINE del documento.</li>
        <li><b>Ctrl + Trascina l'angolo (in Editing):</b> Ridimensionamento libero dell'immagine (ignora proporzioni).</li>
        <li><b>Ctrl + Mouse Hover (sul Pannello Laterale):</b> Sneak Peek (Anteprima rapida del file).</li>
    </ul>
    """
