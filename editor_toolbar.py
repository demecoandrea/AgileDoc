import os
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, 
                             QComboBox, QSpinBox, QColorDialog, QFrame, QHBoxLayout, 
                             QGraphicsDropShadowEffect, QSizePolicy, QSlider, QCheckBox)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF
from PyQt6.QtGui import QColor, QPainter

# Importiamo le costanti centralizzate
from const_and_resources import Colors, Styles

# Importiamo la finestra modale del manager delle firme
from signature_manager import SignatureManagerDialog

def get_custom_colors():
    """Returns a list of 16 hex strings representing the current custom colors in QColorDialog."""
    colors = []
    for i in range(16):
        c = QColorDialog.customColor(i)
        colors.append(c.name(QColor.NameFormat.HexArgb))
    return colors

def set_custom_colors(color_strings):
    """Sets the custom colors in QColorDialog from a list of hex strings."""
    if not color_strings:
        return
    for i, hex_str in enumerate(color_strings):
        if i < 16:
            QColorDialog.setCustomColor(i, QColor(hex_str))

class ColorButton(QPushButton):
    """Bottone quadrato che mostra il colore corrente e apre un color picker (senza alpha)."""
    color_changed = pyqtSignal(QColor)

    def __init__(self, color=Colors.HIGHLIGHT_YELLOW):
        super().__init__()
        self._color = QColor(color.red(), color.green(), color.blue())
        self.setFixedSize(14, 14)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self.choose_color)
        self._update_display()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, c):
        self._color = QColor(c.red(), c.green(), c.blue())
        self._update_display()

    def _update_display(self):
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color.name()}; "
            f"border: 1px solid #888; border-radius: 2px; "
            f"min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px; "
            f"padding: 0; }}"
            f"QPushButton:hover {{ border: 1px solid #fff; }}"
        )

    def choose_color(self):
        color = QColorDialog.getColor(self._color, self.window(), "Scegli Colore")
        if color.isValid():
            self._color = color
            self._update_display()
            self.color_changed.emit(self._color)
            if self.window() and hasattr(self.window(), 'save_config'):
                self.window().save_config()

class ColorRow(QWidget):
    """Riga compatta: etichetta | bottone colore | slider opacità."""
    color_changed = pyqtSignal(QColor)

    def __init__(self, label_text, default_color=Colors.BLACK, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel(label_text)
        lbl.setFixedWidth(38)
        layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_color = ColorButton(default_color)
        self.btn_color.color_changed.connect(self._emit_combined)
        layout.addWidget(self.btn_color, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.slider_alpha = QSlider(Qt.Orientation.Horizontal)
        self.slider_alpha.setRange(0, 100)
        self.slider_alpha.setValue(round(default_color.alpha() / 255 * 100))
        self.slider_alpha.setToolTip("Opacità (0 = trasparente, 100 = opaco)")
        self.slider_alpha.valueChanged.connect(self._emit_combined)
        layout.addWidget(self.slider_alpha, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _emit_combined(self, *args):
        self.color_changed.emit(self.get_color())

    def get_color(self):
        c = self.btn_color.color
        alpha = round(self.slider_alpha.value() / 100 * 255)
        return QColor(c.red(), c.green(), c.blue(), alpha)

    def set_color(self, color):
        self.btn_color.blockSignals(True)
        self.slider_alpha.blockSignals(True)
        self.btn_color.color = color
        self.slider_alpha.setValue(round(color.alpha() / 255 * 100))
        self.btn_color.blockSignals(False)
        self.slider_alpha.blockSignals(False)

class ExclusiveButtonGroup(QWidget):
    """Gruppo di bottoni mutuamente esclusivi (radio-like)."""
    value_changed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self._buttons = {}
        self._current = None

        for icon, value, tooltip in options:
            btn = QPushButton(icon)
            btn.setCheckable(True)
            btn.setFixedSize(24, 22)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(
                "QPushButton { font-size: 12px; padding: 0; }"
                "QPushButton:checked { background-color: #0078d7; color: white; border: 1px solid #005a9e; }"
            )
            btn.clicked.connect(lambda checked, v=value: self.set_value(v))
            self._buttons[value] = btn
            layout.addWidget(btn)

        if options:
            self.set_value(options[0][1], emit=False)

    def set_value(self, value, emit=True):
        self._current = value
        for v, btn in self._buttons.items():
            btn.blockSignals(True)
            btn.setChecked(v == value)
            btn.blockSignals(False)
        if emit:
            self.value_changed.emit(value)

    def get_value(self):
        return self._current

class ToolButton(QPushButton):
    """Bottone strumento con mini indicatore hard/soft (toggle) sulla sinistra."""
    toggle_clicked = pyqtSignal(str) 

    TOGGLE_W = 20
    TOGGLE_H = 10
    TOGGLE_MARGIN = 6

    def __init__(self, text, tool_id, parent=None):
        super().__init__(text, parent)
        self.tool_id = tool_id
        self._is_hard = False
        self.setCheckable(True)
        self.setStyleSheet(
            "QPushButton { padding-left: 28px; text-align: left; }"
            "QPushButton:checked { padding-left: 28px; text-align: left; }"
        )

    @property
    def is_hard(self):
        return self._is_hard

    @is_hard.setter
    def is_hard(self, value):
        self._is_hard = value
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isChecked():
            toggle_x = self.TOGGLE_MARGIN
            toggle_y = (self.height() - self.TOGGLE_H) // 2
            if (toggle_x <= event.pos().x() <= toggle_x + self.TOGGLE_W and 
                toggle_y <= event.pos().y() <= toggle_y + self.TOGGLE_H):
                self.toggle_clicked.emit(self.tool_id)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isChecked():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        
        x = self.TOGGLE_MARGIN
        y = (self.height() - self.TOGGLE_H) // 2
        rect = QRectF(x, y, self.TOGGLE_W, self.TOGGLE_H)
        
        if self._is_hard:
            p.setBrush(QColor(Colors.HEX_SUCCESS))
        else:
            p.setBrush(QColor(Colors.HEX_BORDER))
        
        p.drawRoundedRect(rect, self.TOGGLE_H / 2, self.TOGGLE_H / 2)
        p.setBrush(Colors.WHITE)
        circle_d = self.TOGGLE_H - 4
        if self._is_hard:
            p.drawEllipse(int(x + self.TOGGLE_W - self.TOGGLE_H + 2), int(y + 2), circle_d, circle_d)
        else:
            p.drawEllipse(int(x + 2), int(y + 2), circle_d, circle_d)
        p.end()

class EditorToolbar(QFrame):
    tool_changed = pyqtSignal(str) 
    property_changed = pyqtSignal(str, object) 
    action_requested = pyqtSignal(str)
    dock_mode_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(Styles.TOOLBAR_STYLE)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        self.setFixedWidth(220)
        self._docked_mode = False
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(6)
        
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)
        
        lbl_title = QLabel("MODALITÀ EDITOR")
        lbl_title.setStyleSheet(f"font-weight: bold; color: white; font-size: 13px; border: 1px solid {Colors.HEX_ACCENT}; border-radius: 4px; padding: 4px;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(lbl_title, stretch=1)
        
        self.btn_dock_toggle = QPushButton("📌")
        self.btn_dock_toggle.setFixedSize(24, 24)
        self.btn_dock_toggle.setCheckable(True)
        self.btn_dock_toggle.setToolTip("Aggancia/Sgancia il pannello editor")
        self.btn_dock_toggle.setStyleSheet(
            "QPushButton { font-size: 14px; padding: 0; background: transparent; border: 1px solid #555; border-radius: 3px; }"
            "QPushButton:checked { background-color: #0078d7; border: 1px solid #005a9e; }"
            "QPushButton:hover { background-color: #505050; }"
        )
        self.btn_dock_toggle.toggled.connect(lambda checked: self.dock_mode_toggled.emit(checked))
        title_row.addWidget(self.btn_dock_toggle)
        
        self.main_layout.addLayout(title_row)
        
        self.current_tool = "select"
        self._hard_tool = "select"
        self.tools_buttons = {}
        self.subgroups = {}
        
        self.controls = {}
        self.btn_select = self.create_tool_button("↖️ Selezione", "select")
        
        self.btn_adv_adj = QPushButton("🔍 Regolazione Avanzata")
        self.btn_adv_adj.setStyleSheet(
            "QPushButton { padding-left: 28px; text-align: left; }"
            "QPushButton:disabled { padding-left: 28px; text-align: left; }"
        )
        self.btn_adv_adj.clicked.connect(lambda: self.action_requested.emit("advanced_adjustment"))
        self.btn_adv_adj.setEnabled(False)
        self.main_layout.addWidget(self.btn_adv_adj)
        
        self.btn_freetext = self.create_tool_button("⌨️ Macchina da scrivere", "freetext")
        self.subgroups["freetext"] = self.create_text_subgroup("freetext", is_box=False)

        self.btn_textbox = self.create_tool_button("📝 Casella di Testo", "textbox")
        self.subgroups["textbox"] = self.create_text_subgroup("textbox", is_box=True)
        
        self.btn_marker = self.create_tool_button("🖊️ Pennarello", "marker")
        self.subgroups["marker"] = self.create_drawing_subgroup("marker")
        
        self.btn_highlighter = self.create_tool_button("🖍️ Evidenziatore", "highlighter")
        self.subgroups["highlighter"] = self.create_drawing_subgroup("highlighter")
        
        self.btn_signature = self.create_tool_button("✍️ Firma", "signature")
        self.subgroups["signature"] = self.create_signature_subgroup()
        
        self.main_layout.addStretch()
        
        self.set_active_tool("select")

    def create_tool_button(self, text, tool_id):
        btn = ToolButton(text, tool_id)
        btn.clicked.connect(lambda checked, t=tool_id: self.set_active_tool(t))
        btn.toggle_clicked.connect(self._on_toggle_clicked)
        self.main_layout.addWidget(btn)
        self.tools_buttons[tool_id] = btn
        return btn

    def _on_toggle_clicked(self, tool_id):
        btn = self.tools_buttons.get(tool_id)
        if not btn: return
        if btn.is_hard:
            self.set_active_tool("select")
        else:
            self.set_active_tool(tool_id)

    def create_text_subgroup(self, tid, is_box=False):
        w = QWidget()
        w.setObjectName("subgroup")
        l = QVBoxLayout(w)
        l.setContentsMargins(5, 4, 0, 5)
        l.setSpacing(3)

        default_border = Colors.BLACK if is_box else Colors.TRANSPARENT
        row_border = ColorRow("Bordo", default_border)
        row_border.color_changed.connect(lambda c, t=tid: self.property_changed.emit(f"{t}_border_color", c))
        self.controls[f"{tid}_border_color"] = row_border
        l.addWidget(row_border)

        default_bg = Colors.TEXT_DEFAULT_BG if is_box else Colors.FREETEXT_DEFAULT_BG
        row_bg = ColorRow("Sfondo", default_bg)
        row_bg.color_changed.connect(lambda c, t=tid: self.property_changed.emit(f"{t}_bg_color", c))
        self.controls[f"{tid}_bg_color"] = row_bg
        l.addWidget(row_bg)

        row_text = ColorRow("Testo", Colors.BLACK)
        row_text.color_changed.connect(lambda c, t=tid: self.property_changed.emit(f"{t}_color", c))
        self.controls[f"{tid}_color"] = row_text
        l.addWidget(row_text)

        font_row = QHBoxLayout()
        font_row.setContentsMargins(0, 0, 0, 0)
        font_row.setSpacing(3)

        cmb_font = QComboBox()
        cmb_font.addItems(["Helvetica", "Arial", "Times", "Courier", "Calibri", "Comic Sans MS", "Verdana", "Tahoma"])
        cmb_font.currentTextChanged.connect(lambda t, tid=tid: self.property_changed.emit(f"{tid}_font_family", t))
        self.controls[f"{tid}_font_family"] = cmb_font

        spn_size = QSpinBox()
        spn_size.setRange(6, 72)
        spn_size.setValue(12)
        spn_size.setFixedWidth(48)
        spn_size.valueChanged.connect(lambda v, t=tid: self.property_changed.emit(f"{t}_font_size", v))
        self.controls[f"{tid}_font_size"] = spn_size

        font_row.addWidget(cmb_font, stretch=1)
        font_row.addWidget(spn_size)
        l.addLayout(font_row)

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.setSpacing(2)

        btn_bold = QPushButton("G")
        btn_bold.setCheckable(True)
        btn_bold.setFixedSize(28, 22)
        btn_bold.setToolTip("Grassetto")
        btn_bold.setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 12px; padding: 0; }"
            "QPushButton:checked { background-color: #0078d7; color: white; border: 1px solid #005a9e; }")
        btn_bold.toggled.connect(lambda checked, t=tid: self.property_changed.emit(f"{t}_font_bold", checked))
        self.controls[f"{tid}_font_bold"] = btn_bold
        style_row.addWidget(btn_bold)

        btn_italic = QPushButton("C")
        btn_italic.setCheckable(True)
        btn_italic.setFixedSize(28, 22)
        btn_italic.setToolTip("Corsivo")
        btn_italic.setStyleSheet(
            "QPushButton { font-style: italic; font-size: 12px; padding: 0; }"
            "QPushButton:checked { background-color: #0078d7; color: white; border: 1px solid #005a9e; }")
        btn_italic.toggled.connect(lambda checked, t=tid: self.property_changed.emit(f"{t}_font_italic", checked))
        self.controls[f"{tid}_font_italic"] = btn_italic
        style_row.addWidget(btn_italic)

        btn_underline = QPushButton("S")
        btn_underline.setCheckable(True)
        btn_underline.setFixedSize(28, 22)
        btn_underline.setToolTip("Sottolineato")
        btn_underline.setStyleSheet(
            "QPushButton { text-decoration: underline; font-size: 12px; padding: 0; }"
            "QPushButton:checked { background-color: #0078d7; color: white; border: 1px solid #005a9e; }")
        btn_underline.toggled.connect(lambda checked, t=tid: self.property_changed.emit(f"{t}_font_underline", checked))
        self.controls[f"{tid}_font_underline"] = btn_underline
        style_row.addWidget(btn_underline)

        if is_box:
            chk_wrap = QCheckBox("A capo")
            chk_wrap.setStyleSheet("color: #ccc; font-size: 10px;")
            chk_wrap.setChecked(True)
            chk_wrap.stateChanged.connect(lambda state, tid=tid: self.property_changed.emit(f"{tid}_wrap", bool(state)))
            self.controls[f"{tid}_wrap"] = chk_wrap
            style_row.addWidget(chk_wrap)

        style_row.addStretch()
        l.addLayout(style_row)

        if is_box:
            align_row = QHBoxLayout()
            align_row.setContentsMargins(0, 2, 0, 0)
            align_row.setSpacing(6)

            h_align = ExclusiveButtonGroup([
                ("←", "Sinistra", "Allinea a sinistra"),
                ("↔", "Centro", "Centra orizzontalmente"),
                ("→", "Destra", "Allinea a destra"),
            ])
            h_align.value_changed.connect(lambda v, t=tid: self.property_changed.emit(f"{t}_align_h", v))
            self.controls[f"{tid}_align_h"] = h_align

            v_align = ExclusiveButtonGroup([
                ("↑", "Alto", "Allinea in alto"),
                ("↕", "Centro", "Centra verticalmente"),
                ("↓", "Basso", "Allinea in basso"),
            ])
            v_align.value_changed.connect(lambda v, t=tid: self.property_changed.emit(f"{t}_align_v", v))
            self.controls[f"{tid}_align_v"] = v_align

            align_row.addWidget(h_align)
            align_row.addWidget(v_align)
            align_row.addStretch()
            l.addLayout(align_row)

        self.main_layout.addWidget(w)
        return w

    def create_drawing_subgroup(self, tool_id):
        w = QWidget()
        w.setObjectName("subgroup")
        l = QVBoxLayout(w)
        l.setContentsMargins(5, 4, 0, 5)
        l.setSpacing(3)

        def_color = Colors.HIGHLIGHT_YELLOW if tool_id == "highlighter" else Colors.BLACK
        row_color = ColorRow("Colore", def_color)
        row_color.color_changed.connect(lambda c, t=tool_id: self.property_changed.emit(f"{t}_color", c))
        self.controls[f"{tool_id}_color"] = row_color
        l.addWidget(row_color)

        thick_row = QHBoxLayout()
        thick_row.setContentsMargins(0, 0, 0, 0)
        thick_row.setSpacing(3)
        thick_row.addWidget(QLabel("Spessore:"))
        spn = QSpinBox()
        spn.setRange(1, 50)
        spn.setValue(10 if tool_id == "highlighter" else 2)
        spn.valueChanged.connect(lambda v, t=tool_id: self.property_changed.emit(f"{t}_thickness", v))
        self.controls[f"{tool_id}_thickness"] = spn
        thick_row.addWidget(spn)
        thick_row.addStretch()
        l.addLayout(thick_row)

        self.main_layout.addWidget(w)
        return w

    def create_signature_subgroup(self):
        w = QWidget()
        w.setObjectName("subgroup")
        l = QVBoxLayout(w)
        l.setContentsMargins(15, 0, 0, 5)
        l.setSpacing(4)
        
        combo = QComboBox()
        self.controls["signature_combo"] = combo 
        
        btn_manage = QPushButton("Gestisci Firme ⚙️")
        btn_manage.clicked.connect(self._open_signature_manager)
        
        combo.currentIndexChanged.connect(self._on_signature_combo_changed)
        
        l.addWidget(QLabel("Seleziona Firma:"))
        l.addWidget(combo)
        l.addWidget(btn_manage)
        
        self.main_layout.addWidget(w)
        self.load_signatures()
        return w

    def load_signatures(self):
        combo = self.controls.get("signature_combo")
        if combo is None: return
        
        combo.blockSignals(True)
        combo.clear()
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.conf_dir = os.path.join(base_dir, "conf") 
        json_path = os.path.join(self.conf_dir, "signatures.json")
        sig_dir = os.path.join(base_dir, "signatures")
        
        last_id = None
        last_sig_path = os.path.join(self.conf_dir, "last_sig.txt")
        if os.path.exists(last_sig_path):
            with open(last_sig_path, "r") as f: last_id = f.read().strip()
        
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    sigs = json.load(f)
                for sig_id, data in sigs.items():
                    file_path = os.path.join(sig_dir, data['filename'])
                    if os.path.exists(file_path):
                        combo.addItem(data['name'], {"path": file_path, "scale": data['scale'], "id": sig_id})
            except: pass
        
        if combo.count() == 0:
            combo.addItem("Nessuna firma salvata", None)
        else:
            if last_id:
                for i in range(combo.count()):
                    item_data = combo.itemData(i)
                    if item_data and item_data.get("id") == last_id:
                        combo.setCurrentIndex(i)
                        break
            
        combo.blockSignals(False)
        self._on_signature_combo_changed()

    def _open_signature_manager(self):
        dialog = SignatureManagerDialog(self)
        if dialog.exec(): 
            self.load_signatures()
            if dialog.selected_sig_id:
                combo = self.controls.get("signature_combo")
                if combo is not None:
                    for i in range(combo.count()):
                        sig_data = combo.itemData(i)
                        if sig_data and dialog.selected_sig_id in sig_data.get("path", ""):
                            combo.setCurrentIndex(i)
                            break

    def _on_signature_combo_changed(self):
        combo = self.controls.get("signature_combo")
        if combo is None: return
        
        data = combo.currentData()
        if data:
            sig_id = data.get("id")
            if sig_id and hasattr(self, 'conf_dir'):
                with open(os.path.join(self.conf_dir, "last_sig.txt"), "w") as f:
                    f.write(sig_id)
                    
            self.property_changed.emit("signature_path", data["path"])
            self.property_changed.emit("signature_scale", data["scale"])
        else:
            self.property_changed.emit("signature_path", None)

    def set_active_tool(self, tool_id, silent=False):
        prev_tool = self.current_tool
        self.current_tool = tool_id
        
        if not silent:
            self._hard_tool = tool_id
        
        for tid, btn in self.tools_buttons.items():
            btn.setChecked(tid == tool_id)
            btn.is_hard = (tid == self._hard_tool and btn.isChecked())
        
        if self._docked_mode:
            for tid in self.subgroups:
                self.subgroups[tid].setVisible(True)
        else:
            for tid in self.subgroups:
                self.subgroups[tid].setVisible(tid == tool_id)
            self.adjustSize()
        
        if not silent:
            self.tool_changed.emit(tool_id)

    def set_dock_mode(self, docked):
        self._docked_mode = docked
        self.btn_dock_toggle.blockSignals(True)
        self.btn_dock_toggle.setChecked(docked)
        self.btn_dock_toggle.blockSignals(False)
        
        if docked:
            self.setGraphicsEffect(None)
            self.setStyleSheet(Styles.TOOLBAR_STYLE + " QFrame { border-radius: 0; border: none; }")
            for tid in self.subgroups:
                self.subgroups[tid].setVisible(True)
        else:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(15)
            shadow.setColor(QColor(0, 0, 0, 150))
            shadow.setOffset(0, 4)
            self.setGraphicsEffect(shadow)
            self.setStyleSheet(Styles.TOOLBAR_STYLE)
            for tid in self.subgroups:
                self.subgroups[tid].setVisible(tid == self.current_tool)
            self.adjustSize()

    def update_selection_state(self, has_images_selected):
        self.btn_adv_adj.setEnabled(has_images_selected)

    def set_property_values_from_item(self, item, tool_id):
        if tool_id == "freetext":
            self._set_control_val(f"{tool_id}_border_color", item.border_color)
            self._set_control_val(f"{tool_id}_bg_color", item.bg_color)
            self._set_control_val(f"{tool_id}_color", item.defaultTextColor())
            self._set_control_val(f"{tool_id}_font_family", item.font().family())
            self._set_control_val(f"{tool_id}_font_size", item.font().pointSize())
            self._set_control_val(f"{tool_id}_font_bold", item.font().bold())
            self._set_control_val(f"{tool_id}_font_italic", item.font().italic())
            self._set_control_val(f"{tool_id}_font_underline", item.font().underline())
        elif tool_id == "textbox":
            self._set_control_val(f"{tool_id}_border_color", item.border_color)
            self._set_control_val(f"{tool_id}_bg_color", item.bg_color)
            self._set_control_val(f"{tool_id}_color", item.text_item.defaultTextColor())
            self._set_control_val(f"{tool_id}_font_family", item.text_item.font().family())
            self._set_control_val(f"{tool_id}_font_size", item.text_item.font().pointSize())
            self._set_control_val(f"{tool_id}_font_bold", item.text_item.font().bold())
            self._set_control_val(f"{tool_id}_font_italic", item.text_item.font().italic())
            self._set_control_val(f"{tool_id}_font_underline", item.text_item.font().underline())
            self._set_control_val(f"{tool_id}_align_h", item.align_h)
            self._set_control_val(f"{tool_id}_align_v", item.align_v)
            self._set_control_val(f"{tool_id}_wrap", item.wrap)
        elif tool_id in ["marker", "highlighter"]:
            self._set_control_val(f"{tool_id}_color", item.color)
            self._set_control_val(f"{tool_id}_thickness", item.thickness)

    def _set_control_val(self, key, val):
        if key not in self.controls: return
        ctrl = self.controls[key]
        if isinstance(ctrl, ColorRow):
            ctrl.set_color(val)
        elif isinstance(ctrl, ExclusiveButtonGroup):
            ctrl.set_value(val, emit=False)
        else:
            ctrl.blockSignals(True)
            if isinstance(ctrl, ColorButton):
                ctrl.color = val
            elif isinstance(ctrl, QComboBox):
                ctrl.setCurrentText(str(val))
            elif isinstance(ctrl, QSpinBox):
                ctrl.setValue(int(val))
            elif hasattr(ctrl, 'setChecked'):
                ctrl.setChecked(bool(val))
            ctrl.blockSignals(False)

    def set_property_values(self, tool_id, props):
        pass
