from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

class LatLng(BaseModel):
    lat: float
    lng: Optional[float] = None
    lon: Optional[float] = None

    def get_lat(self) -> float:
        return self.lat

    def get_lon(self) -> float:
        return self.lng if self.lng is not None else (self.lon if self.lon is not None else 0.0)

class DepotModel(BaseModel):
    lat: float
    lng: Optional[float] = None
    lon: Optional[float] = None
    name: Optional[str] = "Centro de Distribución"

    def get_lat(self) -> float:
        return self.lat

    def get_lon(self) -> float:
        return self.lng if self.lng is not None else (self.lon if self.lon is not None else 0.0)

class FleetVehicle(BaseModel):
    id: Union[str, int]
    name: Optional[str] = None
    start_location: Optional[LatLng] = None
    end_location: Optional[LatLng] = None
    capacity: Optional[int] = 100
    capacity_weight_kg: Optional[int] = 1500
    capacity_volume_dm3: Optional[int] = 12000
    capacity_bultos: Optional[int] = 100
    caja_largo_cm: Optional[int] = 320
    caja_ancho_cm: Optional[int] = 180
    caja_alto_cm: Optional[int] = 190
    factor_estiba: Optional[float] = 0.85
    puerta_ancho_cm: Optional[int] = 170
    puerta_alto_cm: Optional[int] = 180
    tipo_puerta: Optional[int] = 1
    start_time: Optional[str] = "08:00"
    end_time: Optional[str] = "19:00"

class JobDelivery(BaseModel):
    id: Union[str, int]
    location: LatLng
    amount: Optional[int] = 1
    weight_kg: Optional[int] = 1
    volume_dm3: Optional[int] = 10
    cant_bultos: Optional[int] = 1
    bultos: Optional[List[Dict[str, Any]]] = None
    service_time: Optional[int] = 180  # 3 minutos por parada
    description: Optional[str] = None
    address: Optional[str] = None
    street: Optional[str] = None

class OptimizationConfig(BaseModel):
    country: Optional[str] = None
    max_capacity: Optional[int] = 100
    service_time: Optional[int] = 180
    fixed_cost: Optional[int] = 10000
    use_capacity: Optional[bool] = True
    sweep_batch_size: Optional[int] = 1000
    use_sweep: Optional[bool] = True
    max_radius_km: Optional[float] = 150.0  # Radio máximo alrededor del depot

class OptimizeRequest(BaseModel):
    depot: Optional[DepotModel] = None
    fleets: List[FleetVehicle]
    jobs: List[JobDelivery]
    config: Optional[OptimizationConfig] = Field(default_factory=OptimizationConfig)
    asistente_id: Optional[int] = 4

# Modelos de Respuesta compatibles con Dribling
class StopModel(BaseModel):
    id: Union[str, int]
    sequence: int
    location: Dict[str, float]
    address: Optional[str] = ""
    street: Optional[str] = ""
    arrival_time: Optional[str] = ""
    duration_seconds: Optional[int] = 0
    distance_meters: Optional[int] = 0

class TourSummary(BaseModel):
    duration: int = 0
    distance: int = 0
    deliveries: int = 0

class TourModel(BaseModel):
    vehicleId: Union[str, int]
    vehicleName: Optional[str] = ""
    stops: List[StopModel]
    polyline: Optional[str] = ""
    coordinates: Optional[List[List[float]]] = None
    summary: TourSummary

class GlobalStatistic(BaseModel):
    total_duration: int = 0
    total_distance: int = 0
    total_deliveries: int = 0
    total_vehicles_used: int = 0

class OptimizeResponse(BaseModel):
    ok: bool = True
    tours: List[TourModel] = []
    dropped: List[Dict[str, Any]] = []
    statistic: GlobalStatistic
    message: Optional[str] = "Ruta optimizada con éxito"

