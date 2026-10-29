# DAROX Lead Engine | Automatización Sales Ops B2B

Sistema automatizado en Python para la **captación de clientes de alta intención de compra** para **DAROX** (Agencia de Diseño Web, Branding y Posicionamiento Digital).

El sistema intercepta a las empresas en dos momentos críticos:
1. **Fase Temprana (Día 0):** En el instante exacto en que se publica su constitución en el **BORME** (Boletín Oficial del Registro Mercantil de España), antes de que contraten a otra agencia o tengan presencia digital.
2. **Fase de Apertura Local:** Detección de nuevos establecimientos y locales comerciales en **Google Maps** cuyo perfil carece de página web (`website is None`).

---

## 🏗 Arquitectura del Sistema

```text
Empresas/
├── config/
│   ├── __init__.py
│   └── settings.py          # Configuración, rutas, variables de entorno
├── data/
│   ├── leads_borme_enriquecidos.csv  # CSV final con scoring y cualificación
│   ├── leads_google_places.csv       # CSV con negocios locales sin web
│   └── places_store.db              # SQLite con historial y control de deltas
├── modules/
│   ├── borme/               # Módulo 1: Scraper y Parser de PDFs del BORME
│   │   ├── models.py        # Modelo de datos (LeadBORME)
│   │   ├── parser.py        # Extracción regex de constituciones, objeto social, administradores
│   │   └── scraper.py       # Descarga y resolución de ediciones del BOE
│   ├── enrichment/          # Módulo 2: Enriquecimiento OSINT
│   │   ├── domain_checker.py# Resolución DNS ultrarrápida (.es, .com)
│   │   ├── linkedin_finder.py# Dorks OSINT para encontrar a fundadores/administradores
│   │   └── enricher.py      # Orquestador y scoring de ventas para DAROX
│   ├── places/              # Módulo 3: Google Places y persistencia
│   │   ├── database.py      # SQLite con control de primera/última detección
│   │   └── tracker.py       # API Google Maps + Modo Demostración
│   └── export/
│       └── csv_exporter.py  # Exportador a CSV optimizado para Excel (UTF-8-SIG)
├── main.py                  # CLI Orquestador del pipeline completo
├── requirements.txt         # Dependencias del proyecto
├── .env.example             # Plantilla de variables de entorno
└── .env                     # Variables de entorno activas
```

---

## 🚀 Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.10 o superior (compatible con Python 3.11, 3.12 y 3.13).

### 2. Instalación de Dependencias
Abre tu terminal en la carpeta del proyecto y ejecuta:

```bash
pip install -r requirements.txt
```

### 3. Configuración del Archivo `.env`
El proyecto incluye un archivo `.env` precargado basado en `.env.example`:

```ini
# Clave API de Google Places (Requerida para búsqueda real en Google Maps)
GOOGLE_PLACES_API_KEY=tu_clave_aqui

# Provincias prioritarias para el BORME (separadas por comas, vacío para toda España)
BORME_PROVINCES=MADRID,BARCELONA,VALENCIA

# Rutas de salida
DB_PATH=data/places_store.db
CSV_BORME_OUTPUT=data/leads_borme_enriquecidos.csv
CSV_PLACES_OUTPUT=data/leads_google_places.csv
```

> **Nota sobre Google Places:** Si aún no dispones de una clave de Google Maps Platform, el sistema se ejecuta automáticamente en **Modo Demostración / Simulación**, permitiendo comprobar el funcionamiento de la base de datos SQLite y la exportación a CSV sin bloquearte.

---

## 🖥 Dashboard Visual de Prospección B2B (`dashboard.py`)

El sistema incluye un **Dashboard visual interactivo** diseñado con estética *Financial Ops / Enterprise B2B* (inspirado en Linear y Stripe, alejado de plantillas genéricas de IA), con alta densidad informativa, ergonomía para equipos Sales Ops y atajos de teclado.

### 1. Iniciar el Dashboard en Vivo (Servidor Local)
Inicia la API FastAPI y abre automáticamente la interfaz en tu navegador por defecto:

```bash
python dashboard.py
# o también:
python main.py --dashboard
```

El servidor estará accesible en: `http://127.0.0.1:8505`

### 2. Versión Autónoma sin Servidor (Standalone HTML)
Si deseas consultar, filtrar o enviar el dashboard sin necesidad de ejecutar Python, el sistema compila automáticamente:
📁 `data/dashboard.html`

> **Doble clic en `data/dashboard.html`:** Funciona 100% en local en cualquier navegador (Chrome, Edge, Safari, Firefox), con búsqueda instantánea en memoria, filtros por sector, visualizador de expedientes, generador de pitchs y exportador de CSV.

### 3. Características Clave del Dashboard:
- **Omnibox Universal (`Ctrl + K`):** Búsqueda multitoken instantánea por nombre de empresa, nombre de fundadores/administradores, provincia, CIF, teléfono o actividad del objeto social.
- **KPIs en Tiempo Real:** Total de prospectos cualificados, % de Hot Leads sin web, volumen acumulado de capital social auditado y porcentaje de dominios `.es` y `.com` libres.
- **Segmentación por Fuentes:** Pestañas para alternar entre *Todos los Leads*, *BORME (Sociedades Día 0)*, *Google Places (Locales comerciales)* y *⭐ Guardados / Favoritos*.
- **Filtros Sectoriales Rápidos:** Filtrado con un clic para *Salud & Dental*, *Inmobiliario*, *Hostelería*, *Reformas & Construcción*, *Tecnología & Digital* y *Asesoría & Legal*.
- **Expediente Lateral Deslizante (Slide-Over Drawer):** Haz clic en cualquier fila para inspeccionar el desglose de puntuación, estado DNS de dominios, objeto social completo, administradores y enlace a Google Maps.
- **Generador de Pitch Comercial DAROX (1-Click Copy):** Redacta automáticamente mensajes hiperpersonalizados para LinkedIn InMail, Email Frío o Guión Telefónico mencionando el nombre del fundador y el sector.
- **Lead Acquisition Hub ("Ampliar Búsqueda"):** Modal para lanzar extracciones directas del BORME por provincias o rastreos de Google Places por nicho y ciudad en segundo plano.

---

## 🛠 Guía de Uso del CLI (`main.py`)

### 1. Ejecución Completa (Recomendado para uso diario)
Ejecuta todo el pipeline: scraping del BORME de hoy, enriquecimiento OSINT de dominios y perfiles, rastreo de locales y exportación de ambos CSVs:

```bash
python main.py
```

### 2. Filtrar por Provincias Concretas
```bash
python main.py --provinces MADRID,BARCELONA,VALENCIA,MALAGA
```

### 3. Modo Rápido (Solo Verificación de Dominios, sin LinkedIn)
Ideal si deseas procesar cientos de empresas en pocos segundos:
```bash
python main.py --no-linkedin
```

### 4. Consultar una Fecha Específica del BORME
```bash
python main.py --date 2026-10-28
```

### 5. Limitar el número de empresas
```bash
python main.py --max-borme 20
```

### 6. Ejecutar únicamente el Rastreador de Google Places
```bash
python main.py --places --query "clinicas dentales y estetica en Madrid"
```

---

## 📊 Estructura de los Leads Cualificados (CSV)

### CSV 1: `data/leads_borme_enriquecidos.csv`
Columnas generadas listas para importar en HubSpot, Notion o Excel:

| Columna | Descripción |
|---|---|
| `categoria_lead` | **ALTA PRIORIDAD (HOT LEAD)**, MEDIA PRIORIDAD o PROSPECTO GENERAL |
| `lead_score` | Puntuación de 50 a 120 según liquidez, ausencia de web y contacto |
| `company_name` | Razón social oficial de la sociedad constituida |
| `province` | Provincia de registro mercantil |
| `borme_date` | Fecha de publicación oficial |
| `administradores_str` | Nombres de administradores únicos, solidarios o mancomunados |
| `linkedin_contacto_nombre` | Nombre en formato natural para prospección |
| `linkedin_url` | Enlace directo al perfil del administrador en LinkedIn |
| `sin_web_detectada` | `True` si ni el dominio `.es` ni el `.com` están registrados |
| `dominio_sugerido` | Slug de marca sugerido (ej: `inversionesbalboa`) |
| `dominio_es_disponible`| `True` si el dominio `.es` está libre para registrar |
| `dominio_com_disponible`| `True` si el dominio `.com` está libre para registrar |
| `capital` | Capital social aportado (ej: `10.000,00 Euros`) |
| `objeto_social` | Actividad mercantil de la empresa |
| `domicilio_social` | Dirección fiscal registrada |
| `accion_sugerida` | Recomendación táctica para el SDR/Comercial |
| `motivos_cualificacion` | Explicación del score asignado |

### CSV 2: `data/leads_google_places.csv`
| Columna | Descripción |
|---|---|
| `alert` | `SIN PAGINA WEB DETECTADA` |
| `is_new_business` | `True` si el local apareció por primera vez en esta búsqueda |
| `name` | Nombre comercial del local |
| `phone` | Teléfono de contacto directo |
| `address` | Dirección física |
| `rating` | Valoración en Google |
| `opportunity` | Venta de web y optimización de Google Business Profile |

---

## 🎯 Playbook de Ventas B2B para DAROX

### Disparador de Venta (Trigger Event):
La empresa se acaba de constituir legalmente en el Registro Mercantil. Todavía no tiene logotipo definitivo, papelería, identidad de marca ni página web.

### Plantilla de Mensaje para LinkedIn (SDR / Outreach):
> *"Hola {{linkedin_contacto_nombre}}, enhorabuena por la constitución de {{company_name}}. He visto que aún tenéis disponible el dominio {{dominio_com}} y no habéis lanzado la identidad digital de la marca. En DAROX nos especializamos en diseñar la identidad visual y página web de empresas en fase de lanzamiento para captar clientes desde el día 1. ¿Tenéis 10 minutos esta semana para ver opciones antes de que compréis el dominio?"*

