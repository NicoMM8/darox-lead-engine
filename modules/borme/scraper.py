import datetime
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
from urllib.parse import urljoin

from config.settings import DEFAULT_HEADERS
from .models import LeadBORME
from .parser import BORMEParser

class BORMEScraper:
    """
    Scraper oficial del Boletín Oficial del Registro Mercantil (BORME).
    Descarga los sumarios provinciales y extrae las sociedades recién constituidas.
    """

    BASE_URL = "https://www.boe.es"

    def __init__(self, target_provinces: Optional[List[str]] = None, timeout: int = 15):
        self.target_provinces = [p.upper() for p in (target_provinces or [])]
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _get_day_url(self, date: datetime.date) -> str:
        return f"{self.BASE_URL}/borme/dias/{date.strftime('%Y/%m/%d')}/"

    def find_latest_available_borme(self, start_date: Optional[datetime.date] = None, max_days_back: int = 7):
        """
        Busca la edición más reciente del BORME hacia atrás en caso de fines de semana o festivos.
        """
        current_date = start_date or datetime.date.today()
        for i in range(max_days_back):
            check_date = current_date - datetime.timedelta(days=i)
            url = self._get_day_url(check_date)
            try:
                res = self.session.get(url, timeout=self.timeout)
                if res.status_code == 200 and "SECCIÓN PRIMERA" in res.text:
                    return check_date, res.text
            except requests.RequestException:
                pass
        return None, None

    def get_provinces_pdf_links(self, html_content: str, date_str: str) -> dict:
        """
        Analiza el sumario HTML del día y extrae {nombre_provincia: url_pdf}
        para la Sección Primera (Actos inscritos).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        province_links = {}

        # Buscamos elementos li con clase 'dispo'
        for dispo in soup.find_all("li", class_="dispo"):
            p_tag = dispo.find("p")
            if not p_tag:
                continue

            province_raw = p_tag.get_text(strip=True)
            # Buscar enlace al PDF
            a_pdf = dispo.find("a", href=lambda h: h and h.endswith(".pdf") and "BORME-A-" in h)
            if not a_pdf:
                continue

            pdf_url = urljoin(self.BASE_URL, a_pdf["href"])

            # Comprobar filtro de provincias (si está configurado)
            if self.target_provinces:
                matched = any(
                    target in province_raw.upper() or province_raw.upper() in target
                    for target in self.target_provinces
                )
                if not matched:
                    continue

            province_links[province_raw] = pdf_url

        return province_links

    def run(self, specific_date: Optional[datetime.date] = None, max_companies: Optional[int] = None) -> List[LeadBORME]:
        """
        Ejecuta el pipeline completo de extracción del BORME.
        """
        print("[*] Iniciando Scraper del BORME...")

        target_date = specific_date or datetime.date.today()
        resolved_date, html_content = self.find_latest_available_borme(target_date)

        if not resolved_date or not html_content:
            print("[!] No se encontró ninguna edición del BORME en los últimos 7 días.")
            return []

        date_str = resolved_date.strftime("%Y-%m-%d")
        print(f"[+] Edición seleccionada del BORME: {date_str} (URL: {self._get_day_url(resolved_date)})")

        province_links = self.get_provinces_pdf_links(html_content, date_str)
        print(f"[+] Provincias a procesar: {len(province_links)}")

        all_leads: List[LeadBORME] = []

        for province, pdf_url in province_links.items():
            print(f"    -> Descargando y procesando BORME de {province}...")
            try:
                res = self.session.get(pdf_url, timeout=self.timeout)
                if res.status_code != 200:
                    print(f"       [!] Error descargando PDF ({res.status_code})")
                    continue

                leads = BORMEParser.parse_pdf(res.content, province, date_str)
                print(f"       [OK] {len(leads)} nuevas sociedades constituidas detectadas.")
                all_leads.extend(leads)

                if max_companies and len(all_leads) >= max_companies:
                    all_leads = all_leads[:max_companies]
                    break

            except Exception as e:
                print(f"       [!] Error procesando {province}: {e}")

        print(f"[OK] Extraccion BORME completada. Total sociedades constituidas: {len(all_leads)}")
        return all_leads
