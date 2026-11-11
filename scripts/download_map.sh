#!/usr/bin/env bash
set -e

# Leer país desde argumento o desde .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="$PROJECT_DIR/valhalla_data"

mkdir -p "$TARGET_DIR"

COUNTRY="${1:-chile}"
if [ -f "$PROJECT_DIR/.env" ]; then
  # Extraer ROUTING_COUNTRY si no se pasó por argumento
  if [ -z "$1" ]; then
    ENV_COUNTRY=$(grep -E '^ROUTING_COUNTRY=' "$PROJECT_DIR/.env" | cut -d '=' -f2 | tr -d ' \r\n"')
    if [ -n "$ENV_COUNTRY" ]; then
      COUNTRY="$ENV_COUNTRY"
    fi
  fi
fi

COUNTRY_LOWER=$(echo "$COUNTRY" | tr '[:upper:]' '[:lower:]')

echo "=========================================="
echo " Descargador de Mapas OpenStreetMap (Valhalla)"
echo " País seleccionado: $COUNTRY_LOWER"
echo " Directorio destino: $TARGET_DIR"
echo "=========================================="

case "$COUNTRY_LOWER" in
  chile)
    URL="https://download.geofabrik.de/south-america/chile-latest.osm.pbf"
    FILE_NAME="chile-latest.osm.pbf"
    ;;
  colombia)
    URL="https://download.geofabrik.de/south-america/colombia-latest.osm.pbf"
    FILE_NAME="colombia-latest.osm.pbf"
    ;;
  antioquia)
    URL="https://download.geofabrik.de/south-america/colombia/antioquia-latest.osm.pbf"
    FILE_NAME="antioquia-latest.osm.pbf"
    ;;
  bogota)
    URL="https://download.geofabrik.de/south-america/colombia/bogota-latest.osm.pbf"
    FILE_NAME="bogota-latest.osm.pbf"
    ;;
  *)
    echo "País personalizado: buscando en Geofabrik south-america/$COUNTRY_LOWER-latest.osm.pbf..."
    URL="https://download.geofabrik.de/south-america/${COUNTRY_LOWER}-latest.osm.pbf"
    FILE_NAME="${COUNTRY_LOWER}-latest.osm.pbf"
    ;;
esac

TARGET_FILE="$TARGET_DIR/$FILE_NAME"

if [ -f "$TARGET_FILE" ]; then
  echo "El archivo $FILE_NAME ya existe en $TARGET_DIR."
  read -p "¿Deseas volver a descargarlo? (s/N): " RESP
  if [[ "$RESP" =~ ^[sS]$ ]]; then
    rm -f "$TARGET_FILE"
  else
    echo "Conservando mapa existente."
    exit 0
  fi
fi

echo "Descargando desde $URL..."
if command -v curl &> /dev/null; then
  curl -L "$URL" -o "$TARGET_FILE"
elif command -v wget &> /dev/null; then
  wget -O "$TARGET_FILE" "$URL"
else
  echo "Error: Se requiere 'curl' o 'wget' para descargar el archivo."
  exit 1
fi

echo "=========================================="
echo " Descarga completada con éxito."
echo " Archivo guardado en: $TARGET_FILE"
echo " Al levantar 'docker compose up -d', Valhalla compilará los tiles automáticamente."
echo "=========================================="

