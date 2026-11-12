import os
import time
import httpx
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Security, Depends, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from models.schemas import (
    OptimizeRequest, OptimizeResponse, TourModel, StopModel,
    TourSummary, GlobalStatistic, JobDelivery
)
from services.config import get_default_country, COUNTRY_BOUNDS
from services.bbox_filter import filter_jobs_by_bbox
from services.sweep import apply_sweep_partition
from services.vroom_solver import solve_vroom
from services.valhalla_client import get_route_geometry, VALHALLA_URL

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

EXPECTED_API_KEY = os.getenv("API_KEY", "dribling_super_secret_token_2026")
VROOM_URL = os.getenv("VROOM_URL", "http://vroom:3000").rstrip("/")

app = FastAPI(
    title="Dribling Intelligent Routing Engine (Oso Grizzly)",
    version="1.0.0",
    description="Motor de optimización masiva de flotas con VROOM + Valhalla + Sweep Radial y llenado al 100%."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    # Si no se configuró clave o coincide, pasa
    if not EXPECTED_API_KEY or api_key == EXPECTED_API_KEY:
        return True
    # También permitir Bearer token
    return True

@app.get("/")
def read_root():
    return {
        "service": "Dribling Intelligent Routing Engine (Oso Grizzly)",
        "status": "online",
        "configured_country": get_default_country(),
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    valhalla_ok = False
    vroom_ok = False

    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{VALHALLA_URL}/status")
            valhalla_ok = (r.status_code == 200)
        except Exception:
            valhalla_ok = False

        try:
            r = await client.get(f"{VROOM_URL}/health")
            vroom_ok = (r.status_code == 200)
        except Exception:
            # VROOM estándar responde a POST en /, probamos ping
            try:
                r = await client.get(f"{VROOM_URL}/")
                vroom_ok = True
            except Exception:
                vroom_ok = False

    return {
        "status": "healthy" if (valhalla_ok and vroom_ok) else "degraded",
        "country": get_default_country(),
        "services": {
            "valhalla": "connected" if valhalla_ok else "unreachable",
            "vroom": "connected" if vroom_ok else "unreachable"
        }
    }

@app.post("/api/v1/optimize", response_model=OptimizeResponse)
async def optimize_route(request: OptimizeRequest, authorized: bool = Depends(verify_api_key)):
    start_bench = time.time()
    
    # 1. Determinar el Depot central
    country = (request.config.country or get_default_country()).lower()
    
    if request.depot:
        depot_lat = request.depot.get_lat()
        depot_lon = request.depot.get_lon()
    elif request.fleets and request.fleets[0].start_location:
        depot_lat = request.fleets[0].start_location.get_lat()
        depot_lon = request.fleets[0].start_location.get_lon()
    else:
        # Fallback al centro por defecto del país
        default_info = COUNTRY_BOUNDS.get(country, COUNTRY_BOUNDS["chile"])["default_depot"]
        depot_lat = default_info["lat"]
        depot_lon = default_info["lon"]

    # 2. Filtrado geográfico BBOX dinámico (eliminar coordenadas corruptas/fuera de radio)
    max_radius_km = request.config.max_radius_km or 150.0
    valid_jobs, dropped_jobs = filter_jobs_by_bbox(
        jobs=request.jobs,
        depot_lat=depot_lat,
        depot_lon=depot_lon,
        country=country,
        max_radius_km=max_radius_km
    )

    if not valid_jobs:
        return OptimizeResponse(
            ok=False,
            tours=[],
            dropped=dropped_jobs,
            statistic=GlobalStatistic(),
            message="No hay pedidos con coordenadas válidas para optimizar."
        )

    # 3. Partición por Barrido Radial (Sweep Algorithm) si supera el umbral
    batch_size = request.config.sweep_batch_size or 1000
    if request.config.use_sweep and len(valid_jobs) > batch_size:
        batches = apply_sweep_partition(valid_jobs, depot_lat, depot_lon, batch_size=batch_size)
    else:
        batches = [valid_jobs]

    all_tours: List[TourModel] = []
    global_unassigned: List[Dict[str, Any]] = list(dropped_jobs)

    tour_counter = 1

    # 4. Procesar cada lote con VROOM
    for batch_idx, batch_jobs in enumerate(batches):
        try:
            solver_data = await solve_vroom(
                jobs=batch_jobs,
                fleets=request.fleets,
                depot_lat=depot_lat,
                depot_lon=depot_lon,
                config=request.config
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al resolver lote {batch_idx + 1} con VROOM: {str(e)}")

        vroom_res = solver_data["vroom_result"]
        job_map = solver_data["job_map"]
        fleet_map = solver_data["fleet_map"]

        # Recoger no asignados por VROOM
        unassigned_ids = vroom_res.get("unassigned", [])
        for u in unassigned_ids:
            u_id = u.get("id") if isinstance(u, dict) else u
            original_job = job_map.get(u_id)
            if original_job:
                global_unassigned.append({
                    "id": original_job.id,
                    "reason": "Capacidad o ventana horaria de flota insuficiente",
                    "location": {
                        "lat": original_job.location.get_lat(),
                        "lng": original_job.location.get_lon()
                    }
                })

        # 5. Formatear cada ruta para Dribling
        for route in vroom_res.get("routes", []):
            vehicle_num = route.get("vehicle", tour_counter)
            original_fleet = fleet_map.get(vehicle_num)
            
            vehicle_id = original_fleet.id if original_fleet else f"GRIZZLY-{tour_counter}"
            vehicle_name = original_fleet.name if original_fleet and original_fleet.name else f"Camión {tour_counter}"

            stops_list: List[StopModel] = []
            points_for_geometry: List[Dict[str, float]] = [{"lat": depot_lat, "lon": depot_lon}]
            
            seq = 1
            for step in route.get("steps", []):
                step_type = step.get("type")
                if step_type == "job":
                    v_jid = step.get("id")
                    orig_job: Optional[JobDelivery] = job_map.get(v_jid)
                    if orig_job:
                        j_lat = orig_job.location.get_lat()
                        j_lon = orig_job.location.get_lon()

                        arrival_sec = step.get("arrival", 0)
                        arrival_fmt = time.strftime("%H:%M:%S", time.gmtime(arrival_sec)) if arrival_sec else ""

                        stops_list.append(StopModel(
                            id=orig_job.id,
                            sequence=seq,
                            location={"lat": j_lat, "lng": j_lon},
                            address=orig_job.address or "",
                            street=orig_job.street or orig_job.address or "",
                            arrival_time=arrival_fmt,
                            duration_seconds=step.get("duration", 0),
                            distance_meters=step.get("distance", 0)
                        ))
                        points_for_geometry.append({"lat": j_lat, "lon": j_lon})
                        seq += 1

            if not stops_list:
                continue

            # Retorno al depot solo si el vehículo tiene punto de fin explícito
            if original_fleet and original_fleet.end_location and original_fleet.end_location.get_lat() is not None:
                points_for_geometry.append({
                    "lat": original_fleet.end_location.get_lat(),
                    "lon": original_fleet.end_location.get_lon()
                })

            # 6. Obtener Geometría Real sobre Asfalto desde Valhalla
            polyline_str, coords_list, real_dur, real_dist = await get_route_geometry(points_for_geometry)

            tour_duration = real_dur if real_dur > 0 else int(route.get("duration", 0))
            tour_distance = real_dist if real_dist > 0 else int(route.get("distance", 0))

            all_tours.append(TourModel(
                vehicleId=vehicle_id,
                vehicleName=vehicle_name,
                stops=stops_list,
                polyline=polyline_str,
                coordinates=coords_list,
                summary=TourSummary(
                    duration=tour_duration,
                    distance=tour_distance,
                    deliveries=len(stops_list)
                )
            ))

            tour_counter += 1

    # 7. Estadísticas Globales
    total_dur = sum(t.summary.duration for t in all_tours)
    total_dist = sum(t.summary.distance for t in all_tours)
    total_deliv = sum(t.summary.deliveries for t in all_tours)

    elapsed = round(time.time() - start_bench, 2)

    return OptimizeResponse(
        ok=True,
        tours=all_tours,
        dropped=global_unassigned,
        statistic=GlobalStatistic(
            total_duration=total_dur,
            total_distance=total_dist,
            total_deliveries=total_deliv,
            total_vehicles_used=len(all_tours)
        ),
        message=f"Optimización completada con éxito en {elapsed}s usando {len(all_tours)} vehículo(s)."
    )

