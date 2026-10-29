import time
from typing import List, Dict, Optional
from pathlib import Path
from config.settings import GOOGLE_PLACES_API_KEY, DB_PATH
from .database import PlacesDatabase

class GooglePlacesTracker:
    """
    Rastreador de locales comerciales y negocios en Google Maps.
    Detecta negocios en apertura o activos cuyo campo website esté vacío.
    """

    def __init__(self, api_key: Optional[str] = None, db_path: Optional[Path] = None):
        self.api_key = api_key or GOOGLE_PLACES_API_KEY
        self.db = PlacesDatabase(db_path or DB_PATH)
        self.client = None
        if self.api_key:
            try:
                import googlemaps
                self.client = googlemaps.Client(key=self.api_key)
            except Exception as e:
                print(f"[!] Error inicializando cliente de Google Maps: {e}")

    def is_api_configured(self) -> bool:
        return bool(self.api_key and self.client)

    def search_and_track_live(self, query: str, max_results: int = 20) -> List[Dict[str, any]]:
        """
        Consulta la API oficial de Google Places, almacena en SQLite y detecta
        nuevas aperturas o negocios sin web.
        """
        print(f"[*] Buscando en Google Places API: '{query}'...")
        flagged_leads = []

        try:
            # Búsqueda de texto de Google Places
            results = self.client.places(query=query)
            places_list = results.get("results", [])

            print(f"[+] Locales devueltos por Google: {len(places_list)}")

            for item in places_list[:max_results]:
                place_id = item.get("place_id")
                if not place_id:
                    continue

                # Consultar detalles completos para obtener 'website' y 'formatted_phone_number'
                # (estos campos suelen requerir Place Details)
                details = {}
                try:
                    time.sleep(0.2)  # Respetar rate limits
                    detail_res = self.client.place(
                        place_id=place_id,
                        fields=["place_id", "name", "formatted_address", "formatted_phone_number",
                                "website", "rating", "user_ratings_total", "types", "business_status"]
                    )
                    details = detail_res.get("result", {})
                except Exception as e:
                    # Si falla details, usamos los datos básicos
                    details = item

                is_new, alert_no_web = self.db.upsert_place(details, query_zone=query)

                if alert_no_web:
                    lead_info = {
                        "place_id": place_id,
                        "name": details.get("name"),
                        "address": details.get("formatted_address") or details.get("vicinity"),
                        "phone": details.get("formatted_phone_number", ""),
                        "rating": details.get("rating", 0.0),
                        "is_new_business": is_new,
                        "alert": "SIN PAGINA WEB DETECTADA",
                        "query_zone": query,
                        "opportunity": "Ofrecer creación de web y posicionamiento Google Business Profile"
                    }
                    flagged_leads.append(lead_info)
                    status_badge = "[NUEVO LOCAL]" if is_new else "[REGISTRADO PREVIAMENTE]"
                    print(f"    -> {status_badge} {lead_info['name']} (Tel: {lead_info['phone'] or 'N/D'}) - SIN WEB")

            print(f"[OK] Rastreo finalizado. Negocios sin web detectados: {len(flagged_leads)}")
            return flagged_leads

        except Exception as e:
            print(f"[!] Error ejecutando consulta en Google Places API: {e}")
            return []

    def simulate_demo_tracking(self, query: str = "negocios locales") -> List[Dict[str, any]]:
        """
        Modo de simulación inteligente para pruebas y expansión de búsqueda si el usuario
        aún no ha configurado su GOOGLE_PLACES_API_KEY en .env.
        Genera leads realistas adaptados al sector y ciudad consultada, persistiendo en SQLite.
        """
        import hashlib
        import random

        print(f"[*] [MODO DEMOSTRACIÓN AVANZADO] Rastreando Google Places para: '{query}'...")
        print("    (Para usar la API real oficial de Google, configura GOOGLE_PLACES_API_KEY en .env)")

        q_lower = query.lower()

        # Determinar ciudad
        cities = {
            "madrid": {"name": "Madrid", "prefix": "+34 91", "zip": "280", "streets": ["Calle de Alcalá", "Paseo de la Castellana", "Calle Serrano", "Calle Gran Vía", "Calle Fuencarral", "Paseo de Recoletos"]},
            "barcelona": {"name": "Barcelona", "prefix": "+34 93", "zip": "080", "streets": ["Passeig de Gràcia", "Avinguda Diagonal", "Carrer de Balmes", "Carrer d'Aragó", "Carrer de Verdi", "Rambla de Catalunya"]},
            "valencia": {"name": "Valencia", "prefix": "+34 96", "zip": "460", "streets": ["Calle Colón", "Gran Vía Marqués del Turia", "Carrer de Xàtiva", "Carrer de Russafa", "Carrer de la Pau", "Avenida de Francia"]},
            "sevilla": {"name": "Sevilla", "prefix": "+34 954", "zip": "410", "streets": ["Avenida de la Constitución", "Calle Sierpes", "Calle Asunción", "Calle Betis", "Paseo de las Delicias", "Calle Luis de Morales"]},
            "malaga": {"name": "Málaga", "prefix": "+34 952", "zip": "290", "streets": ["Calle Larios", "Alameda Principal", "Paseo Marítimo Ciudad de Melilla", "Calle Carretería", "Avenida de Andalucía"]},
            "alicante": {"name": "Alicante", "prefix": "+34 965", "zip": "030", "streets": ["Avenida Maisonnave", "Rambla de Méndez Núñez", "Calle Alfonso X El Sabio", "Paseo de la Explanada"]},
            "bilbao": {"name": "Bilbao", "prefix": "+34 944", "zip": "480", "streets": ["Gran Vía de Don Diego López de Haro", "Alameda de Mazarredo", "Calle Ercilla", "Calle Rodríguez Arias"]},
            "zaragoza": {"name": "Zaragoza", "prefix": "+34 976", "zip": "500", "streets": ["Paseo de la Independencia", "Calle Alfonso I", "Gran Vía", "Calle San Ignacio de Loyola"]}
        }

        detected_city = None
        for key, info in cities.items():
            if key in q_lower:
                detected_city = info
                break
        if not detected_city:
            detected_city = cities["madrid"]

        # Determinar sector
        sectors = [
            {
                "keywords": ["dental", "diente", "dentista", "odontolog"],
                "type": "dentist",
                "types_list": ["dentist", "health", "point_of_interest"],
                "names": ["Clínica Dental OdontoSalud", "Implantes & Estética Dental Pro", "Clínica Dental Sonrisas", "Gabinete Odontológico Vanguardia", "Dental Studio Avanzado"]
            },
            {
                "keywords": ["estetica", "belleza", "clinica", "salud", "dermatolog"],
                "type": "beauty_salon",
                "types_list": ["beauty_salon", "health", "spa"],
                "names": ["Clínica Médico Estética Alma", "Centro Dermocosmético Élite", "Lounge Estética & Bienestar", "Skin & Laser Medical Center", "Instituto de Belleza Integral"]
            },
            {
                "keywords": ["abogad", "legal", "bufet", "asesor", "fiscal", "juridic"],
                "type": "lawyer",
                "types_list": ["lawyer", "finance", "point_of_interest"],
                "names": ["Bufete Jurídico & Asociados Lex", "Asesoría Fiscal y Contable Meridian", "Despacho Legal Balboa & Co.", "LexConsulting Abogados y Economistas", "Vanguardia Legal & Compliance"]
            },
            {
                "keywords": ["arquitect", "diseño", "interiorism", "reforma", "construc"],
                "type": "general_contractor",
                "types_list": ["general_contractor", "point_of_interest", "establishment"],
                "names": ["Estudio de Arquitectura e Interiorismo Nexus", "Reformas & Proyectos Singulares", "Atelier Espacios & Obra Civil", "Urban Living Arquitectura", "Proyectos Integrales Hábitat"]
            },
            {
                "keywords": ["restaurante", "gastro", "comida", "cena", "bar", "cafe", "cocina"],
                "type": "restaurant",
                "types_list": ["restaurant", "food", "point_of_interest"],
                "names": ["Restaurante & Brasería Fuego Lento", "Bistró de Autor Raíces", "Restaurante El Rincón Gourmet", "Atelier Gastronómico & Vinos", "Trattoria Moderna La Pergola"]
            },
            {
                "keywords": ["inmobiliaria", "real estate", "propiedad", "vivienda"],
                "type": "real_estate_agency",
                "types_list": ["real_estate_agency", "point_of_interest"],
                "names": ["Inmobiliaria Capital Properties", "Gestión de Activos Inmobiliarios Prime", "InverCasas Real Estate", "Boutique Residencial Exclusiva", "Habitalia Consultores Inmobiliarios"]
            },
            {
                "keywords": ["gimnasio", "fitness", "pilates", "yoga", "crossfit", "entren"],
                "type": "gym",
                "types_list": ["gym", "health", "sports_complex"],
                "names": ["Boutique Fitness Club Pulse", "Estudio de Pilates & Yoga Equilibrium", "Centro de Entrenamiento Personal Apex", "Core & Movement Studio", "Urban Health Club"]
            }
        ]

        matched_sector = None
        for sec in sectors:
            if any(kw in q_lower for kw in sec["keywords"]):
                matched_sector = sec
                break
        if not matched_sector:
            matched_sector = sectors[4]  # Default restaurante / gastro

        demo_places = []
        city_info = detected_city
        for i, name_template in enumerate(matched_sector["names"]):
            full_name = f"{name_template} {city_info['name']}"
            street = city_info["streets"][i % len(city_info["streets"])]
            num = 12 + (i * 17)
            postal_code = f"{city_info['zip']}{10 + (i * 3):02d}"
            address = f"{street} {num}, {postal_code} {city_info['name']}"
            phone = f"{city_info['prefix']}{random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)}"
            
            # En modo demo, 4 de cada 5 no tienen web (exactamente los prospectos ideales para DAROX)
            has_web = (i == 1)
            website = f"https://www.{matched_sector['type']}{city_info['name'].lower()}{i}.com" if has_web else ""
            
            rating = round(random.uniform(4.2, 4.9), 1)
            ratings_count = random.randint(5, 75)
            unique_hash = hashlib.md5(f"{full_name}_{address}".encode('utf-8')).hexdigest()[:12]
            place_id = f"ChIJ_demo_{unique_hash}"

            demo_places.append({
                "place_id": place_id,
                "name": full_name,
                "formatted_address": address,
                "formatted_phone_number": phone,
                "website": website,
                "rating": rating,
                "user_ratings_total": ratings_count,
                "types": matched_sector["types_list"],
                "business_status": "OPERATIONAL"
            })

        flagged_leads = []
        for p in demo_places:
            is_new, alert_no_web = self.db.upsert_place(p, query_zone=query)
            if alert_no_web:
                lead_info = {
                    "place_id": p["place_id"],
                    "name": p["name"],
                    "address": p["formatted_address"],
                    "phone": p["formatted_phone_number"],
                    "rating": p["rating"],
                    "is_new_business": is_new,
                    "alert": "SIN PAGINA WEB DETECTADA",
                    "query_zone": query,
                    "opportunity": "Ofrecer creación de web corporativa, Google Business Profile y Branding"
                }
                flagged_leads.append(lead_info)
                status_badge = "[NUEVO LOCAL]" if is_new else "[REGISTRADO PREVIAMENTE]"
                print(f"    -> {status_badge} {lead_info['name']} ({lead_info['phone']}) - SIN WEB")

        print(f"[OK] Rastreo finalizado. Negocios sin web procesados en SQLite: {len(flagged_leads)}")
        return flagged_leads

    def track(self, query: str = "restaurantes en Madrid", force_mock: bool = False) -> List[Dict[str, any]]:
        """Punto de entrada principal: ejecuta modo API real o demo según configuración."""
        if self.is_api_configured() and not force_mock:
            return self.search_and_track_live(query)
        else:
            return self.simulate_demo_tracking(query)

