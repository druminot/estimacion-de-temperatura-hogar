# Agente - Estimacion de Temperatura Hogar

## Descripcion
Proyecto para la estimacion de temperatura en el hogar usando datos de sensores y modelos predictivos.

## Reglas del Agente

### Auto-actualizacion en cada cambio
- **Despues de cada modificacion significativa**, el agente debe ejecutar:
  ```bash
  git add -A
  git commit -m "descripcion del cambio"
  git push origin main
  ```
- El agente debe verificar que los cambios esten sincronizados con GitHub antes de finalizar cualquier tarea.

### Flujo de trabajo
1. Antes de comenzar cualquier tarea, ejecutar `git pull origin main` para asegurar la ultima version.
2. Realizar los cambios solicitados.
3. Ejecutar `git status` para revisar los cambios realizados.
4. Hacer commit con un mensaje descriptivo.
5. Hacer push a GitHub.

### Estructura del proyecto
- `src/` - Codigo fuente principal
- `data/` - Datos de sensores y datasets
- `models/` - Modelos predictivos entrenados
- `notebooks/` - Jupyter notebooks para analisis exploratorio
- `tests/` - Tests del proyecto
- `docs/` - Documentacion adicional

### Convenciones
- Lenguaje principal: Python
- Formato de commits: tipo(alcance): descripcion (ej: feat(sensor): agregar lectura de temperatura)
- Mantener el README.md actualizado con el estado del proyecto
- Usar requirements.txt para dependencias

### Comandos utiles
- `git add -A && git commit -m "mensaje" && git push origin main` - Guardar y sincronizar cambios
- `git pull origin main` - Traer ultimos cambios
- `git log --oneline -5` - Ver ultimos commits