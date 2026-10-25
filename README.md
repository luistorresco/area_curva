# CalculusWeb — Cálculo bajo la curva

Aplicación web educativa para dibujar curvas, calcular el área bajo la curva mediante integración numérica (regla del trapecio), reconocer funciones matemáticas y visualizar sólidos de revolución en 3D.

## Arquitectura

- **Frontend**: Astro 4 + Vanilla JS + Tailwind CSS 4 + Three.js 0.160 (CDN)
- **Backend**: FastAPI (Python 3.11) + NumPy + Pydantic
- **Comunicación**: REST API con CORS habilitado
- **Infraestructura**: Docker (imagen única frontend + backend + nginx) + Render

## Estructura del proyecto

```
calculus-web/
├── backend/
│   ├── main.py            # FastAPI — endpoints REST
│   ├── curve_math.py      # Geometría numérica (validación, integración, intersecciones)
│   ├── math_engine.py     # Evaluador seguro de expresiones (AST whitelist)
│   ├── recognition.py     # Reconocimiento de funciones matemáticas
│   ├── schemas.py         # Contratos Pydantic
│   ├── requirements.txt   # Dependencias Python
│   └── tests/             # Tests unitarios (pytest/unittest)
├── frontend/
│   ├── src/
│   │   ├── layouts/
│   │   │   └── Layout.astro       # Layout global (nav, estilos, footer)
│   │   └── pages/
│   │       ├── index.astro         # Plano cartesiano + dibujo + modo función
│   │       ├── curvas.astro        # Reconocimiento de funciones
│   │       ├── curvas3d.astro      # Curvas en 3D
│   │       ├── calculo.astro       # Visualización 3D de la integral
│   │       ├── revolucion.astro    # Sólido de revolución
│   │       ├── results.astro       # Resultados del cálculo
│   │       ├── formula.astro       # Fórmulas y metodología
│   │       └── nosotros.astro      # Equipo
│   ├── astro.config.mjs
│   └── package.json
├── nginx/
│   └── nginx.conf         # Configuración de nginx (proxy /api → backend)
├── Dockerfile             # Imagen única (frontend + backend + nginx)
├── docker-entrypoint.sh   # Script de arranque (sed + uvicorn + nginx)
├── docker-compose.yml     # Compose para desarrollo local
├── .dockerignore
└── README.md
```

## Funcionalidades

1. **Dibujo interactivo**: traza una curva con mouse, touch o trackpad sobre un plano cartesiano
2. **Relleno de trapecios en vivo**: cada segmento se sombrea violeta (positivo) o rosa (negativo) mientras dibujas
3. **Cálculo de área**: integral firmada, área geométrica total, área positiva, área negativa
4. **Detección de intersecciones**: cruces con el eje X mediante cambio de signo + interpolación lineal
5. **Modo función f(x)**: escribe una expresión matemática (`sin(x)`, `x**2`, `exp(-x)*cos(3*x)`, etc.) y se grafica automáticamente
6. **Reconocimiento de funciones**: analiza un trazo dibujado y sugiere la función matemática que mejor se ajusta (polinómica, trigonométrica, exponencial, logarítmica, radical, etc.)
7. **Visualización 3D**: curva y trapecios en volumen con animaciones progresivas (Three.js)
8. **Sólido de revolución**: dibuja una curva o escribe f(x), gírala alrededor de un eje (X, Y, Z o combinaciones) para generar un volumen 3D
9. **Pantalla de resultados**: fórmulas, explicación educativa y desglose de trapecios
10. **Pantalla de fórmulas**: proceso paso a paso con cada fórmula y su justificación
11. **Validación de dibujo**: detecta si el trazo representa una función válida (rechaza círculos, parábolas horizontales, trazos verticales)

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

### Tests

```bash
cd backend
python -m pytest tests/ -v
# o
python -m unittest discover tests/
```

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
2. Render inyecta `PORT` automáticamente; la imagen lo usa para exponer nginx (no hay que configurar nada más).
3. Imagen publicada en Docker Hub: `yoes/calculus-web:latest` (también etiquetada como `yoes/area-curva:latest`).

## API Endpoints

- `POST /api/calculate` — Calcula el área bajo la curva
  - Body: `{ "points": [{ "x": number, "y": number }, ...] }`
  - Response: `{ signed_integral, positive_area, negative_area, total_geometric_area, processed_points, x_axis_intersections, has_valid_result }`

- `POST /api/evaluate-function` — Evalúa una expresión matemática y devuelve puntos muestreados
  - Body: `{ "expression": "sin(x)", "start": -5, "end": 5, "samples": 240 }`
  - Response: `{ expression, start, end, points: [{x, y}, ...] }`

- `POST /api/validate-drawing` — Valida si un trazo representa una función válida
  - Body: `{ "points": [{ "x", "y" }, ...] }`
  - Response: `{ status, is_function, reason_code, diagnostics }`

- `POST /api/recognize-function` — Reconoce la función matemática de un trazo
  - Body: `{ "points": [{ "x", "y" }, ...] }`
  - Response: `{ status, recognized, expression, method, confidence, candidates, warnings }`

- `POST /api/area-between-curves` — Calcula el área entre dos curvas
  - Body: `{ "f_expression": "x**2", "f_start": 0, "f_end": 2, "g_expression": "x", "g_start": 0, "g_end": 2 }`

- `GET /api/health` — Health check

## Algoritmo de integración (regla del trapecio)

1. **Validación**: mínimo 2 puntos, no vertical, sin NaN/Infinity
2. **Limpieza**: eliminar duplicados (ε=1×10⁻⁶) y puntos muy cercanos (<1×10⁻¹²)
3. **Simplificación**: reducir a máx. 500 puntos si es necesario
4. **Ordenamiento**: por coordenada X (monótona)
5. **Intersecciones**: detección por cambio de signo + interpolación lineal
6. **Integración**: regla del trapecio por segmentos consecutivos

$$A_i = \frac{y_i + y_{i+1}}{2} \times (x_{i+1} - x_i)$$

$$\int f(x)\,dx \approx \sum A_i$$

## Fórmulas utilizadas

| Área | Fórmula |
|------|---------|
| Trapecio individual | $A_i = \frac{y_i + y_{i+1}}{2} \times (x_{i+1} - x_i)$ |
| Integral firmada | $\sum A_i$ (áreas bajo el eje X contribuyen negativamente) |
| Área geométrica total | $\sum |A_i|$ |
| Área positiva | $\sum \max(A_i, 0)$ |
| Área negativa | $\sum \min(A_i, 0)$ |
| Intersección con eje X | $x_{int} = x_i - y_i \times \frac{x_{i+1} - x_i}{y_{i+1} - y_i}$ |

## Reconocimiento de funciones

El módulo `recognition.py` ajusta los puntos a modelos matemáticos usando NumPy:

- **Constante**: $y = c$
- **Polinómica**: $y = a_n x^n + \dots + a_0$ (grados 1-4)
- **Exponencial**: $y = a \cdot e^{bx} + c$
- **Logarítmica**: $y = a \cdot \ln(x) + b$
- **Radical**: $y = a \cdot \sqrt{x} + b$
- **Valor absoluto**: $y = a \cdot |x - h| + k$
- **Racional**: $y = \frac{a}{x} + b$
- **Trigonométrica**: $y = a \cdot \sin(bx + c) + d$
- **Sigmoide**: $y = \frac{L}{1 + e^{-k(x - x_0)}}$

Cada modelo se evalúa con métricas de error (MSE, R²) y se devuelven candidatos ordenados por ajuste.

## Seguridad del evaluador de expresiones

El módulo `math_engine.py` usa un parser AST (no `eval`/`exec`) con whitelist estricta:

- **Operadores**: `+ - * / ** ^` (y unario `+ -`)
- **Funciones**: `sin cos tan asin acos atan atan2 sqrt cbrt abs exp log log2 log10 sinh cosh tanh floor ceil factorial radians degrees pow hypot`
- **Constantes**: `pi e tau`
- **Límites**: longitud máxima 200 caracteres, máx. 300 nodos AST, potencias acotadas a |base| ≤ 512, factorial acotado a n ≤ 170
- Rechaza: `__import__`, `open`, comprehensions, lambdas, ternarios, llamadas a métodos, nombres desconocidos

## Tecnologías

- **FastAPI 0.109** + Uvicorn — API REST asíncrona
- **Astro 4.16** — SSG con islas de interactividad
- **Three.js 0.160** (CDN) — escenas 3D (visualización de integral, sólido de revolución)
- **Tailwind CSS 4** — estilos utilitarios
- **NumPy** — validaciones numéricas y ajuste de curvas
- **Pydantic 2.5** — validación de schemas
- **Fraunces + Inter + JetBrains Mono** — tipografía

## Docker Hub

Imagen publicada: `yoes/calculus-web:latest` (también `yoes/area-curva:latest`)
- Contiene frontend estático + backend FastAPI + nginx en un solo contenedor
- Variable `PORT` para despliegue en Render
- Entrypoint ejecuta `sed` de forma secuencial antes de arrancar nginx (evita race condition)