import os
import sys
import json
import re
import datetime
import threading
import webbrowser
from pathlib import Path
from typing import List, Dict, Optional, Any

import pandas as pd
from fastapi import FastAPI, Query, Body, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Configuración de rutas
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

CSV_BORME = DATA_DIR / "leads_borme_enriquecidos.csv"
CSV_PLACES = DATA_DIR / "leads_google_places.csv"
DB_PLACES = DATA_DIR / "places_store.db"
CRM_STORE_PATH = DATA_DIR / "crm_store.json"

# Módulos del proyecto
from modules.borme.scraper import BORMEScraper
from modules.enrichment.enricher import LeadEnricher
from modules.places.tracker import GooglePlacesTracker
from modules.export.csv_exporter import CSVExporter

app = FastAPI(title="DAROX Sales Ops Dashboard API", version="2.4.0")

# Estado de tareas en segundo plano
CURRENT_JOB = {
    "status": "idle",
    "type": None,
    "progress": "",
    "logs": [],
    "last_result": None
}

def log_job(msg: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    CURRENT_JOB["logs"].append(formatted)
    CURRENT_JOB["progress"] = msg
    if len(CURRENT_JOB["logs"]) > 100:
        CURRENT_JOB["logs"].pop(0)

def load_crm_store() -> Dict[str, Any]:
    if CRM_STORE_PATH.exists():
        try:
            with open(CRM_STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_crm_store(data: Dict[str, Any]):
    CRM_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CRM_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def infer_sector(name: str, objeto_social: str, types: str = "") -> str:
    """Clasifica de manera precisa el sector empresarial según la actividad."""
    combined = f"{name} {objeto_social} {types}".lower()

    if any(k in combined for k in ["dental", "diente", "odontol", "estetic", "salud", "medic", "dermato", "fisioter", "clinica", "belleza"]):
        return "Salud, Dental & Estética"
    if any(k in combined for k in ["inmobiliari", "vivienda", "inmueble", "fincas", "promocion inmobiliaria", "arrendamiento de bienes"]):
        return "Inmobiliario & PropTech"
    if any(k in combined for k in ["restauran", "hosteler", "bar", "cafeter", "gastronom", "catering", "vinoteca", "bebida", "comida", "alimentos", "cocina"]):
        return "Hostelería & Gastronomía"
    if any(k in combined for k in ["arquitect", "interiorism", "reforma", "construc", "albanil", "instalac", "edific", "obras"]):
        return "Construcción & Reformas"
    if any(k in combined for k in ["software", "tecnolog", "informatic", "ai", "inteligencia artificial", "app", "digital", "e-commerce", "datos", "plataforma", "it "]):
        return "Tecnología & Digital"
    if any(k in combined for k in ["abogad", "legal", "bufet", "asesor", "fiscal", "juridic", "auditor", "consultor", "holding", "participacion"]):
        return "Asesoría & Legal"
    if any(k in combined for k in ["gimnasio", "fitness", "pilates", "yoga", "deport", "entrenam"]):
        return "Fitness & Deportes"
    if any(k in combined for k in ["transporte", "logistic", "almacen", "distribuc", "import", "export"]):
        return "Logística & Comercio"
    
    return "Servicios & Comercio"

def clean_capital_value(cap_str: Any) -> float:
    if not cap_str or pd.isna(cap_str):
        return 0.0
    text = str(cap_str).replace("Euros", "").replace("€", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(text)
    except Exception:
        return 0.0

def get_all_unified_leads() -> List[Dict[str, Any]]:
    leads: List[Dict[str, Any]] = []
    crm_data = load_crm_store()

    # 1. Cargar BORME
    if CSV_BORME.exists():
        try:
            borme_df = pd.read_csv(CSV_BORME, sep=";")
            for idx, row in borme_df.iterrows():
                company_name = str(row.get("company_name", "")).strip()
                if not company_name or company_name == "nan":
                    continue

                act_num = str(row.get("act_number", f"borme_{idx}"))
                lead_id = f"borme_{act_num}"
                objeto = str(row.get("objeto_social", "")).strip()
                capital_str = str(row.get("capital", "")).strip()
                capital_num = clean_capital_value(capital_str)

                # Administradores
                admins_str = str(row.get("administradores_str", ""))
                admins_list = [a.strip() for a in admins_str.split(";") if a.strip() and a != "nan"]
                if not admins_list:
                    raw_admins = str(row.get("administradores", "[]"))
                    try:
                        import ast
                        parsed = ast.literal_eval(raw_admins)
                        if isinstance(parsed, list):
                            admins_list = parsed
                    except Exception:
                        pass

                # Dominios y estado web
                sin_web = bool(row.get("sin_web_detectada", True))
                dom_es_disp = bool(row.get("dominio_es_disponible", True))
                dom_com_disp = bool(row.get("dominio_com_disponible", True))

                # CRM override
                lead_crm = crm_data.get(lead_id, {})

                lead = {
                    "id": lead_id,
                    "source": "BORME",
                    "source_label": "BORME (Día 0)",
                    "name": company_name,
                    "subtitle": str(row.get("domicilio_social", "")),
                    "province": str(row.get("province", "España")),
                    "city": str(row.get("province", "España")),
                    "category": str(row.get("categoria_lead", "ALTA PRIORIDAD (HOT LEAD)")),
                    "score": int(row.get("lead_score", 85)),
                    "date": str(row.get("borme_date", datetime.date.today().strftime("%Y-%m-%d"))),
                    "capital": capital_str if capital_str != "nan" else "3.000,00 Euros",
                    "capital_num": capital_num if capital_num > 0 else 3000.0,
                    "sector": infer_sector(company_name, objeto),
                    "objeto_social": objeto if objeto != "nan" else "Constitución de nueva sociedad mercantil.",
                    "administradores": admins_list,
                    "contact_name": str(row.get("linkedin_contacto_nombre", "")) if str(row.get("linkedin_contacto_nombre", "")) != "nan" else (admins_list[0] if admins_list else ""),
                    "linkedin_url": str(row.get("linkedin_url", "")) if str(row.get("linkedin_url", "")) != "nan" else "",
                    "phone": "",
                    "website": "",
                    "has_website": False,
                    "sin_web_detectada": sin_web,
                    "domain_suggested": str(row.get("dominio_sugerido", "")),
                    "domain_es_available": dom_es_disp,
                    "domain_com_available": dom_com_disp,
                    "rating": 0.0,
                    "opportunity": str(row.get("accion_sugerida", "Contactar para ofrecer identidad corporativa y desarrollo web.")),
                    "reasons": str(row.get("motivos_cualificacion", "Sociedad recién constituida sin presencia web")),
                    "crm_status": lead_crm.get("status", "Nuevo"),
                    "is_favorite": lead_crm.get("favorite", False),
                    "notes": lead_crm.get("notes", "")
                }
                leads.append(lead)
        except Exception as e:
            print(f"[!] Error cargando BORME leads: {e}")

    # 2. Cargar Google Places
    if CSV_PLACES.exists():
        try:
            places_df = pd.read_csv(CSV_PLACES, sep=";")
            for idx, row in places_df.iterrows():
                name = str(row.get("name", "")).strip()
                if not name or name == "nan":
                    continue

                place_id = str(row.get("place_id", f"place_{idx}"))
                lead_id = f"place_{place_id}"
                address = str(row.get("address", ""))
                query_zone = str(row.get("query_zone", ""))

                # Extraer ciudad de la dirección o query_zone
                city = "Madrid"
                for c in ["Madrid", "Barcelona", "Valencia", "Sevilla", "Málaga", "Alicante", "Bilbao", "Zaragoza"]:
                    if c.lower() in address.lower() or c.lower() in query_zone.lower():
                        city = c
                        break

                rating = float(row.get("rating", 4.5)) if not pd.isna(row.get("rating")) else 4.5
                lead_crm = crm_data.get(lead_id, {})

                lead = {
                    "id": lead_id,
                    "source": "PLACES",
                    "source_label": "Google Places",
                    "name": name,
                    "subtitle": address,
                    "province": city.upper(),
                    "city": city,
                    "category": "HOT LEAD (LOCAL SIN WEB)",
                    "score": 95 if rating >= 4.5 else 85,
                    "date": datetime.date.today().strftime("%Y-%m-%d"),
                    "capital": "Negocio Local",
                    "capital_num": 15000.0,
                    "sector": infer_sector(name, "", query_zone),
                    "objeto_social": f"Establecimiento comercial físico detectado en Google Maps sin sitio web registrado. Valoración media: {rating} ★. Zona de prospección: {query_zone}.",
                    "administradores": [],
                    "contact_name": "Gerente / Propietario del Local",
                    "linkedin_url": "",
                    "phone": str(row.get("phone", "")),
                    "website": "",
                    "has_website": False,
                    "sin_web_detectada": True,
                    "domain_suggested": re.sub(r'[^a-zA-Z0-9]', '', name).lower(),
                    "domain_es_available": True,
                    "domain_com_available": True,
                    "rating": rating,
                    "opportunity": "Ofrecer creación de web corporativa para reservas/pedidos y posicionamiento Google Maps.",
                    "reasons": f"Local en Google Maps con {rating}★ de valoración sin página web activa.",
                    "crm_status": lead_crm.get("status", "Nuevo"),
                    "is_favorite": lead_crm.get("favorite", False),
                    "notes": lead_crm.get("notes", "")
                }
                leads.append(lead)
        except Exception as e:
            print(f"[!] Error cargando Places leads: {e}")

    # Ordenar por defecto por score descendente
    leads.sort(key=lambda x: (x.get("score", 0), x.get("capital_num", 0)), reverse=True)
    return leads

# Endpoints API

@app.get("/api/leads")
def get_leads(
    q: Optional[str] = None,
    source: Optional[str] = "all",
    province: Optional[str] = None,
    sector: Optional[str] = None,
    time_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    min_capital: Optional[float] = 0,
    max_capital: Optional[float] = 0,
    hot_only: Optional[bool] = False,
    no_web_only: Optional[bool] = False,
    has_contact: Optional[bool] = False,
    favorites_only: Optional[bool] = False,
    sort_by: Optional[str] = "score",
    sort_order: Optional[str] = "desc"
):
    all_leads = get_all_unified_leads()
    filtered = all_leads

    # Filtro fuente
    if source and source.lower() != "all":
        filtered = [l for l in filtered if l["source"].lower() == source.lower()]

    # Filtro temporal (3 días, 1 semana, 1 mes, 1 año)
    now_date = datetime.date.today()
    if time_range and time_range != "all":
        def check_time(lead_date_str: str) -> bool:
            if not lead_date_str:
                return True
            try:
                ld = datetime.datetime.strptime(lead_date_str[:10], "%Y-%m-%d").date()
                delta_days = (now_date - ld).days
                if time_range == "today":
                    return delta_days == 0
                elif time_range == "3d":
                    return 0 <= delta_days <= 3
                elif time_range == "7d":
                    return 0 <= delta_days <= 7
                elif time_range == "30d":
                    return 0 <= delta_days <= 30
                elif time_range == "1y":
                    return 0 <= delta_days <= 365
                return True
            except Exception:
                return True
        filtered = [l for l in filtered if check_time(l.get("date", ""))]

    # Rango de fechas manual
    if from_date and from_date.strip():
        try:
            fd = datetime.datetime.strptime(from_date[:10], "%Y-%m-%d").date()
            filtered = [l for l in filtered if datetime.datetime.strptime(l.get("date", "2000-01-01")[:10], "%Y-%m-%d").date() >= fd]
        except Exception:
            pass

    if to_date and to_date.strip():
        try:
            td = datetime.datetime.strptime(to_date[:10], "%Y-%m-%d").date()
            filtered = [l for l in filtered if datetime.datetime.strptime(l.get("date", "2099-01-01")[:10], "%Y-%m-%d").date() <= td]
        except Exception:
            pass

    # Filtro texto omnibox
    if q and q.strip():
        tokens = [t.lower() for t in q.strip().split() if t.strip()]
        def match_lead(l: dict) -> bool:
            searchable = f"{l['name']} {l['province']} {l['city']} {l['sector']} {l['contact_name']} {l['objeto_social']} {l['phone']} {l['subtitle']}".lower()
            return all(token in searchable for token in tokens)
        filtered = [l for l in filtered if match_lead(l)]

    # Filtro provincia
    if province and province.strip() and province.upper() != "TODAS":
        prov_list = [p.strip().upper() for p in province.split(",")]
        filtered = [l for l in filtered if any(p in l["province"].upper() or l["province"].upper() in p for p in prov_list)]

    # Filtro sector
    if sector and sector.strip() and sector != "Todos":
        filtered = [l for l in filtered if l["sector"].lower() == sector.lower()]

    # Filtro capital
    if min_capital and min_capital > 0:
        filtered = [l for l in filtered if l["capital_num"] >= min_capital]
    if max_capital and max_capital > 0:
        filtered = [l for l in filtered if l["capital_num"] <= max_capital]

    # Filtros flags
    if hot_only:
        filtered = [l for l in filtered if "HOT" in l["category"].upper() or l["score"] >= 90]
    if no_web_only:
        filtered = [l for l in filtered if l["sin_web_detectada"]]
    if has_contact:
        filtered = [l for l in filtered if bool(l["linkedin_url"] or l["phone"] or (l["contact_name"] and "Gerente" not in l["contact_name"]))]
    if favorites_only:
        filtered = [l for l in filtered if l.get("is_favorite", False)]

    # Ordenación
    reverse = (sort_order.lower() == "desc")
    if sort_by == "score":
        filtered.sort(key=lambda x: x.get("score", 0), reverse=reverse)
    elif sort_by == "capital":
        filtered.sort(key=lambda x: x.get("capital_num", 0), reverse=reverse)
    elif sort_by == "name":
        filtered.sort(key=lambda x: x.get("name", "").lower(), reverse=reverse)
    elif sort_by == "date":
        filtered.sort(key=lambda x: x.get("date", ""), reverse=reverse)

    return {
        "total": len(filtered),
        "total_unfiltered": len(all_leads),
        "leads": filtered
    }

@app.get("/api/stats")
def get_stats():
    all_leads = get_all_unified_leads()
    total = len(all_leads)
    borme_count = sum(1 for l in all_leads if l["source"] == "BORME")
    places_count = sum(1 for l in all_leads if l["source"] == "PLACES")
    hot_count = sum(1 for l in all_leads if "HOT" in l["category"].upper() or l["score"] >= 90)
    sin_web_count = sum(1 for l in all_leads if l["sin_web_detectada"])
    with_contact_count = sum(1 for l in all_leads if l["linkedin_url"] or l["phone"] or (l["contact_name"] and "Gerente" not in l["contact_name"]))
    
    # Capital total sumado (solo empresas con capital real numérico)
    total_capital = sum(l["capital_num"] for l in all_leads if l["source"] == "BORME")

    # Provincias
    provinces: Dict[str, int] = {}
    for l in all_leads:
        p = l["province"]
        provinces[p] = provinces.get(p, 0) + 1
    top_provinces = sorted([{"name": k, "count": v} for k, v in provinces.items()], key=lambda x: x["count"], reverse=True)[:8]

    # Sectores
    sectors: Dict[str, int] = {}
    for l in all_leads:
        s = l["sector"]
        sectors[s] = sectors.get(s, 0) + 1
    top_sectors = sorted([{"name": k, "count": v} for k, v in sectors.items()], key=lambda x: x["count"], reverse=True)

    return {
        "total_leads": total,
        "borme_leads": borme_count,
        "places_leads": places_count,
        "hot_leads": hot_count,
        "hot_percentage": round((hot_count / total * 100), 1) if total else 0,
        "without_web_count": sin_web_count,
        "without_web_pct": round((sin_web_count / total * 100), 1) if total else 0,
        "with_contact_count": with_contact_count,
        "total_capital": total_capital,
        "top_provinces": top_provinces,
        "top_sectors": top_sectors
    }

@app.post("/api/crm/lead")
def update_crm_lead(payload: Dict[str, Any] = Body(...)):
    lead_id = payload.get("id")
    if not lead_id:
        raise HTTPException(status_code=400, detail="Missing lead id")

    crm_data = load_crm_store()
    current = crm_data.get(lead_id, {})

    if "status" in payload:
        current["status"] = payload["status"]
    if "favorite" in payload:
        current["favorite"] = bool(payload["favorite"])
    if "notes" in payload:
        current["notes"] = payload["notes"]

    crm_data[lead_id] = current
    save_crm_store(crm_data)
    return {"status": "ok", "lead_id": lead_id, "data": current}

# Tareas en background para ampliación de búsqueda

def run_borme_task(provinces: List[str], max_companies: int, date_str: Optional[str] = None):
    try:
        CURRENT_JOB["status"] = "running"
        CURRENT_JOB["type"] = "BORME"
        log_job(f"Iniciando escaneo oficial del BORME para: {provinces or 'Todas las provincias'} (Máx: {max_companies})")

        target_date = None
        if date_str:
            try:
                target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        scraper = BORMEScraper(target_provinces=provinces)
        borme_leads = scraper.run(specific_date=target_date, max_companies=max_companies)

        if not borme_leads:
            log_job("[!] No se encontraron nuevas sociedades constituidas en el período.")
            CURRENT_JOB["status"] = "done"
            CURRENT_JOB["last_result"] = {"count": 0}
            return

        log_job(f"Extracción completada: {len(borme_leads)} sociedades. Iniciando enriquecimiento ultrarrápido...")
        enricher = LeadEnricher(check_linkedin=False)
        enriched = enricher.enrich_leads(borme_leads)

        log_job(f"Guardando {len(enriched)} leads cualificados en CSV...")
        CSVExporter.export_borme_leads(enriched, CSV_BORME)

        log_job("[OK] Búsqueda ampliada del BORME completada exitosamente.")
        CURRENT_JOB["status"] = "done"
        CURRENT_JOB["last_result"] = {"count": len(enriched)}
    except Exception as e:
        log_job(f"[ERROR] Falló la extracción del BORME: {e}")
        CURRENT_JOB["status"] = "error"
        CURRENT_JOB["last_result"] = {"error": str(e)}

def run_places_task(query: str):
    try:
        CURRENT_JOB["status"] = "running"
        CURRENT_JOB["type"] = "PLACES"
        log_job(f"Rastreando Google Places para: '{query}'...")

        tracker = GooglePlacesTracker()
        places_leads = tracker.track(query=query)

        if places_leads:
            log_job(f"Guardando {len(places_leads)} locales sin página web en base de datos...")
            db_leads = tracker.db.get_leads_without_website()
            export_list = []
            for d in db_leads:
                export_list.append({
                    "place_id": d.get("place_id"),
                    "name": d.get("name"),
                    "address": d.get("address"),
                    "phone": d.get("phone"),
                    "rating": d.get("rating"),
                    "is_new_business": (d.get("times_seen", 1) == 1),
                    "alert": "SIN PAGINA WEB DETECTADA",
                    "query_zone": d.get("query_zone"),
                    "opportunity": "Ofrecer creación de web y posicionamiento Google Business Profile"
                })
            CSVExporter.export_places_leads(export_list if export_list else places_leads, CSV_PLACES)

        log_job(f"[OK] Rastreo de Google Places completado. {len(places_leads)} nuevos prospectos.")
        CURRENT_JOB["status"] = "done"
        CURRENT_JOB["last_result"] = {"count": len(places_leads)}
    except Exception as e:
        log_job(f"[ERROR] Falló el rastreo de Google Places: {e}")
        CURRENT_JOB["status"] = "error"
        CURRENT_JOB["last_result"] = {"error": str(e)}

@app.post("/api/search/borme")
def api_search_borme(background_tasks: BackgroundTasks, payload: Dict[str, Any] = Body(...)):
    if CURRENT_JOB["status"] == "running":
        raise HTTPException(status_code=409, detail="Hay otra búsqueda en curso actualmente.")

    CURRENT_JOB["logs"] = []
    provinces = payload.get("provinces", [])
    max_c = int(payload.get("max_companies", 30))
    date_val = payload.get("date", "")

    background_tasks.add_task(run_borme_task, provinces, max_c, date_val)
    return {"status": "started", "message": "Búsqueda en BORME iniciada en segundo plano."}

@app.post("/api/search/places")
def api_search_places(background_tasks: BackgroundTasks, payload: Dict[str, Any] = Body(...)):
    if CURRENT_JOB["status"] == "running":
        raise HTTPException(status_code=409, detail="Hay otra búsqueda en curso actualmente.")

    CURRENT_JOB["logs"] = []
    query = payload.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Debe especificar una consulta para Google Places.")

    background_tasks.add_task(run_places_task, query)
    return {"status": "started", "message": f"Rastreo de Google Places para '{query}' iniciado."}

@app.get("/api/search/job-status")
def get_job_status():
    return CURRENT_JOB

@app.get("/api/export-csv")
def export_filtered_csv(
    q: Optional[str] = None,
    source: Optional[str] = "all",
    province: Optional[str] = None,
    sector: Optional[str] = None,
    time_range: Optional[str] = "all",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    min_capital: Optional[float] = 0,
    hot_only: Optional[bool] = False
):
    leads_res = get_leads(
        q=q,
        source=source,
        province=province,
        sector=sector,
        time_range=time_range,
        from_date=from_date,
        to_date=to_date,
        min_capital=min_capital,
        hot_only=hot_only
    )
    leads = leads_res["leads"]

    export_df = pd.DataFrame(leads)
    temp_export = DATA_DIR / "export_seleccion_darox.csv"
    export_df.to_csv(temp_export, index=False, sep=";", encoding="utf-8-sig")

    return FileResponse(
        path=temp_export,
        filename=f"darox_leads_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        media_type="text/csv"
    )

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_path = TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Error: templates/index.html no encontrado.</h1>", status_code=500)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

def build_static_dashboard() -> Path:
    """Compila una versión HTML autónoma con los datos actuales embebidos (cero dependencias para abrir directamente)."""
    index_path = TEMPLATES_DIR / "index.html"
    out_path = DATA_DIR / "dashboard.html"

    if not index_path.exists():
        print("[!] No se encontró templates/index.html")
        return out_path

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    stats = get_stats()
    leads = get_all_unified_leads()
    initial_data = {
        "stats": stats,
        "leads": leads
    }

    injected_script = f"""
  <script>
    // Datos precargados para uso local y offline sin necesidad de servidor
    window.INITIAL_DATA = {json.dumps(initial_data, ensure_ascii=False)};
  </script>
</head>"""

    html_standalone = html.replace("</head>", injected_script, 1)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_standalone)

    print(f"[OK] Dashboard estático offline generado en: {out_path.resolve()}")
    return out_path

def find_free_port(preferred: int = 8505) -> int:
    """Encuentra un puerto libre evitando conflictos con servicios como Oracle o proxies."""
    import socket
    for p in [preferred, 8506, 8507, 8888, 5050, 8123]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                return p
        except OSError:
            continue
    return preferred

def start_server(port: Optional[int] = None, open_browser: bool = True):
    # Seleccionar un puerto libre automáticamente (por defecto 8505 para evitar 8080 de Oracle)
    selected_port = port if port else find_free_port(8505)

    print("======================================================================")
    print("          DAROX LEAD ENGINE | DASHBOARD DE PROSPECCIÓN B2B            ")
    print("======================================================================")
    print(f" Servidor activo en: http://127.0.0.1:{selected_port}")
    print(" Diseñado para Sales Ops, Cualificación Temprana y Captación Directa")
    print("======================================================================")

    # Auto-generar archivo estático standalone
    build_static_dashboard()

    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{selected_port}")).start()

    uvicorn.run(app, host="127.0.0.1", port=selected_port, log_level="warning")

if __name__ == "__main__":
    start_server(port=None, open_browser=True)
