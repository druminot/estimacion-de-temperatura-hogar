"""
Descarga datos historicos de temperatura desde Home Assistant.

Fuentes:
- Sensores Tuya/SmartLife (via HA)
- HomePod (via HA)
- Termostato R11-B (via HA)

Configuracion:
- HA_URL: URL de Home Assistant (default: http://192.168.1.123:8123)
- HA_TOKEN: Long-lived access token (en .env o variable de entorno)

Uso:
    python src/download_ha_data.py                     # Descargar ultimas 24h
    python src/download_ha_data.py --days 7            # Ultimos 7 dias
    python src/download_ha_data.py --days 30            # Ultimos 30 dias
    python src/download_ha_data.py --continuous         # Lectura continua cada 5 min
    python src/download_ha_data.py --list-sensors      # Listar sensores disponibles
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests no instalado. Ejecuta: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass

HA_URL = os.getenv("HA_URL", "http://192.168.1.123:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
DATA_DIR = Path(__file__).parent.parent / "data"

SENSORES_DEFAULT = [
    "sensor.t_h_sensor_temperature",
    "sensor.t_h_sensor_humidity",
    "sensor.energy_meter_temperature",
    "climate.r11_b_smart_wifi_thermostat",
    "sensor.temperatura_media_casa",
    "sensor.humedad_media_casa",
]


def ha_request(endpoint, params=None):
    """Hace una peticion a la API de Home Assistant."""
    if not HA_TOKEN:
        print("Error: HA_TOKEN no configurado. Agrega HA_TOKEN al archivo .env")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{HA_URL}/api/{endpoint}"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f"Error: No se pudo conectar a {HA_URL}")
        print("Verifica que Home Assistant este encendido y accesible")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Error: Token invalido o expirado. Genera uno nuevo en HA")
        else:
            print(f"Error HTTP: {e}")
        sys.exit(1)


def list_sensors():
    """Lista todos los sensores de temperatura y humedad disponibles."""
    data = ha_request("states")

    temp_keywords = ["temperat", "temp", "humid", "climate"]
    sensors = []
    for state in data:
        eid = state["entity_id"]
        attrs = state.get("attributes", {})
        device_class = attrs.get("device_class", "")
        unit = attrs.get("unit_of_measurement", "")
        friendly = attrs.get("friendly_name", "")

        if any(k in eid.lower() for k in temp_keywords) or device_class in ["temperature", "humidity"]:
            sensors.append({
                "entity_id": eid,
                "state": state["state"],
                "unit": unit,
                "friendly_name": friendly,
                "device_class": device_class,
            })

    print(f"\nSensores de temperatura/humedad encontrados ({len(sensors)}):\n")
    print(f"{'Entity ID':<55} {'Estado':>8} {'Unidad':>5}  {'Nombre'}")
    print("-" * 110)
    for s in sensors:
        print(f"{s['entity_id']:<55} {s['state']:>8} {s['unit']:>5}  {s['friendly_name']}")

    return [s["entity_id"] for s in sensors]


def download_history(sensors, start_date, end_date):
    """Descarga historial de sensores desde HA."""
    all_data = {}

    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    for sensor in sensors:
        print(f"Descargando: {sensor} ...", end=" ", flush=True)

        params = {
            "filter_entity_id": sensor,
            "end_time": end_str,
        }

        try:
            data = ha_request(f"history/period/{start_str}", params=params)

            if isinstance(data, list) and len(data) > 0:
                if isinstance(data[0], list):
                    records = data[0]
                else:
                    records = data

                valid_records = [
                    r for r in records
                    if r.get("state") not in ("unknown", "unavailable", "None", "")
                    and r.get("state") is not None
                ]

                all_data[sensor] = valid_records
                print(f"{len(valid_records)} registros")
            else:
                print("sin datos")
                all_data[sensor] = []
        except Exception as e:
            print(f"error: {e}")
            all_data[sensor] = []

    return all_data


def get_current_values(sensors):
    """Obtiene valores actuales de los sensores."""
    data = ha_request("states")
    current = {}

    for state in data:
        if state["entity_id"] in sensors:
            current[state["entity_id"]] = {
                "state": state["state"],
                "unit": state.get("attributes", {}).get("unit_of_measurement", ""),
                "friendly_name": state.get("attributes", {}).get("friendly_name", ""),
                "last_updated": state.get("last_updated", ""),
            }

    return current


def save_to_csv(all_data, filename, output_dir=DATA_DIR):
    """Guarda los datos en formato CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / filename

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "sensor", "valor", "unidad"])

        for sensor, records in all_data.items():
            for r in records:
                ts = r.get("last_updated", "")[:19]
                state = r.get("state", "")
                unit = r.get("attributes", {}).get("unit_of_measurement", "")
                writer.writerow([ts, sensor, state, unit])

    print(f"CSV guardado: {csv_path}")
    return csv_path


def save_to_json(all_data, filename, output_dir=DATA_DIR):
    """Guarda los datos en formato JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / filename

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"JSON guardado: {json_path}")
    return json_path


def continuous_read(sensors, interval_seconds=300):
    """Lee valores actuales continuamente y los agrega al CSV."""
    print(f"Lectura continua cada {interval_seconds}s. Ctrl+C para detener.\n")

    csv_path = DATA_DIR / "temperatura_hogar_live.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    file_exists = csv_path.exists()

    while True:
        try:
            current = get_current_values(sensors)

            timestamp = datetime.now().isoformat()[:19]

            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "sensor", "valor", "unidad"])
                    file_exists = True

                for sensor_id, data in current.items():
                    if data["state"] not in ("unknown", "unavailable"):
                        writer.writerow([
                            timestamp,
                            data.get("friendly_name", sensor_id),
                            data["state"],
                            data["unit"],
                        ])
                        print(f"  {timestamp} | {data.get('friendly_name', sensor_id):40s} | {data['state']:>6s} {data['unit']}")
                    else:
                        print(f"  {timestamp} | {data.get('friendly_name', sensor_id):40s} | sin dato")

            print()
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\nDetenido por el usuario.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description="Descarga datos de temperatura desde Home Assistant")
    parser.add_argument("--days", type=int, default=1, help="Dias de historial a descargar (default: 1)")
    parser.add_argument("--start", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--sensors", nargs="+", help="Sensores especificos a consultar")
    parser.add_argument("--list-sensors", action="store_true", help="Listar sensores disponibles")
    parser.add_argument("--continuous", action="store_true", help="Lectura continua")
    parser.add_argument("--interval", type=int, default=300, help="Intervalo en segundos para lectura continua")
    parser.add_argument("--output", help="Nombre del archivo de salida (sin extension)")
    parser.add_argument("--current", action="store_true", help="Solo leer valores actuales")

    args = parser.parse_args()

    sensors = args.sensors or SENSORES_DEFAULT

    if args.list_sensors:
        list_sensors()
        return

    if args.continuous:
        continuous_read(sensors, args.interval)
        return

    if args.current:
        current = get_current_values(sensors)
        print(f"\nValores actuales:\n")
        for sid, data in current.items():
            print(f"  {data.get('friendly_name', sid):45s} {data['state']:>8s} {data['unit']}")
        return

    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = datetime.now() - timedelta(days=args.days)

    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    print(f"Descargando historial desde {start_date.date()} hasta {end_date.date()}...\n")

    all_data = download_history(sensors, start_date, end_date)

    total = sum(len(v) for v in all_data.values())
    print(f"\nTotal: {total} registros descargados")

    if total == 0:
        print("No se encontraron datos. Verifica que los sensores tengan historial en HA.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = args.output or f"temperatura_hogar_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"

    save_to_json(all_data, f"{base_name}.json")
    save_to_csv(all_data, f"{base_name}.csv")


if __name__ == "__main__":
    main()