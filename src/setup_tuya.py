"""
Configuracion inicial de Tuya Cloud para obtener local keys.

PASOS (5 minutos):

1. Ir a https://iot.tuya.com/ y registrarse (usar misma cuenta que SmartLife)

2. Crear un proyecto Cloud:
   - Ir a Cloud Development -> Create Project
   - Nombre: "estimacion-temperatura" (o cualquiera)
   - Seleccionar "Smart Home" como industry
   - Region: Americas (us) o la que corresponda
   - Metodo de autorizacion: Custom

3. Vincular la app SmartLife:
   - En el proyecto, ir a "Link App" o "Devices"
   - Escanear el codigo QR con la app SmartLife
   - Esto vincula todos tus dispositivos

4. Activar las APIs necesarias:
   - Ir a Service API -> IoT Core -> Subscribe (gratis)
   - Ir a Service API -> Authorization -> Subscribe (gratis)

5. Obtener credenciales:
   - En el proyecto, copiar Access ID y Access Secret
   - Anotar tu region (us, eu, cn, etc.)

6. Ejecutar este script:
   python src/setup_tuya.py --access-id TU_ACCESS_ID --access-secret TU_ACCESS_SECRET --region us

Esto descargara todos los local keys y nombres de dispositivos.
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import tinytuya
except ImportError:
    print("Error: tinytuya no instalado. Ejecuta: pip install tinytuya")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent.parent
DEVICES_FILE = PROJECT_ROOT / "devices.json"


def setup_tuya_cloud(access_id, access_secret, region="us"):
    """Se conecta a Tuya Cloud y obtiene los datos de todos los dispositivos."""
    print(f"\nConectando a Tuya Cloud ({region})...")

    try:
        cloud = tinytuya.Cloud(
            apiRegion=region,
            apiKey=access_id,
            apiSecret=access_secret,
            apiDeviceID=access_id,
        )
        print("Conexion exitosa!\n")
    except Exception as e:
        print(f"Error de conexion: {e}")
        print("\nVerifica:")
        print("  - Access ID y Access Secret correctos")
        print("  - Region correcta (us, eu, cn, etc.)")
        print("  - APIs IoT Core y Authorization activadas")
        return False

    print("Obteniendo lista de dispositivos...")
    try:
        devices = cloud.getdevices()
        if not devices:
            print("No se encontraron dispositivos.")
            print("Asegurate de vincular tu app SmartLife al proyecto en iot.tuya.com")
            return False

        print(f"\nSe encontraron {len(devices)} dispositivos:\n")
        print(f"{'Nombre':35s} {'Device ID':25s} {'Local Key':20s} {'Categoria':15s} {'Online'}")
        print("-" * 120)

        for dev in devices:
            name = dev.get("name", "Sin nombre")
            dev_id = dev.get("id", "")
            local_key = dev.get("local_key", "")
            category = dev.get("category", "")
            online = dev.get("online", False)

            print(f"{name:35s} {dev_id:25s} {local_key:20s} {category:15s} {'Si' if online else 'No'}")

        devices_path = PROJECT_ROOT / "devices.json"
        with open(devices_path, "w") as f:
            json.dump(devices, f, indent=2, ensure_ascii=False)
        print(f"\nDispositivos guardados en: {devices_path}")

        print("\nObteniendo IPs locales...")
        scan = tinytuya.deviceScan(max_time=10)
        for dev in devices:
            dev_id = dev.get("id", "")
            if dev_id in scan:
                dev["ip"] = scan[dev_id].get("ip", "")
                dev["ver"] = scan[dev_id].get("version", "")

        with open(devices_path, "w") as f:
            json.dump(devices, f, indent=2, ensure_ascii=False)
        print(f"IPs actualizadas en: {devices_path}")

        config = {
            "apiKey": access_id,
            "apiSecret": access_secret,
            "apiRegion": region,
            "apiDeviceID": access_id,
        }
        config_path = PROJECT_ROOT / "tinytuya.json"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"Credenciales guardadas en: {config_path}")

        print("\n" + "=" * 60)
        print("Setup completado! Ahora puedes ejecutar:")
        print("  python src/download_tuya_data.py --local --tuya-ip IP \\")
        print("    --tuya-device-id DEVICE_ID --tuya-local-key LOCAL_KEY")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"Error obteniendo dispositivos: {e}")
        return False


def list_devices():
    """Lista los dispositivos guardados localmente."""
    if not DEVICES_FILE.exists():
        print("No se encontro devices.json. Ejecuta setup_tuya primero.")
        return

    with open(DEVICES_FILE) as f:
        devices = json.load(f)

    print(f"\nDispositivos guardados ({len(devices)}):\n")
    for dev in devices:
        name = dev.get("name", "Sin nombre")
        dev_id = dev.get("id", "")
        local_key = dev.get("local_key", "")
        ip = dev.get("ip", "IP desconocida")
        ver = dev.get("ver", dev.get("version", "?"))
        online = dev.get("online", False)
        category = dev.get("category", "")

        is_temp = any(kw in category.lower() for kw in ["temp", "wsdcg", "sensor", "thermostat"]) or \
                   "temperat" in name.lower() or "term" in name.lower() or "sensor" in name.lower()

        marker = " <<< TERMOMETRO" if is_temp else ""
        print(f"  {name:30s} | {dev_id:25s} | {local_key:20s} | {ip:15s} | v{ver}{marker}")

    print(f"\nPara leer un dispositivo:")
    print(f"  python src/download_tuya_data.py --local \\")
    print(f"    --tuya-ip IP --tuya-device-id DEVICE_ID --tuya-local-key LOCAL_KEY")


def test_device(device_id, local_key, ip, version="3.3"):
    """Prueba la conexion local a un dispositivo y muestra sus datos."""
    print(f"\nConectando a {device_id} en {ip}...")

    try:
        d = tinytuya.Device(device_id, ip, local_key, version=float(version))
        data = d.status()

        if "Error" in data:
            print(f"Error: {data['Error']}")
            print("Prueba con otra version (3.3, 3.4, 3.5)")
            return None

        print("Conexion exitosa! Datos del dispositivo:\n")
        if "dps" in data:
            for dp_id, value in data["dps"].items():
                print(f"  DP {dp_id:>3s}: {value}")

        return data

    except Exception as e:
        print(f"Error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Configuracion de Tuya Cloud para obtener local keys y datos de dispositivos"
    )
    parser.add_argument("--access-id", help="Tuya Cloud Access ID")
    parser.add_argument("--access-secret", help="Tuya Cloud Access Secret")
    parser.add_argument("--region", default="us", choices=["cn", "us", "us-e", "eu", "eu-w", "sg", "in"],
                        help="Region de Tuya Cloud (default: us)")
    parser.add_argument("--list", action="store_true", help="Listar dispositivos guardados")
    parser.add_argument("--test", action="store_true", help="Probar conexion a un dispositivo")
    parser.add_argument("--device-id", help="Device ID para probar")
    parser.add_argument("--local-key", help="Local Key para probar")
    parser.add_argument("--ip", help="IP del dispositivo para probar")
    parser.add_argument("--version", default="3.3", help="Version del protocolo (3.1-3.5)")

    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    if args.test:
        if not all([args.device_id, args.local_key, args.ip]):
            print("Error: Necesitas --device-id, --local-key y --ip para probar")
            sys.exit(1)
        test_device(args.device_id, args.local_key, args.ip, args.version)
        return

    if not args.access_id or not args.access_secret:
        print("""
========================================
SETUP DE TUYA CLOUD - Paso a Paso
========================================

Para obtener el historial completo de SmartLife necesitas
crear una cuenta GRATUITA en Tuya IoT Platform:

1. Ve a https://iot.tuya.com/ y registrate
   (puedes usar la misma cuenta que SmartLife)

2. Crea un proyecto Cloud:
   - Cloud Development -> Create Project
   - Nombre: cualquiera (ej: "mi-casa")
   - Industry: Smart Home
   - Region: la que corresponda (us para Americas)

3. Vincula tu app SmartLife:
   - Dentro del proyecto, ve a "Devices" -> "Link App"
   - Escanea el codigo QR con la app SmartLife
   - Esto importara todos tus dispositivos

4. Activa las APIs (gratis):
   - Service API -> IoT Core -> Subscribe
   - Service API -> Authorization -> Subscribe

5. Copia tus credenciales:
   - Access ID y Access Secret del proyecto

6. Ejecuta este script con tus credenciales:
   python src/setup_tuya.py --access-id TU_ACCESS_ID --access-secret TU_ACCESS_SECRET --region us
""")
        sys.exit(0)

    setup_tuya_cloud(args.access_id, args.access_secret, args.region)


if __name__ == "__main__":
    main()