"""
Descarga datos historicos de temperatura desde termometros SmartLife/Tuya.

Requisitos previos:
1. Instalar dependencias: pip install -r requirements.txt
2. Obtener credenciales de Tuya IoT Platform:
   - Ir a https://iot.tuya.com/ y crear cuenta de desarrollador
   - Crear un proyecto en Cloud Development
   - Obtener Access ID y Access Secret
   - Enlazar la app SmartLife al proyecto (Cloud > App SDK)
   - Obtener el Device ID y Local Key de cada dispositivo

3. Configurar las credenciales en un archivo .env o pasarlas como argumentos.

Uso:
    python src/download_tuya_data.py --access-id TU_ACCESS_ID --access-secret TU_ACCESS_SECRET --device-id DEVICE_ID --local-key LOCAL_KEY
    o con archivo .env:
    python src/download_tuya_data.py
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import tinytuya
except ImportError:
    print("Error: tinytuya no esta instalado. Ejecuta: pip install tinytuya")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATA_DIR = Path(__file__).parent.parent / "data"


def discover_devices():
    """Escanea la red local en busca de dispositivos Tuya."""
    print("Escaneando dispositivos Tuya en la red local...")
    devices = tinytuya.deviceScan()
    print(f"\nSe encontraron {len(devices)} dispositivos:\n")
    for dev in devices.values():
        print(f"  Nombre:     {dev.get('name', 'N/A')}")
        print(f"  Device ID:  {dev.get('id', 'N/A')}")
        print(f"  IP:         {dev.get('ip', 'N/A')}")
        print(f"  Version:    {dev.get('version', 'N/A')}")
        print(f"  Local Key:  {dev.get('key', 'N/A')}")
        print()
    return devices


def get_device_data(access_id, access_secret, device_id, local_key, ip=None):
    """Obtiene datos historicos de un dispositivo Tuya via API Cloud."""
    try:
        from tuya_iot import TuyaOpenAPI
    except ImportError:
        print("Error: tuya-iot-python-sdk no instalado. Ejecuta: pip install tuya-iot-python-sdk")
        print("Alternativamente, usa el modo local con --local")
        sys.exit(1)

    api = TuyaOpenAPI("https://openapi.tuyaus.com", access_id, access_secret)
    api.connect()

    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

    response = api.get(
        f"/v1.0/devices/{device_id}/logs",
        params={
            "start_time": start_time,
            "end_time": end_time,
            "size": 1000,
        }
    )

    return response


def get_device_data_local(device_id, local_key, ip, version="3.3"):
    """Obtiene datos en tiempo real de un dispositivo Tuya localmente."""
    device = tinytuya.Device(device_id, ip, local_key, version=version)
    device.set_dpsUsed({"1": None, "2": None})

    try:
        data = device.status()
        return data
    except Exception as e:
        print(f"Error conectando al dispositivo: {e}")
        return None


def save_data(data, filename, output_dir=DATA_DIR):
    """Guarda los datos en formato CSV y JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{filename}.json"
    csv_path = output_dir / f"{filename}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Datos guardados en: {json_path}")

    if isinstance(data, dict) and "result" in data and "logs" in data["result"]:
        logs = data["result"]["logs"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "dps", "value"])
            for log in logs:
                writer.writerow([log.get("time", ""), log.get("code", ""), log.get("value", "")])
        print(f"Datos CSV guardados en: {csv_path}")

    elif isinstance(data, dict) and "dps" in data:
        dps = data["dps"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["dps_id", "valor"])
            for key, value in dps.items():
                writer.writerow([key, value])
        print(f"Datos CSV guardados en: {csv_path}")

    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(description="Descarga datos de termometros SmartLife/Tuya")
    parser.add_argument("--access-id", default=os.getenv("TUYA_ACCESS_ID"), help="Tuya Access ID")
    parser.add_argument("--access-secret", default=os.getenv("TUYA_ACCESS_SECRET"), help="Tuya Access Secret")
    parser.add_argument("--device-id", default=os.getenv("TUYA_DEVICE_ID"), help="Device ID del termometro")
    parser.add_argument("--local-key", default=os.getenv("TUYA_LOCAL_KEY"), help="Local Key del dispositivo")
    parser.add_argument("--ip", default=os.getenv("TUYA_DEVICE_IP"), help="IP del dispositivo (modo local)")
    parser.add_argument("--local", action="store_true", help="Usar conexion local en vez de API Cloud")
    parser.add_argument("--discover", action="store_true", help="Solo escanear dispositivos en la red")
    parser.add_argument("--days", type=int, default=7, help="Dias de historial a descargar (solo API Cloud)")

    args = parser.parse_args()

    if args.discover:
        discover_devices()
        return

    if args.local:
        if not all([args.device_id, args.local_key, args.ip]):
            print("Error: Para modo local necesitas --device-id, --local-key y --ip")
            print("Usa --discover para encontrar tus dispositivos")
            sys.exit(1)
        data = get_device_data_local(args.device_id, args.local_key, args.ip)
        if data:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_data(data, f"tuya_local_{timestamp}")
    else:
        if not all([args.access_id, args.access_secret, args.device_id]):
            print("Error: Para API Cloud necesitas --access-id, --access-secret y --device-id")
            print("Configura las variables de entorno o pasa los argumentos:")
            print("  TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_DEVICE_ID")
            sys.exit(1)
        data = get_device_data(args.access_id, args.access_secret, args.device_id, args.local_key, args.ip)
        if data:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_data(data, f"tuya_cloud_{timestamp}")


if __name__ == "__main__":
    main()