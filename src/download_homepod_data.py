"""
Descarga datos de temperatura desde HomePod via HomeKit.

Requisitos previos:
1. Instalar dependencias: pip install -r requirements.txt
2. Emparejar el HomePod con el script (primera vez):
   python src/download_homepod_data.py --pair
3. Los datos se guardan en la carpeta data/

Uso:
    python src/download_homepod_data.py --pair          # Primera vez, para emparejar
    python src/download_homepod_data.py                  # Leer temperatura actual
    python src/download_homepod_data.py --continuous     # Lectura continua cada N segundos
    python src/download_homepod_data.py --history        # Intentar obtener historial
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from homekit import HomeKit
    from homekit.exceptions import AccessoryNotFoundError
except ImportError:
    try:
        from homekit_python import HomeKit
    except ImportError:
        print("Error: homekit no esta instalado. Ejecuta: pip install homekit")
        sys.exit(1)

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIG_PATH = Path(__file__).parent.parent / "homekit_config.json"


def create_default_config():
    """Crea configuracion por defecto para HomeKit."""
    config = {
        "accessories": {}
    }
    return config


def discover_accessories():
    """Busca accesorios HomeKit en la red local."""
    print("Buscando accesorios HomeKit en la red...")
    print("Esto puede tardar unos segundos...\n")

    try:
        from homekit import discover
        results = discover()
        for name, info in results.items():
            print(f"  Nombre: {name}")
            print(f"  ID:    {info.get('id', 'N/A')}")
            print(f"  IP:    {info.get('address', 'N/A')}")
            print(f"  Port:  {info.get('port', 'N/A')}")
            print()
        return results
    except Exception as e:
        print(f"Error al descubrir accesorios: {e}")
        return {}


def pair_accessory(device_id, pin, ip, port=51826):
    """Empareja un accesorio HomeKit."""
    try:
        from homekit import Controller
        controller = Controller()

        pairing_data = controller.perform_pairing(
            name="homepod-temp",
            device_id=device_id,
            pin=pin,
            ip=ip,
            port=port
        )

        config = {
            "homepod-temp": pairing_data
        }

        config_path = CONFIG_PATH
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        print(f"Emparejamiento exitoso. Config guardada en {config_path}")
        return pairing_data

    except Exception as e:
        print(f"Error al emparejar: {e}")
        print("\nAsegurate de:")
        print("1. Que el HomePod este encendido y en la misma red WiFi")
        print("2. Que el codigo PIN sea correcto (aparece en la app Casa/Home)")
        return None


def get_temperature(config_path=CONFIG_PATH):
    """Lee la temperatura actual del HomePod."""
    if not config_path.exists():
        print(f"Error: No se encontro config en {config_path}")
        print("Ejecuta primero con --pair para emparejar el dispositivo")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    try:
        controller = Controller()
        for alias, data in config.items():
            controller.load_data(alias, data)

        for alias in config:
            try:
                accessories = controller.get_accessory_info(alias)
                print(f"Accesorio: {alias}")
                print(f"Info: {json.dumps(accessories, indent=2)}")

                characteristics = controller.list_characteristics_and_values(alias)
                for char in characteristics:
                    if char.get("type") in ["CurrentTemperature", "Temperature"]:
                        print(f"Temperatura: {char.get('value')} {char.get('unit', '°C')}")
                        return {
                            "timestamp": datetime.now().isoformat(),
                            "temperature": char.get("value"),
                            "unit": char.get("unit", "°C"),
                            "device": alias
                        }
            except Exception as e:
                print(f"Error leyendo {alias}: {e}")

    except Exception as e:
        print(f"Error: {e}")
        print("Puede que necesites re-emparejar el dispositivo")

    return None


def save_temperature_data(data, output_dir=DATA_DIR):
    """Guarda datos de temperatura en CSV y JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"homepod_temp_{timestamp}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Datos guardados en: {json_path}")

    csv_path = output_dir / "homepod_temperatures.csv"
    file_exists = csv_path.exists()

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "temperatura", "unidad", "dispositivo"])
        writer.writerow([
            data.get("timestamp", ""),
            data.get("temperature", ""),
            data.get("unit", ""),
            data.get("device", "")
        ])
    print(f"Datos CSV guardados en: {csv_path}")

    return json_path, csv_path


def continuous_read(interval_seconds=300):
    """Lee temperatura continuamente cada N segundos."""
    print(f"Leyendo temperatura cada {interval_seconds} segundos (Ctrl+C para detener)...")
    while True:
        try:
            data = get_temperature()
            if data:
                save_temperature_data(data)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Temp: {data['temperature']}{data.get('unit', '°C')}")
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nDetenido por el usuario.")
            break


def main():
    parser = argparse.ArgumentParser(description="Descarga datos de temperatura desde HomePod via HomeKit")
    parser.add_argument("--pair", action="store_true", help="Emparejar un nuevo dispositivo")
    parser.add_argument("--discover", action="store_true", help="Buscar accesorios HomeKit en la red")
    parser.add_argument("--device-id", help="Device ID del HomePod para emparejar")
    parser.add_argument("--pin", help="Codigo PIN del HomePod (8 digitos)")
    parser.add_argument("--ip", help="IP del HomePod")
    parser.add_argument("--port", type=int, default=51826, help="Puerto del HomePod")
    parser.add_argument("--continuous", action="store_true", help="Lectura continua")
    parser.add_argument("--interval", type=int, default=300, help="Intervalo en segundos para lectura continua")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Ruta al archivo de configuracion")

    args = parser.parse_args()

    if args.discover:
        discover_accessories()
        return

    if args.pair:
        if not all([args.device_id, args.pin, args.ip]):
            print("Error: Necesitas --device-id, --pin y --ip para emparejar")
            print("Usa --discover para encontrar tu HomePod")
            sys.exit(1)
        pair_accessory(args.device_id, args.pin, args.ip, args.port)
        return

    if args.continuous:
        continuous_read(args.interval)
        return

    data = get_temperature(args.config)
    if data:
        save_temperature_data(data)


if __name__ == "__main__":
    main()