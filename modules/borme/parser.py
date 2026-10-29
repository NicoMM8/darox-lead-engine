import re
import io
from typing import List, Optional
import pdfplumber
from .models import LeadBORME

class BORMEParser:
    """
    Parser especializado en extraer actos de constitución de sociedades
    del Boletín Oficial del Registro Mercantil (BORME).
    """

    @staticmethod
    def clean_text(text: str) -> str:
        """Limpia saltos de línea irregulares y espacios duplicados."""
        if not text:
            return ""
        # Normalizar espacios y saltos de línea
        text = re.sub(r'[\r\n]+', ' ', text)
        text = re.sub(r'\s{2,}', ' ', text)
        return text.strip()

    @staticmethod
    def extract_administradores(act_text: str) -> List[str]:
        """
        Extrae los nombres de los administradores y apoderados clave nombrados.
        """
        admins = []

        # Patrones comunes de cargos en BORME
        patterns = [
            r'Adm\.\s*(?:[Uu]nico|[UÚ]NICO):\s*([^.\n]+)',
            r'Adm\.\s*(?:Solidario|SOLIDARIO):\s*([^.\n]+)',
            r'Adm\.\s*(?:Mancomunado|Mancom\.?|MANCOMUNADO):\s*([^.\n]+)',
            r'Consejero:\s*([^.\n]+)',
            r'Presidente:\s*([^.\n]+)',
            r'Consejero Delegado:\s*([^.\n]+)',
            r'Liquidador:\s*([^.\n]+)',
        ]

        for pat in patterns:
            matches = re.findall(pat, act_text, re.IGNORECASE)
            for m in matches:
                name = m.strip().strip(",.-")
                # Si vienen varios separados por comas o punto y coma
                parts = [p.strip().strip(",.-") for p in re.split(r'[,;]', name) if p.strip()]
                for p in parts:
                    if len(p) > 3 and p not in admins:
                        admins.append(p)

        # Si no encontramos ningún patrón específico pero hay bloque 'Nombramientos'
        if not admins:
            nomb_match = re.search(r'Nombramientos\.\s*([^.]+?)(?=\.\s*(?:Datos registrales|Otros conceptos|$))', act_text, re.IGNORECASE)
            if nomb_match:
                raw_nomb = nomb_match.group(1).strip()
                # Extraer texto tras dos puntos
                after_colon = re.findall(r':\s*([^,;]+)', raw_nomb)
                for item in after_colon:
                    cleaned = item.strip().strip(",.-")
                    if len(cleaned) > 3 and cleaned not in admins:
                        admins.append(cleaned)

        return admins

    @classmethod
    def parse_pdf(cls, pdf_source, province: str, borme_date: str) -> List[LeadBORME]:
        """
        Lee el PDF del BORME (bytes o ruta) y extrae todas las nuevas constituciones.
        """
        leads: List[LeadBORME] = []

        if isinstance(pdf_source, (bytes, bytearray)):
            pdf_file = io.BytesIO(pdf_source)
        else:
            pdf_file = pdf_source

        full_text = ""
        try:
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
        except Exception as e:
            print(f"[!] Error leyendo PDF ({province}): {e}")
            return leads

        if not full_text:
            return leads

        # Dividir por actos inscritos: suelen comenzar por el número de acto (5-7 dígitos seguido de guion)
        # Ejemplo: 480986 - GRUPO MATINEE MONHER SL.
        act_blocks = re.split(r'\n(?=\d{5,7}\s*-\s*)', full_text)

        for block in act_blocks:
            cleaned_block = cls.clean_text(block)

            # Nos interesan únicamente las CONSTITUCIONES de empresas nuevas
            if not re.search(r'Constituci[oó]n\.', cleaned_block, re.IGNORECASE):
                continue

            # Extraer número de acto y nombre de la empresa
            header_match = re.match(r'^(\d{5,7})\s*-\s*([^.]+?)(?:\.|$)', cleaned_block)
            if not header_match:
                continue

            act_number = header_match.group(1).strip()
            company_name = header_match.group(2).strip().strip(".-")

            # Extraer Domicilio Social
            domicilio = ""
            dom_match = re.search(r'Domicilio:\s*(.*?)(?=\.\s*(?:Capital|Declaraci[oó]n|Nombramientos|Datos registrales|Comienzo|Objeto social)|$)', cleaned_block, re.IGNORECASE)
            if dom_match:
                domicilio = cls.clean_text(dom_match.group(1))

            # Extraer Capital Social
            capital = ""
            cap_match = re.search(r'Capital:\s*([\d\.,]+\s*Euros)', cleaned_block, re.IGNORECASE)
            if cap_match:
                capital = cap_match.group(1).strip()

            # Extraer Objeto Social (vital para que DAROX entienda a qué se dedica)
            objeto_social = ""
            obj_match = re.search(r'Objeto social:\s*(.*?)(?=\.\s*(?:Domicilio|Capital|Declaraci[oó]n|Nombramientos|Datos registrales)|$)', cleaned_block, re.IGNORECASE)
            if obj_match:
                objeto_social = cls.clean_text(obj_match.group(1))

            # Extraer Socio Único (si unipersonal)
            socio_unico = ""
            socio_match = re.search(r'Socio\s*[uú]nico:\s*([^.\n]+)', cleaned_block, re.IGNORECASE)
            if socio_match:
                socio_unico = socio_match.group(1).strip().strip(",.-")

            # Extraer Administradores
            administradores = cls.extract_administradores(cleaned_block)
            if socio_unico and socio_unico not in administradores:
                administradores.append(socio_unico)

            lead = LeadBORME(
                company_name=company_name,
                province=province.upper(),
                borme_date=borme_date,
                act_number=act_number,
                domicilio_social=domicilio,
                capital=capital,
                objeto_social=objeto_social,
                administradores=administradores,
                socio_unico=socio_unico,
                raw_text=cleaned_block[:600]
            )
            leads.append(lead)

        return leads

