from typing import List, Tuple, Dict, Any
from models.schemas import JobDelivery
from services.config import compute_dynamic_bbox, COUNTRY_BOUNDS, get_default_country

def filter_jobs_by_bbox(
    jobs: List[JobDelivery],
    depot_lat: float,
    depot_lon: float,
    country: str = None,
    max_radius_km: float = 150.0
) -> Tuple[List[JobDelivery], List[Dict[str, Any]]]:
    """
    Filtra los pedidos que tengan coordenadas GPS válidas y que se encuentren
    dentro del radio de servicio razonable del Depot.
    """
    country_key = (country or get_default_country()).lower()
    national_bounds = COUNTRY_BOUNDS.get(country_key, COUNTRY_BOUNDS["chile"])

    lat_min, lat_max, lon_min, lon_max = compute_dynamic_bbox(depot_lat, depot_lon, max_radius_km)

    valid_jobs: List[JobDelivery] = []
    dropped_jobs: List[Dict[str, Any]] = []

    for job in jobs:
        j_lat = job.location.get_lat()
        j_lon = job.location.get_lon()

        # 1. Validar que no sea 0,0 o nulo
        if abs(j_lat) < 0.0001 and abs(j_lon) < 0.0001:
            dropped_jobs.append({
                "id": job.id,
                "reason": "Coordenadas GPS en 0,0 o vacías",
                "location": {"lat": j_lat, "lng": j_lon}
            })
            continue

        # 2. Validar que esté dentro del país
        if not (national_bounds["lat_min"] <= j_lat <= national_bounds["lat_max"] and
                national_bounds["lon_min"] <= j_lon <= national_bounds["lon_max"]):
            dropped_jobs.append({
                "id": job.id,
                "reason": f"Coordenadas fuera de los límites del país ({country_key.capitalize()})",
                "location": {"lat": j_lat, "lng": j_lon}
            })
            continue

        # 3. Validar que esté dentro del radio dinámico alrededor del Depot
        if not (lat_min <= j_lat <= lat_max and lon_min <= j_lon <= lon_max):
            dropped_jobs.append({
                "id": job.id,
                "reason": f"Punto excede el radio máximo de {max_radius_km} km respecto al centro de distribución",
                "location": {"lat": j_lat, "lng": j_lon}
            })
            continue

        valid_jobs.append(job)

    return valid_jobs, dropped_jobs

