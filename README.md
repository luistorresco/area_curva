# CalculusWeb - Cálculo bajo la curva

Aplicación web educativa para dibujar curvas y calcular el área bajo la curva mediante integración numérica (regla del trapecio).

## Arquitectura

- **Frontend**: Astro.js + Vanilla JS (Canvas API) + Three.js
- **Backend**: FastAPI (Python)
- **Comunicación**: REST API con CORS habilitado

## Estructura del proyecto

```
calculus-web/
├── backend/
│   ├── main.py           # FastAPI application
│   └── requirements.txt  # Python dependencies
└── frontend/
    ├── src/
    │   ├── layouts/
    │   │   └── Layout.astro
    │   └── pages/
    │       ├── index.astro      # Pantalla principal (canvas)
    │       └── results.astro    # Pantalla de resultados
    ├── astro.config.mjs
    └── package.json
```

## Funcionalidades

1. **Dibujo interactivo**: Mouse, touch, trackpad
2. **Plano cartesiano**: Ejes, cuadrícula, etiquetas numéricas
3. **Relleno de trapecios en vivo**: Cada segmento se sombrea según su signo mientras dibujas
4. **Integración numérica**: Regla del trapecio
5. **Detección de intersecciones**: Cruces con eje X
6. **Cálculo de áreas**:
   - Integral firmada
   - Área positiva
   - Área negativa
   - Área geométrica total
7. **Pantalla de resultados**: Fórmulas y explicación educativa
8. **Visualización 3D (Three.js)**: Curva y trapecios en volumen con animaciones progresivas
9. **Hero animado (Three.js)**: Plano cartesiano vivo con curva luminosa, trapecios y partículas

## Cómo ejecutar

### Backend (FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

El servidor estará en `http://localhost:8000`

### Frontend (Astro)

```bash
cd frontend
npm install
npm run dev
```

El frontend estará en `http://localhost:4321` (con proxy a `/api` hacia el backend)

### Docker (imagen única: frontend + backend)

```bash
docker build -t calculus-web .
docker run -p 8080:80 calculus-web
# o con compose:
docker compose up --build
```

Un solo contenedor sirve el frontend estático con nginx y levanta la API FastAPI
en `127.0.0.1:8000`; nginx redirige `/api/` al backend interno. La variable de
entorno `PORT` define el puerto de escucha de nginx (por defecto 80).

### Despliegue en Render

1. Conecta el repositorio en Render y selecciona **Docker** como runtime.
2. Render inyecta `PORT` automáticamente; la imagen lo usa para exponer nginx
   (no hay que configurar nada más).
3. Imagen publicada en Docker Hub: `yeos/calculus-web:latest`
   (también etiquetada como `yeos/area-curva:latest`).

## API Endpoints

- `POST /api/calculate` - Calcula el área bajo la curva
  - Body: `{ "points": [{ "x": number, "y": number }, ...] }`
  - Response: `{ signed_integral, positive_area, negative_area, total_geometric_area, processed_points, x_axis_intersections, has_valid_result }`

- `GET /api/health` - Health check

## Algoritmo

1. **Validación**: Mínimo 2 puntos, no vertical, sin NaN/Infinity
2. **Limpieza**: Eliminar duplicados y puntos muy cercanos (< 1e-6)
3. **Simplificación**: Reducir a máx. 500 puntos si es necesario
4. **Ordenamiento**: Por coordenada X (monótona)
5. **Intersecciones**: Detección por cambio de signo + interpolación lineal
6. **Integración**: Regla del trapecio por segmentos consecutivos

## Tecnologías

- FastAPI 0.109 + Uvicorn
- Astro 4.16
- Three.js 0.160 (CDN, escenas del hero y de la visualización 3D)
- Fraunces + Inter + JetBrains Mono (tipografía)
- NumPy para validaciones numéricas
- Pydantic para validación de schemas