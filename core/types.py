from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class Color:
    r: float
    g: float
    b: float

@dataclass
class Star:
    x: float
    y: float
    brightness: float
    radius: float
    color: Color

@dataclass
class SpikeConfig:
    # Detection
    threshold: int = 240
    star_amount: float = 100.0

    # Main Spikes
    quantity: int = 4
    length: float = 300.0
    global_scale: float = 1.0
    angle: float = 45.0
    intensity: float = 1.0
    spike_width: float = 1.0
    sharpness: float = 0.5

    # Appearance
    color_saturation: float = 3.0  # Updated max
    hue_shift: float = 0.0

    # Secondary Spikes
    secondary_intensity: float = 0.5
    secondary_length: float = 120.0
    secondary_offset: float = 45.0

    # Soft Flare
    soft_flare_intensity: float = 3.0
    soft_flare_size: float = 15.0

    # Halo
    enable_halo: bool = False
    halo_intensity: float = 0.5
    halo_scale: float = 5.0
    halo_width: float = 1.0
    halo_blur: float = 0.5
    halo_saturation: float = 1.0

    # Spectral
    enable_rainbow: bool = False
    rainbow_spikes: bool = True
    rainbow_spike_intensity: float = 0.8
    rainbow_spike_frequency: float = 1.0
    rainbow_spike_length: float = 0.8

DEFAULT_CONFIG = SpikeConfig()
