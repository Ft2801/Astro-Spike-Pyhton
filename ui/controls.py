from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QSlider, QScrollArea, QCheckBox, QGroupBox, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from core.types import SpikeConfig

class SliderControl(QWidget):
    value_changed = pyqtSignal(float)

    def __init__(self, label: str, min_val: float, max_val: float, step: float, initial: float, unit: str = ""):
        super().__init__()
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.unit = unit
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(2)
        
        header = QHBoxLayout()
        self.label = QLabel(label)
        self.value_label = QLabel(f"{initial:.2f}{unit}")
        header.addWidget(self.label)
        header.addStretch()
        header.addWidget(self.value_label)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        # Map float to int range 0-1000 for precision
        self.slider.setRange(0, 1000)
        self.slider.setValue(self._float_to_int(initial))
        self.slider.valueChanged.connect(self._on_slider_change)
        
        layout.addLayout(header)
        layout.addWidget(self.slider)
        
    def _float_to_int(self, val: float) -> int:
        ratio = (val - self.min_val) / (self.max_val - self.min_val)
        return int(ratio * 1000)
        
    def _int_to_float(self, val: int) -> float:
        ratio = val / 1000.0
        return self.min_val + ratio * (self.max_val - self.min_val)
        
    def _on_slider_change(self, val: int):
        f_val = self._int_to_float(val)
        # Snap to step
        if self.step > 0:
            f_val = round(f_val / self.step) * self.step
            
        self.value_label.setText(f"{f_val:.2f}{self.unit}")
        self.value_changed.emit(f_val)
        
    def set_value(self, val: float):
        self.slider.blockSignals(True)
        self.slider.setValue(self._float_to_int(val))
        self.value_label.setText(f"{val:.2f}{self.unit}")
        self.slider.blockSignals(False)

class ControlPanel(QWidget):
    config_changed = pyqtSignal(SpikeConfig)
    reset_requested = pyqtSignal()

    def __init__(self, config: SpikeConfig):
        super().__init__()
        self.config = config
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header with Reset
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(10, 10, 10, 0)
        
        lbl_title = QLabel("PARAMETERS")
        lbl_title.setStyleSheet("font-weight: bold; color: #888; letter-spacing: 1px;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        
        btn_reset = QPushButton("↺ Reset")
        btn_reset.setToolTip("Reset to Defaults")
        btn_reset.setStyleSheet("background: #333; border: 1px solid #555; padding: 4px 8px; font-size: 11px;")
        btn_reset.clicked.connect(self.reset_requested.emit)
        header_layout.addWidget(btn_reset)
        
        main_layout.addLayout(header_layout)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.content = QWidget()
        self.layout = QVBoxLayout(self.content)
        self.layout.setSpacing(15)
        
        self._build_controls()
        
        self.scroll.setWidget(self.content)
        main_layout.addWidget(self.scroll)

    def _build_controls(self):
        # Clear existing controls if any
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Detection
        self._add_group("Detection", [
            ("Threshold", 1, 100, 1, self.config.threshold, "threshold", ""),
            ("Quantity Limit %", 0, 100, 1, self.config.star_amount, "star_amount", "%"),
            ("Min Star Size", 0, 100, 1, self.config.min_star_size, "min_star_size", ""),
            ("Max Star Size", 0, 100, 1, self.config.max_star_size, "max_star_size", "")
        ])
        
        # Geometry
        self._add_group("Geometry", [
            ("Global Scale", 0.2, 3.0, 0.1, self.config.global_scale, "global_scale", ""),
            ("Points", 2, 8, 1, self.config.quantity, "quantity", ""),
            ("Length", 10, 1500, 10, self.config.length, "length", ""),
            ("Angle", 0, 180, 1, self.config.angle, "angle", "°"),
            ("Thickness", 0.1, 5.0, 0.1, self.config.spike_width, "spike_width", "")
        ])
        
        # Appearance
        self._add_group("Appearance", [
            ("Intensity", 0, 1.0, 0.05, self.config.intensity, "intensity", ""),
            ("Color Saturation", 0, 2.0, 0.05, self.config.color_saturation, "color_saturation", ""),
            ("Hue Shift", -180, 180, 1, self.config.hue_shift, "hue_shift", "°")
        ])
        
        # Halo
        halo_group = QGroupBox("Star Halo / Rings")
        halo_layout = QVBoxLayout()
        
        self.halo_check = QCheckBox("Enable Halo")
        self.halo_check.setChecked(self.config.enable_halo)
        self.halo_check.toggled.connect(lambda c: self._update_config("enable_halo", c))
        halo_layout.addWidget(self.halo_check)
        
        self._add_slider(halo_layout, "Intensity", 0, 1.0, 0.05, self.config.halo_intensity, "halo_intensity", "")
        self._add_slider(halo_layout, "Radius", 0.1, 5.0, 0.1, self.config.halo_scale, "halo_scale", "")
        self._add_slider(halo_layout, "Width", 0.2, 10.0, 0.2, self.config.halo_width, "halo_width", "")
        self._add_slider(halo_layout, "Blur", 0, 10.0, 0.1, self.config.halo_blur, "halo_blur", "")
        self._add_slider(halo_layout, "Saturation", 0, 3.0, 0.1, self.config.halo_saturation, "halo_saturation", "")
        
        halo_group.setLayout(halo_layout)
        self.layout.addWidget(halo_group)
        
        # Secondary Spikes
        self._add_group("Secondary Spikes", [
            ("Intensity", 0, 1.0, 0.05, self.config.secondary_intensity, "secondary_intensity", ""),
            ("Length", 0, 500, 10, self.config.secondary_length, "secondary_length", ""),
            ("Offset Angle", 0, 90, 1, self.config.secondary_offset, "secondary_offset", "°")
        ])
        
        # Soft Flare
        self._add_group("Soft Flare", [
            ("Glow Intensity", 0, 3.0, 0.05, self.config.soft_flare_intensity, "soft_flare_intensity", ""),
            ("Glow Size", 0, 200, 5, self.config.soft_flare_size, "soft_flare_size", "")
        ])
        
        # Spectral
        spectral_group = QGroupBox("Spectral Effects")
        spectral_layout = QVBoxLayout()
        
        self.rainbow_check = QCheckBox("Enable Rainbow FX")
        self.rainbow_check.setChecked(self.config.enable_rainbow)
        self.rainbow_check.toggled.connect(lambda c: self._update_config("enable_rainbow", c))
        spectral_layout.addWidget(self.rainbow_check)
        
        # Removed Spike Diffraction toggle as requested
        
        self._add_slider(spectral_layout, "Intensity", 0, 1.0, 0.05, self.config.rainbow_spike_intensity, "rainbow_spike_intensity", "")
        self._add_slider(spectral_layout, "Frequency", 0.1, 3.0, 0.1, self.config.rainbow_spike_frequency, "rainbow_spike_frequency", "")
        self._add_slider(spectral_layout, "Coverage", 0.1, 1.0, 0.1, self.config.rainbow_spike_length, "rainbow_spike_length", "")
        
        spectral_group.setLayout(spectral_layout)
        self.layout.addWidget(spectral_group)
        
        self.layout.addStretch()

    def _add_group(self, title, sliders):
        group = QGroupBox(title)
        layout = QVBoxLayout()
        for label, min_v, max_v, step, init, key, unit in sliders:
            self._add_slider(layout, label, min_v, max_v, step, init, key, unit)
        group.setLayout(layout)
        self.layout.addWidget(group)

    def _add_slider(self, layout, label, min_v, max_v, step, init, key, unit):
        slider = SliderControl(label, min_v, max_v, step, init, unit)
        slider.value_changed.connect(lambda v, k=key: self._update_config(k, v))
        layout.addWidget(slider)

    def _update_config(self, key, value):
        setattr(self.config, key, value)
        self.config_changed.emit(self.config)

    def set_config(self, config: SpikeConfig):
        self.config = config
        self._build_controls()
