from .name_extractor import extract_name_candidates, select_primary_name
from .plate_extractor import extract_chilean_plates, select_primary_plate
from .rut_extractor import extract_chilean_ruts, select_primary_rut

__all__ = [
    "extract_name_candidates",
    "select_primary_name",
    "extract_chilean_plates",
    "select_primary_plate",
    "extract_chilean_ruts",
    "select_primary_rut",
]
