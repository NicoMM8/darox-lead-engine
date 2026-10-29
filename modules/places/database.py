import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

class PlacesDatabase:
    """
    Gestor de base de datos local SQLite para registrar y rastrear negocios
    encontrados en Google Maps / Places y detectar aperturas recientes o negocios sin web.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Inicializa las tablas e índices de la base de datos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS places (
                    place_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    address TEXT,
                    phone TEXT,
                    website TEXT,
                    has_website INTEGER DEFAULT 0,
                    rating REAL,
                    user_ratings_total INTEGER,
                    types TEXT,
                    query_zone TEXT,
                    business_status TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    times_seen INTEGER DEFAULT 1,
                    alert_no_website INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_places_has_website ON places(has_website)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_places_first_seen ON places(first_seen)")
            conn.commit()

    def upsert_place(self, place_data: dict, query_zone: str = "") -> Tuple[bool, bool]:
        """
        Inserta o actualiza un negocio.
        Devuelve (is_new: bool, is_alert_no_website: bool).
        """
        now_iso = datetime.datetime.now().isoformat()
        place_id = place_data.get("place_id")
        if not place_id:
            return False, False

        name = place_data.get("name", "").strip()
        address = place_data.get("formatted_address") or place_data.get("vicinity", "")
        phone = place_data.get("formatted_phone_number", "")
        website = (place_data.get("website") or "").strip()
        has_website = 1 if website else 0
        rating = place_data.get("rating", 0.0)
        ratings_total = place_data.get("user_ratings_total", 0)
        types_str = ",".join(place_data.get("types", []))
        business_status = place_data.get("business_status", "OPERATIONAL")
        alert_no_website = 1 if not has_website else 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT place_id, times_seen, website FROM places WHERE place_id = ?", (place_id,))
            row = cursor.fetchone()

            if row:
                # Ya existía en la base de datos (seguimiento)
                is_new = False
                times_seen = row["times_seen"] + 1
                final_website = website if website else (row["website"] or "")
                has_web_val = 1 if final_website else 0
                alert_val = 1 if not final_website else 0

                cursor.execute("""
                    UPDATE places
                    SET last_seen = ?,
                        times_seen = ?,
                        website = ?,
                        has_website = ?,
                        alert_no_website = ?
                    WHERE place_id = ?
                """, (now_iso, times_seen, final_website, has_web_val, alert_val, place_id))
            else:
                # Es un NUEVO negocio detectado
                is_new = True
                cursor.execute("""
                    INSERT INTO places (
                        place_id, name, address, phone, website, has_website,
                        rating, user_ratings_total, types, query_zone, business_status,
                        first_seen, last_seen, times_seen, alert_no_website
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    place_id, name, address, phone, website, has_website,
                    rating, ratings_total, types_str, query_zone, business_status,
                    now_iso, now_iso, alert_no_website
                ))

            conn.commit()

        return is_new, bool(alert_no_website)

    def get_leads_without_website(self, only_new: bool = False) -> List[Dict[str, any]]:
        """Obtiene negocios registrados que no tienen página web."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if only_new:
                # Solo los que se han visto por primera vez hoy/recientemente
                cursor.execute("SELECT * FROM places WHERE has_website = 0 AND times_seen = 1 ORDER BY first_seen DESC")
            else:
                cursor.execute("SELECT * FROM places WHERE has_website = 0 ORDER BY first_seen DESC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_all_places(self) -> List[Dict[str, any]]:
        """Devuelve todos los negocios en la base de datos."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM places ORDER BY last_seen DESC")
            return [dict(r) for r in rows]
