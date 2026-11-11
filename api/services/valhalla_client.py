import os
import httpx
from typing import List, Dict, Any, Optional, Tuple

VALHALLA_URL = os.getenv("VALHALLA_URL", "http://valhalla:8002").rstrip("/")

def decodificar_asfalto(polyline_str: str) -> List[List[float]]:
    """
    Decodifica una cadena polyline con precisión 6 (estándar de Valhalla)
    a una lista de coordenadas [[lat, lon], [lat, lon], ...].
    """
    index, lat, lng, coordinates = 0, 0, 0, []
    while index < len(polyline_str):
        cambios = {'lat': 0, 'lon': 0}
        for unidad in ['lat', 'lon']:
            shift, result = 0, 0
            while True:
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20:
                    break
            cambios[unidad] = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += cambios['lat']
        lng += cambios['lon']
        coordinates.append([round(lat / 1e6, 6), round(lng / 1e6, 6)])
    return coordinates

def encode_polyline5(coordinates: List[List[float]]) -> str:
    """
    Codifica una lista de coordenadas [[lat, lon], ...] a Polyline de precisión 5
    (estándar compatible con Mapbox y Google Maps en frontend de Dribling).
    """
    result = []
    prev_lat = 0
    prev_lng = 0
    for coord in coordinates:
        lat, lng = coord[0], coord[1]
        late5 = int(round(lat * 1e5))
        lnge5 = int(round(lng * 1e5))
        d_lat = late5 - prev_lat
        d_lng = lnge5 - prev_lng
        prev_lat = late5
        prev_lng = lnge5
        for num in (d_lat, d_lng):
            num = ~(num << 1) if num < 0 else (num << 1)
            while num >= 0x20:
                result.append(chr((0x20 | (num & 0x1f)) + 63))
                num >>= 5
            result.append(chr(num + 63))
    return "".join(result)

async def get_route_geometry(points: List[Dict[str, float]], costing: str = "auto") -> Tuple[Optional[str], List[List[float]], int, int]:
    """
    Consulta a Valhalla (/route) la geometría exacta sobre el asfalto para una secuencia de puntos.
    Retorna: (polyline_str_precision_5, coordinates_list, duration_seconds, distance_meters)
    """
    if len(points) < 2:
        return "", [], 0, 0

    locations = [{"lat": p["lat"], "lon": p["lon"]} for p in points]
    payload = {
        "locations": locations,
        "costing": costing,
        "directions_options": {
            "units": "kilometers"
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{VALHALLA_URL}/route", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                trip = data.get("trip", {})
                legs = trip.get("legs", [])
                
                all_coords: List[List[float]] = []
                total_duration = int(trip.get("summary", {}).get("time", 0))
                total_distance = int(trip.get("summary", {}).get("length", 0) * 1000)

                for leg in legs:
                    shape = leg.get("shape", "")
                    if shape:
                        coords = decodificar_asfalto(shape)
                        all_coords.extend(coords)

                # Codificar toda la ruta continua en polyline 5 para el frontend
                poly5 = encode_polyline5(all_coords) if all_coords else ""
                return poly5, all_coords, total_duration, total_distance
    except Exception as e:
        print(f"[ValhallaClient] Error obteniendo geometría: {e}")

    # Fallback: líneas rectas si Valhalla falla temporalmente
    fallback_coords = [[p["lat"], p["lon"]] for p in points]
    fallback_poly = encode_polyline5(fallback_coords) if fallback_coords else ""
    return fallback_poly, fallback_coords, 0, 0
