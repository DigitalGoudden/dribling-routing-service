@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "TARGET_DIR=%PROJECT_DIR%\valhalla_data"

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

set "COUNTRY=%1"
if "%COUNTRY%"=="" (
  if exist "%PROJECT_DIR%\.env" (
    for /f "tokens=1,2 delims==" %%A in (%PROJECT_DIR%\.env) do (
      if "%%A"=="ROUTING_COUNTRY" set "COUNTRY=%%B"
    )
  )
)
if "%COUNTRY%"=="" set "COUNTRY=chile"

echo ==========================================
echo  Descargador de Mapas OpenStreetMap (Valhalla)
echo  Pais seleccionado: %COUNTRY%
echo  Directorio destino: %TARGET_DIR%
echo ==========================================

if /i "%COUNTRY%"=="chile" (
  set "URL=https://download.geofabrik.de/south-america/chile-latest.osm.pbf"
  set "FILE_NAME=chile-latest.osm.pbf"
) else if /i "%COUNTRY%"=="colombia" (
  set "URL=https://download.geofabrik.de/south-america/colombia-latest.osm.pbf"
  set "FILE_NAME=colombia-latest.osm.pbf"
) else (
  set "URL=https://download.geofabrik.de/south-america/%COUNTRY%-latest.osm.pbf"
  set "FILE_NAME=%COUNTRY%-latest.osm.pbf"
)

set "TARGET_FILE=%TARGET_DIR%\%FILE_NAME%"

if exist "%TARGET_FILE%" (
  echo El archivo %FILE_NAME% ya existe en %TARGET_DIR%.
  echo Conservando mapa existente.
  goto end
)

echo Descargando desde %URL%...
curl -L "%URL%" -o "%TARGET_FILE%"

echo ==========================================
echo  Descarga completada con exito.
echo  Archivo guardado en: %TARGET_FILE%
echo ==========================================

:end
pause

