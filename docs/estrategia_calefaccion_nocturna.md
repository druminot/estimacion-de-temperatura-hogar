# Estrategia de Calefaccion Nocturna (00:00-10:00)

## Contexto

- **Sistema**: Radiador de agua (alta inercia termica, ~45min en dejar de emitir calor)
- **Tasa enfriamiento**: ~0.30 C/h (mediana con exterior templado), ~1.0 C/h con exterior frio
- **Tasa calentamiento**: +3.44 C/h (mediana)
- **Hora mas fria afuera**: 07:00-09:00 AM (~2-3C, minimo 1.7C)
- **Objetivo**: Mantener confort (nunca < 16.5C interior) ahorrando energia

## Horario Propuesto

```
Hora   Temp   Accion                      Nota
─────────────────────────────────────────────────
00:00  18.0C  OFF  (fin horario tarde)   Radiador sigue emitiendo ~45min
00:45  17.8C   └─ inercia del radiador
01:30  16.8C  ON 20min                   Radiador aun tibio, calienta rapido
01:50  18.0C  OFF                        Inercia: sube a ~18.3C
02:30  18.3C   └─ pico por inercia
03:20  17.3C  ON 20min                   2C afuera, no dejar bajar mas
03:40  18.5C  OFF                        Inercia: sube a ~18.8C
04:10  18.8C   └─ pico por inercia
05:10  17.8C  ON 20min                   Hora mas fria (2-3C afuera)
05:30  19.0C  OFF                        Inercia: sube a ~19.3C
06:00  19.3C   └─ pico por inercia
06:30  18.8C  ON 40min                   Calentar para la manana
07:10  20.2C  OFF                        Inercia: sube a ~20.5C
07:40  20.5C   └─ pico por inercia
08:40  19.5C  ON 15min                   Mantener
08:55  20.0C  OFF
09:30  19.7C  ON 10min                   Mantener
09:40  20.0C  OFF
10:00  19.8C  ✅ confortable
```

## Resumen

| Concepto | Valor |
|----------|-------|
| Encendidos | 6 veces |
| Tiempo total ON | 2h 05min |
| Temp minima | 16.8C (nunca baja de 16.5C) |
| Temp maxima | 20.5C |
| Temp a las 08:00 | ~20C |
| Temp a las 10:00 | ~20C |
| Ahorro vs 05-08 continuo | ~30% (2h05 vs 3h) |
| Ahorro vs 00-10 continuo | ~79% (2h05 vs 10h) |

## Principios

1. **Aprovechar inercia termica**: El radiador de agua sigue emitiendo calor 30-45min despues de apagar. Cada ciclo OFF arranca con radiador aun tibio.
2. **Ciclos cortos**: 10-40min ON son suficientes para subir 1-2C con inercia.
3. **No dejar enfriar del todo**: La temperatura nunca baja de 16.5C, asi no se siente frio.
4. **Mas frecuencia en horas frias**: Entre 03:00-06:00 (2-5C afuera) se enciende cada ~1.5h.
5. **Ciclo largo en la manana**: A las 06:30, 40min ON para llegar a 20C a las 08:00.

## Datos del Modelo (5 Julio 2026)

| Metrica | Valor |
|---------|-------|
| Enfriamiento (promedio) | -0.76 C/hora |
| Enfriamiento (mediana) | -0.30 C/hora |
| Calentamiento (promedio) | +2.89 C/hora |
| Calentamiento (mediana) | +3.44 C/hora |
| Correlacion interior/exterior | r = -0.512 |
| Delta medio int/ext | +2.8C |

## Clima Actual (met.no)

Hora mas fria: 07:00-09:00 AM (~2-3C)
Minimo absoluto: 1.7C a las 12:00

## Horarios de Calefaccion

| Periodo | Horario |
|---------|---------|
| Tarde | 17:00 - 00:00 |
| Manana | 05:00 - 08:00 |

## Próximos Pasos

- [ ] Crear automation en Home Assistant con estos ciclos
- [ ] Ajustar tasa de enfriamiento segun temperatura exterior en tiempo real
- [ ] Acumular mas datos con collect_continuous.py para mejorar el modelo
- [ ] Obtener API key de OpenWeatherMap para historial meteorologico completo