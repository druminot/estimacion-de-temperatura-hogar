"""
Descarga datos meteorologicos de OpenWeatherMap API.

Se usa para correlacionar la temperatura exterior con la tasa
de enfriamiento del hogar y mejorar el modelo predictivo.

Configuracion:
- OPENWEATHER_API_KEY: API key de OpenWeatherMap (en .env)
- OPENWEATHER_LAT/LON: Coordenadas (default: Santiago, Chile)
- OPENWEATHER_UNITS: metric/imperial (default: metric)

Uso:
    python src/download_weather.py                     # Datos actuales
    python src/download_weather.py --history 5          # Ultimos 5 dias (plan gratuito)
    python src/download_weather.py --continuous          # Lectura cada 30 min
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

API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
LAT = os.getenv("OPENWEATHER_LAT", "-33.45")
LON = os.getenv("OPENWEATHER_LON", "-70.67")
UNITS = os.getenv("OPENWEATHER_UNITS", "metric")
DATA_DIR = Path(__file__).parent.parent / "data"

BASE_URL = "https://api.openweathermap.org/data/3.0"
BASE_URL_25 = "https://api.openweathermap.org/data/2.5"


def get_current_weather():
    """Obtiene el clima actual."""
    if not API_KEY:
        print("Error: OPENWEATHER_API_KEY no configurada.")
        print("Obtén una gratis en: https://openweathermap.org/api")
        print("Luego agrega OPENWEATHER_API_KEY=tu_key al archivo .env")
        sys.exit(1)

    url = f"{BASE_URL_25}/weather"
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": API_KEY,
        "units": UNITS,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = {
            "timestamp": datetime.now().isoformat(),
            "temp": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "temp_min": data["main"]["temp_min"],
            "temp_max": data["main"]["temp_max"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "description": data["weather"][0]["description"],
            "wind_speed": data["wind"]["speed"],
            "clouds": data["clouds"]["all"],
            "dt": data["dt"],
        }

        print(f"Clima actual ({data['name']}):")
        print(f"  Temperatura: {result['temp']}°C")
        print(f"  Sensacion: {result['feels_like']}°C")
        print(f"  Min/Max: {result['temp_min']}/{result['temp_max']}°C")
        print(f"  Humedad: {result['humidity']}%")
        print(f"  Viento: {result['wind_speed']} m/s")
        print(f"  Descripcion: {result['description']}")

        return result

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Error: API key invalida. Verifica OPENWEATHER_API_KEY en .env")
        elif e.response.status_code == 429:
            print("Error: Limite de peticiones excedido. Espera un momento.")
        else:
            print(f"Error HTTP: {e}")
        sys.exit(1)


def get_historical_weather(days=5):
    """
    Obtiene datos historicos usando la API One Call.

    El plan gratuito permite hasta 5 dias de historial.
    """
    if not API_KEY:
        print("Error: OPENWEATHER_API_KEY no configurada.")
        sys.exit(1)

    url = f"{BASE_URL}/onecall/timemachine"

    all_data = []
    now = datetime.now(timezone.utc)

    for day_offset in range(days):
        dt = now - timedelta(days=day_offset + 1)
        params = {
            "lat": LAT,
            "lon": LON,
            "appid": API_KEY,
            "units": UNITS,
            "dt": int(dt.timestamp()),
        }

        try:
            print(f"Descargando: {dt.strftime('%Y-%m-%d')}...", end=" ", flush=True)
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 401:
                print("API key invalida")
                sys.exit(1)
            elif response.status_code == 429:
                print("Limite excedido, esperando 60s...")
                time.sleep(60)
                response = requests.get(url, params=params, timeout=30)

            response.raise_for_status()
            data = response.json()

            hourly = data.get("data", [])
            for h in hourly:
                all_data.append({
                    "timestamp": datetime.fromtimestamp(h["dt"], tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    "temp": h.get("temp"),
                    "feels_like": h.get("feels_like"),
                    "humidity": h.get("humidity"),
                    "pressure": h.get("pressure"),
                    "wind_speed": h.get("wind_speed"),
                    "clouds": h.get("clouds"),
                    "description": h.get("weather", [{}])[0].get("description", ""),
                })

            print(f"{len(hourly)} registros")

            if day_offset < days - 1:
                time.sleep(1)

        except Exception as e:
            print(f"error: {e}")
            continue

    return all_data


def get_forecast():
    """Obtiene pronostico de 5 dias (cada 3 horas)."""
    if not API_KEY:
        print("Error: OPENWEATHER_API_KEY no configurada.")
        sys.exit(1)

    url = f"{BASE_URL_25}/forecast"
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": API_KEY,
        "units": UNITS,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        forecast = []
        for item in data["list"]:
            forecast.append({
                "timestamp": item["dt_txt"],
                "temp": item["main"]["temp"],
                "feels_like": item["main"]["feels_like"],
                "temp_min": item["main"]["temp_min"],
                "temp_max": item["main"]["temp_max"],
                "humidity": item["main"]["humidity"],
                "description": item["weather"][0]["description"],
                "wind_speed": item["wind"]["speed"],
                "clouds": item["clouds"]["all"],
                "pop": item.get("pop", 0),
            })

        return forecast

    except Exception as e:
        print(f"Error: {e}")
        return []


def save_weather_csv(data, filename, output_dir=DATA_DIR):
    """Guarda datos meteorologicos en CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / filename

    if not data:
        print("No hay datos para guardar")
        return csv_path

    fieldnames = list(data[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"CSV guardado: {csv_path} ({len(data)} registros)")
    return csv_path


def continuous_read(interval_minutes=30):
    """Lee el clima actual continuamente y lo agrega al CSV."""
    print(f"Lectura continua cada {interval_minutes} min. Ctrl+C para detener.\n")

    csv_path = DATA_DIR / "weather_live.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp", "temp", "feels_like", "temp_min", "temp_max",
        "humidity", "pressure", "description", "wind_speed", "clouds", "dt",
    ]

    while True:
        try:
            weather = get_current_weather()

            file_exists = csv_path.exists()
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(weather)

            print(f"  Guardado: {weather['temp']}°C\n")

            time.sleep(interval_minutes * 60)

        except KeyboardInterrupt:
            print("\nDetenido por el usuario.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Descarga datos meteorologicos de OpenWeatherMap")
    parser.add_argument("--history", type=int, help="Dias de historial a descargar (max 5, plan gratuito)")
    parser.add_argument("--forecast", action="store_true", help="Pronostico de 5 dias")
    parser.add_argument("--continuous", action="store_true", help="Lectura continua cada 30 min")
    parser.add_argument("--interval", type=int, default=30, help="Intervalo en minutos para lectura continua")
    parser.add_argument("--output", help="Nombre del archivo de salida")
    args = parser.parse_args()

    if args.continuous:
        continuous_read(args.interval)
        return

    if args.forecast:
        print("Descargando pronostico...\n")
        forecast = get_forecast()
        if forecast:
            filename = args.output or f"weather_forecast_{datetime.now().strftime('%Y%m%d')}.csv"
            save_weather_csv(forecast, filename)
        return

    if args.history:
        print(f"Descargando historial de {args.history} dias...\n")
        data = get_historical_weather(args.history)
        if data:
            filename = args.output or f"weather_history_{datetime.now().strftime('%Y%m%d')}.csv"
            save_weather_csv(data, filename)
        return

    weather = get_current_weather()
    if weather:
        filename = args.output or f"weather_current_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        save_weather_csv([weather], filename)


if __name__ == "__main__":
    main()