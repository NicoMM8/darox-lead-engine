import time
from typing import List, Dict
from modules.borme.models import LeadBORME
from .domain_checker import DomainChecker
from .linkedin_finder import LinkedInFinder

class LeadEnricher:
    """
    Orquesta el enriquecimiento OSINT para cada lead del BORME:
    - Verificación de dominios (.es, .com)
    - Localización del perfil de LinkedIn del fundador/administrador
    - Cualificación y scoring para el equipo de ventas de DAROX
    """

    def __init__(self, check_linkedin: bool = True, linkedin_delay: float = 0.8):
        self.domain_checker = DomainChecker()
        self.check_linkedin = check_linkedin
        self.linkedin_finder = LinkedInFinder(delay_seconds=linkedin_delay) if check_linkedin else None

    def calculate_sales_ops_qualification(self, lead: LeadBORME, domain_info: dict, linkedin_info: dict) -> Dict[str, any]:
        """
        Calcula un score de oportunidad de venta de diseño y branding para DAROX.
        """
        score = 50
        motivos = []

        # Disponibilidad de dominios
        if domain_info.get("sin_web_detectada"):
            score += 35
            motivos.append("Dominios .es y .com libres (No tienen web)")
        elif domain_info.get("dominio_es_disponible"):
            score += 20
            motivos.append("Dominio .es libre")
        elif domain_info.get("dominio_com_disponible"):
            score += 20
            motivos.append("Dominio .com libre")
        else:
            motivos.append("Dominios ya registrados")

        # Localización de administrador
        if linkedin_info.get("linkedin_url"):
            score += 25
            motivos.append("Contacto directo en LinkedIn disponible")

        # Capital social
        if lead.capital:
            try:
                # Extraer valor numérico del capital
                cleaned_num = lead.capital.replace("Euros", "").replace(".", "").replace(",", ".").strip()
                val = float(cleaned_num)
                if val > 5000:
                    score += 10
                    motivos.append(f"Capital solvente ({lead.capital})")
            except Exception:
                pass

        # Clasificación final
        if score >= 80:
            categoria = "ALTA PRIORIDAD (HOT LEAD)"
            accion = "Contactar hoy mismo por LinkedIn ofreciendo pack Web + Branding de lanzamiento."
        elif score >= 60:
            categoria = "MEDIA PRIORIDAD (WARM LEAD)"
            accion = "Enviar propuesta por carta/email o conectar con administrador."
        else:
            categoria = "PROSPECTO GENERAL"
            accion = "Seguimiento estándar."

        return {
            "lead_score": score,
            "categoria_lead": categoria,
            "motivos_cualificacion": " | ".join(motivos),
            "accion_sugerida": accion
        }

    def enrich_single(self, lead: LeadBORME) -> Dict[str, any]:
        """Enriquece un único lead del BORME."""
        base_dict = lead.to_dict()

        # 1. Comprobación de dominios
        domain_data = self.domain_checker.check_domains(lead.company_name)
        base_dict.update(domain_data)

        # 2. Búsqueda de LinkedIn del administrador principal
        admin_target = ""
        if lead.administradores:
            admin_target = lead.administradores[0]
        elif lead.socio_unico:
            admin_target = lead.socio_unico

        linkedin_data = {
            "linkedin_contacto_nombre": LinkedInFinder.normalize_borme_name(admin_target) if admin_target else "",
            "linkedin_url": "",
            "linkedin_title": "",
            "linkedin_status": "Omitido"
        }

        if self.check_linkedin and self.linkedin_finder and admin_target:
            res = self.linkedin_finder.search_profile(admin_target, lead.company_name, lead.province)
            linkedin_data["linkedin_url"] = res.get("linkedin_url", "")
            linkedin_data["linkedin_title"] = res.get("linkedin_title", "")
            linkedin_data["linkedin_status"] = res.get("status", "")

        base_dict.update(linkedin_data)

        # 3. Cualificación Sales Ops
        qual_data = self.calculate_sales_ops_qualification(lead, domain_data, linkedin_data)
        base_dict.update(qual_data)

        return base_dict

    def enrich_leads(self, leads: List[LeadBORME]) -> List[Dict[str, any]]:
        """
        Enriquece una lista de leads del BORME con barra de progreso en consola.
        """
        print(f"[*] Iniciando enriquecimiento OSINT para {len(leads)} sociedades...")
        enriched_list = []

        for i, lead in enumerate(leads, 1):
            print(f"    [{i}/{len(leads)}] Analizando dominios y perfiles para: {lead.company_name[:40]}...")
            enriched = self.enrich_single(lead)

            # Resumen visual en consola
            status_web = "SIN WEB (Dominios libres)" if enriched.get("sin_web_detectada") else "Dominios ocupados"
            status_li = "LinkedIn OK" if enriched.get("linkedin_url") else "Sin LinkedIn"
            print(f"          -> {status_web} | {status_li} | Score: {enriched.get('lead_score')}")

            enriched_list.append(enriched)

        print(f"[OK] Enriquecimiento completado para {len(enriched_list)} empresas.")
        return enriched_list

