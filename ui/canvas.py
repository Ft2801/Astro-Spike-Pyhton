from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPainter, QImage, QPaintEvent, QMouseEvent, QWheelEvent, QColor
from core.types import SpikeConfig, Star
from core.renderer import Renderer
from typing import List, Optional

class CanvasPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.image: Optional[QImage] = None
        self.stars: List[Star] = []
        self.config: Optional[SpikeConfig] = None
        self.renderer = Renderer()
        
        # View State
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        
        self.is_dragging = False
        self.last_mouse_pos = QPointF()

    def set_image(self, image: QImage):
        self.image = image
        self.fit_to_view()
        self.update()

    def set_stars(self, stars: List[Star]):
        self.stars = stars
        self.update()

    def set_config(self, config: SpikeConfig):
        self.config = config
        self.update()

    def fit_to_view(self):
        if not self.image:
            return
        
        # Calculate scale to fit
        w_ratio = self.width() / self.image.width()
        h_ratio = self.height() / self.image.height()
        self.scale = min(w_ratio, h_ratio) * 0.9
        
        self.center_image()

    def zoom_in(self):
        self.scale *= 1.2
        self.center_image()
        
    def zoom_out(self):
        self.scale /= 1.2
        self.center_image()

    def center_image(self):
        if not self.image:
            return
        # Center based on current scale
        self.offset_x = (self.width() - self.image.width() * self.scale) / 2
        self.offset_y = (self.height() - self.image.height() * self.scale) / 2
        self.update()

    def resizeEvent(self, event):
        # Re-center on resize if not manually panned (optional, but good for "fit" feel)
        # For now, just re-center to keep it looking good
        if self.image:
             self.center_image()
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 10, 12)) # Dark background
        
        if not self.image:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Image Loaded")
            return

        painter.save()
        painter.translate(self.offset_x, self.offset_y)
        painter.scale(self.scale, self.scale)
        
        # Draw Background Image
        target_rect = QRectF(0, 0, self.image.width(), self.image.height())
        painter.drawImage(target_rect, self.image)
        
        # Render Effects
        if self.config:
            self.renderer.render(painter, self.image.width(), self.image.height(), self.stars, self.config)
            
        painter.restore()
        
        # Debug Info
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(10, 20, f"Zoom: {self.scale*100:.0f}% Stars: {len(self.stars)}")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.position()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging:
            delta = event.position() - self.last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.last_mouse_pos = event.position()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False

    def wheelEvent(self, event: QWheelEvent):
        zoom_sensitivity = 0.001
        delta = event.angleDelta().y() * zoom_sensitivity
        
        old_scale = self.scale
        new_scale = max(0.05, min(20.0, self.scale * (1 + delta)))
        
        # Zoom towards mouse cursor
        mouse_pos = event.position()
        
        # Calculate mouse pos relative to image
        # screen_x = offset_x + img_x * scale
        # img_x = (screen_x - offset_x) / scale
        
        rel_x = (mouse_pos.x() - self.offset_x) / old_scale
        rel_y = (mouse_pos.y() - self.offset_y) / old_scale
        
        self.offset_x = mouse_pos.x() - rel_x * new_scale
        self.offset_y = mouse_pos.y() - rel_y * new_scale
        self.scale = new_scale
        
        self.update()
