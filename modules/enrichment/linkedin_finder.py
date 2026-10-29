import time
import re
from typing import Dict, List, Optional
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

class LinkedInFinder:
    """
    Localizador OSINT de perfiles de LinkedIn para fundadores y administradores
    mediante búsquedas específicas sin autenticación directa en LinkedIn.
    """

    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds

    @staticmethod
    def normalize_borme_name(raw_name: str) -> str:
        """
        Convierte nombres del BORME (usualmente en formato APELLIDO1 APELLIDO2 NOMBRE)
        a formato natural: NOMBRE APELLIDO1 APELLIDO2.
        Ejemplo: 'DIEZ REQUENA DANIEL' -> 'Daniel Diez Requena'
        """
        parts = [p.capitalize() for p in raw_name.strip().split() if p]
        if len(parts) >= 3:
            # En España el BORME casi siempre coloca los 2 apellidos primero y el nombre al final
            first_name = parts[-1]
            last_names = " ".join(parts[:-1])
            return f"{first_name} {last_names}"
        elif len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
        return " ".join(parts)

    def search_profile(self, person_name: str, company_name: Optional[str] = None, province: Optional[str] = None) -> Dict[str, str]:
        """
        Busca el perfil de LinkedIn de la persona.
        """
        if not person_name:
            return {"linkedin_url": "", "linkedin_title": "", "status": "Sin nombre"}

        natural_name = self.normalize_borme_name(person_name)

        # Construir consulta OSINT
        # Intentamos primero con nombre natural y país España
        query = f'site:linkedin.com/in/ "{natural_name}" España'

        try:
            time.sleep(self.delay_seconds)
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=2))

                # Si no hubo resultados con nombre normalizado, intentamos con el nombre tal cual
                if not results and person_name != natural_name:
                    alt_query = f'site:linkedin.com/in/ "{person_name}"'
                    results = list(ddgs.text(alt_query, max_results=1))

                if results:
                    best = results[0]
                    url = best.get("href", "")
                    title = best.get("title", "")
                    # Asegurar que es un enlace de perfil individual
                    if "linkedin.com/in/" in url:
                        return {
                            "linkedin_url": url,
                            "linkedin_title": title,
                            "status": "Encontrado"
                        }

            return {"linkedin_url": "", "linkedin_title": "", "status": "No encontrado"}

        except Exception as e:
            # Fallback silencioso para no romper el pipeline masivo
            return {
                "linkedin_url": "",
                "linkedin_title": "",
                "status": f"Error/RateLimit: {str(e)[:30]}"
            }

