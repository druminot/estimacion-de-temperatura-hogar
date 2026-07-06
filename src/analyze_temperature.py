"""
Analisis y modelo de estimacion de temperatura del hogar.

Objetivo: Determinar el momento optimo para encender la calefaccion
basandose en la tasa de caida de temperatura y la relacion
temperatura interior/exterior.

Horario de calefaccion:
- Tarde: 17:00 - 00:00
- Manana: 05:00 - 08:00

Uso:
    python src/analyze_temperature.py                    # Analisis completo
    python src/analyze_temperature.py --plot             # Generar graficos
    python src/analyze_temperature.py --predict          # Predecir temperatura
    python src/analyze_temperature.py --predict --hours 3  # Predecir 3 horas
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from scipy import stats

DATA_DIR = Path(__file__).parent.parent / "data"
MODELS_DIR = Path(__file__).parent.parent / "models"
RESULTS_DIR = Path(__file__).parent.parent / "docs"

HEATING_SCHEDULE = [
    ("morning", 5, 8),
    ("evening", 17, 24),
]


def load_ha_data():
    """Carga datos de Home Assistant desde el CSV mas reciente."""
    csv_files = sorted(DATA_DIR.glob("temperatura_hogar_*.csv"))
    if not csv_files:
        print("Error: No se encontraron archivos de datos de HA")
        sys.exit(1)

    latest = csv_files[-1]
    print(f"Cargando datos de HA: {latest.name}")

    df = pd.read_csv(latest, parse_dates=["timestamp"])
    df = df[df["valor"] != "unavailable"]
    df = df[df["valor"] != "unknown"]
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["valor"])

    return df


def load_tuya_data():
    """Carga datos de SmartLife/Tuya."""
    dfs = {}

    th_file = DATA_DIR / "smartlife_history_T_H_Sensor.csv"
    if th_file.exists():
        df = pd.read_csv(th_file)
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
        dfs["th_sensor"] = df

    r11b_file = DATA_DIR / "smartlife_history_R11B_Thermostat.csv"
    if r11b_file.exists():
        df = pd.read_csv(r11b_file)
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
        dfs["r11b"] = df

    return dfs


def build_time_series(ha_df):
    """Construye series temporales por sensor desde datos HA."""
    series = {}

    for sensor in ha_df["sensor"].unique():
        mask = ha_df["sensor"] == sensor
        s = ha_df[mask].set_index("timestamp")["valor"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        series[sensor] = s

    return series


def build_r11b_time_series(tuya_dfs):
    """Construye series temporales del termostato R11-B desde datos Tuya."""
    if "r11b" not in tuya_dfs:
        return {}, {}

    df = tuya_dfs["r11b"]
    temp_current = df[df["codigo"] == "temp_current"].set_index("fecha_hora")["valor"].sort_index()
    temp_current = temp_current[~temp_current.index.duplicated(keep="last")]
    temp_current.name = "temp_current"

    temp_set = df[df["codigo"] == "temp_set"].set_index("fecha_hora")["valor"].sort_index()
    temp_set = temp_set[~temp_set.index.duplicated(keep="last")]
    temp_set.name = "temp_set"

    return temp_current, temp_set


def is_heating_hour(hour):
    """Determina si una hora esta en el horario de calefaccion."""
    for _, start, end in HEATING_SCHEDULE:
        if start <= hour < end:
            return True
        if start > end:
            if hour >= start or hour < end:
                return True
    return False


def detect_heating_periods(temp_set_series):
    """Detecta periodos donde la calefaccion esta activa basandose en temp_set."""
    if temp_set_series is None or len(temp_set_series) == 0:
        return pd.Series(dtype=bool)

    HEATING_THRESHOLD = 22.0
    heating = temp_set_series >= HEATING_THRESHOLD
    return heating


def calculate_cooling_rate(temp_series, heating_mask=None):
    """
    Calcula la tasa de caida de temperatura cuando la calefaccion esta apagada.

    Returns:
        tasa promedio en grados/hora, y datos detallados
    """
    if len(temp_series) < 10:
        return None, None

    temp_series = temp_series.sort_index()

    if heating_mask is not None:
        heating_mask = heating_mask.reindex(temp_series.index, method="ffill").fillna(False)
        cooling_periods = temp_series[~heating_mask]
    else:
        cooling_mask = pd.Series(
            [not is_heating_hour(t.hour) for t in temp_series.index],
            index=temp_series.index,
        )
        cooling_periods = temp_series[cooling_mask]

    if len(cooling_periods) < 5:
        return None, None

    cooling_periods = cooling_periods.sort_index()

    rates = []
    details = []

    window = 6
    for i in range(len(cooling_periods) - window):
        segment = cooling_periods.iloc[i : i + window]
        if len(segment) < 4:
            continue

        time_hours = (segment.index - segment.index[0]).total_seconds() / 3600
        temps = segment.values

        if time_hours[-1] < 0.5:
            continue

        slope, intercept, r_value, p_value, std_err = stats.linregress(time_hours, temps)

        if slope < 0 and p_value < 0.1:
            rates.append(slope)
            details.append({
                "start": segment.index[0],
                "end": segment.index[-1],
                "duration_hours": time_hours[-1],
                "rate_c_per_hour": round(slope, 3),
                "r_squared": round(r_value**2, 3),
                "p_value": round(p_value, 4),
                "temp_start": round(float(temps[0]), 1),
                "temp_end": round(float(temps[-1]), 1),
            })

    if not rates:
        return None, None

    avg_rate = np.mean(rates)
    return avg_rate, details


def calculate_heating_rate(temp_series, heating_mask=None, r11b_current=None, r11b_set=None):
    """Calcula la tasa de calentamiento cuando la calefaccion esta activa."""
    rates = []
    details = []

    if r11b_current is not None and r11b_set is not None and len(r11b_current) > 0 and len(r11b_set) > 0:
        set_resampled = r11b_set.resample("1min").ffill().dropna()
        current_resampled = r11b_current.resample("1min").mean().dropna()

        common_idx = set_resampled.index.intersection(current_resampled.index)
        if len(common_idx) > 5:
            HEATING_THRESHOLD = 22.0
            is_heating = set_resampled.loc[common_idx] >= HEATING_THRESHOLD

            heating_times = current_resampled.loc[common_idx[is_heating]]
            heating_times = heating_times.sort_index()

            if len(heating_times) >= 6:
                window = 6
                for i in range(len(heating_times) - window):
                    segment = heating_times.iloc[i : i + window]
                    if len(segment) < 4:
                        continue

                    time_hours = (segment.index - segment.index[0]).total_seconds() / 3600
                    temps = segment.values

                    if time_hours[-1] < 0.3:
                        continue

                    slope, intercept, r_value, p_value, std_err = stats.linregress(time_hours, temps)

                    if slope > 0 and p_value < 0.2:
                        rates.append(slope)
                        details.append({
                            "source": "r11b_direct",
                            "start": segment.index[0],
                            "end": segment.index[-1],
                            "duration_hours": time_hours[-1],
                            "rate_c_per_hour": round(slope, 3),
                            "r_squared": round(r_value**2, 3),
                            "p_value": round(p_value, 4),
                            "temp_start": round(float(temps[0]), 1),
                            "temp_end": round(float(temps[-1]), 1),
                        })

    if len(temp_series) >= 10 and not rates:
        temp_series = temp_series.sort_index()

        if heating_mask is not None:
            heating_periods = temp_series[heating_mask.reindex(temp_series.index, method="ffill").fillna(False)]
        else:
            heating_mask_vals = pd.Series(
                [is_heating_hour(t.hour) for t in temp_series.index],
                index=temp_series.index,
            )
            heating_periods = temp_series[heating_mask_vals]

        if len(heating_periods) >= 6:
            heating_periods = heating_periods.sort_index()

            window = 6
            for i in range(len(heating_periods) - window):
                segment = heating_periods.iloc[i : i + window]
                if len(segment) < 4:
                    continue

                time_hours = (segment.index - segment.index[0]).total_seconds() / 3600
                temps = segment.values

                if time_hours[-1] < 0.3:
                    continue

                slope, intercept, r_value, p_value, std_err = stats.linregress(time_hours, temps)

                if slope > 0 and p_value < 0.2:
                    rates.append(slope)
                    details.append({
                        "source": "schedule_based",
                        "start": segment.index[0],
                        "end": segment.index[-1],
                        "duration_hours": time_hours[-1],
                        "rate_c_per_hour": round(slope, 3),
                        "r_squared": round(r_value**2, 3),
                        "p_value": round(p_value, 4),
                        "temp_start": round(float(temps[0]), 1),
                        "temp_end": round(float(temps[-1]), 1),
                    })

    if not rates:
        return None, None

    avg_rate = np.mean(rates)
    return avg_rate, details


def predict_temperature(current_temp, hours_ahead, cooling_rate, heating_rate=None, target_temp=20.0):
    """
    Predice la temperatura futura y calcula cuando encender la calefaccion.

    Args:
        current_temp: Temperatura actual
        hours_ahead: Horas a predecir
        cooling_rate: Tasa de enfriamiento en C/hora (negativo)
        heating_rate: Tasa de calentamiento en C/hora (positivo)
        target_temp: Temperatura objetivo

    Returns:
        dict con prediccion y recomendaciones
    """
    now = datetime.now()

    predictions = []
    temp = current_temp
    heating_on = False

    for h in range(int(hours_ahead * 60)):
        minute = h + 1
        hour_of_day = ((now.hour * 60 + now.minute + minute) % 1440) / 60

        if is_heating_hour(hour_of_day):
            if not heating_on:
                heating_on = True
                if heating_rate:
                    pass
            if heating_rate:
                temp += heating_rate / 60
        else:
            heating_on = False
            if cooling_rate:
                temp += cooling_rate / 60

        if minute % 15 == 0:
            predictions.append({
                "minute": minute,
                "time": (now + timedelta(minutes=minute)).strftime("%H:%M"),
                "hour_of_day": round(hour_of_day, 2),
                "heating_on": heating_on,
                "predicted_temp": round(temp, 1),
            })

    time_to_target = None
    if cooling_rate and cooling_rate < 0 and current_temp > target_temp:
        time_to_target = round((current_temp - target_temp) / abs(cooling_rate), 1)

    min_temp = min(p["predicted_temp"] for p in predictions) if predictions else current_temp
    min_temp_time = None
    for p in predictions:
        if p["predicted_temp"] == min_temp:
            min_temp_time = p["time"]
            break

    warmup_time = None
    if heating_rate and heating_rate > 0 and target_temp > min_temp:
        warmup_time = round((target_temp - min_temp) / heating_rate, 1)

    optimal_start = None
    if heating_rate and heating_rate > 0 and cooling_rate and cooling_rate < 0:
        evening_start = 17
        morning_start = 5

        for schedule_name, start_h, end_h in HEATING_SCHEDULE:
            hours_before_start = (target_temp - current_temp) / heating_rate if heating_rate > 0 else 999
            if hours_before_start < 0:
                hours_before_start = 0.5

            if schedule_name == "evening":
                optimal_start = f"{evening_start - int(hours_before_start):02d}:{int((hours_before_start % 1) * 60):02d}"
            elif schedule_name == "morning":
                morning_optimal = f"{morning_start - int(hours_before_start):02d}:{int((hours_before_start % 1) * 60):02d}"
                optimal_start = f"Tarde: {evening_start - int(hours_before_start):02d}:{int((hours_before_start % 1) * 60):02d}, Manana: {morning_optimal}"

    result = {
        "current_temp": current_temp,
        "target_temp": target_temp,
        "cooling_rate_c_per_hour": round(cooling_rate, 3) if cooling_rate else None,
        "heating_rate_c_per_hour": round(heating_rate, 3) if heating_rate else None,
        "time_to_target_hours": time_to_target,
        "min_predicted_temp": round(min_temp, 1),
        "min_temp_at": min_temp_time,
        "warmup_time_hours": warmup_time,
        "optimal_start_time": optimal_start,
        "predictions": predictions,
    }

    return result


def generate_plots(ha_df, series, cooling_details, heating_details, cooling_rate, heating_rate):
    """Genera graficos de analisis."""
    if not HAS_MPL:
        print("matplotlib no disponible. Instalalo con: pip install matplotlib")
        return

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Analisis de Temperatura del Hogar", fontsize=16, fontweight="bold")

    ax1 = axes[0, 0]
    temp_sensors = [k for k in series.keys() if "temperature" in k or "climate" in k]
    colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"]
    for i, sensor in enumerate(temp_sensors[:4]):
        series[sensor].plot(ax=ax1, label=sensor.replace("sensor.", "").replace("climate.", ""), color=colors[i % len(colors)], alpha=0.8)
    ax1.set_title("Temperatura en el tiempo")
    ax1.set_ylabel("Temperatura (C)")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2 = axes[0, 1]
    if "sensor.t_h_sensor_temperature" in series:
        th = series["sensor.t_h_sensor_temperature"]
        hourly = th.groupby(th.index.hour).agg(["mean", "std", "min", "max"])
        ax2.bar(hourly.index, hourly["max"] - hourly["min"], bottom=hourly["min"], alpha=0.3, color="#3498db", label="Rango")
        ax2.plot(hourly.index, hourly["mean"], "o-", color="#e74c3c", label="Promedio")
        for _, start, end in HEATING_SCHEDULE:
            ax2.axvspan(start, end, alpha=0.15, color="orange", label="Calefaccion ON" if _ == "morning" else "")
        ax2.set_title("Patron horario - Sensor T&H")
        ax2.set_xlabel("Hora del dia")
        ax2.set_ylabel("Temperatura (C)")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

    ax3 = axes[1, 0]
    if cooling_details:
        rates = [d["rate_c_per_hour"] for d in cooling_details]
        ax3.hist(rates, bins=15, color="#3498db", alpha=0.7, edgecolor="black")
        ax3.axvline(np.mean(rates), color="#e74c3c", linestyle="--", linewidth=2, label=f"Promedio: {np.mean(rates):.3f} C/h")
        ax3.set_title("Distribucion de tasas de enfriamiento")
        ax3.set_xlabel("Tasa (C/hora)")
        ax3.set_ylabel("Frecuencia")
        ax3.legend()
        ax3.grid(True, alpha=0.3)

    ax4 = axes[1, 1]
    if "sensor.t_h_sensor_temperature" in series:
        th = series["sensor.t_h_sensor_temperature"]
        hourly_means = th.groupby(th.index.hour).mean()

        hours = np.arange(24)
        cooling_temps = []
        heating_temps = []

        current = hourly_means.get(8, 18)
        for h in hours:
            if is_heating_hour(h):
                if heating_rate:
                    current += heating_rate
                heating_temps.append(current)
                cooling_temps.append(np.nan)
            else:
                if cooling_rate:
                    current += cooling_rate
                cooling_temps.append(current)
                heating_temps.append(np.nan)

        ax4.plot(hours, hourly_means.values, "o-", color="#2c3e50", label="Real (promedio)", alpha=0.7)
        ax4.plot(hours, cooling_temps, "--", color="#3498db", label="Enfriamiento modelo", alpha=0.7)
        ax4.plot(hours, heating_temps, "--", color="#e74c3c", label="Calentamiento modelo", alpha=0.7)
        ax4.axhline(y=20, color="green", linestyle=":", alpha=0.5, label="Objetivo 20C")
        ax4.set_title("Modelo vs Real")
        ax4.set_xlabel("Hora del dia")
        ax4.set_ylabel("Temperatura (C)")
        ax4.legend(fontsize=8)
        ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plot_path = MODELS_DIR / "temperature_analysis.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Grafico guardado: {plot_path}")


def run_analysis(ha_df, tuya_dfs, do_plot=False, do_predict=False, predict_hours=4):
    """Ejecuta el analisis completo."""
    print("=" * 60)
    print("ANALISIS DE TEMPERATURA DEL HOGAR")
    print("=" * 60)

    series = build_time_series(ha_df)

    print(f"\nDatos disponibles:")
    for name, s in series.items():
        print(f"  {name}: {len(s)} registros, {s.index[0]} a {s.index[-1]}")

    print(f"\nHorario calefaccion: 17:00-00:00 y 05:00-08:00")

    r11b_current, r11b_set = build_r11b_time_series(tuya_dfs)

    heating_mask = None
    if r11b_set is not None and len(r11b_set) > 0:
        heating_mask = detect_heating_periods(r11b_set)
        print(f"\nPeriodos con calefaccion ON (temp_set >= 22C): {heating_mask.sum()} de {len(heating_mask)} mediciones")

    print("\n" + "=" * 60)
    print("ANALISIS DE ENFRIAMIENTO")
    print("=" * 60)

    cooling_rate = None
    cooling_details = None

    if "sensor.t_h_sensor_temperature" in series:
        cooling_rate, cooling_details = calculate_cooling_rate(
            series["sensor.t_h_sensor_temperature"], heating_mask
        )
    elif "sensor.energy_meter_temperature" in series:
        cooling_rate, cooling_details = calculate_cooling_rate(
            series["sensor.energy_meter_temperature"], heating_mask
        )

    if cooling_rate:
        print(f"\nTasa de enfriamiento: {cooling_rate:.3f} C/hora")
        if cooling_details:
            print(f"  Segmentos analizados: {len(cooling_details)}")
            rates = [d["rate_c_per_hour"] for d in cooling_details]
            print(f"  Rango: {min(rates):.3f} a {max(rates):.3f} C/hora")
            print(f"  Mediana: {np.median(rates):.3f} C/hora")

            print(f"\n  Top 5 enfriamientos mas rapidos:")
            sorted_details = sorted(cooling_details, key=lambda x: x["rate_c_per_hour"])
            for d in sorted_details[:5]:
                print(f"    {d['start'].strftime('%Y-%m-%d %H:%M')} - {d['end'].strftime('%H:%M')}: "
                      f"{d['rate_c_per_hour']:.3f} C/h ({d['temp_start']}C -> {d['temp_end']}C, R2={d['r_squared']:.3f})")
    else:
        print("\nNo se pudo calcular la tasa de enfriamiento con los datos disponibles")

    print("\n" + "=" * 60)
    print("ANALISIS DE CALENTAMIENTO")
    print("=" * 60)

    heating_rate = None
    heating_details = None

    main_temp = series.get("sensor.t_h_sensor_temperature", series.get("sensor.energy_meter_temperature"))
    if main_temp is not None:
        heating_rate, heating_details = calculate_heating_rate(
            main_temp, heating_mask, r11b_current, r11b_set
        )

    if heating_rate:
        print(f"\nTasa de calentamiento: {heating_rate:.3f} C/hora")
        if heating_details:
            print(f"  Segmentos analizados: {len(heating_details)}")
            rates = [d["rate_c_per_hour"] for d in heating_details]
            print(f"  Rango: {min(rates):.3f} a {max(rates):.3f} C/hora")
            print(f"  Mediana: {np.median(rates):.3f} C/hora")
    else:
        print("\nNo se pudo calcular la tasa de calentamiento")

    if cooling_rate and heating_rate:
        print("\n" + "=" * 60)
        print("RESUMEN DEL MODELO")
        print("=" * 60)

        print(f"\nEnfriamiento: {cooling_rate:.2f} C/hora (sin calefaccion)")
        print(f"Calentamiento: {heating_rate:.2f} C/hora (con calefaccion)")

        current_temp = None
        main_sensor = "sensor.t_h_sensor_temperature"
        if main_sensor in series:
            current_temp = float(series[main_sensor].iloc[-1])
        elif "sensor.energy_meter_temperature" in series:
            current_temp = float(series["sensor.energy_meter_temperature"].iloc[-1])

        if current_temp:
            print(f"\nTemperatura actual: {current_temp:.1f} C")

            target = 20.0
            if current_temp > target:
                hours_to_target = (current_temp - target) / abs(cooling_rate) if cooling_rate else None
                print(f"Tiempo para llegar a {target}C sin calefaccion: {hours_to_target:.1f} horas" if hours_to_target else "")

            warmup_needed = max(0, target - current_temp)
            if warmup_needed > 0 and heating_rate:
                warmup_time = warmup_needed / heating_rate
                print(f"Tiempo para calentar de {current_temp:.1f}C a {target}C: {warmup_time:.1f} horas")

                print(f"\nRecomendacion para horario de 17:00:")
                pre_heat = warmup_time
                optimal = 17 - pre_heat
                if optimal < 12:
                    optimal = 12
                    print(f"  Encender a las {int(optimal):02d}:{int((optimal % 1) * 60):02d} para llegar a {target}C a las 17:00")
                    print(f"  (se necesitan {warmup_time:.1f}h para calentar)")
                else:
                    print(f"  Encender a las {int(optimal):02d}:{int((optimal % 1) * 60):02d} para llegar a {target}C a las 17:00")
                    print(f"  (se necesitan {warmup_time:.1f}h para calentar)")

                print(f"\nRecomendacion para horario de 05:00:")
                optimal_m = 5 - warmup_time
                if optimal_m < 0:
                    optimal_m = 0
                print(f"  Encender a las {int(optimal_m):02d}:{int((optimal_m % 1) * 60):02d} para llegar a {target}C a las 05:00")

    if do_predict and (cooling_rate or heating_rate):
        print("\n" + "=" * 60)
        print(f"PREDICCION ({predict_hours} HORAS)")
        print("=" * 60)

        current_temp = None
        if "sensor.t_h_sensor_temperature" in series:
            current_temp = float(series["sensor.t_h_sensor_temperature"].iloc[-1])
        elif "sensor.energy_meter_temperature" in series:
            current_temp = float(series["sensor.energy_meter_temperature"].iloc[-1])

        if current_temp:
            result = predict_temperature(current_temp, predict_hours, cooling_rate, heating_rate)
            print(f"\nPrediccion desde {datetime.now().strftime('%Y-%m-%d %H:%M')}:")
            print(f"  Temperatura actual: {result['current_temp']:.1f}C")
            print(f"  Temperatura minima predicha: {result['min_predicted_temp']:.1f}C a las {result['min_temp_at']}")
            if result["time_to_target_hours"]:
                print(f"  Tiempo para llegar a {result['target_temp']}C sin calefaccion: {result['time_to_target_hours']:.1f} horas")
            if result["warmup_time_hours"]:
                print(f"  Tiempo de calentamiento a {result['target_temp']}C: {result['warmup_time_hours']:.1f} horas")

            print(f"\n  Proyeccion horaria:")
            for p in result["predictions"]:
                status = "🔥" if p["heating_on"] else "❄️"
                print(f"    {p['time']} | {p['predicted_temp']:.1f}C | {status}")

            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            pred_path = MODELS_DIR / "prediction_latest.json"
            with open(pred_path, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n  Prediccion guardada: {pred_path}")

    if do_plot:
        generate_plots(ha_df, series, cooling_details, heating_details, cooling_rate, heating_rate)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_data = {
        "generated_at": datetime.now().isoformat(),
        "data_period": {
            "start": str(ha_df["timestamp"].min()),
            "end": str(ha_df["timestamp"].max()),
            "records": len(ha_df),
        },
        "cooling_rate_c_per_hour": round(cooling_rate, 4) if cooling_rate else None,
        "heating_rate_c_per_hour": round(heating_rate, 4) if heating_rate else None,
        "cooling_segments": cooling_details,
        "heating_segments": heating_details,
        "heating_schedule": [{"name": n, "start": s, "end": e} for n, s, e in HEATING_SCHEDULE],
        "recommendations": {
            "target_temp": 20.0,
            "optimal_pre_heat_minutes_evening": None,
            "optimal_pre_heat_minutes_morning": None,
        },
    }

    if cooling_rate and heating_rate:
        target = 20.0
        current = None
        if "sensor.t_h_sensor_temperature" in series:
            current = float(series["sensor.t_h_sensor_temperature"].iloc[-1])
        elif "sensor.energy_meter_temperature" in series:
            current = float(series["sensor.energy_meter_temperature"].iloc[-1])

        if current:
            warmup = max(0, target - current) / heating_rate if heating_rate else 0
            model_data["recommendations"]["optimal_pre_heat_minutes_evening"] = round(warmup * 60)
            model_data["recommendations"]["optimal_pre_heat_minutes_morning"] = round(warmup * 60)

    model_path = MODELS_DIR / "temperature_model.json"
    with open(model_path, "w") as f:
        json.dump(model_data, f, indent=2, default=str)
    print(f"\nModelo guardado: {model_path}")

    return model_data


def main():
    parser = argparse.ArgumentParser(description="Analisis y modelo de temperatura del hogar")
    parser.add_argument("--plot", action="store_true", help="Generar graficos")
    parser.add_argument("--predict", action="store_true", help="Generar prediccion")
    parser.add_argument("--hours", type=float, default=4, help="Horas a predecir (default: 4)")
    args = parser.parse_args()

    ha_df = load_ha_data()
    tuya_dfs = load_tuya_data()

    model = run_analysis(ha_df, tuya_dfs, do_plot=args.plot, do_predict=args.predict, predict_hours=args.hours)


if __name__ == "__main__":
    main()