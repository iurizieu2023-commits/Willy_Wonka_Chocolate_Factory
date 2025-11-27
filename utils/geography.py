# utils/geography.py

import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth.
    
    Args:
        lat1, lon1: First location (latitude, longitude) in degrees
        lat2, lon2: Second location (latitude, longitude) in degrees
        
    Returns:
        Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of Earth in kilometers
    r = 6371
    
    return c * r


def delivery_time(distance_km: float, speed_kmph: float = 600.0) -> float:
    """
    Convert distance to delivery time in seconds.
    
    Args:
        distance_km: Distance in kilometers
        speed_kmph: Delivery speed in km/h (default: 600 km/h, like air freight)
        
    Returns:
        Delivery time in seconds
        
    Example:
        100 km @ 600 km/h = 0.167 hours = 10 seconds (scaled for simulation)
    """
    if distance_km <= 0:
        return 5.0  # Minimum local delivery time
    
    # hours = distance / speed
    # Scale: 1 hour real = 10 seconds simulation
    hours = distance_km / speed_kmph
    simulation_seconds = hours * 10.0  # Scaling factor
    
    # Add base processing time (5-10s)
    import random
    base_time = random.uniform(5, 10)
    
    return base_time + simulation_seconds


def format_distance(distance_km: float) -> str:
    """Format distance for display."""
    if distance_km < 1:
        return f"{distance_km * 1000:.0f}m"
    elif distance_km < 100:
        return f"{distance_km:.1f}km"
    else:
        return f"{distance_km:.0f}km"
