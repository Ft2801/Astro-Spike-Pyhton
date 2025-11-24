import numpy as np
from typing import List, Optional
from .types import Star, Color
import math

def detect_stars(image_data: np.ndarray, threshold: int) -> List[Star]:
    """
    Analyzes image data (H, W, 3) or (H, W, 4) to find stars.
    """
    height, width = image_data.shape[:2]
    
    # Calculate luminance
    # 0.2126 * r + 0.7152 * g + 0.0722 * b
    r = image_data[:, :, 0].astype(float)
    g = image_data[:, :, 1].astype(float)
    b = image_data[:, :, 2].astype(float)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    raw_stars: List[Star] = []
    stride = 4
    checked = np.zeros((height, width), dtype=bool)
    
    # Stride-based scanning using NumPy slicing for speed
    # We create a mask of potential candidates
    # lum[y, x] > threshold
    # We only check pixels at stride intervals
    
    # Create a strided view
    y_indices = np.arange(0, height, stride)
    x_indices = np.arange(0, width, stride)
    
    # Meshgrid for coordinates
    yy, xx = np.meshgrid(y_indices, x_indices, indexing='ij')
    
    # Extract luminance at these points
    lum_strided = lum[0:height:stride, 0:width:stride]
    
    # Find candidates
    candidates = np.argwhere((lum_strided > threshold) & (~checked[0:height:stride, 0:width:stride]))
    
    # Convert strided indices back to full coordinates
    # candidates is (N, 2) array of (y_idx, x_idx) in strided space
    
    for cand in candidates:
        y_idx, x_idx = cand
        y = y_idx * stride
        x = x_idx * stride
        
        if checked[y, x]:
            continue
            
        star = flood_fill_star(image_data, lum, width, height, x, y, threshold, checked)
        if star:
            raw_stars.append(star)
            
    # Merging Phase
    raw_stars.sort(key=lambda s: s.radius, reverse=True)
    merged_stars: List[Star] = []
    
    for star in raw_stars:
        merged = False
        for existing in merged_stars:
            dx = star.x - existing.x
            dy = star.y - existing.y
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist < (existing.radius + star.radius + 5):
                merged = True
                break
        
        if not merged:
            merged_stars.append(star)
            
    # Sample Halo Colors
    for star in merged_stars:
        star.color = sample_halo_color(image_data, width, height, star)
        
    # Final sort
    merged_stars.sort(key=lambda s: s.brightness * s.radius, reverse=True)
    return merged_stars

def flood_fill_star(data: np.ndarray, lum_data: np.ndarray, width: int, height: int, 
                   start_x: int, start_y: int, threshold: int, checked: np.ndarray) -> Optional[Star]:
    
    sum_x = 0.0
    sum_y = 0.0
    sum_lum = 0.0
    
    pixel_count = 0
    max_lum = 0.0
    
    stack = [(start_x, start_y)]
    max_pixels = 2500
    
    while stack and pixel_count < max_pixels:
        cx, cy = stack.pop()
        
        if cx < 0 or cx >= width or cy < 0 or cy >= height:
            continue
            
        if checked[cy, cx]:
            continue
            
        l = lum_data[cy, cx]
        
        if l > threshold:
            checked[cy, cx] = True
            
            sum_x += cx * l
            sum_y += cy * l
            sum_lum += l
            
            pixel_count += 1
            if l > max_lum:
                max_lum = l
                
            # 4-connectivity
            stack.append((cx + 1, cy))
            stack.append((cx - 1, cy))
            stack.append((cx, cy + 1))
            stack.append((cx, cy - 1))
            
    if pixel_count == 0:
        return None
        
    return Star(
        x=sum_x / sum_lum,
        y=sum_y / sum_lum,
        brightness=max_lum / 255.0,
        radius=math.sqrt(pixel_count / math.pi),
        color=Color(255, 255, 255) # Placeholder
    )

def sample_halo_color(data: np.ndarray, width: int, height: int, star: Star) -> Color:
    inner_radius = star.radius * 1.5
    outer_radius = star.radius * 3.0
    
    sum_r = 0.0
    sum_g = 0.0
    sum_b = 0.0
    sample_count = 0
    
    samples = 24
    for i in range(samples):
        angle = (i / samples) * math.pi * 2
        radius = (inner_radius + outer_radius) / 2
        
        x = int(round(star.x + math.cos(angle) * radius))
        y = int(round(star.y + math.sin(angle) * radius))
        
        if 0 <= x < width and 0 <= y < height:
            sum_r += data[y, x, 0]
            sum_g += data[y, x, 1]
            sum_b += data[y, x, 2]
            sample_count += 1
            
    if sample_count == 0:
        return Color(255, 255, 255)
        
    return Color(
        r=sum_r / sample_count,
        g=sum_g / sample_count,
        b=sum_b / sample_count
    )
