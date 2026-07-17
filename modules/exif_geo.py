# modules/exif_geo.py
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

def _to_float(val) -> float:
    if hasattr(val, 'numerator') and hasattr(val, 'denominator'):
        if val.denominator == 0:
            return 0.0
        return float(val.numerator) / float(val.denominator)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def _convert_to_degrees(value) -> float:
    """Helper to convert GPS coordinates in EXIF format to degrees (decimal)."""
    # Exif values are typically in the form (degrees, minutes, seconds)
    if not value or not isinstance(value, (list, tuple)):
        return 0.0
        
    d = _to_float(value[0]) if len(value) > 0 else 0.0
    m = _to_float(value[1]) if len(value) > 1 else 0.0
    s = _to_float(value[2]) if len(value) > 2 else 0.0

    return d + (m / 60.0) + (s / 3600.0)

def extract_gps(image_path: str) -> dict | None:
    """
    Extracts GPS coordinates (latitude, longitude) from an image file's EXIF.
    Returns:
        dict: {"lat": float, "lng": float}
        None: if no GPS EXIF tag is present or if file is not a valid image.
    """
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None
                
            # GPSInfo is EXIF tag 0x8825 (34853)
            gps_info = exif.get_ifd(34853)
            if not gps_info:
                return None

            # Keys inside gps_info are numeric tags defined in GPSTAGS
            # We need:
            # 2: GPSLatitude (tuple/list)
            # 1: GPSLatitudeRef ('N' or 'S')
            # 4: GPSLongitude (tuple/list)
            # 3: GPSLongitudeRef ('E' or 'W')
            
            lat_ref = gps_info.get(1)
            lat_val = gps_info.get(2)
            lng_ref = gps_info.get(3)
            lng_val = gps_info.get(4)

            if not lat_ref or not lat_val or not lng_ref or not lng_val:
                return None

            lat = _convert_to_degrees(lat_val)
            lng = _convert_to_degrees(lng_val)

            if lat_ref.upper() == 'S':
                lat = -lat
            if lng_ref.upper() == 'W':
                lng = -lng

            return {
                "lat": round(lat, 6),
                "lng": round(lng, 6)
            }
    except Exception:
        # Silently fail on non-images or other read errors
        return None
