from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QRadialGradient, QBrush, QPen, QImage, QPainterPath
from .types import SpikeConfig, Star, Color
import math

class Renderer:
    def __init__(self):
        self.glow_sprite = self._create_glow_sprite()

    def _create_glow_sprite(self) -> QImage:
        size = 256
        image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        half = size / 2
        grad = QRadialGradient(half, half, half)
        grad.setColorAt(0, QColor(255, 255, 255, 255))
        grad.setColorAt(0.2, QColor(255, 255, 255, 100)) # 0.4 * 255
        grad.setColorAt(0.6, QColor(255, 255, 255, 13))  # 0.05 * 255
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, size, size)
        painter.end()
        return image

    def get_star_color(self, star: Star, hue_shift: float, saturation_mult: float, alpha: float) -> QColor:
        r, g, b = int(star.color.r), int(star.color.g), int(star.color.b)
        
        # RGB to HSL
        r1, g1, b1 = r / 255.0, g / 255.0, b / 255.0
        max_c = max(r1, g1, b1)
        min_c = min(r1, g1, b1)
        l = (max_c + min_c) / 2.0
        h = 0.0
        s = 0.0
        
        if max_c != min_c:
            d = max_c - min_c
            s = d / (2.0 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
            
            if max_c == r1:
                h = (g1 - b1) / d + (6.0 if g1 < b1 else 0.0)
            elif max_c == g1:
                h = (b1 - r1) / d + 2.0
            elif max_c == b1:
                h = (r1 - g1) / d + 4.0
            h /= 6.0
        else:
            # Deterministic hue for gray stars
            h = ((star.x * 0.618 + star.y * 0.382) % 1.0)

        new_h = (h * 360.0) + hue_shift
        
        # Saturation Logic
        base_saturation = max(s, 0.25)
        new_s = base_saturation * 100.0 * saturation_mult
        
        if saturation_mult > 1.5:
            extra_boost = math.pow(saturation_mult - 1.5, 1.5) * 40.0
            new_s += extra_boost
            
        # Lightness Logic
        new_l = max(l * 100.0, 40.0)
        if saturation_mult > 1.0:
            new_l = min(95.0, new_l + (saturation_mult - 1.0) * 10.0)
            
        new_l = max(65.0, min(95.0, new_l))
        
        # HSL to RGB conversion for QColor
        # QColor.fromHslF expects 0-1 range for H, S, L
        # But we calculated S > 100 which QColor might clamp or handle.
        # We need to manually convert HSL to RGB if we want S > 100 behavior,
        # but standard HSL definition caps S at 1.
        # However, the JS code produced a CSS string `hsla(...)` which browsers handle.
        # If S > 100% in CSS, it just clamps to 100% usually, unless using modern color spaces.
        # Wait, my JS logic allowed S > 100. Browsers clamp it.
        # So I should clamp S to 1.0 (100%) for QColor, OR implement the "vibrancy" by other means.
        # Actually, if S is very high, it just means pure color.
        # I will clamp S to 1.0 for QColor but maybe adjust L?
        # No, the user liked the "vibrant" look.
        # If I clamp S to 1.0, I lose the "extra boost" if it was doing anything special in browser.
        # In CSS `hsl(0, 150%, 50%)` is same as `hsl(0, 100%, 50%)`.
        
        final_s = min(1.0, new_s / 100.0)
        final_l = min(1.0, new_l / 100.0)
        final_h = (new_h % 360.0) / 360.0
        
        c = QColor.fromHslF(final_h, final_s, final_l, alpha)
        return c

    def render(self, painter: QPainter, width: int, height: int, stars: list[Star], config: SpikeConfig):
        if not stars:
            return

        limit = int(len(stars) * (config.star_amount / 100.0))
        active_stars = stars[:limit]
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        
        deg_to_rad = math.pi / 180.0
        main_angle_rad = config.angle * deg_to_rad
        sec_angle_rad = (config.angle + config.secondary_offset) * deg_to_rad
        
        # Soft Flare
        if config.soft_flare_intensity > 0:
            painter.setOpacity(1.0) # Opacity handled in drawImage? No, global alpha
            for star in active_stars:
                glow_r = (star.radius * config.soft_flare_size * 0.4 + (star.radius * 2))
                if glow_r > 2:
                    draw_size = glow_r * 2
                    opacity = config.soft_flare_intensity * 0.8 * star.brightness
                    painter.setOpacity(min(1.0, opacity))
                    # Draw centered
                    target_rect = QRectF(star.x - glow_r, star.y - glow_r, draw_size, draw_size)
                    painter.drawImage(target_rect, self.glow_sprite, QRectF(self.glow_sprite.rect()))
            painter.setOpacity(1.0)

        # Spikes & Halos
        for star in active_stars:
            radius_factor = math.pow(star.radius, 1.2)
            base_length = radius_factor * (config.length / 40.0) * config.global_scale
            thickness = max(0.5, star.radius * config.spike_width * 0.15 * config.global_scale)
            
            if base_length < 2:
                continue
                
            color = self.get_star_color(star, config.hue_shift, config.color_saturation, config.intensity)
            sec_color = self.get_star_color(star, config.hue_shift, config.color_saturation, config.secondary_intensity)
            
            # Main Spikes
            if config.intensity > 0:
                self.draw_spikes(painter, star, base_length, config.intensity, main_angle_rad, 
                               config.quantity, thickness, color, False, 
                               config.rainbow_spike_intensity if (config.enable_rainbow and config.rainbow_spikes) else 0,
                               config.rainbow_spike_frequency, config.rainbow_spike_length, config.sharpness)
                               
            # Secondary Spikes
            if config.secondary_intensity > 0:
                sec_len = base_length * (config.secondary_length / config.length)
                self.draw_spikes(painter, star, sec_len, config.secondary_intensity, sec_angle_rad,
                               config.quantity, thickness * 0.6, sec_color, True,
                               0, 0, 0, config.sharpness)
                               
            # Halo
            classification_score = star.radius * star.brightness
            intensity_weight = math.pow(min(1.0, classification_score / 10.0), 2)
            
            if config.enable_halo and config.halo_intensity > 0 and intensity_weight > 0.01:
                final_halo_intensity = config.halo_intensity * intensity_weight
                halo_color = self.get_star_color(star, config.hue_shift, config.halo_saturation, final_halo_intensity)
                
                r_halo = star.radius * config.halo_scale
                if r_halo > 0.5:
                    relative_width = r_halo * (config.halo_width * 0.15)
                    self.draw_halo(painter, star, r_halo, relative_width, config.halo_blur, halo_color)

    def draw_spikes(self, painter: QPainter, star: Star, length: float, intensity: float, angle: float,
                   count: int, thick: float, color: QColor, is_secondary: bool,
                   rainbow_str: float, rainbow_freq: float, rainbow_len: float, sharpness: float):
        
        if length < 1:
            return
            
        for i in range(int(count)):
            theta = angle + (i * (math.pi * 2) / count)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            
            start_offset = 1.0 if is_secondary else 0.5
            start_x = star.x + cos_t * start_offset
            start_y = star.y + sin_t * start_offset
            end_x = star.x + cos_t * length
            end_y = star.y + sin_t * length
            
            # 1. Standard Spike (ALWAYS)
            if rainbow_str > 0:
                painter.setOpacity(0.4) # Dim standard spike to allow rainbow to be visible
                
            fade_point = max(0.0, min(0.99, sharpness))
            grad = QLinearGradient(star.x, star.y, end_x, end_y)
            grad.setColorAt(0, color)
            
            if fade_point > 0:
                c_mid = QColor(color)
                c_mid.setAlphaF(min(1.0, intensity * 0.8))
                grad.setColorAt(fade_point, c_mid)
                
            c_end = QColor(int(star.color.r), int(star.color.g), int(star.color.b), 0)
            grad.setColorAt(1, c_end)
            
            pen = QPen(QBrush(grad), thick)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap) # Butt cap
            painter.setPen(pen)
            painter.drawLine(QPointF(start_x, start_y), QPointF(end_x, end_y))
            
            if rainbow_str > 0:
                painter.setOpacity(1.0) # Reset opacity
            
            # 2. Rainbow Overlay (IF ENABLED)
            if rainbow_str > 0:
                r_grad = QLinearGradient(star.x, star.y, end_x, end_y)
                alpha = intensity
                c0 = QColor(color)
                r_grad.setColorAt(0, c0)
                
                stops = 10
                for s in range(1, stops + 1):
                    pos = s / stops
                    if pos > rainbow_len:
                        break
                    
                    hue = (pos * 360.0 * rainbow_freq) % 360.0
                    # Boost alpha to make it more "opaque"
                    a = min(1.0, alpha * rainbow_str * 2.0) * (1.0 - pos)
                    # HSLA to QColor
                    c = QColor.fromHslF(hue / 360.0, 0.8, 0.6, min(1.0, a))
                    r_grad.setColorAt(pos, c)
                
                r_grad.setColorAt(1, QColor(0, 0, 0, 0))
                
                r_pen = QPen(QBrush(r_grad), thick)
                r_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(r_pen)
                painter.drawLine(QPointF(start_x, start_y), QPointF(end_x, end_y))
            
            # Hot Core
            if not is_secondary and length > 30:
                core_len = length * 0.15
                core_end_x = star.x + cos_t * core_len
                core_end_y = star.y + sin_t * core_len
                
                core_pen = QPen(QColor(255, 255, 255, int(intensity * 0.8 * 255)), thick * 0.6)
                painter.setPen(core_pen)
                painter.drawLine(QPointF(start_x, start_y), QPointF(core_end_x, core_end_y))

    def draw_halo(self, painter: QPainter, star: Star, radius: float, width: float, blur: float, color: QColor):
        if radius <= 0 or width <= 0:
            return
            
        blur_expand = blur * 20.0
        inner_r = max(0.0, radius - width/2.0)
        outer_r = radius + width/2.0
        
        draw_inner = max(0.0, inner_r - blur_expand)
        draw_outer = outer_r + blur_expand
        
        grad = QRadialGradient(star.x, star.y, draw_outer)
        
        range_val = draw_outer - draw_inner
        if range_val <= 0:
            return
            
        start_peak = (inner_r - draw_inner) / range_val
        end_peak = (outer_r - draw_inner) / range_val
        center = (start_peak + end_peak) / 2.0
        blur_factor = (blur * 2.0) / range_val * 10.0
        
        # QGradient expects 0-1 relative to the radius (draw_outer)
        # But our draw_inner is not 0.
        # Wait, QRadialGradient(center, radius) covers 0 to radius.
        # We need to map our relative positions.
        # Actually, we should just use transparent for 0 to draw_inner/draw_outer
        # But QRadialGradient starts at center.
        # We need to offset the stops.
        
        # Correct mapping:
        # 0.0 is center of star.
        # 1.0 is draw_outer.
        
        # We want transparency until draw_inner
        stop_inner = draw_inner / draw_outer
        
        # Then rise to peak
        stop_start_peak = inner_r / draw_outer
        stop_end_peak = outer_r / draw_outer
        
        # Apply blur factor logic roughly
        # 0 -> stop_inner: transparent
        # stop_inner -> stop_start_peak: rise
        # ...
        
        # Simplified for QGradient:
        grad.setColorAt(0, QColor(0,0,0,0))
        if stop_start_peak > 0:
             grad.setColorAt(max(0, stop_start_peak - blur_factor * 0.1), QColor(0,0,0,0))
             
        grad.setColorAt((stop_start_peak + stop_end_peak)/2, color)
        
        if stop_end_peak < 1:
            grad.setColorAt(min(1, stop_end_peak + blur_factor * 0.1), QColor(0,0,0,0))
            
        grad.setColorAt(1, QColor(0,0,0,0))
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(star.x, star.y), draw_outer, draw_outer)
