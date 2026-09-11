import sqlite3
import csv
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.alert_lookup import AlertLookup

logger = logging.getLogger("skyalert.enricher")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RELATIONAL_DB = DATA_DIR / "skyalert_relational.db"
REFERENCE_CSV = DATA_DIR / "reference" / "aircraft.csv"

OPERATOR_MAP = {
    'SIA': ('Singapore Airlines', 'Singapore'),
    'IGO': ('IndiGo', 'India'),
    'AIC': ('Air India', 'India'),
    'AXB': ('Air India Express', 'India'),
    'QTR': ('Qatar Airways', 'Qatar'),
    'UAE': ('Emirates', 'United Arab Emirates'),
    'ETD': ('Etihad Airways', 'United Arab Emirates'),
    'CPA': ('Cathay Pacific', 'Hong Kong'),
    'THA': ('Thai Airways', 'Thailand'),
    'JAL': ('Japan Airlines', 'Japan'),
    'ANA': ('All Nippon Airways', 'Japan'),
    'ABY': ('Air Arabia', 'United Arab Emirates'),
    'THY': ('Turkish Airlines', 'Turkey'),
    'RNA': ('Nepal Airlines', 'Nepal'),
    'KNE': ('Flynas', 'Saudi Arabia'),
    'SVA': ('Saudia', 'Saudi Arabia'),
    'MAS': ('Malaysia Airlines', 'Malaysia'),
    'HVN': ('Vietnam Airlines', 'Vietnam'),
    'VJC': ('VietJet Air', 'Vietnam'),
    'SWR': ('Swiss International Air Lines', 'Switzerland'),
    'CLX': ('Cargolux', 'Luxembourg'),
    'CKS': ('Kalitta Air', 'United States'),
    'BOX': ('AeroLogic', 'Germany'),
    'CSC': ('Sichuan Airlines', 'China'),
    'VTI': ('Vistara', 'India'),
    'AZG': ('Silk Way West Airlines', 'Azerbaijan'),
    'HYT': ('Tiantian Airlines', 'China'),
    'QQE': ('Qatar Executive', 'Qatar'),
    'IAD': ('Air India Regional', 'India'),
    'TVJ': ('Thai VietJet Air', 'Thailand'),
    'EVA': ('EVA Air', 'Taiwan'),
    'CAL': ('China Airlines', 'Taiwan'),
    'IRM': ('Mahan Air', 'Iran'),
    'HGO': ('Hainan Airlines', 'China'),
    'MXD': ('Batik Air Malaysia', 'Malaysia'),
    'BDA': ('Blue Dart Aviation', 'India'),
    'EXV': ('Expo Aviation', 'Sri Lanka'),
    'ALK': ('SriLankan Airlines', 'Sri Lanka'),
    'CBJ': ('Capital Airlines', 'China'),
    'HKC': ('Hong Kong Air Cargo', 'Hong Kong'),
    'TVR': ('Tropic Air', 'Belize'),
    'TLM': ('Thai Lion Air', 'Thailand'),
    'ETH': ('Ethiopian Airlines', 'Ethiopia'),
    'DHK': ('DHL Air UK', 'United Kingdom'),
    'BAW': ('British Airways', 'United Kingdom'),
    'DLH': ('Lufthansa', 'Germany'),
    'BBC': ('Biman Bangladesh Airlines', 'Bangladesh'),
    'FDB': ('flydubai', 'United Arab Emirates'),
    'CQN': ('Chongqing Airlines', 'China'),
    'HLF': ('TUI fly Deutschland', 'Germany'),
    'RJA': ('Royal Jordanian', 'Jordan'),
    'FIN': ('Finnair', 'Finland'),
    'AFR': ('Air France', 'France'),
    'VUA': ('Air Vistara', 'India'),
    'AUA': ('Austrian Airlines', 'Austria'),
    'ACI': ('Aircalin', 'New Caledonia'),
    'KZR': ('Air Astana', 'Kazakhstan'),
    'MSR': ('EgyptAir', 'Egypt'),
    'QFA': ('Qantas', 'Australia'),
    'BRU': ('Belavia', 'Belarus'),
    'KLM': ('KLM Royal Dutch Airlines', 'Netherlands'),
    'CFG': ('Condor', 'Germany'),
    'ABD': ('Air Atlanta Icelandic', 'Iceland'),
    'DRK': ('Drukair', 'Bhutan'),
    'BTN': ('Druk Air Bhutan', 'Bhutan'),
    'IFC': ('Indian Air Force', 'India'),
    'IAF': ('Indian Air Force', 'India'),
    'NVY': ('Indian Navy', 'India'),
    'ICG': ('Indian Coast Guard', 'India'),
    'YZR': ('YTO Cargo Airlines', 'China'),
    'AKJ': ('Akasa Air', 'India'),
    'SEJ': ('SpiceJet', 'India'),
    'GOW': ('Go First', 'India'),
    'LLR': ('Alliance Air', 'India'),
    'CCA': ('Air China', 'China'),
    'CES': ('China Eastern Airlines', 'China'),
    'CSN': ('China Southern Airlines', 'China'),
    'FDX': ('FedEx Express', 'United States'),
    'UPS': ('United Parcel Service', 'United States'),
    'DAL': ('Delta Air Lines', 'United States'),
    'AAL': ('American Airlines', 'United States'),
    'UAL': ('United Airlines', 'United States'),
    'SWA': ('Southwest Airlines', 'United States'),
    'JBU': ('JetBlue Airways', 'United States'),
    'ASA': ('Alaska Airlines', 'United States'),
    'HAL': ('Hawaiian Airlines', 'United States'),
    'NKS': ('Spirit Airlines', 'United States'),
    'PAL': ('Philippine Airlines', 'Philippines'),
    'CEB': ('Cebu Pacific', 'Philippines'),
    'PIA': ('Pakistan International Airlines', 'Pakistan'),
    'GFA': ('Gulf Air', 'Bahrain'),
    'OMA': ('Oman Air', 'Oman'),
    'RBA': ('Royal Brunei Airlines', 'Brunei'),
    'FJI': ('Fiji Airways', 'Fiji'),
    'RAM': ('Royal Air Maroc', 'Morocco'),
    'RWW': ('Air Arabia Abu Dhabi', 'United Arab Emirates'),
    'DKH': ('Juneyao Air', 'China'),
    'CHH': ('Hainan Airlines', 'China'),
    'CXA': ('XiamenAir', 'China'),
    'CSZ': ('Shenzhen Airlines', 'China'),
}

class AircraftEnricher:
    """
    Unified enrichment service aggregating:
    1. skyalert_relational.db (relational aircraft & enrichment tables)
    2. AlertLookup (16,959 special/military aircraft)
    3. reference/aircraft.csv (625,000+ ICAO aircraft records)
    4. Call-sign operator mapping
    """

    def __init__(self):
        self.alert_lookup = AlertLookup()
        self.db_aircraft = {}
        self.csv_aircraft = {}
        self.load_relational_db()
        self.load_reference_csv()

    def load_relational_db(self):
        if not RELATIONAL_DB.exists():
            return
        try:
            conn = sqlite3.connect(str(RELATIONAL_DB))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM aircraft")
            for row in cur.fetchall():
                hex_c = (row["icao_hex"] or "").strip().upper()
                if hex_c:
                    self.db_aircraft[hex_c] = dict(row)
            conn.close()
            logger.info("Loaded %d aircraft from relational DB", len(self.db_aircraft))
        except Exception as e:
            logger.warning("Error loading relational DB for enrichment: %s", e)

    def load_reference_csv(self):
        if not REFERENCE_CSV.exists():
            return
        try:
            with open(REFERENCE_CSV, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split(";")
                    if len(parts) >= 5:
                        hex_c = parts[0].strip().upper()
                        reg = parts[1].strip()
                        t_code = parts[2].strip()
                        desc = parts[4].strip()
                        if hex_c and len(hex_c) == 6:
                            self.csv_aircraft[hex_c] = {
                                "registration": reg,
                                "type_code": t_code,
                                "model_name": desc
                            }
            logger.info("Loaded %d reference aircraft records from CSV", len(self.csv_aircraft))
        except Exception as e:
            logger.warning("Error loading reference aircraft.csv: %s", e)

    def extract_manufacturer(self, model_str: str, type_code: str = "") -> str:
        text = f"{model_str} {type_code}".upper()
        if any(k in text for k in ["AIRBUS", "A318", "A319", "A320", "A321", "A330", "A340", "A350", "A380", "A20N", "A21N", "A319", "A332", "A333", "A359", "A388"]):
            return "Airbus"
        if any(k in text for k in ["BOEING", "B737", "B738", "B739", "B38M", "B39M", "B744", "B748", "B752", "B763", "B772", "B77W", "B77L", "B788", "B789", "B78X"]):
            return "Boeing"
        if any(k in text for k in ["EMBRAER", "E145", "E170", "E175", "E190", "E195", "E290", "E295", "ERJ"]):
            return "Embraer"
        if any(k in text for k in ["BOMBARDIER", "CRJ", "CL60", "GLOBAL", "DHC8", "Q400"]):
            return "Bombardier"
        if any(k in text for k in ["CESSNA", "C172", "C182", "C208", "C550", "C560", "C680", "C750"]):
            return "Cessna"
        if any(k in text for k in ["BEECH", "KING AIR", "BE20", "BE30", "BE90", "BE9L", "B350"]):
            return "Beechcraft"
        if any(k in text for k in ["GULFSTREAM", "GLF", "G150", "G280", "G450", "G550", "G650"]):
            return "Gulfstream"
        if any(k in text for k in ["DASSAULT", "FALCON", "FA7X", "FA8X", "FA50", "FA20"]):
            return "Dassault"
        if any(k in text for k in ["ATR", "AT43", "AT45", "AT72", "AT75", "AT76"]):
            return "ATR"
        if any(k in text for k in ["ANTONOV", "AN12", "AN24", "AN26", "AN32", "AN72", "AN124", "AN225"]):
            return "Antonov"
        if any(k in text for k in ["ILYUSHIN", "IL76", "IL62", "IL96", "IL114"]):
            return "Ilyushin"
        if any(k in text for k in ["TUPOLEV", "TU134", "TU154", "TU204", "TU214"]):
            return "Tupolev"
        if any(k in text for k in ["SUKHOI", "SU95", "SSJ100"]):
            return "Sukhoi"
        if any(k in text for k in ["BELL"]):
            return "Bell"
        if any(k in text for k in ["SIKORSKY"]):
            return "Sikorsky"
        if any(k in text for k in ["EUROCOPTER"]):
            return "Eurocopter"

        parts = model_str.strip().split()
        if parts and parts[0] not in ("-", "Unknown", "Unknown Type"):
            return parts[0].title()
        return "Airframe"

    def expand_operator_name(self, op_name: str) -> str:
        """Expands 3-letter ICAO codes and known abbreviations to full, human-readable airline names."""
        if not op_name or op_name in ("-", "Unknown", "Unknown Operator", "None", "null"):
            return "Unknown Operator"
        op_clean = op_name.strip()
        op_upper = op_clean.upper()
        if op_upper in OPERATOR_MAP:
            return OPERATOR_MAP[op_upper][0]
        match = re.match(r"^([A-Z]{3})$", op_upper)
        if match and match.group(1) in OPERATOR_MAP:
            return OPERATOR_MAP[match.group(1)][0]
        return op_clean

    def enrich_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Enriches flat aircraft record (used in Aircraft Database table and Live Airspace feed)."""
        hex_u = (item.get("icao_hex") or item.get("id") or "").strip().upper()
        callsign = item.get("callsign") or "-"
        reg = item.get("registration") or "-"
        ac_type = item.get("aircraft_type") or "-"
        mfr = item.get("manufacturer") or "-"
        model = item.get("model") or "-"
        op = item.get("operator") or "-"

        placeholders = {
            "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7",
            "B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7",
            "C0", "C1", "C2", "Unknown", "Unknown Operator", "Unknown Type",
            "-", "", "None", "null", hex_u,
            "adsb_icao", "adsb_other", "tisb_trackfile", "mode_s",
            "Commercial Operator", "Commercial", "In Transit"
        }

        if reg in placeholders or reg.lower() in ("unknown", "-", "none"):
            reg = "-"
        if ac_type in placeholders or ac_type.lower() in ("adsb_icao", "adsb_other", "tisb_trackfile", "mode_s", "unknown"):
            ac_type = "-"
        if mfr in placeholders or mfr.lower() in ("unknown", "-", "none"):
            mfr = "-"
        if model in placeholders or model.lower() in ("unknown", "-", "none", "adsb_icao"):
            model = "-"
        if op in placeholders or op.lower() in ("unknown", "unknown operator", "commercial operator", "in transit", "-", "none"):
            op = "-"

        # 1. Check relational DB
        db_match = self.db_aircraft.get(hex_u)
        if db_match:
            if db_match.get("registration") and reg in ("-", hex_u, ""):
                reg = db_match["registration"]
            if db_match.get("aircraft_type") and ac_type in ("-", "Unknown", ""):
                ac_type = db_match["aircraft_type"]
            if db_match.get("manufacturer") and mfr in ("-", "Unknown", ""):
                mfr = db_match["manufacturer"]
            if db_match.get("model") and model in ("-", "Unknown", ""):
                model = db_match["model"]
            if db_match.get("operator") and op in ("-", "Unknown Operator", ""):
                op = db_match["operator"]

        # 2. Check AlertLookup
        alert_match = self.alert_lookup.get(hex_u)
        if alert_match:
            if alert_match.get("registration") and reg in ("-", hex_u, ""):
                reg = alert_match["registration"]
            if alert_match.get("operator") and op in ("-", "Unknown Operator", ""):
                op = alert_match["operator"]
            if alert_match.get("aircraft") and model in ("-", "Unknown", ""):
                model = alert_match["aircraft"]
            if alert_match.get("icao_type") and ac_type in ("-", "Unknown", ""):
                ac_type = alert_match["icao_type"]

        # 3. Check Reference CSV
        csv_match = self.csv_aircraft.get(hex_u)
        if csv_match:
            if csv_match.get("registration") and reg in ("-", hex_u, ""):
                reg = csv_match["registration"]
            if csv_match.get("type_code") and ac_type in ("-", "Unknown", ""):
                ac_type = csv_match["type_code"]
            if csv_match.get("model_name") and model in ("-", "Unknown", ""):
                model = csv_match["model_name"]

        # 4. Extract Manufacturer if missing
        if mfr in ("-", "Unknown", "") and model not in ("-", "Unknown", ""):
            mfr = self.extract_manufacturer(model, ac_type)

        # 5. Resolve Operator from callsign
        if (op in ("-", "Unknown Operator", "") or not op) and callsign and callsign != "-":
            match = re.match(r"^([A-Z]{3})", callsign.upper())
            if match:
                code = match.group(1)
                if code in OPERATOR_MAP:
                    op = OPERATOR_MAP[code][0]

        # 6. Expand operator abbreviation if 3-letter ICAO or mapped code
        op = self.expand_operator_name(op)

        resolved_reg = reg if reg and reg != "-" else hex_u
        country = self.get_country_from_registration(resolved_reg, item.get("country") or "Unknown")

        item["registration"] = resolved_reg
        item["aircraft_type"] = ac_type if ac_type and ac_type != "-" else "Unknown"
        item["manufacturer"] = mfr if mfr and mfr != "-" else "Unknown"
        item["model"] = model if model and model != "-" else "Unknown"
        item["operator"] = op
        item["country"] = country
        item["is_enriched"] = (item["manufacturer"] != "Unknown" or item["operator"] != "Unknown Operator")
        return item

    def enrich_rare_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Enriches individual Rare Aircraft card items."""
        hex_u = (item.get("icao_hex") or "").strip().upper()
        callsign = item.get("callsign") or "-"
        reg = item.get("registration")
        if not reg or reg in ("None", "null", "-", hex_u):
            reg = None
        ac_type = item.get("aircraft_type")
        if not ac_type or ac_type in ("None", "null", "-"):
            ac_type = None
        mfr = item.get("manufacturer")
        if not mfr or mfr in ("None", "null", "-"):
            mfr = None
        model = item.get("model")
        if not model or model in ("None", "null", "-"):
            model = None
        op = item.get("operator")
        if not op or op in ("None", "null", "-"):
            op = None
        country = item.get("country")
        if not country or country in ("None", "null", "-", "India Airspace"):
            country = None

        temp_item = {
            "icao_hex": hex_u,
            "callsign": callsign,
            "registration": reg,
            "aircraft_type": ac_type,
            "manufacturer": mfr,
            "model": model,
            "operator": op
        }
        enriched = self.enrich_item(temp_item)

        resolved_reg = enriched["registration"]
        resolved_op = enriched["operator"]
        if resolved_op in OPERATOR_MAP:
            resolved_op = OPERATOR_MAP[resolved_op][0]

        resolved_country = self.get_country_from_registration(resolved_reg, country or "Unknown")

        item["registration"] = resolved_reg
        item["aircraft_type"] = enriched["aircraft_type"]
        item["manufacturer"] = enriched["manufacturer"]
        item["model"] = enriched["model"] if enriched["model"] != "Unknown" else (ac_type or "Unknown")
        item["operator"] = resolved_op
        item["country"] = resolved_country
        return item

    def get_country_from_registration(self, reg: str, fallback_country: str = "Unknown") -> str:
        """Resolves country of registration based on international aircraft registration prefix."""
        if not reg or reg in ("-", "Unknown"):
            return fallback_country if fallback_country and fallback_country != "India Airspace" else "Unknown"

        reg_u = reg.upper().strip()

        prefixes = [
            ("VT-", "India"), ("VT", "India"),
            ("9V-", "Singapore"), ("9V", "Singapore"),
            ("A6-", "United Arab Emirates"), ("A6", "United Arab Emirates"),
            ("A7-", "Qatar"), ("A7", "Qatar"),
            ("S2-", "Bangladesh"), ("S2", "Bangladesh"),
            ("HS-", "Thailand"),
            ("9M-", "Malaysia"),
            ("VN-", "Vietnam"),
            ("JA", "Japan"),
            ("HL", "South Korea"),
            ("XU-", "Cambodia"),
            ("9N-", "Nepal"),
            ("4R-", "Sri Lanka"),
            ("A5-", "Bhutan"),
            ("HZ-", "Saudi Arabia"),
            ("JY-", "Jordan"),
            ("A9C-", "Bahrain"),
            ("9K-", "Kuwait"),
            ("A4O-", "Oman"),
            ("AP-", "Pakistan"),
            ("YA-", "Afghanistan"),
            ("EP-", "Iran"),
            ("YI-", "Iraq"),
            ("4X-", "Israel"),
            ("TC-", "Turkey"),
            ("G-", "United Kingdom"),
            ("F-", "France"),
            ("D-", "Germany"),
            ("HB-", "Switzerland"),
            ("PH-", "Netherlands"),
            ("OE-", "Austria"),
            ("EI-", "Ireland"), ("EJ-", "Ireland"),
            ("SP-", "Poland"),
            ("OK-", "Czech Republic"),
            ("YR-", "Romania"),
            ("LZ-", "Bulgaria"),
            ("SX-", "Greece"),
            ("CS-", "Portugal"), ("CR-", "Portugal"),
            ("EC-", "Spain"),
            ("I-", "Italy"),
            ("SE-", "Sweden"),
            ("LN-", "Norway"),
            ("OH-", "Finland"),
            ("OY-", "Denmark"),
            ("TF-", "Iceland"),
            ("RA-", "Russia"), ("RF-", "Russia"),
            ("EW-", "Belarus"),
            ("UR-", "Ukraine"),
            ("UP-", "Kazakhstan"),
            ("EX-", "Kyrgyzstan"),
            ("EY-", "Tajikistan"),
            ("EZ-", "Turkmenistan"),
            ("UK-", "Uzbekistan"),
            ("VH-", "Australia"),
            ("ZK-", "New Zealand"),
            ("C-", "Canada"), ("CF-", "Canada"), ("CG-", "Canada"),
            ("N", "United States"),
            ("XA-", "Mexico"), ("XB-", "Mexico"), ("XC-", "Mexico"),
            ("PR-", "Brazil"), ("PT-", "Brazil"), ("PP-", "Brazil"), ("PU-", "Brazil"),
            ("LV-", "Argentina"),
            ("CC-", "Chile"),
            ("HK-", "Colombia"),
            ("YV-", "Venezuela"),
            ("SU-", "Egypt"),
            ("ET-", "Ethiopia"),
            ("5Y-", "Kenya"),
            ("ZS-", "South Africa"), ("ZT-", "South Africa"), ("ZU-", "South Africa"),
            ("5N-", "Nigeria"),
            ("CN-", "Morocco"),
            ("7T-", "Algeria"),
            ("TS-", "Tunisia"),
            ("B-", "China"),
        ]

        for pfx, country in prefixes:
            if reg_u.startswith(pfx):
                return country

        if fallback_country and fallback_country != "India Airspace":
            return fallback_country

        return "Unknown"

    def enrich_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Enriches complete Aircraft Intelligence Profile structure."""
        if not profile:
            return profile

        hex_u = (profile.get("icao_hex") or profile.get("id") or "").strip().upper()
        callsign = profile.get("callsign") or "-"
        reg = profile.get("registration") or "-"

        mfr_obj = profile.get("manufacturer") or {}
        op_obj = profile.get("operator") or {}
        identity_obj = profile.get("identity") or {}
        ownership_obj = profile.get("ownership") or {}
        history_obj = profile.get("history") or {}

        mfr_name = mfr_obj.get("manufacturer") or "Unknown"
        model_name = mfr_obj.get("model") or profile.get("aircraft_type") or "Unknown"
        op_name = op_obj.get("operator") or "Unknown Operator"
        op_country = op_obj.get("country") or "India Airspace"
        op_icao = op_obj.get("operator_icao") or "-"
        op_iata = op_obj.get("operator_iata") or "-"
        ac_type = identity_obj.get("aircraft_type") or profile.get("aircraft_type") or "Unknown"
        type_code = identity_obj.get("type_code") or ac_type

        # 1. Relational DB lookup
        db_match = self.db_aircraft.get(hex_u)
        if db_match:
            if db_match.get("registration") and reg in ("-", hex_u, ""):
                reg = db_match["registration"]
            if db_match.get("manufacturer") and mfr_name in ("-", "Unknown", ""):
                mfr_name = db_match["manufacturer"]
            if db_match.get("model") and model_name in ("-", "Unknown", ""):
                model_name = db_match["model"]
            if db_match.get("operator") and op_name in ("-", "Unknown Operator", ""):
                op_name = db_match["operator"]
            if db_match.get("aircraft_type") and ac_type in ("-", "Unknown", ""):
                ac_type = db_match["aircraft_type"]

        # 2. AlertLookup
        alert_match = self.alert_lookup.get(hex_u)
        if alert_match:
            if alert_match.get("registration") and reg in ("-", hex_u, ""):
                reg = alert_match["registration"]
            if alert_match.get("operator") and op_name in ("-", "Unknown Operator", ""):
                op_name = alert_match["operator"]
            if alert_match.get("aircraft") and model_name in ("-", "Unknown", ""):
                model_name = alert_match["aircraft"]
            if alert_match.get("icao_type") and ac_type in ("-", "Unknown", ""):
                ac_type = alert_match["icao_type"]

        # 3. Reference CSV
        csv_match = self.csv_aircraft.get(hex_u)
        if csv_match:
            if csv_match.get("registration") and reg in ("-", hex_u, ""):
                reg = csv_match["registration"]
            if csv_match.get("model_name") and model_name in ("-", "Unknown", ""):
                model_name = csv_match["model_name"]
            if csv_match.get("type_code") and ac_type in ("-", "Unknown", ""):
                ac_type = csv_match["type_code"]

        # 4. Extract Manufacturer if missing
        if mfr_name in ("-", "Unknown", "") and model_name not in ("-", "Unknown", ""):
            mfr_name = self.extract_manufacturer(model_name, type_code)

        # 5. Extract Operator from Callsign if missing
        if (op_name in ("-", "Unknown Operator", "") or not op_name) and callsign and callsign != "-":
            match = re.match(r"^([A-Z]{3})", callsign.upper())
            if match:
                code = match.group(1)
                if code in OPERATOR_MAP:
                    op_name, fallback_op_country = OPERATOR_MAP[code]
                    op_icao = code
                    op_iata = code
                    if op_country in ("India Airspace", "Unknown", "-"):
                        op_country = fallback_op_country

        # 6. Expand operator abbreviation if 3-letter ICAO or mapped code
        op_name = self.expand_operator_name(op_name)

        # 7. Resolve Country of Registration
        country_of_registration = self.get_country_from_registration(reg, op_country)

        # Update profile structure
        profile["registration"] = reg if reg and reg != "-" else hex_u
        profile["aircraft_type"] = ac_type if ac_type and ac_type != "-" else "Unknown"

        profile["identity"]["icao_hex"] = hex_u
        profile["identity"]["registration"] = profile["registration"]
        profile["identity"]["callsign"] = callsign
        profile["identity"]["aircraft_type"] = profile["aircraft_type"]
        profile["identity"]["type_code"] = type_code
        profile["identity"]["icao_aircraft_type"] = ac_type

        profile["manufacturer"]["manufacturer"] = mfr_name if mfr_name and mfr_name != "-" else "Unknown"
        profile["manufacturer"]["model"] = model_name if model_name and model_name != "-" else "Unknown"
        profile["manufacturer"]["manufacturer_icao"] = mfr_name.upper()[:10]

        profile["operator"]["operator"] = op_name
        profile["operator"]["operator_icao"] = op_icao
        profile["operator"]["operator_iata"] = op_iata
        profile["operator"]["operator_callsign"] = op_name
        profile["operator"]["country"] = country_of_registration

        profile["ownership"]["owner"] = op_name
        profile["ownership"]["serial_number"] = ownership_obj.get("serial_number") or "Unknown"

        profile["history"]["built"] = history_obj.get("built") or "Unknown"
        profile["history"]["first_flight_date"] = history_obj.get("first_flight_date") or "Unknown"

        return profile

aircraft_enricher = AircraftEnricher()
