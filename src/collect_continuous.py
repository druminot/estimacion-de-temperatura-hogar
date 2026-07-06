"""
Recoleccion continua de datos de temperatura y clima.

Ejecuta lecturas periodicas de Home Assistant y almacena
los datos para mejorar el modelo predictivo.

Uso:
    python src/collect_continuous.py                # Lectura cada 5 min
    python src/collect_continuous.py --interval 10  # Cada 10 min
    python src/collect_continuous.py --once          # Solo una lectura
"""

import argparse
import csv
import json
import os
import signal
import sys
import time
from datetime import datetime
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

SENSORES_TEMPERATURA = [
    "sensor.t_h_sensor_temperature",
    "sensor.t_h_sensor_humidity",
    "sensor.energy_meter_temperature",
    "climate.r11_b_smart_wifi_thermostat",
]

SENSORES_CLIMA = [
    "weather.forecast_casa",
]

running = True


def signal_handler(sig, frame):
    global running
    print("\nDeteniendo...")
    running = False


signal.signal(signal.SIGINT, signal_handler)


def ha_request(endpoint):
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{HA_URL}/api/{endpoint}"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error en peticion HA: {e}")
        return None


def collect_reading():
    """Realiza una lectura de todos los sensores y la guarda en CSV."""
    data = ha_request("states")
    if not data:
        return None

    timestamp = datetime.now().isoformat()[:19]
    readings = []

    temp_sensors = {s["entity_id"]: s for s in data if s["entity_id"] in SENSORES_TEMPERATURA}
    weather_sensors = {s["entity_id"]: s for s in data if s["entity_id"] in SENSORES_CLIMA}

    for entity_id, state in temp_sensors.items():
        valor = state.get("state", "")
        if valor not in ("unknown", "unavailable", "None", ""):
            unit = state.get("attributes", {}).get("unit_of_measurement", "")
            readings.append({
                "timestamp": timestamp,
                "sensor": entity_id,
                "valor": float(valor) if valor.replace(".", "").replace("-", "").isdigit() else valor,
                "unidad": unit,
            })

    for entity_id, state in weather_sensors.items():
        attrs = state.get("attributes", {})
        temp = attrs.get("temperature")
        if temp is not None:
            readings.append({
                "timestamp": timestamp,
                "sensor": f"{entity_id}_temp",
                "valor": float(temp),
                "unidad": "°C",
            })
        humidity = attrs.get("humidity")
        if humidity is not None:
            readings.append({
                "timestamp": timestamp,
                "sensor": f"{entity_id}_humidity",
                "valor": float(humidity),
                "unidad": "%",
            })
        wind = attrs.get("wind_speed")
        if wind is not None:
            readings.append({
                "timestamp": timestamp,
                "sensor": f"{entity_id}_wind",
                "valor": float(wind),
                "unidad": "m/s",
            })

    return readings


def save_readings(readings, csv_path):
    """Guarda las lecturas en el CSV continuo."""
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "sensor", "valor", "unidad"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(readings)


def main():
    parser = argparse.ArgumentParser(description="Recoleccion continua de datos")
    parser.add_argument("--interval", type=int, default=5, help="Intervalo en minutos (default: 5)")
    parser.add_argument("--once", action="store_true", help="Solo una lectura")
    args = parser.parse_args()

    if not HA_TOKEN:
        print("Error: HA_TOKEN no configurado. Agrega HA_TOKEN al archivo .env")
        sys.exit(1)

    csv_path = DATA_DIR / "temperatura_hogar_live.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    interval_seconds = args.interval * 60

    print(f"Recoleccion continua cada {args.interval} min")
    print(f"Archivo: {csv_path}")
    print(f"Presiona Ctrl+C para detener\n")

    count = 0
    errors = 0

    while running:
        try:
            readings = collect_reading()
            if readings:
                save_readings(readings, csv_path)
                count += len(readings)

                for r in readings:
                    print(f"  {r['timestamp']} | {r['sensor']:50s} | {r['valor']:>8} {r['unidad']}")
                print(f"  [{count} lecturas totales, {errors} errores]")
            else:
                errors += 1
                print(f"  Sin datos ({errors} errores)")

            if args.once:
                break

            time.sleep(interval_seconds)

        except Exception as e:
            errors += 1
            print(f"Error: {e}")
            time.sleep(30)

    print(f"\nRecoleccion finalizada: {count} lecturas, {errors} errores")


if __name__ == "__main__":
    main()