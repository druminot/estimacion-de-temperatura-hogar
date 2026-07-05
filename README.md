# Estimacion de Temperatura Hogar

Proyecto para la estimacion de temperatura en el hogar usando datos de sensores y modelos predictivos.

## Fuentes de Datos

### SmartLife/Tuya (Termometros)
Los termometros SmartLife usan la plataforma Tuya. Hay dos modos de conexion:
- **API Cloud**: Via Tuya IoT Platform (necesita cuenta de desarrollador)
- **Local**: Conexion directa al dispositivo en la red local (via `tinytuya`)

### HomePod (Apple)
El HomePod expone sensores de temperatura y humedad via HomeKit.

## Estructura del Proyecto

```
estimacion-de-temperatura-hogar/
├── src/
│   ├── main.py                      # Script principal
│   ├── download_tuya_data.py        # Descarga datos de SmartLife/Tuya
│   ├── download_homepod_data.py     # Descarga datos de HomePod
│   └── __init__.py
├── data/          # Datos de sensores y datasets
├── models/        # Modelos predictivos entrenados
├── notebooks/     # Jupyter notebooks para analisis exploratorio
├── tests/         # Tests del proyecto
├── docs/          # Documentacion adicional
├── .env.example   # Plantilla de variables de entorno
├── AGENTS.md      # Instrucciones del agente
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

### Para SmartLife/Tuya:
1. Ir a [iot.tuya.com](https://iot.tuya.com/) y crear cuenta de desarrollador
2. Crear proyecto en Cloud Development
3. Obtener Access ID y Access Secret
4. Enlazar la app SmartLife al proyecto
5. Obtener Device ID y Local Key de cada dispositivo

### Para HomePod:
1. Ejecutar el emparejamiento:
```bash
python src/download_homepod_data.py --pair --device-id DEVICE_ID --pin PIN --ip IP
```
2. El PIN se encuentra en la app Casa (Home) de Apple

## Uso

```bash
# Escanear dispositivos en la red
python src/main.py --discover

# Descargar datos de todas las fuentes
python src/main.py --all

# Solo SmartLife/Tuya (modo local)
python src/main.py --tuya --tuya-local --tuya-ip 192.168.1.100 \
  --tuya-device-id XXXX --tuya-local-key YYYY

# Solo SmartLife/Tuya (API Cloud)
python src/main.py --tuya

# Solo HomePod
python src/main.py --homepod

# Lectura continua cada 5 minutos
python src/main.py --all --continuous --interval 300
```

## Notas

- Para HomeKit se necesita la libreria `homekit` (pip install homekit)
- Los datos se guardan en la carpeta `data/` en formato JSON y CSV
- El archivo `.env` con credenciales NO se sube al repositorio