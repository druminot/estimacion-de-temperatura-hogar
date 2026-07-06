# Estimacion de Temperatura Hogar

Proyecto para la estimacion de temperatura en el hogar usando datos de sensores y modelos predictivos.

## Objetivo

Determinar el momento optimo para encender la calefaccion basandose en:
- Tasa de enfriamiento del hogar cuando la calefaccion esta apagada
- Tasa de calentamiento cuando la calefaccion esta encendida
- Correlacion con temperatura exterior
- Horarios de calefaccion: 17:00-00:00 y 05:00-08:00

## Resultados del Modelo (5 Julio 2026)

| Metrica | Valor |
|---------|-------|
| Enfriamiento (promedio) | -0.76 C/hora |
| Enfriamiento (mediana) | -0.30 C/hora |
| Calentamiento (promedio) | +2.89 C/hora |
| Calentamiento (mediana) | +3.44 C/hora |
| Correlacion interior/exterior | r = -0.512 |
| Delta medio int/ext | +2.8 C |

**Recomendacion actual**: Encender calefaccion ~2h antes del horario para llegar a 20C.

## Fuentes de Datos

### Home Assistant (principal)
- Sensor T&H (temperatura y humedad interior)
- R11-B Smart Wifi Thermostat (temperatura y setpoint)
- Energy Meter (temperatura del medidor)
- Weather forecast casa (temperatura exterior)

### SmartLife/Tuya (complementario)
- API Cloud: Limitado a 7 dias en plan gratuito
- Local: Conexion directa via tinytuya

## Estructura del Proyecto

```
estimacion-de-temperatura-hogar/
├── src/
│   ├── analyze_temperature.py       # Analisis y modelo predictivo
│   ├── collect_continuous.py        # Recoleccion continua de datos
│   ├── download_ha_data.py          # Descarga datos de Home Assistant
│   ├── download_tuya_history.py     # Historial de Tuya Cloud API
│   ├── download_weather.py          # Datos de OpenWeatherMap
│   ├── download_tuya_data.py        # Descarga datos SmartLife/Tuya
│   ├── download_homepod_data.py     # Descarga datos HomePod
│   ├── setup_tuya.py               # Configuracion Tuya Cloud
│   ├── intercept_smartlife.py      # Intercepcion mitmproxy
│   └── main.py                      # Script principal
├── data/                            # Datos de sensores (CSV, JSON)
├── models/                          # Modelos y predicciones
├── venv/                            # Entorno virtual Python
├── .env                             # Credenciales (no subir)
├── .env.example                     # Plantilla de credenciales
├── AGENTS.md                        # Instrucciones del agente
├── devices_config.json               # Config de dispositivos (gitignore)
└── README.md
```

## Instalacion

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuracion

1. Copia `.env.example` a `.env` y completa con tus credenciales:

```bash
cp .env.example .env
```

### Para Home Assistant:
- HA_URL: URL de HA (default: http://192.168.1.123:8123)
- HA_TOKEN: Long-lived access token (generar en HA > Perfil > Seguridad)

### Para SmartLife/Tuya:
1. Ir a iot.tuya.com y crear cuenta de desarrollador
2. Crear proyecto en Cloud Development
3. Obtener Access ID y Access Secret
4. Enlazar la app SmartLife al proyecto

## Uso

```bash
# Analisis completo del modelo
python src/analyze_temperature.py

# Analisis con graficos
python src/analyze_temperature.py --plot

# Prediccion de temperatura (6 horas)
python src/analyze_temperature.py --predict --hours 6

# Descargar datos de HA (7 dias)
python src/download_ha_data.py --days 7

# Descargar datos meteorologicos de HA
python src/download_ha_data.py --weather --days 7

# Recoleccion continua cada 5 minutos
python src/collect_continuous.py

# Lectura unica
python src/collect_continuous.py --once
```

## Dispositivos Configurados

| Dispositivo | Tipo | Integracion | Entity |
|-------------|------|-------------|--------|
| T & H Sensor | Temperatura/Humedad | Tuya Cloud | sensor.t_h_sensor_temperature |
| R11-B Thermostat | Termostato | Tuya Cloud | climate.r11_b_smart_wifi_thermostat |
| Energy Meter | Medidor energia | Tuya Local | sensor.energy_meter_temperature |
| Forecast Casa | Meteorologico | HA | weather.forecast_casa |

## Notas

- Los datos se guardan en `data/` en formato CSV y JSON
- El modelo se guarda en `models/temperature_model.json`
- Las predicciones se guardan en `models/prediction_latest.json`
- Tuya Cloud free plan: solo 7 dias de historial
- `.env` y `data/*.csv` estan en `.gitignore`