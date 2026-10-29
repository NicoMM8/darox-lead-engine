from pathlib import Path
from typing import List, Dict
import pandas as pd

class CSVExporter:
    """
    Exportador de leads a CSV optimizado para Microsoft Excel y CRMs (HubSpot, Notion, etc.).
    Utiliza utf-8-sig para preservar acentos y caracteres españoles (ñ, á, é, etc.).
    """

    @staticmethod
    def export_borme_leads(leads: List[Dict[str, any]], output_path: Path) -> Path:
        """Exporta leads del BORME enriquecidos."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not leads:
            print("[!] No hay leads del BORME para exportar.")
            return output_path

        df = pd.DataFrame(leads)

        # Si el CSV ya existe, fusionar y deduplicar para preservar el historial acumulado
        if output_path.exists():
            try:
                existing_df = pd.read_csv(output_path, sep=";")
                combined = pd.concat([existing_df, df], ignore_index=True)
                if "company_name" in combined.columns:
                    combined = combined.drop_duplicates(subset=["company_name"], keep="last")
                df = combined
            except Exception as e:
                print(f"[!] Aviso al fusionar histórico de BORME: {e}")

        # Definir orden preferente de columnas para Sales Ops
        priority_cols = [
            "categoria_lead",
            "lead_score",
            "company_name",
            "province",
            "borme_date",
            "administradores_str",
            "linkedin_contacto_nombre",
            "linkedin_url",
            "linkedin_title",
            "sin_web_detectada",
            "dominio_sugerido",
            "dominio_es",
            "dominio_es_disponible",
            "dominio_com",
            "dominio_com_disponible",
            "domicilio_social",
            "capital",
            "objeto_social",
            "accion_sugerida",
            "motivos_cualificacion",
            "act_number"
        ]

        # Mantener solo las columnas que existan en el dataframe
        cols_to_use = [c for c in priority_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in priority_cols and c != "raw_text"]
        final_cols = cols_to_use + other_cols

        df = df[final_cols]

        # Ordenar por mayor score de oportunidad
        if "lead_score" in df.columns:
            df = df.sort_values(by="lead_score", ascending=False)

        # Exportar con BOM utf-8 para compatibilidad nativa con Excel en España
        df.to_csv(output_path, index=False, encoding="utf-8-sig", sep=";")

        print(f"[OK] Archivo CSV exportado con exito: {output_path}")
        print(f"     -> Total registros: {len(df)}")
        if "categoria_lead" in df.columns:
            hot_count = len(df[df["categoria_lead"].str.contains("HOT", na=False)])
            print(f"     -> Leads de ALTA PRIORIDAD (HOT): {hot_count}")

        return output_path

    @staticmethod
    def export_places_leads(leads: List[Dict[str, any]], output_path: Path) -> Path:
        """Exporta leads de Google Places sin página web."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not leads:
            print("[!] No hay leads de Google Places para exportar.")
            return output_path

        df = pd.DataFrame(leads)

        # Reordenar columnas prioritarias
        order = ["alert", "is_new_business", "name", "phone", "address", "rating", "query_zone", "opportunity", "place_id"]
        cols = [c for c in order if c in df.columns] + [c for c in df.columns if c not in order]
        df = df[cols]

        df.to_csv(output_path, index=False, encoding="utf-8-sig", sep=";")

        print(f"[OK] Archivo CSV de Google Places exportado: {output_path}")
        print(f"     -> Total negocios sin web: {len(df)}")
        return output_path

