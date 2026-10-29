import re
import unicodedata
import dns.resolver
from typing import Dict, Tuple

class DomainChecker:
    """
    Verifica la disponibilidad de dominios .es y .com para empresas recién constituidas.
    """

    LEGAL_SUFFIXES = [
        r'\bSOCIEDAD\s+LIMITADA\s+UNIPERSONAL\b',
        r'\bSOCIEDAD\s+LIMITADA\s+LABORAL\b',
        r'\bSOCIEDAD\s+LIMITADA\b',
        r'\bSOCIEDAD\s+ANONIMA\s+UNIPERSONAL\b',
        r'\bSOCIEDAD\s+ANONIMA\b',
        r'\bSOCIEDAD\s+COOPERATIVA\b',
        r'\bSOCIEDAD\s+PROFESIONAL\b',
        r'\bS\.?L\.?U\.?\b',
        r'\bS\.?L\.?L\.?\b',
        r'\bS\.?L\.?\b',
        r'\bS\.?A\.?U\.?\b',
        r'\bS\.?A\.?\b',
        r'\bS\.?C\.?P\.?\b',
        r'\bC\.?B\.?\b',
    ]

    def __init__(self, timeout: float = 0.8):
        self.resolver = dns.resolver.Resolver()
        self.resolver.nameservers = ['8.8.8.8', '1.1.1.1', '9.9.9.9']
        self.resolver.lifetime = timeout
        self.resolver.timeout = timeout

    @classmethod
    def clean_company_name_to_slug(cls, company_name: str) -> str:
        """
        Transforma el nombre de la empresa en un slug limpio apto para dominio.
        Ejemplo: 'D10 CAPITAL HOLDING EMPRESARIAL SOCIEDAD LIMITADA' -> 'd10capitalholdingempresarial'
        """
        text = company_name.upper()

        # Eliminar formas jurídicas
        for suffix in cls.LEGAL_SUFFIXES:
            text = re.sub(suffix, '', text, flags=re.IGNORECASE)

        # Quitar acentos y diacríticos
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')

        # Dejar solo caracteres alfanuméricos
        slug = re.sub(r'[^a-zA-Z0-9]', '', text).lower()

        # Si el slug es demasiado largo (> 30 caracteres), podemos intentar truncar o usar la primera parte
        if len(slug) > 35:
            # Intentar tomar las primeras palabras clave
            words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', ' ', text).split() if len(w) > 1]
            if len(words) >= 2:
                short_slug = "".join(words[:3]).lower()
                if len(short_slug) >= 4:
                    return short_slug

        return slug or "empresa"

    def is_domain_registered(self, domain: str) -> bool:
        """
        Consulta DNS (A, NS, SOA) para determinar si el dominio está registrado y activo.
        Devuelve True si existe registro DNS, False si está libre o no configurado.
        """
        for record_type in ['A', 'NS', 'SOA']:
            try:
                answers = self.resolver.resolve(domain, record_type)
                if answers:
                    return True
            except dns.resolver.NXDOMAIN:
                # Si el dominio da NXDOMAIN, no existe absolutamente en el TLD
                return False
            except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
                continue
            except (dns.resolver.LifetimeTimeout, dns.resolver.Timeout):
                return False
            except Exception:
                pass
        return False

    def check_domains(self, company_name: str) -> Dict[str, any]:
        """
        Verifica la disponibilidad de .es y .com para la empresa.
        """
        slug = self.clean_company_name_to_slug(company_name)
        domain_es = f"{slug}.es"
        domain_com = f"{slug}.com"

        reg_es = self.is_domain_registered(domain_es)
        reg_com = self.is_domain_registered(domain_com)

        return {
            "dominio_sugerido": slug,
            "dominio_es": domain_es,
            "dominio_es_registrado": reg_es,
            "dominio_es_disponible": not reg_es,
            "dominio_com": domain_com,
            "dominio_com_registrado": reg_com,
            "dominio_com_disponible": not reg_com,
            "sin_web_detectada": (not reg_es and not reg_com),
        }

