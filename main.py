import sys
import argparse
import datetime
from pathlib import Path

# Configurar salida estándar para evitar errores de codificación en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config.settings import (
    BORME_PROVINCES,
    CSV_BORME_OUTPUT,
    CSV_PLACES_OUTPUT,
    DB_PATH
)
from modules.borme.scraper import BORMEScraper
from modules.enrichment.enricher import LeadEnricher
from modules.places.tracker import GooglePlacesTracker
from modules.export.csv_exporter import CSVExporter

BANNER = """
======================================================================
       DAROX LEAD ENGINE | Automatización Sales Ops B2B
======================================================================
 Captación temprana de empresas en España (BORME + OSINT + Maps)
 Agencia de Diseño Web, Branding y Posicionamiento
======================================================================
"""

def parse_args():
    parser = argparse.ArgumentParser(description="DAROX Sales Ops Lead Automation")
    parser.add_argument("--all", action="store_true", help="Ejecutar todo el pipeline (BORME + Enriquecimiento + Places)")
    parser.add_argument("--borme", action="store_true", help="Ejecutar únicamente el Scraper del BORME")
    parser.add_argument("--enrich", action="store_true", help="Ejecutar enriquecimiento OSINT (Dominios y LinkedIn)")
    parser.add_argument("--places", action="store_true", help="Ejecutar rastreador de Google Places")
    parser.add_argument("--date", type=str, default="", help="Fecha específica para el BORME (formato: YYYY-MM-DD)")
    parser.add_argument("--provinces", type=str, default="", help="Provincias separadas por coma (ej: MADRID,BARCELONA)")
    parser.add_argument("--max-borme", type=int, default=0, help="Límite máximo de empresas a procesar del BORME")
    parser.add_argument("--query", type=str, default="restaurantes y clínicas en Madrid", help="Consulta para Google Places")
    parser.add_argument("--no-linkedin", action="store_true", help="Omitir búsqueda de LinkedIn (para ejecución ultrarrápida)")
    parser.add_argument("--mock-places", action="store_true", help="Forzar modo demostración en Google Places")
    parser.add_argument("--dashboard", action="store_true", help="Iniciar el Dashboard visual interactivo de DAROX")
    parser.add_argument("--port", type=int, default=8505, help="Puerto del dashboard (por defecto 8505)")
    return parser.parse_args()

def run_pipeline():
    print(BANNER)
    args = parse_args()

    # Si se solicita abrir el Dashboard, iniciamos la interfaz visual
    if args.dashboard:
        from dashboard import start_server
        start_server(port=args.port, open_browser=True)
        return

    # Si no se especifica ninguna bandera modular, ejecutamos todo
    run_all = args.all or (not args.borme and not args.enrich and not args.places)
    run_borme = run_all or args.borme or args.enrich
    run_enrich = run_all or args.enrich
    run_places = run_all or args.places

    # 1. Configurar provincias
    provinces = []
    if args.provinces:
        provinces = [p.strip().upper() for p in args.provinces.split(",") if p.strip()]
    elif BORME_PROVINCES:
        provinces = BORME_PROVINCES

    # 2. Configurar fecha
    target_date = None
    if args.date:
        try:
            target_date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"[!] Formato de fecha inválido: {args.date}. Use YYYY-MM-DD.")
            return

    # --- MÓDULO 1: BORME ---
    borme_leads = []
    if run_borme:
        print("\n>>> FASE 1: Scraper del BORME (Nuevas Sociedades Constituidas)")
        scraper = BORMEScraper(target_provinces=provinces)
        max_c = args.max_borme if args.max_borme > 0 else None
        borme_leads = scraper.run(specific_date=target_date, max_companies=max_c)

    # --- MÓDULO 2: ENRIQUECIMIENTO OSINT ---
    enriched_leads = []
    if run_enrich and borme_leads:
        print("\n>>> FASE 2: Enriquecimiento OSINT (Verificación de Dominios y LinkedIn)")
        enricher = LeadEnricher(check_linkedin=(not args.no_linkedin))
        enriched_leads = enricher.enrich_leads(borme_leads)

        # Exportar CSV de BORME enriquecido
        print("\n>>> Guardando Leads de BORME en CSV...")
        CSVExporter.export_borme_leads(enriched_leads, CSV_BORME_OUTPUT)
    elif run_borme and not run_enrich and borme_leads:
        # Exportar BORME sin enriquecer
        raw_dicts = [l.to_dict() for l in borme_leads]
        CSVExporter.export_borme_leads(raw_dicts, CSV_BORME_OUTPUT)

    # --- MÓDULO 3: GOOGLE PLACES ---
    places_leads = []
    if run_places:
        print("\n>>> FASE 3: Google Places Tracker (Detección de Locales Sin Web)")
        tracker = GooglePlacesTracker()
        places_leads = tracker.track(query=args.query, force_mock=args.mock_places)

        # Exportar CSV de Places acumulado en base de datos
        if places_leads:
            print("\n>>> Guardando Leads de Google Places en CSV...")
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
            CSVExporter.export_places_leads(export_list if export_list else places_leads, CSV_PLACES_OUTPUT)

    # --- RESUMEN FINAL SALES OPS ---
    print("\n======================================================================")
    print("                        RESUMEN DE EJECUCIÓN")
    print("======================================================================")
    if enriched_leads:
        hot_leads = [l for l in enriched_leads if "HOT" in l.get("categoria_lead", "")]
        print(f" [+] Leads BORME detectados : {len(enriched_leads)}")
        print(f" [+] HOT LEADS (Sin Web)    : {len(hot_leads)}")
        print(f" [+] CSV BORME generado     : {CSV_BORME_OUTPUT.resolve()}")

    if places_leads:
        print(f" [+] Negocios Places sin web: {len(places_leads)}")
        print(f" [+] CSV Places generado    : {CSV_PLACES_OUTPUT.resolve()}")
        print(f" [+] Base de datos SQLite   : {DB_PATH.resolve()}")

    print("\n[OK] Pipeline finalizado con éxito. Listo para importación en CRM o prospección.")
    print("======================================================================\n")

if __name__ == "__main__":
    run_pipeline()

