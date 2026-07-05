"""
Descarga historial completo de temperatura desde Tuya Cloud API.

Usa los tokens de la integracion Tuya de Home Assistant para conectarse
a la API Cloud de Tuya y descargar el historial de los termometros.

Sensores soportados:
- T & H Sensor (temperatura + humedad)
- R11-B Smart Wifi Thermostat
- Y todos los dispositivos Tuya configurados en HA

Uso:
    python src/download_tuya_history.py                  # Descargar ultimos 7 dias
    python src/download_tuya_history.py --days 30        # Ultimos 30 dias
    python src/download_tuya_history.py --list            # Listar dispositivos
    python src/download_tuya_history.py --all            # Todos los dispositivos
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass

HA_URL = os.getenv("HA_URL", "http://192.168.1.123:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
DATA_DIR = Path(__file__).parent.parent / "data"

TUYA_API_BASE = "https://apigw.tuyaus.com"

HA_DEVICES = {
    "ebad43a02883af0a74edfr": {
        "name": "T & H Sensor",
        "type": "temperature_humidity",
    },
    "ebfce82a251d26fe96exn2": {
        "name": "R11-B Smart Wifi Thermostat",
        "type": "thermostat",
    },
    "eb7283ccb2f56c18f38dv5": {"name": "Salon (interruptor)", "type": "switch"},
    "eb5425dab97360be31wlhz": {"name": "Monitor Mac", "type": "smartplug"},
    "eb04887187b592417dtsym": {"name": "Centro salon (regleta)", "type": "powerstrip"},
    "ebe1a13c843119f70fqjx4": {"name": "Encimera Lavadora", "type": "smartplug"},
    "eb618f3a166c116c22qozr": {"name": "Casa (medidor energia)", "type": "energy_meter"},
    "ebfd1f19f5bc32a3d2zdub": {"name": "Dormitorio (interruptor)", "type": "switch"},
    "ebac6224209797f7ddpgu4": {"name": "Oficina (interruptor)", "type": "switch"},
}

TEMP_SENSORS = ["ebad43a02883af0a74edfr", "ebfce82a251d26fe96exn2"]


class TuyaCloudAPI:
    def __init__(self, access_id, access_secret, endpoint=TUYA_API_BASE):
        self.access_id = access_id
        self.access_secret = access_secret
        self.endpoint = endpoint
        self.token = None
        self.token_expire = 0

    def _get_sign(self, t, token=None):
        import hashlib
        import hmac
        message = self.access_id + t
        if token:
            message = token + t
        sign = hmac.new(
            self.access_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest().upper()
        return sign

    def _get_headers(self, token=None, need_token=True):
        t = str(int(time.time() * 1000))
        headers = {
            "client_id": self.access_id,
            "t": t,
            "sign_method": "HMAC-SHA256",
        }
        if need_token and self.token:
            headers["access_token"] = self.token
        sign = self._get_sign(t, self.token if need_token else None)
        headers["sign"] = sign
        return headers

    def connect(self):
        url = f"{self.endpoint}/v1.0/token?grant_type=1"
        headers = self._get_headers(need_token=False)
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Error getting token: {response.text}")
        result = response.json()
        if result.get("success") is False:
            raise Exception(f"Error: {result.get('msg', 'Unknown error')}")
        self.token = result["result"]["access_token"]
        self.token_expire = result["result"]["expire_time"]
        return self.token

    def _ensure_token(self):
        if not self.token or time.time() > self.token_expire - 60:
            self.connect()

    def get_device_status(self, device_id):
        self._ensure_token()
        url = f"{self.endpoint}/v1.0/devices/{device_id}/status"
        headers = self._get_headers()
        response = requests.get(url, headers=headers, timeout=30)
        return response.json()

    def get_device_logs(self, device_id, start_time, end_time, size=100, event_type="7"):
        self._ensure_token()
        all_logs = []

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        while start_ms < end_ms:
            url = f"{self.endpoint}/v1.0/devices/{device_id}/logs"
            params = {
                "start_time": start_ms,
                "end_time": end_ms,
                "size": min(size, 100),
            }
            if event_type:
                params["event_type"] = event_type

            headers = self._get_headers()
            response = requests.get(url, headers=headers, params=params, timeout=30)
            result = response.json()

            if not result.get("success"):
                print(f"  Error: {result.get('msg', 'Unknown')}")
                break

            logs = result.get("result", {}).get("logs", [])
            if not logs:
                break

            all_logs.extend(logs)

            if len(logs) < size:
                break

            last_ts = int(logs[-1].get("time", 0))
            if last_ts <= start_ms:
                break
            start_ms = last_ts + 1

            time.sleep(0.5)

        return all_logs

    def get_devices(self, uid):
        self._ensure_token()
        url = f"{self.endpoint}/v1.0/users/{uid}/devices"
        headers = self._get_headers()
        response = requests.get(url, headers=headers, timeout=30)
        return response.json()


def get_tuya_credentials_from_ha():
    """Obtiene las credenciales de Tuya Cloud desde Home Assistant."""
    import websocket

    ws = websocket.create_connection(f"ws://{HA_URL.replace('http://', '').replace('https://', '')}/api/websocket", timeout=10)
    ws.recv()

    ws.send(json.dumps({"type": "auth", "access_token": HA_TOKEN}))
    ws.recv()

    ws.send(json.dumps({"id": 1, "type": "config_entries/get"}))
    result = json.loads(ws.recv())

    entries = result.get("result", [])
    ws.close()

    tuya_entry = None
    for entry in entries:
        if entry.get("domain") == "tuya":
            tuya_entry = entry
            break

    if not tuya_entry:
        raise Exception("No se encontro la integracion Tuya en Home Assistant")

    data = tuya_entry.get("data", {})
    endpoint = data.get("endpoint", TUYA_API_BASE)
    uid = data.get("uid", data.get("user_code", ""))
    token_info = data.get("token_info", {})

    return {
        "endpoint": endpoint,
        "access_token": token_info.get("access_token"),
        "refresh_token": token_info.get("refresh_token"),
        "uid": uid,
    }


def get_tuya_config_from_ha_ssh():
    """Obtiene la configuracion completa de Tuya desde HA via SSH."""
    import subprocess

    result = subprocess.run(
        ["sshpass", "-p", "asdASD123", "ssh", "-o", "StrictHostKeyChecking=no",
         "druminot@100.114.148.95",
         "docker exec homeassistant cat /config/.storage/core.config_entries"],
        capture_output=True, text=True, timeout=30
    )

    data = json.loads(result.stdout)
    entries = data.get("data", {}).get("entries", data.get("entries", []))

    tuya_entry = None
    for entry in entries:
        if entry.get("domain") == "tuya":
            tuya_entry = entry
            break

    if not tuya_entry:
        return None

    entry_data = tuya_entry.get("data", {})
    return entry_data


def get_tuya_access_id_from_ha():
    """Obtiene el access_id y access_secret de HA config."""
    entry_data = get_tuya_config_from_ha_ssh()
    if entry_data:
        return entry_data.get("access_id"), entry_data.get("access_secret")
    return None, None


def save_logs_to_csv(logs, device_name, device_id, output_dir=DATA_DIR):
    """Guarda los logs en formato CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"tuya_{device_name.replace(' ', '_').replace('-', '')}_{device_id[:12]}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "timestamp_iso", "dp_code", "dp_name", "value"])
        for log in logs:
            ts_ms = log.get("time", 0)
            ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat() if ts_ms else ""
            writer.writerow([
                ts_ms,
                ts_iso,
                log.get("code", ""),
                log.get("code", ""),
                log.get("value", ""),
            ])

    print(f"  CSV guardado: {csv_path}")
    return csv_path


def save_logs_to_json(logs, device_name, device_id, output_dir=DATA_DIR):
    """Guarda los logs en formato JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"tuya_{device_name.replace(' ', '_').replace('-', '')}_{device_id[:12]}.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    print(f"  JSON guardado: {json_path}")
    return json_path


def main():
    parser = argparse.ArgumentParser(description="Descarga historial de Tuya Cloud API")
    parser.add_argument("--days", type=int, default=7, help="Dias de historial (default: 7)")
    parser.add_argument("--start", help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--end", help="Fecha fin YYYY-MM-DD")
    parser.add_argument("--sensors-only", action="store_true", help="Solo sensores de temperatura")
    parser.add_argument("--all", action="store_true", help="Todos los dispositivos")
    parser.add_argument("--device-id", help="Device ID especifico")
    parser.add_argument("--list", action="store_true", help="Listar dispositivos")
    parser.add_argument("--current", action="store_true", help="Solo estado actual")

    args = parser.parse_args()

    print("Obteniendo credenciales Tuya desde Home Assistant...")
    try:
        creds = get_tuya_credentials_from_ha()
    except Exception as e:
        print(f"Error obteniendo credenciales: {e}")
        print("Asegurate de que Home Assistant este accesible y el token sea valido")
        sys.exit(1)

    print(f"Credenciales obtenidas. Endpoint: {creds['endpoint']}")

    if args.list:
        print("\nDispositivos Tuya configurados:\n")
        for dev_id, info in HA_DEVICES.items():
            marker = " <<< SENSOR" if dev_id in TEMP_SENSORS else ""
            print(f"  {info['name']:35s} {dev_id:25s} {info['type']}{marker}")
        return

    access_id, access_secret = get_tuya_access_id_from_ha()

    if access_id and access_secret:
        print(f"Access ID encontrado: {access_id[:8]}...")
        api = TuyaCloudAPI(access_id, access_secret, creds["endpoint"])
    else:
        print("Access ID/Secret no encontrado directamente en HA config.")
        print("Intentando usar token existente de la integracion Tuya...")
        
        ha_config = get_tuya_config_from_ha_ssh()
        if ha_config and ha_config.get("token_info", {}).get("access_token"):
            access_id = ha_config.get("terminal_id", "")
            access_secret = ha_config.get("token_info", {}).get("access_token", "")
            endpoint = ha_config.get("endpoint", TUYA_API_BASE)
            uid = ha_config.get("token_info", {}).get("uid", "")
            print(f"Usando token de HA (expira en {ha_config['token_info'].get('expire_time', '?')}s)")
            print(f"UID: {uid}")
            print(f"Terminal ID: {access_id}")
            print(f"\nNOTA: El token de HA tiene duracion limitada y NO es lo mismo que access_id/access_secret.")
            print("Para descargas recurrentes, necesitas crear cuenta en iot.tuya.com")
            print("y ejecutar: python src/setup_tuya.py --access-id ID --access-secret SECRET")
            print("\nIntentando obtener lista de dispositivos con token de HA...")

            url = f"{endpoint}/v1.0/users/{uid}/devices"
            headers = {
                "access_token": ha_config["token_info"]["access_token"],
                "client_id": access_id,
                "sign_method": "HMAC-SHA256",
                "t": str(int(time.time() * 1000)),
            }
            try:
                response = requests.get(url, headers=headers, timeout=30)
                result = response.json()
                if result.get("success"):
                    devices = result.get("result", [])
                    print(f"\nSe encontraron {len(devices)} dispositivos en Tuya Cloud!")
                    for dev in devices:
                        dev_id = dev.get("id", "")
                        dev_name = dev.get("name", "")
                        dev_model = dev.get("model", "")
                        marker = " <<< SENSOR" if dev_id in TEMP_SENSORS else ""
                        print(f"  {dev_name:35s} {dev_id:25s} {dev_model}{marker}")
                    print("\nLa API funciona con el token de HA!")
                    print("Pero para descargar historial necesitamos access_id/access_secret.")
                else:
                    print(f"API response: {json.dumps(result, indent=2)[:300]}")
            except Exception as e:
                print(f"Error: {e}")
            
            print("\nPara obtener access_id y access_secret:")
            print("1. Ve a https://iot.tuya.com/ y crea una cuenta (gratuita)")
            print("2. Crea un proyecto en Cloud Development")
            print("3. Vincula tu app SmartLife (escanea QR)")
            print("4. Copia Access ID y Access Secret del proyecto")
            print("5. Ejecuta: python src/setup_tuya.py --access-id ID --access-secret SECRET")
        sys.exit(1)

    try:
        print("Conectando a Tuya Cloud API...")
        api.connect()
        print("Conexion exitosa!\n")
    except Exception as e:
        print(f"Error conectando: {e}")
        sys.exit(1)

    if args.current:
        for dev_id in (TEMP_SENSORS if not args.all else HA_DEVICES):
            name = HA_DEVICES.get(dev_id, {}).get("name", dev_id)
            print(f"Consultando estado actual de {name}...")
            try:
                status = api.get_device_status(dev_id)
                print(f"  {json.dumps(status, indent=2)[:300]}")
            except Exception as e:
                print(f"  Error: {e}")
        return

    if args.start:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
    else:
        start_date = datetime.now() - timedelta(days=args.days)

    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    devices = TEMP_SENSORS if args.sensors_only and not args.all else list(HA_DEVICES.keys())
    if args.device_id:
        devices = [args.device_id]

    print(f"Descargando historial desde {start_date.date()} hasta {end_date.date()}...\n")

    for dev_id in devices:
        name = HA_DEVICES.get(dev_id, {}).get("name", dev_id)
        print(f"Descargando: {name} ({dev_id})...")

        try:
            logs = api.get_device_logs(dev_id, start_date, end_date)
            if logs:
                print(f"  {len(logs)} registros encontrados")
                save_logs_to_csv(logs, name, dev_id)
                save_logs_to_json(logs, name, dev_id)
            else:
                print(f"  Sin datos para este dispositivo")
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(1)

    print("\nDescarga completada!")


if __name__ == "__main__":
    main()