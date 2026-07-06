"""
Script mitmproxy para interceptar y guardar el historial de SmartLife.

Uso:
    mitmdump -s src/intercept_smartlife.py --listen-port 8080

Luego configura el iPhone:
    WiFi > tu red > Proxy Manual > IP: 192.168.1.151 Puerto: 8080
    Visita http://mitm.it en Safari e instala el certificado
    En Ajustes > General > VPN y gestión del dispositivo > confiar en certificado
    Abre SmartLife y navega por los graficos de temperatura
"""

import json
import csv
import os
from datetime import datetime
from pathlib import Path
from mitmproxy import http

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CAPTURED_FILE = DATA_DIR / "smartlife_intercepted_raw.json"
CSV_FILE = DATA_DIR / "smartlife_intercepted_temperature.csv"

all_captured = []

KEYWORDS = [
    "stat", "history", "log", "record", "dp",
    "temp", "humid", "sensor", "device",
    "tuyaus.com", "tuyacn.com", "tuyaeu.com",
    "smart321.com", "wgine.com"
]


def response(flow: http.HTTPFlow) -> None:
    url = flow.request.url.lower()

    if not any(kw in url for kw in KEYWORDS):
        return

    if flow.response.status_code != 200:
        return

    try:
        body = flow.response.get_text()
        if not body:
            return

        data = json.loads(body)
    except Exception:
        return

    raw_str = json.dumps(data)

    # Buscar datos de temperatura o humedad
    has_temp = any(kw in raw_str.lower() for kw in [
        "temp_current", "humidity_value", "temp", "humid",
        "temperature", "humidity", "statisticDatas", "stat_datas",
        "records", "histories", "datapoints"
    ])

    if not has_temp:
        return

    timestamp = datetime.now().isoformat()
    entry = {
        "timestamp": timestamp,
        "url": flow.request.url,
        "method": flow.request.method,
        "request_body": _safe_json(flow.request.get_text()),
        "response": data,
    }

    all_captured.append(entry)

    # Guardar JSON acumulativo
    with open(CAPTURED_FILE, "w", encoding="utf-8") as f:
        json.dump(all_captured, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"CAPTURADO: {flow.request.url[:80]}")

    # Intentar extraer datos de temperatura directamente
    _extract_and_save(data, flow.request.url)


def _safe_json(text):
    try:
        return json.loads(text) if text else None
    except Exception:
        return text


def _extract_and_save(data, url):
    """Intenta extraer lecturas de temperatura/humedad del JSON capturado."""
    records = []

    # Buscar recursivamente listas de datos
    _find_records(data, records)

    if not records:
        return

    print(f"  Encontrados {len(records)} registros de temperatura/humedad")

    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp_ms", "fecha_hora", "codigo", "valor", "unidad", "url"])

        for rec in records:
            ts = rec.get("ts", rec.get("time", rec.get("event_time", rec.get("timestamp", 0))))
            if ts and int(str(ts)[:10]) > 1000000000:
                ts_ms = int(ts) if int(str(ts)) > 9999999999 else int(ts) * 1000
                try:
                    fecha = datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    fecha = str(ts)
            else:
                fecha = ""
                ts_ms = ts

            code = rec.get("code", rec.get("dp_id", rec.get("key", "")))
            value = rec.get("value", rec.get("val", rec.get("v", "")))
            unit = ""

            # Convertir temperatura (viene en decimas)
            if code in ["temp_current", "temperature"] and value:
                try:
                    value = round(float(value) / 10.0, 1)
                    unit = "C"
                except Exception:
                    pass
            elif code in ["humidity_value", "humidity"] and value:
                try:
                    value = round(float(value) / 10.0, 1)
                    unit = "%"
                except Exception:
                    pass

            writer.writerow([ts_ms, fecha, code, value, unit, url[:60]])
            if fecha:
                print(f"    {fecha}  {code}: {value}{unit}")

    print(f"  CSV actualizado: {CSV_FILE}")


def _find_records(obj, results, depth=0):
    """Busca recursivamente listas de lecturas en el JSON."""
    if depth > 6:
        return

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                keys = set(item.keys())
                # Patrones comunes de SmartLife
                if keys & {"temp_current", "humidity_value", "temperature", "humidity"}:
                    results.append(item)
                elif keys & {"code", "value", "event_time"}:
                    if item.get("code") in ["temp_current", "humidity_value", "temp_set"]:
                        results.append(item)
                elif keys & {"ts", "val", "v"} and ("time" in keys or "ts" in keys):
                    results.append(item)
                elif keys & {"time", "value"} and len(keys) <= 5:
                    results.append(item)
                else:
                    _find_records(item, results, depth + 1)
    elif isinstance(obj, dict):
        for key, val in obj.items():
            if key in ["logs", "records", "histories", "datapoints",
                        "stat_datas", "statisticDatas", "data", "list",
                        "items", "result", "results", "dps"]:
                _find_records(val, results, depth + 1)
            elif isinstance(val, (dict, list)):
                _find_records(val, results, depth + 1)
