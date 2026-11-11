import numpy as np
from typing import List
from models.schemas import JobDelivery

def apply_sweep_partition(
    jobs: List[JobDelivery],
    depot_lat: float,
    depot_lon: float,
    batch_size: int = 1000
) -> List[List[JobDelivery]]:
    """
    Algoritmo de Barrido Radial (Sweep Algorithm):
    Ordena los pedidos angularmente (como las manecillas de un reloj o radar)
    desde el centro de distribución (Depot).

    Esto permite partir lotes masivos en grupos espacialmente continuos
    sin generar el efecto de 'fronteras invisibles' de K-Means, y protegiendo
    la memoria RAM del optimizador.
    """
    if len(jobs) <= batch_size:
        return [jobs]

    # Calcular el ángulo de cada punto respecto al Depot
    job_angles = []
    for job in jobs:
        d_lat = job.location.get_lat() - depot_lat
        d_lon = job.location.get_lon() - depot_lon
        angle = np.arctan2(d_lon, d_lat)
        job_angles.append((angle, job))

    # Ordenar por ángulo creciente
    job_angles.sort(key=lambda x: x[0])
    sorted_jobs = [item[1] for item in job_angles]

    # Partir en porciones de tamaño batch_size
    batches = []
    for i in range(0, len(sorted_jobs), batch_size):
        batches.append(sorted_jobs[i:i + batch_size])

    return batches

