"""
Script principal para descargar datos de temperatura de todas las fuentes.

Fuentes soportadas:
- SmartLife/Tuya (termometros)
- HomePod (sensor de temperatura HomeKit)

Uso:
    python src/main.py --all              # Descargar de todas las fuentes
    python src/main.py --tuya             # Solo SmartLife/Tuya
    python src/main.py --homepod          # Solo HomePod
    python src/main.py --discover         # Escanear dispositivos en la red
    python src/main.py --continuous       # Lectura continua de todas las fuentes
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SRC_DIR = Path(__file__).parent


def run_script(script_name, extra_args=None):
    """Ejecuta un script de descarga como subproceso."""
    script_path = SRC_DIR / script_name
    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'='*60}")
    print(f"Ejecutando: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except FileNotFoundError:
        print(f"Error: No se encontro el script {script_path}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Estimacion de Temperatura Hogar - Descarga de datos"
    )
    parser.add_argument("--all", action="store_true", help="Descargar de todas las fuentes")
    parser.add_argument("--tuya", action="store_true", help="Solo SmartLife/Tuya")
    parser.add_argument("--homepod", action="store_true", help="Solo HomePod")
    parser.add_argument("--discover", action="store_true", help="Escanear dispositivos")
    parser.add_argument("--continuous", action="store_true", help="Lectura continua")
    parser.add_argument("--interval", type=int, default=300, help="Intervalo en segundos para lectura continua")
    parser.add_argument("--tuya-access-id", help="Tuya Access ID")
    parser.add_argument("--tuya-access-secret", help="Tuya Access Secret")
    parser.add_argument("--tuya-device-id", help="Tuya Device ID")
    parser.add_argument("--tuya-local-key", help="Tuya Local Key")
    parser.add_argument("--tuya-ip", help="Tuya Device IP")
    parser.add_argument("--tuya-local", action="store_true", help="Tuya modo local")
    parser.add_argument("--homepod-pin", help="HomePod PIN (para emparejar)")
    parser.add_argument("--homepod-ip", help="HomePod IP")

    args = parser.parse_args()

    if not any([args.all, args.tuya, args.homepod, args.discover]):
        parser.print_help()
        print("\nEjemplos:")
        print("  python src/main.py --discover                    # Escanear dispositivos")
        print("  python src/main.py --tuya --tuya-local --tuya-ip 192.168.1.100 \\")
        print("    --tuya-device-id XXXX --tuya-local-key YYYY   # Leer Tuya local")
        print("  python src/main.py --homepod                      # Leer HomePod")
        print("  python src/main.py --all                          # Leer todo")
        return

    if args.discover:
        print("Escaneando dispositivos en la red...")
        print("\n--- Dispositivos Tuya/SmartLife ---")
        run_script("download_tuya_data.py", ["--discover"])
        print("\n--- Dispositivos HomeKit ---")
        run_script("download_homepod_data.py", ["--discover"])
        return

    if args.continuous:
        print(f"Iniciando lectura continua cada {args.interval} segundos...")
        print("Presiona Ctrl+C para detener\n")

    success = True

    if args.all or args.tuya:
        tuya_args = []
        if args.tuya_local:
            tuya_args.append("--local")
        if args.tuya_access_id:
            tuya_args.extend(["--access-id", args.tuya_access_id])
        if args.tuya_access_secret:
            tuya_args.extend(["--access-secret", args.tuya_access_secret])
        if args.tuya_device_id:
            tuya_args.extend(["--device-id", args.tuya_device_id])
        if args.tuya_local_key:
            tuya_args.extend(["--local-key", args.tuya_local_key])
        if args.tuya_ip:
            tuya_args.extend(["--ip", args.tuya_ip])

        if not tuya_args:
            print("Nota: Sin credenciales Tuya, se intentara usar variables de entorno (.env)")

        ok = run_script("download_tuya_data.py", tuya_args)
        if not ok:
            success = False

    if args.all or args.homepod:
        homepod_args = []
        if args.homepod_pin:
            homepod_args.extend(["--pin", args.homepod_pin])
        if args.homepod_ip:
            homepod_args.extend(["--ip", args.homepod_ip])

        if args.continuous:
            homepod_args.extend(["--continuous", "--interval", str(args.interval)])

        ok = run_script("download_homepod_data.py", homepod_args)
        if not ok:
            success = False

    if success:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Descarga completada exitosamente")
    else:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Algunas descargas fallaron")
        sys.exit(1)


if __name__ == "__main__":
    main()