import sys
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QPushButton, QFileDialog, QLabel, QSlider)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter
from PIL import Image

from core.types import DEFAULT_CONFIG, SpikeConfig, Star, ToolMode
from core.detection import detect_stars
from ui.controls import ControlPanel
from ui.canvas import CanvasPreview

class StarDetectionThread(QThread):
    stars_detected = pyqtSignal(list)

    def __init__(self, image_data, threshold):
        super().__init__()
        self.image_data = image_data
        self.threshold = threshold

    def run(self):
        stars = detect_stars(self.image_data, self.threshold)
        self.stars_detected.emit(stars)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AstroSpike Python")
        self.resize(1200, 800)
        
        self.config = DEFAULT_CONFIG
        self.image_data = None # NumPy array
        self.qimage = None
        self.thread = None
        
        # Tool state
        self.tool_mode = ToolMode.NONE
        self.star_input_radius = 4.0
        self.eraser_input_size = 20.0
        
        # History management for undo/redo
        self.history: list[list[Star]] = []
        self.history_index = -1
        
        # Debounce timer for detection
        self.detect_timer = QTimer()
        self.detect_timer.setSingleShot(True)
        self.detect_timer.setInterval(200) # 200ms debounce
        self.detect_timer.timeout.connect(self.detect_stars)
        
        self._init_ui()
        
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout (Horizontal: Toolbar/Canvas | Controls)
        # Actually, standard is Top Toolbar, then Splitter or HBox
        
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # Top Toolbar
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(50)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)
        top_layout.setSpacing(15)
        
        # File Operations
        btn_load = QPushButton("📂 Load")
        btn_load.setToolTip("Load Image")
        btn_load.clicked.connect(self.load_image)
        
        btn_save = QPushButton("💾 Save")
        btn_save.setToolTip("Save Image")
        btn_save.clicked.connect(self.save_image)
        
        top_layout.addWidget(btn_load)
        top_layout.addWidget(btn_save)
        
        # Separator
        line1 = QWidget()
        line1.setFixedWidth(1)
        line1.setStyleSheet("background: #444;")
        top_layout.addWidget(line1)
        
        # Edit Tools (Undo/Redo)
        self.btn_undo = QPushButton("↩️ Undo")
        self.btn_undo.setToolTip("Undo (Ctrl+Z)")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_undo.setEnabled(False)
        
        self.btn_redo = QPushButton("↪️ Redo")
        self.btn_redo.setToolTip("Redo (Ctrl+Y)")
        self.btn_redo.clicked.connect(self.redo)
        self.btn_redo.setEnabled(False)
        
        top_layout.addWidget(self.btn_undo)
        top_layout.addWidget(self.btn_redo)
        
        # Separator
        line2 = QWidget()
        line2.setFixedWidth(1)
        line2.setStyleSheet("background: #444;")
        top_layout.addWidget(line2)
        
        # Brushes / Tools
        lbl_tools = QLabel("Tools:")
        lbl_tools.setStyleSheet("color: #888; font-weight: bold;")
        top_layout.addWidget(lbl_tools)
        
        self.btn_pan = QPushButton("✋ Pan")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)
        self.btn_pan.setToolTip("Pan/Move (P)")
        self.btn_pan.clicked.connect(lambda: self.set_tool_mode(ToolMode.NONE))
        
        self.btn_brush_add = QPushButton("⭐ Add Star")
        self.btn_brush_add.setCheckable(True)
        self.btn_brush_add.setToolTip("Add Star Brush (B)")
        self.btn_brush_add.clicked.connect(lambda: self.set_tool_mode(ToolMode.ADD))
        
        self.btn_eraser = QPushButton("🧹 Eraser")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.setToolTip("Eraser (E)")
        self.btn_eraser.clicked.connect(lambda: self.set_tool_mode(ToolMode.ERASE))
        
        top_layout.addWidget(self.btn_pan)
        top_layout.addWidget(self.btn_brush_add)
        top_layout.addWidget(self.btn_eraser)
        
        # Tool Size Controls
        line_tool_sep = QWidget()
        line_tool_sep.setFixedWidth(1)
        line_tool_sep.setStyleSheet("background: #444;")
        top_layout.addWidget(line_tool_sep)
        
        lbl_star_size = QLabel("Star Size:")
        lbl_star_size.setStyleSheet("color: #888;")
        top_layout.addWidget(lbl_star_size)
        
        self.slider_star_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_star_size.setRange(1, 50)
        self.slider_star_size.setValue(int(self.star_input_radius))
        self.slider_star_size.setFixedWidth(80)
        self.slider_star_size.valueChanged.connect(self.on_star_size_changed)
        top_layout.addWidget(self.slider_star_size)
        
        self.lbl_star_size_val = QLabel(f"{self.star_input_radius:.0f}")
        self.lbl_star_size_val.setFixedWidth(25)
        top_layout.addWidget(self.lbl_star_size_val)
        
        lbl_eraser_size = QLabel("Eraser:")
        lbl_eraser_size.setStyleSheet("color: #888;")
        top_layout.addWidget(lbl_eraser_size)
        
        self.slider_eraser_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_eraser_size.setRange(5, 100)
        self.slider_eraser_size.setValue(int(self.eraser_input_size))
        self.slider_eraser_size.setFixedWidth(80)
        self.slider_eraser_size.valueChanged.connect(self.on_eraser_size_changed)
        top_layout.addWidget(self.slider_eraser_size)
        
        self.lbl_eraser_size_val = QLabel(f"{self.eraser_input_size:.0f}")
        self.lbl_eraser_size_val.setFixedWidth(25)
        top_layout.addWidget(self.lbl_eraser_size_val)
        
        # Separator
        line3 = QWidget()
        line3.setFixedWidth(1)
        line3.setStyleSheet("background: #444;")
        top_layout.addWidget(line3)
        
        # Zoom Controls
        btn_zoom_in = QPushButton("➕")
        btn_zoom_in.setToolTip("Zoom In")
        
        btn_zoom_out = QPushButton("➖")
        btn_zoom_out.setToolTip("Zoom Out")
        
        btn_fit = QPushButton("⛶ Fit")
        btn_fit.setToolTip("Fit to Screen")
        
        top_layout.addWidget(btn_zoom_in)
        top_layout.addWidget(btn_zoom_out)
        top_layout.addWidget(btn_fit)
        
        top_layout.addStretch()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #aaa;")
        top_layout.addWidget(self.status_label)
        
        root_layout.addWidget(top_bar)
        
        # Content Area (Canvas + Controls)
        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # Canvas
        self.canvas = CanvasPreview()
        self.canvas.stars_updated.connect(self.on_stars_updated)
        content_layout.addWidget(self.canvas, stretch=1)
        
        # Connect Zoom Signals (now that canvas exists)
        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        btn_fit.clicked.connect(self.canvas.fit_to_view)
        
        # Controls (Right Sidebar)
        self.controls = ControlPanel(self.config)
        self.controls.setFixedWidth(340)
        self.controls.config_changed.connect(self.on_config_changed)
        self.controls.reset_requested.connect(self.reset_config)
        
        # Container for controls to add background/border
        controls_container = QWidget()
        controls_container.setObjectName("controlsContainer")
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.controls)
        
        content_layout.addWidget(controls_container)
        
        root_layout.addWidget(content_area)
        
        # Style
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QWidget { color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
            
            #topBar { background-color: #252526; border-bottom: 1px solid #333; }
            #controlsContainer { background-color: #252526; border-left: 1px solid #333; }
            
            QPushButton { 
                background-color: transparent; 
                border: 1px solid transparent; 
                padding: 6px 12px; 
                border-radius: 4px; 
                color: #ccc;
            }
            QPushButton:hover { background-color: #3e3e42; color: white; }
            QPushButton:pressed { background-color: #007acc; color: white; }
            QPushButton:checked { background-color: #007acc; color: white; border: 1px solid #005a9e; }
            
            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #3e3e42; 
                margin-top: 16px; 
                padding-top: 16px; 
                border-radius: 4px; 
                background: #2d2d30; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left;
                left: 10px; 
                top: 0px;
                padding: 0 5px; 
                color: #007acc; 
            }
            
            QSlider::groove:horizontal { border: 1px solid #3e3e42; height: 4px; background: #1e1e1e; margin: 2px 0; border-radius: 2px; }
            QSlider::handle:horizontal { background: #007acc; border: 1px solid #007acc; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }
            QSlider::handle:horizontal:hover { background: #1f8ad2; }
            
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { border: none; background: #1e1e1e; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #424242; min-height: 20px; border-radius: 5px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

    def save_image(self):
        if self.image_data is None:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", "astrospike_output.png", "PNG Images (*.png);;JPEG Images (*.jpg)")
        if file_path:
            # Create a copy of the original image for rendering
            final_image = self.qimage.copy()
            
            # Create a painter for the final image
            painter = QPainter(final_image)
            
            # Render effects using the canvas renderer
            # We use the full resolution width/height
            self.canvas.renderer.render(painter, final_image.width(), final_image.height(), self.canvas.stars, self.config)
            
            painter.end()
            
            # Save to file
            final_image.save(file_path)
            self.status_label.setText(f"Saved to {file_path}")

    def closeEvent(self, event):
        # Ensure thread is stopped before closing
        if self.thread and self.thread.isRunning():
            self.thread.terminate() # Force stop if needed, or wait
            self.thread.wait()
        event.accept()

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.tif *.tiff)")
        if file_path:
            # Load with PIL
            pil_img = Image.open(file_path).convert('RGB')
            self.image_data = np.array(pil_img)
            
            # Convert to QImage
            height, width, channel = self.image_data.shape
            bytes_per_line = 3 * width
            self.qimage = QImage(self.image_data.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
            
            self.canvas.set_image(self.qimage)
            self.canvas.set_config(self.config)
            
            self.detect_stars()

    def detect_stars(self):
        if self.image_data is None:
            return
            
        # If thread is already running, don't kill it, just restart timer?
        # Or wait?
        if self.thread and self.thread.isRunning():
            # If running, we can't easily stop it safely without logic in the thread.
            # We'll just reschedule detection to try again later
            self.detect_timer.start(100)
            return

        self.status_label.setText("Detecting stars...")
        self.thread = StarDetectionThread(self.image_data, self.config.threshold)
        self.thread.stars_detected.connect(self.on_stars_detected)
        self.thread.start()

    def on_stars_detected(self, stars):
        self.status_label.setText(f"Found {len(stars)} stars")
        self.canvas.set_stars(stars)
        # Reset history when new detection happens
        self._reset_history(stars)

    def on_config_changed(self, config):
        if self.image_data is not None:
            # Check if thread exists to avoid AttributeError
            current_threshold = self.thread.threshold if hasattr(self, 'thread') and self.thread else -1
            
            if config.threshold != current_threshold:
                 # Threshold changed, trigger debounced detection
                 self.detect_timer.start()
             
        self.config = config
        self.canvas.set_config(config)

    def reset_config(self):
        # Create fresh default config
        self.config = SpikeConfig()
        
        # Update UI components
        self.controls.set_config(self.config)
        self.canvas.set_config(self.config)
        
        # Re-detect if needed (threshold might have changed back to default)
        if self.image_data is not None:
             self.detect_stars()
    
    # === TOOL MODE MANAGEMENT ===
    def set_tool_mode(self, mode: ToolMode):
        self.tool_mode = mode
        self.canvas.set_tool_mode(mode)
        
        # Update button states
        self.btn_pan.setChecked(mode == ToolMode.NONE)
        self.btn_brush_add.setChecked(mode == ToolMode.ADD)
        self.btn_eraser.setChecked(mode == ToolMode.ERASE)
    
    def on_star_size_changed(self, value: int):
        self.star_input_radius = float(value)
        self.lbl_star_size_val.setText(f"{value}")
        self.canvas.set_star_input_radius(self.star_input_radius)
    
    def on_eraser_size_changed(self, value: int):
        self.eraser_input_size = float(value)
        self.lbl_eraser_size_val.setText(f"{value}")
        self.canvas.set_eraser_input_size(self.eraser_input_size)
    
    # === HISTORY / UNDO / REDO ===
    def on_stars_updated(self, new_stars: list, push_history: bool):
        """Called when canvas updates stars (brush/eraser actions)"""
        self.canvas.stars = new_stars
        
        if push_history:
            # Truncate any redo history
            self.history = self.history[:self.history_index + 1]
            # Add new state
            self.history.append(list(new_stars))
            self.history_index += 1
        
        self._update_history_buttons()
        self.canvas.update()
    
    def _update_history_buttons(self):
        """Update enabled state of undo/redo buttons"""
        self.btn_undo.setEnabled(self.history_index > 0)
        self.btn_redo.setEnabled(self.history_index < len(self.history) - 1)
    
    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            prev_stars = self.history[self.history_index]
            self.canvas.stars = list(prev_stars)
            self.canvas.update()
            self._update_history_buttons()
    
    def redo(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            next_stars = self.history[self.history_index]
            self.canvas.stars = list(next_stars)
            self.canvas.update()
            self._update_history_buttons()
    
    def _reset_history(self, initial_stars: list):
        """Reset history when new image is loaded or detection resets"""
        self.history = [list(initial_stars)]
        self.history_index = 0
        self._update_history_buttons()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
