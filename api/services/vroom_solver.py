import json
import gzip
import httpx
from typing import List, Dict, Any, Optional

from models.schemas import JobDelivery, FleetVehicle, OptimizationConfig
from services.config import parse_time_to_seconds

VROOM_URL = "http://vroom:3000"


def _package_fits_vehicle(bulto: Dict[str, Any], fleet: Optional[FleetVehicle]) -> bool:
    """
    Valida si un bulto con dimensiones explícitas (> 0) cabe por la puerta
    y dentro del compartimento de carga del vehículo (permitiendo rotación 3D).
    Si el bulto no tiene dimensiones (0 o None), siempre retorna True (degradación elegante).
    """
    if not fleet:
        return True
    try:
        l = float(bulto.get("largo") or 0)
        w = float(bulto.get("ancho") or 0)
        h = float(bulto.get("alto") or 0)
    except (TypeError, ValueError):
        return True

    if l <= 0 or w <= 0 or h <= 0:
        return True

    pkg_dims = sorted([l, w, h])  # [d_min, d_mid, d_max]

    # 1. Validar dimensiones interiores de la caja
    box_l = float(fleet.caja_largo_cm or 320)
    box_w = float(fleet.caja_ancho_cm or 180)
    box_h = float(fleet.caja_alto_cm or 190)
    box_dims = sorted([box_l, box_w, box_h])

    if pkg_dims[0] > box_dims[0] or pkg_dims[1] > box_dims[1] or pkg_dims[2] > box_dims[2]:
        return False

    # 2. Validar gálibo de puerta (las dos dimensiones menores deben cruzar la puerta)
    door_w = float(fleet.puerta_ancho_cm or 170)
    door_h = float(fleet.puerta_alto_cm or 180)
    door_dims = sorted([door_w, door_h])

    if pkg_dims[0] > door_dims[0] or pkg_dims[1] > door_dims[1]:
        return False

    return True


def _job_fits_vehicle(job: JobDelivery, fleet: Optional[FleetVehicle]) -> bool:
    if not job.bultos or not fleet:
        return True
    return all(_package_fits_vehicle(b, fleet) for b in job.bultos)

async def solve_vroom(
    jobs: List[JobDelivery],
    fleets: Optional[List[FleetVehicle]],
    depot_lat: float,
    depot_lon: float,
    config: OptimizationConfig
) -> Dict[str, Any]:
    """
    Construye el problema VROOM inyectando los costos fijos altos (fixed: 10000)
    para forzar el llenado máximo de vehículos, respetando tiempos de servicio
    y capacidades tanto para flotas pequeñas como masivas.
    Maneja graceful degradation: si el operador no gestiona pesos o dimensiones,
    las restricciones volumétricas no limitan ni provocan caídas o pedidos no asignados.
    """
    fixed_cost = config.fixed_cost if config.fixed_cost is not None else 10000
    service_time = config.service_time if config.service_time is not None else 180
    max_capacity = config.max_capacity if config.max_capacity is not None else 100
    use_capacity = config.use_capacity if config.use_capacity is not None else True

    # Detectar si el operador realmente gestiona pesos y volúmenes en los pedidos (y si el check está activo)
    has_custom_dimensions = use_capacity and any(
        ((j.weight_kg is not None and j.weight_kg > 0) or 
         (j.volume_dm3 is not None and j.volume_dm3 > 0))
        for j in jobs
    )

    # Pre-evaluar compatibilidad física (puerta y caja) por vehículo usando skills de VROOM
    vehicle_skills: Dict[int, List[int]] = {i + 1: [] for i in range(len(fleets) if fleets else 0)}
    job_skills: Dict[int, List[int]] = {}
    if use_capacity and fleets and len(fleets) > 0:
        for idx, job in enumerate(jobs):
            if not job.bultos:
                continue
            v_job_id = idx + 1
            compatible = [f_idx + 1 for f_idx, fl in enumerate(fleets) if _job_fits_vehicle(job, fl)]
            if len(compatible) < len(fleets):
                skill_id = 10000 + v_job_id
                job_skills[v_job_id] = [skill_id]
                for c_vid in compatible:
                    vehicle_skills[c_vid].append(skill_id)

    # 1. Construir lista de Jobs para VROOM
    vroom_jobs = []
    job_map: Dict[int, JobDelivery] = {}

    for idx, job in enumerate(jobs):
        v_job_id = idx + 1
        job_map[v_job_id] = job
        j_lat = job.location.get_lat()
        j_lon = job.location.get_lon()
        amount = int(job.amount) if job.amount else 1
        b_cnt = int(job.cant_bultos or amount)

        # Si el operador no ingresó peso/volumen, usamos 0 para que no limite artificialmente
        if has_custom_dimensions:
            w_kg = int(round(job.weight_kg)) if (job.weight_kg is not None and job.weight_kg > 0) else 0
            v_dm3 = int(round(job.volume_dm3)) if (job.volume_dm3 is not None and job.volume_dm3 > 0) else 0
            delivery_vec = [w_kg, v_dm3, b_cnt]
        else:
            # Modo estándar / sin dimensiones
            delivery_vec = [0, 0, b_cnt]

        v_job_data = {
            "id": v_job_id,
            "location": [j_lon, j_lat],
            "service": job.service_time or service_time,
            "delivery": delivery_vec,
            "description": str(job.description or job.id)
        }
        if v_job_id in job_skills:
            v_job_data["skills"] = job_skills[v_job_id]

        vroom_jobs.append(v_job_data)

    # 2. Construir lista de Vehículos para VROOM
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

        # Determinar punto de fin solo si está configurado explícitamente
        has_explicit_end = False
        e_lat = None
        e_lon = None
        if fleet_obj and fleet_obj.end_location and fleet_obj.end_location.get_lat() is not None:
            e_lat = fleet_obj.end_location.get_lat()
            e_lon = fleet_obj.end_location.get_lon()
            has_explicit_end = True

        # Capacidad de bultos: respeta la distribución calculada para no dejar pedidos fuera
        calc_cap = fleet_obj.capacity if (fleet_obj and fleet_obj.capacity and fleet_obj.capacity > 0) else max_capacity
        spec_cap_bultos = fleet_obj.capacity_bultos if (fleet_obj and fleet_obj.capacity_bultos and fleet_obj.capacity_bultos > 0) else 0
        v_cap_bultos = max(calc_cap, spec_cap_bultos)

        # Peso y volumen: si el operador no los gestiona, capacidad ilimitada (999999) para evitar falsos rechazos
        if has_custom_dimensions:
            v_cap_weight = int(fleet_obj.capacity_weight_kg) if (fleet_obj and fleet_obj.capacity_weight_kg and fleet_obj.capacity_weight_kg > 0) else 999999
            v_cap_volume = int(fleet_obj.capacity_volume_dm3) if (fleet_obj and fleet_obj.capacity_volume_dm3 and fleet_obj.capacity_volume_dm3 > 0) else 999999
        else:
            v_cap_weight = 999999
            v_cap_volume = 999999

        start_sec = parse_time_to_seconds(fleet_obj.start_time if (fleet_obj and fleet_obj.start_time) else "08:00")
        end_sec = parse_time_to_seconds(fleet_obj.end_time if (fleet_obj and fleet_obj.end_time) else "19:00")

        v_data = {
            "id": v_id,
            "profile": "auto",
            "start": [s_lon, s_lat],
            "capacity": [v_cap_weight, v_cap_volume, v_cap_bultos],
            "time_window": [start_sec, end_sec],
            "costs": {
                "fixed": fixed_cost
            }
        }

        if has_explicit_end:
            v_data["end"] = [e_lon, e_lat]

        if vehicle_skills.get(v_id):
            v_data["skills"] = vehicle_skills[v_id]

        vroom_vehicles.append(v_data)

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
