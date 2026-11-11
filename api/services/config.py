import os
import math
from typing import Dict, Any, Tuple

# Bounding boxes generales por país para evitar coordenadas absurdas
COUNTRY_BOUNDS = {
    "chile": {
        "lat_min": -56.0,
        "lat_max": -17.5,
        "lon_min": -76.0,
        "lon_max": -66.0,
        "default_depot": {"lat": -33.4489, "lon": -70.6693, "name": "Santiago"}
    },
    "colombia": {
        "lat_min": -4.3,
        "lat_max": 13.5,
        "lon_min": -79.5,
        "lon_max": -66.8,
        "default_depot": {"lat": 4.6669, "lon": -74.1300, "name": "Bogotá"}
    }
}

def get_default_country() -> str:
    return os.getenv("ROUTING_COUNTRY", "chile").strip().lower()

def compute_dynamic_bbox(depot_lat: float, depot_lon: float, max_radius_km: float = 150.0) -> Tuple[float, float, float, float]:
    """
    Calcula un recuadro BBOX en grados alrededor del Depot basado en un radio en kilómetros.
    1 grado de latitud equivale a ~111 km.
    1 grado de longitud equivale a ~111 km * cos(lat).
    """
    delta_lat = max_radius_km / 111.0
    cos_lat = math.cos(math.radians(depot_lat))
    if abs(cos_lat) < 0.01:
        cos_lat = 0.01
    delta_lon = max_radius_km / (111.0 * abs(cos_lat))

    lat_min = depot_lat - delta_lat
    lat_max = depot_lat + delta_lat
    lon_min = depot_lon - delta_lon
    lon_max = depot_lon + delta_lon

    return lat_min, lat_max, lon_min, lon_max

