# CalculusWeb — Cálculo bajo la curva

Aplicación web educativa para dibujar curvas, calcular el área bajo la curva mediante integración numérica (regla del trapecio), reconocer funciones matemáticas, visualizar sólidos de revolución en 3D y calcular volúmenes por discos, arandelas o capas cilíndricas.

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
│   ├── volume_math.py     # Volúmenes de revolución (discos, arandelas, capas)
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
9. **Cálculo de volumen por revolución**: discos, arandelas y capas cilíndricas alrededor de X o Y, con fórmula, integral planteada, validaciones y explicación paso a paso. El botón «Calcular volumen» toma automáticamente la curva dibujada o escrita en el visor superior: si la función no está graficada o cambió la expresión/intervalo, se grafica antes de calcular. Cambiar el método o el eje recalcula el nuevo sólido con esa misma curva y conserva la selección.
10. **Pantalla de resultados**: fórmulas, explicación educativa y desglose de trapecios
11. **Pantalla de fórmulas**: proceso paso a paso con cada fórmula y su justificación
12. **Validación de dibujo**: detecta si el trazo representa una función válida (rechaza círculos, parábolas horizontales, trazos verticales)

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

- `POST /api/volume` — Calcula el volumen de un sólido de revolución a partir de expresiones
  - Body: `{ "method": "discos", "axis": "x", "f_expression": "sqrt(x)", "g_expression": "0", "start": 0, "end": 4, "samples": 2000 }`
  - `method`: `discos`, `arandelas` o `capas`; `axis`: `x` o `y`
  - Response: `{ volume, integral, factor, variable, method_label, axis_label, formula, setup, steps, f_points, g_points, warnings, ... }`

- `POST /api/volume-profile` — Calcula el volumen directamente desde el trazo dibujado o la función escrita en el visor
  - Body: `{ "method": "capas", "axis": "y", "points": [{ "x": 0, "y": 0 }, { "x": 1, "y": 1 }, ...], "g_expression": "0", "samples": 2000, "f_expression": "x", "source": "draw" }`
  - `start` y `end` son opcionales: si no se envían, el backend deriva el intervalo correcto para la variable de integración.
  - La curva `points` es la frontera real de la región. El backend obtiene los radios (discos/arandelas) o las alturas (capas) de cada corte, incluso cuando el método integra en `y`.
  - Response: igual que `/api/volume`, más `profile: true`, `profile_points`, `f_expression` y `g_expression`.

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

## Volúmenes de revolución

El cálculo se hace numéricamente con la regla compuesta de Simpson y valida los casos en que la región cruza el eje de giro (arandelas y capas).

| Método | Fórmula | Variable de integración |
|--------|---------|-------------------------|
| Discos | $V = \pi \int [R(t)]^2\,dt$ | El eje de giro |
| Arandelas | $V = \pi \int ([R(t)]^2 - [r(t)]^2)\,dt$ | El eje de giro |
| Capas cilíndricas | $V = 2\pi \int \rho(t)h(t)\,dt$ | Perpendicular al eje de giro |

Al girar alrededor de **X**, la coordenada axial es $x$ y el radio es $|y|$. Al girar alrededor de **Y**, la coordenada axial es $y$ y el radio es $|x|$. Por eso el mismo perfil produce sólidos distintos según el eje.

### Cálculo desde la curva dibujada o escrita

El botón «Calcular volumen» lee el perfil actual del sólido de arriba (el trazo dibujado o la función escrita) y usa sus puntos reales como frontera de la región:

- Si el visor está en modo Función y la expresión escrita todavía no se ha graficado, o si cambió la expresión o el intervalo desde la última gráfica, se pulsa «Graficar» automáticamente y se espera a que el perfil esté disponible antes de calcular.
- El intervalo natural se deriva de la región para cada combinación método/eje:
  - discos y arandelas alrededor de **X** integran en $x$;
  - capas alrededor de **Y** integran en $x$ (usando la parte $x \ge 0$ o reflejando un trazo negativo);
  - discos y arandelas alrededor de **Y** integran en $y$ con cortes horizontales;
  - capas alrededor de **X** integran en $y$ con el ancho horizontal del trazo para cada radio.
- Cambiar el método o el eje después de calcular **no reinicia** la selección ni borra la curva: se recalcula automáticamente el nuevo sólido con la misma curva. Si todavía no hay un resultado, el cambio solo actualiza la vista previa y se aplica al pulsar «Calcular volumen».
- La gráfica 2D dibuja el trazo original con línea discontinua y la región derivada para el método elegido. La vista 3D usa los radios/alturas calculados del trazo.
- Si el trazo tiene un hueco interior y se elige discos, se emite una advertencia y se sugiere arandelas. Si hay varios tramos horizontales en un corte, se usa el radio exterior máximo y el interior mínimo.
- El resultado se calcula con los puntos muestreados, por lo que puede diferir ligeramente del valor exacto de la expresión escrita. Aumentar «muestras» reduce esa diferencia.

Los campos f(x), g(x) e intervalo del panel son de **solo lectura**: muestran la referencia usada en el último cálculo. Para cambiar la curva, edítala en el visor superior y vuelve a pulsar «Calcular volumen». Con una sola curva, $g(x)=0$; en arandelas alrededor de X el resultado coincide con discos, mientras que alrededor de Y los cortes horizontales pueden producir un hueco interior.

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
- **Variables**: `x` (por defecto) o `y` en expresiones de volumen
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