"""
Utility functions for coordinate operations.
"""
import math
from bookings.utils.pincode_coords import PINCODE_COORDS


def get_coords_from_pincode(pincode):
    """
    Get latitude and longitude coordinates from a pincode.
    
    Args:
        pincode: String pincode (e.g., '110001')
        
    Returns:
        Tuple of (lat, lng) if found, None otherwise
    """
    if not pincode:
        return None
    
    # Normalize pincode (strip whitespace, convert to string)
    pincode = str(pincode).strip()
    
    return PINCODE_COORDS.get(pincode)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points on Earth using the Haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of first point in decimal degrees
        lat2, lon2: Latitude and longitude of second point in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    # Earth radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance

