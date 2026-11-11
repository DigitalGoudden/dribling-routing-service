import os
import httpx
import json
import gzip
from typing import List, Dict, Any, Tuple
from models.schemas import JobDelivery, FleetVehicle, OptimizationConfig

VROOM_URL = os.getenv("VROOM_URL", "http://vroom:3000").rstrip("/")

def parse_time_to_seconds(time_str: str) -> int:
    """Convierte formato 'HH:MM' o 'HH:MM:SS' a segundos desde las 00:00."""
    try:
        parts = [int(p) for p in time_str.strip().split(":")]
        if len(parts) == 2:
            return parts[0] * 3600 + parts[1] * 60
        elif len(parts) >= 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 8 * 3600  # Default 08:00 AM

async def solve_vroom(
    jobs: List[JobDelivery],
    fleets: List[FleetVehicle],
    depot_lat: float,
    depot_lon: float,
    config: OptimizationConfig
) -> Dict[str, Any]:
    """
    Construye el problema VROOM inyectando los costos fijos altos (fixed: 10000)
    para forzar el llenado máximo de vehículos, respetando tiempos de servicio
    y capacidades tanto para flotas pequeñas como masivas.
    """
    fixed_cost = config.fixed_cost if config.fixed_cost is not None else 10000
    service_time = config.service_time if config.service_time is not None else 180
    max_capacity = config.max_capacity if config.max_capacity is not None else 100

    # 1. Construir lista de Jobs para VROOM
    # Coordenadas en formato [lon, lat] requeridas por VROOM
    vroom_jobs = []
    job_map: Dict[int, JobDelivery] = {}

    for idx, job in enumerate(jobs):
        v_job_id = idx + 1
        job_map[v_job_id] = job
        j_lat = job.location.get_lat()
        j_lon = job.location.get_lon()
        amount = int(job.amount) if job.amount else 1

        vroom_jobs.append({
            "id": v_job_id,
            "location": [j_lon, j_lat],
            "service": job.service_time or service_time,
            "delivery": [amount],
            "description": str(job.description or job.id)
        })

    # 2. Construir lista de Vehículos para VROOM
    # Si el usuario seleccionó vehículos en Dribling, respetamos estrictamente esos vehículos y su capacidad.
    # Si no se pasó ninguna flota, generamos vehículos virtuales necesarios según max_capacity.
    if fleets and len(fleets) > 0:
        vehicles_count = len(fleets)
    else:
        total_items = sum(int(j.amount or 1) for j in jobs)
        min_vehicles_needed = max(1, (total_items // max_capacity) + 1)
        vehicles_count = min_vehicles_needed

    vroom_vehicles = []
    fleet_map: Dict[int, FleetVehicle] = {}

    for idx in range(vehicles_count):
        v_id = idx + 1
        fleet_obj = fleets[idx] if (fleets and idx < len(fleets)) else None
        
        # Determinar punto de inicio
        if fleet_obj and fleet_obj.start_location:
            s_lat = fleet_obj.start_location.get_lat()
            s_lon = fleet_obj.start_location.get_lon()
        else:
            s_lat = depot_lat
            s_lon = depot_lon

        # Determinar punto de fin
        if fleet_obj and fleet_obj.end_location:
            e_lat = fleet_obj.end_location.get_lat()
            e_lon = fleet_obj.end_location.get_lon()
        else:
            e_lat = s_lat
            e_lon = s_lon

        # Capacidad configurable por vehículo o fallback global
        v_cap = fleet_obj.capacity if (fleet_obj and fleet_obj.capacity and fleet_obj.capacity > 0) else max_capacity
        start_sec = parse_time_to_seconds(fleet_obj.start_time if (fleet_obj and fleet_obj.start_time) else "08:00")
        end_sec = parse_time_to_seconds(fleet_obj.end_time if (fleet_obj and fleet_obj.end_time) else "19:00")

        vroom_vehicles.append({
            "id": v_id,
            "start": [s_lon, s_lat],
            "end": [e_lon, e_lat],
            "capacity": [v_cap],
            "time_window": [start_sec, end_sec],
            "costs": {
                "fixed": fixed_cost  # Penalización alta para forzar el llenado al 100% de los camiones utilizados
            }
        })

        if fleet_obj:
            fleet_map[v_id] = fleet_obj

    payload = {
        "jobs": vroom_jobs,
        "vehicles": vroom_vehicles
    }

    # 3. Enviar a VROOM (con compresión GZIP si supera los 200 KB)
    json_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json"
    }

    if len(json_bytes) > 200 * 1024:
        headers["Content-Encoding"] = "gzip"
        data_to_send = gzip.compress(json_bytes)
    else:
        data_to_send = json_bytes

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{VROOM_URL}/", content=data_to_send, headers=headers)
            if resp.status_code != 200:
                raise Exception(f"VROOM retornó HTTP {resp.status_code}: {resp.text}")
            
            vroom_data = resp.json()
            return {
                "vroom_result": vroom_data,
                "job_map": job_map,
                "fleet_map": fleet_map
            }
    except Exception as e:
        raise Exception(f"Fallo al conectar con VROOM en {VROOM_URL}: {str(e)}")
