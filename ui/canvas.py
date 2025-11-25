from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPainter, QImage, QPaintEvent, QMouseEvent, QWheelEvent, QColor, QPen, QBrush
from core.types import SpikeConfig, Star, Color, ToolMode
from core.renderer import Renderer
from typing import List, Optional
import math

class CanvasPreview(QWidget):
    # Signals for star updates (to sync with history in main window)
    stars_updated = pyqtSignal(list, bool)  # (new_stars, push_to_history)
    
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
        
        # Pan drag state
        self.is_dragging = False
        self.last_mouse_pos = QPointF()
        
        # Tool State
        self.tool_mode: ToolMode = ToolMode.NONE
        self.star_input_radius: float = 4.0  # Default star radius for brush tool
        self.eraser_input_size: float = 20.0  # Default eraser radius
        
        # Cursor tracking for preview circle
        self.cursor_pos = QPointF(-9999, -9999)  # Screen coords
        self.is_erasing = False  # Track if we're dragging eraser

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
    
    def set_tool_mode(self, mode: ToolMode):
        self.tool_mode = mode
        # Update cursor style
        if mode == ToolMode.NONE:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.BlankCursor)  # Hide cursor, we draw our own
        self.update()
    
    def set_star_input_radius(self, radius: float):
        self.star_input_radius = radius
        self.update()
    
    def set_eraser_input_size(self, size: float):
        self.eraser_input_size = size
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
        if self.image:
            self.center_image()
        super().resizeEvent(event)
    
    def _screen_to_image(self, screen_pos: QPointF) -> QPointF:
        """Convert screen coordinates to image coordinates"""
        img_x = (screen_pos.x() - self.offset_x) / self.scale
        img_y = (screen_pos.y() - self.offset_y) / self.scale
        return QPointF(img_x, img_y)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(10, 10, 12))  # Dark background
        
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
        
        # Draw Tool Cursor Preview (in screen coords)
        if self.tool_mode != ToolMode.NONE and self.cursor_pos.x() > -9000:
            self._draw_cursor_preview(painter)
        
        # Info overlay
        painter.setPen(QColor(200, 200, 200))
        mode_str = self.tool_mode.value.upper() if self.tool_mode else "NONE"
        painter.drawText(10, 20, f"Zoom: {self.scale*100:.0f}% | Stars: {len(self.stars)} | Tool: {mode_str}")

    def _draw_cursor_preview(self, painter: QPainter):
        """Draw the circular cursor preview for brush/eraser tools"""
        if self.tool_mode == ToolMode.ADD:
            # Star brush preview
            preview_radius = self.star_input_radius * self.scale
            color = QColor(56, 189, 248, 150)  # Sky blue
            border_color = QColor(56, 189, 248, 255)
        elif self.tool_mode == ToolMode.ERASE:
            # Eraser preview
            preview_radius = self.eraser_input_size * self.scale
            color = QColor(248, 113, 113, 80)  # Red-ish
            border_color = QColor(248, 113, 113, 200)
        else:
            return
        
        # Ensure minimum visible size
        preview_radius = max(4, preview_radius)
        
        # Draw filled circle with border
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(border_color, 2))
        painter.drawEllipse(self.cursor_pos, preview_radius, preview_radius)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.tool_mode == ToolMode.NONE:
                # Pan mode
                self.is_dragging = True
                self.last_mouse_pos = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            elif self.tool_mode == ToolMode.ADD:
                # Add star at click position
                self._add_star_at(event.position())
            elif self.tool_mode == ToolMode.ERASE:
                # Start erasing
                self.is_erasing = True
                self._erase_stars_at(event.position(), push_history=False)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Always track cursor for preview
        self.cursor_pos = event.position()
        
        if self.is_dragging and self.tool_mode == ToolMode.NONE:
            # Pan
            delta = event.position() - self.last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.last_mouse_pos = event.position()
        elif self.is_erasing and self.tool_mode == ToolMode.ERASE:
            # Continue erasing (don't push to history during drag)
            self._erase_stars_at(event.position(), push_history=False)
        
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_dragging and self.tool_mode == ToolMode.NONE:
                self.is_dragging = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.is_erasing and self.tool_mode == ToolMode.ERASE:
                # Finished erasing, push final state to history
                self.is_erasing = False
                self.stars_updated.emit(list(self.stars), True)

    def leaveEvent(self, event):
        """Hide cursor preview when mouse leaves canvas"""
        self.cursor_pos = QPointF(-9999, -9999)
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        zoom_sensitivity = 0.001
        delta = event.angleDelta().y() * zoom_sensitivity
        
        old_scale = self.scale
        new_scale = max(0.05, min(20.0, self.scale * (1 + delta)))
        
        # Zoom towards mouse cursor
        mouse_pos = event.position()
        
        rel_x = (mouse_pos.x() - self.offset_x) / old_scale
        rel_y = (mouse_pos.y() - self.offset_y) / old_scale
        
        self.offset_x = mouse_pos.x() - rel_x * new_scale
        self.offset_y = mouse_pos.y() - rel_y * new_scale
        self.scale = new_scale
        
        self.update()

    def _add_star_at(self, screen_pos: QPointF):
        """Add a new star at the given screen position"""
        if not self.image:
            return
        
        img_pos = self._screen_to_image(screen_pos)
        
        # Check bounds
        if img_pos.x() < 0 or img_pos.x() >= self.image.width():
            return
        if img_pos.y() < 0 or img_pos.y() >= self.image.height():
            return
        
        # Create new star with white color (user-added stars are neutral)
        new_star = Star(
            x=img_pos.x(),
            y=img_pos.y(),
            brightness=1.0,
            radius=self.star_input_radius,
            color=Color(255, 255, 255)
        )
        
        # Add to list and emit signal with history push
        new_stars = list(self.stars) + [new_star]
        self.stars = new_stars
        self.stars_updated.emit(new_stars, True)
        self.update()

    def _erase_stars_at(self, screen_pos: QPointF, push_history: bool = False):
        """Remove stars within eraser radius of the given screen position"""
        if not self.image:
            return
        
        img_pos = self._screen_to_image(screen_pos)
        erase_radius = self.eraser_input_size
        erase_radius_sq = erase_radius * erase_radius
        
        initial_count = len(self.stars)
        
        # Filter out stars within eraser radius
        filtered_stars = [
            star for star in self.stars
            if (star.x - img_pos.x()) ** 2 + (star.y - img_pos.y()) ** 2 > erase_radius_sq
        ]
        
        if len(filtered_stars) != initial_count:
            self.stars = filtered_stars
            self.stars_updated.emit(filtered_stars, push_history)
            self.update()
