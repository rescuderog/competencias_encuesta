# Sistema de Votación - Vicerrectorado de Investigación UCA

Aplicación web para gestionar votaciones de las competencias **3MT - UCA** y **3min - UCA TFG**.

## Características

- 📊 Dos competencias independientes con URLs separadas
- 🗳️ Votación anónima (un voto por navegador mediante cookies)
- 📈 Dashboard administrativo con estadísticas en tiempo real
- 👥 Gestión de candidatos (agregar, eliminar, randomizar orden)
- 🎨 Diseño minimalista y profesional con los colores institucionales
- 🐳 Dockerizado y listo para Railway.app

## Stack Tecnológico

- **Backend**: Flask + SQLAlchemy (SQLite)
- **Frontend**: HTMX + Alpine.js + Tailwind CSS
- **Deployment**: Docker + Gunicorn

## Instalación Local

### Requisitos
- Python 3.11+
- Docker (opcional)

### Opción 1: Ejecución Directa con Python

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno (opcional)
cp .env.example .env
# Editar .env con tu contraseña de admin

# Ejecutar la aplicación
python app.py
```

La aplicación estará disponible en `http://localhost:5000`

### Opción 2: Ejecución con Docker

```bash
# Construir y ejecutar con Docker Compose
docker-compose up --build
```

La aplicación estará disponible en `http://localhost:5000`

## Configuración

Variables de entorno disponibles:

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `ADMIN_PASSWORD` | Contraseña del dashboard administrativo | `admin123` |
| `SECRET_KEY` | Clave secreta de Flask. **Obligatoria en producción**: firma la cookie de sesión. | Auto-generada (solo válida con 1 worker) |
| `SESSION_COOKIE_SECURE` | `1` para enviar la cookie solo por HTTPS (Railway). `0` en local. | `0` |
| `PORT` | Puerto del servidor | `5000` |

## Uso

### Votación

- **Página principal**: `http://localhost:5000`
- **3MT - UCA**: `http://localhost:5000/vote/3mt-uca`
- **3min - UCA TFG**: `http://localhost:5000/vote/3min-uca-tfg`

### Dashboard Administrativo

- **Login**: `http://localhost:5000/dashboard`
- **Contraseña por defecto**: `admin123` (cambiar en producción)

Desde el dashboard puedes:
- Ver estadísticas de votación en tiempo real (1º, 2º, 3º lugar, etc.)
- Agregar y eliminar candidatos
- Activar/desactivar el orden aleatorio de candidatos
- Gestionar ambas competencias de forma independiente

## Deploy en Railway.app

1. Conecta tu repositorio de GitHub a Railway
2. Railway detectará automáticamente el `Dockerfile`
3. Configura las variables de entorno:
   - `ADMIN_PASSWORD`: Tu contraseña segura
   - `SECRET_KEY`: Una clave secreta aleatoria
   - `SESSION_COOKIE_SECURE`: `1`
4. Railway asignará automáticamente el puerto (variable `PORT`)

## Estructura del Proyecto

```
competencias_encuesta/
├── app.py                 # Aplicación Flask principal
├── requirements.txt       # Dependencias Python
├── Dockerfile            # Configuración Docker
├── docker-compose.yml    # Configuración Docker Compose
├── templates/            # Plantillas HTML
│   ├── base.html
│   ├── index.html
│   ├── vote.html
│   ├── dashboard_login.html
│   └── dashboard.html
├── static/              # Archivos estáticos
│   └── logo_vri.png
└── instance/            # Base de datos SQLite (generada automáticamente)
```

## Seguridad

- Las votaciones están limitadas a una por navegador mediante una sesión firmada (cookie `HttpOnly`, `SameSite=Lax`)
- El endpoint de voto exige un token de un solo uso que solo se emite al cargar la página de votación; un `POST` directo sin sesión se rechaza con `403`
- Cada voto debe contener exactamente 3 candidatos distintos de la misma competencia
- El dashboard está protegido con contraseña; la sesión del admin también va en la cookie firmada, nunca la contraseña en claro
- Limitación conocida: la sesión vive en el navegador, así que una ventana de incógnito sigue contando como votante nuevo. Cerrar eso requiere identidad (login), no cookies.
- En producción, asegúrate de cambiar `ADMIN_PASSWORD` y `SECRET_KEY`

## Licencia

© 2025 Universidad Católica Argentina - Vicerrectorado de Investigación
