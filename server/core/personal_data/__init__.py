from .address_extractor import address_fingerprint, extract_chilean_address_matches, extract_chilean_addresses, find_address_near_target, select_primary_address
from .name_extractor import extract_name_candidates, select_primary_name
from .plate_extractor import extract_chilean_plate_matches, extract_chilean_plates, select_primary_plate
from .phone_extractor import extract_chilean_phone_matches, extract_chilean_phones, select_primary_phone
from .rut_extractor import extract_chilean_ruts, select_primary_rut

__all__ = [
    "extract_chilean_address_matches",
    "extract_chilean_addresses",
    "address_fingerprint",
    "find_address_near_target",
    "select_primary_address",
    "extract_name_candidates",
    "select_primary_name",
    "extract_chilean_plate_matches",
    "extract_chilean_plates",
    "select_primary_plate",
    "extract_chilean_phones",
    "extract_chilean_phone_matches",
    "select_primary_phone",
    "extract_chilean_ruts",
    "select_primary_rut",
]
