# Dribling Routing Engine (Oso Grizzly) 🐻🚛

Microservicio de optimización logística masiva basado en **VROOM**, **Valhalla** y **FastAPI**. Diseñado para procesar lotes masivos de entregas (+1.000 a +3.000 paradas) minimizando la cantidad de camiones mediante costos fijos altos y particionado radial (Sweep Algorithm).

---

## 🚀 Arquitectura

* **Valhalla (C++)**: Motor de red vial basado en OpenStreetMap para matrices y geometrías de asfalto real.
* **VROOM (C++)**: Optimizador heurístico para resolver problemas VRP (Vehicle Routing Problem) de alta complejidad en segundos.
* **API FastAPI (Python)**:
  * Filtro geográfico **BBOX dinámico** (elimina coordenadas atípicas o fuera del país).
  * Algoritmo de **Barrido Radial (Sweep)** desde el Depot (evita desbordamientos de memoria en lotes masivos).
  * Inyección de **Costo Fijo** (`costs: {"fixed": 10000}`) para forzar el llenado de camiones al 100%.
  * Trazado de polilíneas reales de asfalto para la visualización en Dribling.

---

## 🛠️ Puesta en Marcha Local (Docker)

### 1. Configurar variables de entorno
Copiar el archivo de ejemplo:
```bash
cp .env.example .env
```
En `.env`, definir el país deseado (`chile` o `colombia`):
```env
ROUTING_COUNTRY=chile
PORT=8088
```

### 2. Descargar el mapa de OpenStreetMap
* En Linux / Mac / WSL:
  ```bash
  chmod +x scripts/download_map.sh
  ./scripts/download_map.sh
  ```
* En Windows:
  ```cmd
  scripts\download_map.bat
  ```

### 3. Levantar los Contenedores
```bash
docker-compose up -d --build
```

### 4. Verificar Salud del Servicio
Abrir en el navegador:
* Documentación Swagger: `http://localhost:8088/docs`
* Chequeo de Salud: `http://localhost:8088/health`

---

## ☁️ Despliegue en AWS EC2 (Producción)

### 1. Requisitos de la Instancia
* Tipo sugerido: **`t3.large`** (2 vCPU, 8 GB RAM) con **Ubuntu 22.04 LTS** o **24.04 LTS**.
* Disco: **30 a 50 GB gp3**.
* Puertos abiertos en Security Group: `22` (SSH), `80` (HTTP), `443` (HTTPS) y `8088`.

### 2. Comandos en la EC2:
```bash
# Actualizar e instalar Docker
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 curl
sudo usermod -aG docker $USER

# Clonar o subir esta carpeta a /opt/dribling-routing-service
cd /opt/dribling-routing-service

# Descargar el mapa de Chile (o Colombia)
chmod +x scripts/download_map.sh
./scripts/download_map.sh chile

# Levantar el servicio
docker compose up -d --build
```

---

## 📡 Integración con Dribling (Backend Laravel)

En el archivo `.env` de Dribling:
```env
ROUTING_SERVICE_URL=http://localhost:8088/api/v1
ROUTING_SERVICE_TOKEN=dribling_super_secret_token_2026
ROUTING_COUNTRY=chile
```
*(En producción cambiar la URL por `https://routing.tudominio.com/api/v1`)*.

