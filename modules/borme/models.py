from dataclasses import dataclass, field, asdict
from typing import List, Optional

@dataclass
class LeadBORME:
    company_name: str
    province: str
    borme_date: str
    act_number: Optional[str] = ""
    domicilio_social: Optional[str] = ""
    capital: Optional[str] = ""
    objeto_social: Optional[str] = ""
    administradores: List[str] = field(default_factory=list)
    socio_unico: Optional[str] = ""
    raw_text: Optional[str] = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["administradores_str"] = "; ".join(self.administradores) if self.administradores else ""
        return data

