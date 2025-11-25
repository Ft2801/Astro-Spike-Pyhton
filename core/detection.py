import numpy as np
from typing import List, Optional, Tuple, Dict
from .types import Star, Color
import math

def map_threshold_to_internal(ui_threshold: int) -> float:
    """
    Maps UI threshold (1-100) to internal threshold (140-240).
    UI 1 -> 140 (more sensitive, detects more stars)
    UI 100 -> 240 (less sensitive, only brightest stars)
    """
    # Linear mapping: ui 1-100 -> internal 140-240
    return 140 + (ui_threshold - 1) * (240 - 140) / (100 - 1)

def find_local_peak(lum_data: np.ndarray, x: int, y: int, width: int, height: int) -> Tuple[int, int, float]:
    """
    Finds the local maximum brightness starting from (x, y).
    """
    curr_x, curr_y = x, y
    curr_lum = lum_data[y, x]
    
    # Limit iterations to prevent infinite loops
    for _ in range(20):
        best_lum = curr_lum
        best_x, best_y = curr_x, curr_y
        changed = False
        
        # Check 3x3 neighborhood
        y_min = max(0, curr_y - 1)
        y_max = min(height, curr_y + 2)
        x_min = max(0, curr_x - 1)
        x_max = min(width, curr_x + 2)
        
        # Extract local window
        window = lum_data[y_min:y_max, x_min:x_max]
        max_val = np.max(window)
        
        if max_val > best_lum:
            # Find coordinates of max value in window
            local_y, local_x = np.unravel_index(np.argmax(window), window.shape)
            best_x = x_min + local_x
            best_y = y_min + local_y
            best_lum = max_val
            changed = True
        
        if not changed:
            break
            
        curr_x, curr_y = best_x, best_y
        curr_lum = best_lum
        
    return curr_x, curr_y, curr_lum

def detect_stars(image_data: np.ndarray, threshold: int) -> List[Star]:
    """
    Analyzes image data (H, W, 3) or (H, W, 4) to find stars.
    Uses a peak-finding approach followed by valley-aware flood fill.
    """
    height, width = image_data.shape[:2]
    
    # Map UI threshold to internal value
    internal_threshold = map_threshold_to_internal(threshold)
    
    # Calculate luminance
    # 0.2126 * r + 0.7152 * g + 0.0722 * b
    r = image_data[:, :, 0].astype(float)
    g = image_data[:, :, 1].astype(float)
    b = image_data[:, :, 2].astype(float)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    stride = 4
    
    # Stride-based scanning to find potential candidates
    lum_strided = lum[0:height:stride, 0:width:stride]
    cy_indices, cx_indices = np.where(lum_strided > internal_threshold)
    
    # Find true peaks for each candidate
    unique_peaks: Dict[Tuple[int, int], float] = {}
    
    for i in range(len(cy_indices)):
        y = cy_indices[i] * stride
        x = cx_indices[i] * stride
        
        px, py, plum = find_local_peak(lum, x, y, width, height)
        
        if plum > internal_threshold:
            unique_peaks[(px, py)] = plum
            
    # Sort peaks by brightness (descending)
    # This ensures we process the core of bright stars first
    sorted_peaks = sorted(unique_peaks.items(), key=lambda item: item[1], reverse=True)
    
    stars: List[Star] = []
    checked = np.zeros((height, width), dtype=bool)
    
    for (px, py), plum in sorted_peaks:
        if checked[py, px]:
            continue
            
        star = flood_fill_star(image_data, lum, width, height, px, py, internal_threshold, checked)
        if star:
            stars.append(star)
            
    # Merging Phase
    # Relaxed merging: only merge if very close or if one is clearly an artifact
    stars.sort(key=lambda s: s.radius, reverse=True)
    merged_stars: List[Star] = []
    
    for star in stars:
        merged = False
        for existing in merged_stars:
            dx = star.x - existing.x
            dy = star.y - existing.y
            dist = math.sqrt(dx*dx + dy*dy)
            
            # Merge logic:
            # 1. If star is much dimmer (< 40% brightness) OR tiny, it's likely an artifact/noise -> Aggressive merge
            # 2. If both are significant, only merge if they are extremely close (overlapping cores)
            
            brightness_ratio = star.brightness / max(existing.brightness, 0.01)
            is_much_dimmer = brightness_ratio < 0.4
            is_tiny = star.radius < 5
            
            should_merge = False
            
            if is_much_dimmer or is_tiny:
                # Aggressive merging for artifacts
                if dist < (existing.radius + star.radius) * 1.2:
                    should_merge = True
            else:
                # Both are significant stars. Only merge if they are practically the same star.
                # Previously 0.5, which was too aggressive when radii are large (low threshold).
                # Reduced to 0.25 to allow close double stars.
                if dist < (existing.radius + star.radius) * 0.25:
                    should_merge = True
            
            if should_merge:
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
    
    # Color tracking with weighted average (penalizing white core)
    sum_r = 0.0
    sum_g = 0.0
    sum_b = 0.0
    sum_color_weight = 0.0
    
    pixel_count = 0
    max_lum = lum_data[start_y, start_x] # Start at peak
    
    # Track bounding box for compactness check
    min_x, max_x = start_x, start_x
    min_y, max_y = start_y, start_y
    
    # Track pixel coordinates for shape analysis
    pixel_coords_x = []
    pixel_coords_y = []
    
    stack = [(start_x, start_y)]
    
    # Increased pixel limit for large stars
    max_pixels = int(1000 + (max_lum / 255.0) * 50000)
    
    # Minimum luminance ratio
    min_lum_ratio = 0.20
    
    # Valley detection: track the minimum luminance seen along the path
    # If we see brightness increasing significantly after a valley, stop (entering another star)
    path_min_lum = max_lum  # Track minimum luminance along the path
    
    while stack and pixel_count < max_pixels:
        cx, cy = stack.pop()
        
        if cx < 0 or cx >= width or cy < 0 or cy >= height:
            continue
            
        if checked[cy, cx]:
            continue
            
        l = lum_data[cy, cx]
        
        # Basic threshold check
        if l > threshold:
            # Ratio check
            if max_lum > 0 and l < (max_lum * min_lum_ratio):
                continue
            
            checked[cy, cx] = True
            
            # Update path minimum for valley detection
            if l < path_min_lum:
                path_min_lum = l
            
            # Update bounding box
            min_x = min(min_x, cx)
            max_x = max(max_x, cx)
            min_y = min(min_y, cy)
            max_y = max(max_y, cy)
            
            # Track pixel coordinates for shape analysis
            pixel_coords_x.append(cx)
            pixel_coords_y.append(cy)
            
            sum_x += cx * l
            sum_y += cy * l
            sum_lum += l
            
            # Color extraction with white core penalization
            pr = float(data[cy, cx, 0])
            pg = float(data[cy, cx, 1])
            pb = float(data[cy, cx, 2])
            
            max_rgb = max(pr, pg, pb)
            min_rgb = min(pr, pg, pb)
            saturation = (max_rgb - min_rgb) / 255.0 if max_rgb > 0 else 0
            
            # Calculate color weight:
            # - If pixel is "burned" (R, G, B all > 245), reduce weight drastically
            # - If pixel is colored (has saturation), increase weight
            if pr > 245 and pg > 245 and pb > 245:
                # White/burned pixel - minimal weight
                color_weight = 0.01
            else:
                # Colored pixel - weight based on luminance + saturation boost
                color_weight = (l / 255.0) + saturation * 2.0
            
            sum_r += pr * color_weight
            sum_g += pg * color_weight
            sum_b += pb * color_weight
            sum_color_weight += color_weight
            
            pixel_count += 1
            
            # Check neighbors
            neighbors = [
                (cx + 1, cy), (cx - 1, cy),
                (cx, cy + 1), (cx, cy - 1)
            ]
            
            for nx, ny in neighbors:
                if 0 <= nx < width and 0 <= ny < height:
                    nl = lum_data[ny, nx]
                    # Valley detection: if we've descended into a valley and now 
                    # brightness is climbing back up significantly, we're entering another star
                    # Don't cross if neighbor is brighter than our path minimum + tolerance
                    valley_climb_tolerance = max(10, path_min_lum * 0.15)  # 15% of path min or 10, whichever is higher
                    if nl > path_min_lum + valley_climb_tolerance:
                        continue
                    stack.append((nx, ny))
            
    if pixel_count == 0:
        return None
    
    # === SHAPE ANALYSIS: Eccentricity Check ===
    # Reject irregular blobs (nebulosity) based on axis ratio
    if pixel_count >= 10:  # Only check if we have enough pixels
        coords_x = np.array(pixel_coords_x, dtype=float)
        coords_y = np.array(pixel_coords_y, dtype=float)
        
        # Calculate centroid
        cx = np.mean(coords_x)
        cy = np.mean(coords_y)
        
        # Central moments (second-order)
        dx = coords_x - cx
        dy = coords_y - cy
        
        mu20 = np.mean(dx * dx)
        mu02 = np.mean(dy * dy)
        mu11 = np.mean(dx * dy)
        
        # Covariance matrix: [[mu20, mu11], [mu11, mu02]]
        # Eigenvalues give variance along principal axes
        # Calculate eigenvalues analytically for 2x2 matrix
        trace = mu20 + mu02
        det = mu20 * mu02 - mu11 * mu11
        
        # Eigenvalues: λ = (trace ± sqrt(trace² - 4*det)) / 2
        discriminant = trace * trace - 4 * det
        
        if discriminant >= 0 and trace > 0:
            sqrt_disc = math.sqrt(discriminant)
            lambda1 = (trace + sqrt_disc) / 2.0
            lambda2 = (trace - sqrt_disc) / 2.0
            
            # Axis ratio: larger / smaller
            if lambda2 > 0:
                axis_ratio = math.sqrt(lambda1 / lambda2)
                
                # Reject if too elongated/irregular
                if axis_ratio > 1.5:
                    return None
    
    # Relaxed Compactness check
    bbox_width = max_x - min_x + 1
    bbox_height = max_y - min_y + 1
    bbox_area = bbox_width * bbox_height
    
    aspect_ratio = max(bbox_width, bbox_height) / max(min(bbox_width, bbox_height), 1)
    if aspect_ratio > 5.0:  # Relaxed from 3
        return None
    
    fill_ratio = pixel_count / max(bbox_area, 1)
    if fill_ratio < 0.10 and pixel_count > 50:  # Relaxed from 0.15
        return None
    
    # Removed Max Radius Check to allow large stars
    calculated_radius = math.sqrt(pixel_count / math.pi)
    
    # Calculate average color from weighted samples
    if sum_color_weight > 0:
        avg_r = sum_r / sum_color_weight
        avg_g = sum_g / sum_color_weight
        avg_b = sum_b / sum_color_weight
    else:
        avg_r, avg_g, avg_b = 255, 255, 255
        
    return Star(
        x=sum_x / sum_lum,
        y=sum_y / sum_lum,
        brightness=max_lum / 255.0,
        radius=calculated_radius,
        color=Color(avg_r, avg_g, avg_b)
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
