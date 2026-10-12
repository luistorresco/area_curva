# CalculusWeb - Cálculo bajo la curva

Aplicación web educativa para dibujar curvas y calcular el área bajo la curva mediante integración numérica (regla del trapecio).

## Arquitectura

- **Frontend**: Astro.js + Vanilla JS (Canvas API)
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
3. **Integración numérica**: Regla del trapecio
4. **Detección de intersecciones**: Cruces con eje X
5. **Cálculo de áreas**:
   - Integral firmada
   - Área positiva
   - Área negativa
   - Área geométrica total
6. **Pantalla de resultados**: Fórmulas y explicación educativa

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
- NumPy para validaciones numéricas
- Pydantic para validación de schemas