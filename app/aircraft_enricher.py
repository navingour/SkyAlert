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

ICAO_TYPE_MAP = {
    # Airbus
    "A318": ("Airbus A318", "Airbus"),
    "A319": ("Airbus A319", "Airbus"),
    "A320": ("Airbus A320", "Airbus"),
    "A321": ("Airbus A321", "Airbus"),
    "A20N": ("Airbus A320neo", "Airbus"),
    "A21N": ("Airbus A321neo", "Airbus"),
    "A19N": ("Airbus A319neo", "Airbus"),
    "A332": ("Airbus A330-200", "Airbus"),
    "A333": ("Airbus A330-300", "Airbus"),
    "A338": ("Airbus A330-800neo", "Airbus"),
    "A339": ("Airbus A330-900neo", "Airbus"),
    "A342": ("Airbus A340-200", "Airbus"),
    "A343": ("Airbus A340-300", "Airbus"),
    "A345": ("Airbus A340-500", "Airbus"),
    "A346": ("Airbus A340-600", "Airbus"),
    "A359": ("Airbus A350-900", "Airbus"),
    "A35K": ("Airbus A350-1000", "Airbus"),
    "A388": ("Airbus A380-800", "Airbus"),
    "A220": ("Airbus A220", "Airbus"),
    "BCS1": ("Airbus A220-100", "Airbus"),
    "BCS3": ("Airbus A220-300", "Airbus"),
    "A306": ("Airbus A300-600", "Airbus"),
    "A30B": ("Airbus A300B4", "Airbus"),
    "A3ST": ("Airbus Beluga", "Airbus"),
    "A337": ("Airbus BelugaXL", "Airbus"),
    "A400": ("Airbus A400M Atlas", "Airbus"),

    # Boeing
    "B732": ("Boeing 737-200", "Boeing"),
    "B733": ("Boeing 737-300", "Boeing"),
    "B734": ("Boeing 737-400", "Boeing"),
    "B735": ("Boeing 737-500", "Boeing"),
    "B736": ("Boeing 737-600", "Boeing"),
    "B737": ("Boeing 737-700", "Boeing"),
    "B738": ("Boeing 737-800", "Boeing"),
    "B739": ("Boeing 737-900", "Boeing"),
    "B38M": ("Boeing 737 MAX 8", "Boeing"),
    "B39M": ("Boeing 737 MAX 9", "Boeing"),
    "B37M": ("Boeing 737 MAX 7", "Boeing"),
    "B3JM": ("Boeing 737 MAX 10", "Boeing"),
    "B742": ("Boeing 747-200", "Boeing"),
    "B743": ("Boeing 747-300", "Boeing"),
    "B744": ("Boeing 747-400", "Boeing"),
    "B748": ("Boeing 747-8", "Boeing"),
    "B752": ("Boeing 757-200", "Boeing"),
    "B753": ("Boeing 757-300", "Boeing"),
    "B762": ("Boeing 767-200", "Boeing"),
    "B763": ("Boeing 767-300", "Boeing"),
    "B764": ("Boeing 767-400", "Boeing"),
    "B772": ("Boeing 777-200", "Boeing"),
    "B77L": ("Boeing 777-200LR/F", "Boeing"),
    "B773": ("Boeing 777-300", "Boeing"),
    "B77W": ("Boeing 777-300ER", "Boeing"),
    "B778": ("Boeing 777-8", "Boeing"),
    "B779": ("Boeing 777-9", "Boeing"),
    "B788": ("Boeing 787-8 Dreamliner", "Boeing"),
    "B789": ("Boeing 787-9 Dreamliner", "Boeing"),
    "B78X": ("Boeing 787-10 Dreamliner", "Boeing"),
    "C17": ("Boeing C-17 Globemaster III", "Boeing"),
    "P8": ("Boeing P-8 Poseidon", "Boeing"),
    "E3TF": ("Boeing E-3 Sentry", "Boeing"),
    "K35R": ("Boeing KC-135 Stratotanker", "Boeing"),
    "B52": ("Boeing B-52 Stratofortress", "Boeing"),

    # ATR
    "AT43": ("ATR 42-300", "ATR"),
    "AT45": ("ATR 42-500", "ATR"),
    "AT46": ("ATR 42-600", "ATR"),
    "AT72": ("ATR 72-200", "ATR"),
    "AT73": ("ATR 72-210", "ATR"),
    "AT75": ("ATR 72-500", "ATR"),
    "AT76": ("ATR 72-600", "ATR"),

    # Bombardier / De Havilland
    "DH8A": ("De Havilland Dash 8-100", "Bombardier"),
    "DH8B": ("De Havilland Dash 8-200", "Bombardier"),
    "DH8C": ("De Havilland Dash 8-300", "Bombardier"),
    "DH8D": ("De Havilland Dash 8-400 (Q400)", "Bombardier"),
    "DHC6": ("De Havilland DHC-6 Twin Otter", "De Havilland"),
    "CRJ1": ("Bombardier CRJ-100", "Bombardier"),
    "CRJ2": ("Bombardier CRJ-200", "Bombardier"),
    "CRJ7": ("Bombardier CRJ-700", "Bombardier"),
    "CRJ9": ("Bombardier CRJ-900", "Bombardier"),
    "CRJX": ("Bombardier CRJ-1000", "Bombardier"),
    "CL60": ("Bombardier Challenger 600", "Bombardier"),
    "CL30": ("Bombardier Challenger 300", "Bombardier"),
    "CL35": ("Bombardier Challenger 350", "Bombardier"),
    "GLEX": ("Bombardier Global Express", "Bombardier"),
    "GL5T": ("Bombardier Global 5000", "Bombardier"),
    "GL6T": ("Bombardier Global 6000", "Bombardier"),
    "GL75": ("Bombardier Global 7500", "Bombardier"),

    # Embraer
    "E120": ("Embraer EMB 120 Brasilia", "Embraer"),
    "E135": ("Embraer ERJ 135", "Embraer"),
    "E145": ("Embraer ERJ 145", "Embraer"),
    "E170": ("Embraer E170", "Embraer"),
    "E75S": ("Embraer E175 (Short Wing)", "Embraer"),
    "E75L": ("Embraer E175 (Long Wing)", "Embraer"),
    "E175": ("Embraer E175", "Embraer"),
    "E190": ("Embraer E190", "Embraer"),
    "E195": ("Embraer E195", "Embraer"),
    "E290": ("Embraer E190-E2", "Embraer"),
    "E295": ("Embraer E195-E2", "Embraer"),
    "E50P": ("Embraer Phenom 100", "Embraer"),
    "E55P": ("Embraer Phenom 300", "Embraer"),
    "E545": ("Embraer Legacy 450 / Praetor 500", "Embraer"),
    "E550": ("Embraer Legacy 500 / Praetor 600", "Embraer"),
    "C390": ("Embraer C-390 Millennium", "Embraer"),

    # Gulfstream
    "GLF4": ("Gulfstream G-IV / G450", "Gulfstream"),
    "GLF5": ("Gulfstream G-V / G550", "Gulfstream"),
    "GLF6": ("Gulfstream G650 / G700", "Gulfstream"),
    "G150": ("Gulfstream G150", "Gulfstream"),
    "G280": ("Gulfstream G280", "Gulfstream"),
    "GA5C": ("Gulfstream G500", "Gulfstream"),
    "GA6C": ("Gulfstream G600", "Gulfstream"),

    # Dassault
    "FA7X": ("Dassault Falcon 7X", "Dassault"),
    "FA8X": ("Dassault Falcon 8X", "Dassault"),
    "FA50": ("Dassault Falcon 50", "Dassault"),
    "FA20": ("Dassault Falcon 20", "Dassault"),
    "F2TH": ("Dassault Falcon 2000", "Dassault"),
    "F900": ("Dassault Falcon 900", "Dassault"),
    "RFAL": ("Dassault Rafale", "Dassault"),
    "MRF1": ("Dassault Mirage F1", "Dassault"),
    "M200": ("Dassault Mirage 2000", "Dassault"),

    # Cessna / Beechcraft / Textron
    "C172": ("Cessna 172 Skyhawk", "Cessna"),
    "C182": ("Cessna 182 Skylane", "Cessna"),
    "C208": ("Cessna 208 Caravan", "Cessna"),
    "C510": ("Cessna Citation Mustang", "Cessna"),
    "C525": ("Cessna CitationJet / CJ1/CJ2/CJ3/CJ4", "Cessna"),
    "C550": ("Cessna Citation II / Bravo", "Cessna"),
    "C560": ("Cessna Citation V / Ultra / Encore", "Cessna"),
    "C56X": ("Cessna Citation Excel / XLS", "Cessna"),
    "C680": ("Cessna Citation Sovereign", "Cessna"),
    "C750": ("Cessna Citation X", "Cessna"),
    "C700": ("Cessna Citation Longitude", "Cessna"),
    "BE20": ("Beechcraft Super King Air 200", "Beechcraft"),
    "BE30": ("Beechcraft Super King Air 300", "Beechcraft"),
    "B350": ("Beechcraft Super King Air 350", "Beechcraft"),
    "BE90": ("Beechcraft King Air 90", "Beechcraft"),
    "BE9L": ("Beechcraft King Air 90", "Beechcraft"),
    "B190": ("Beechcraft 1900", "Beechcraft"),
    "HA4T": ("Hawker 4000", "Hawker"),
    "H25B": ("Hawker 800 / 850 / 900", "Hawker"),

    # Pilatus
    "PC12": ("Pilatus PC-12", "Pilatus"),
    "PC24": ("Pilatus PC-24", "Pilatus"),
    "PC7": ("Pilatus PC-7", "Pilatus"),

    # Russian / Antonov / Ilyushin / Tupolev / Sukhoi
    "IL76": ("Ilyushin Il-76", "Ilyushin"),
    "IL62": ("Ilyushin Il-62", "Ilyushin"),
    "IL96": ("Ilyushin Il-96", "Ilyushin"),
    "AN12": ("Antonov An-12", "Antonov"),
    "AN24": ("Antonov An-24", "Antonov"),
    "AN26": ("Antonov An-26", "Antonov"),
    "AN32": ("Antonov An-32", "Antonov"),
    "AN72": ("Antonov An-72", "Antonov"),
    "AN124": ("Antonov An-124 Ruslan", "Antonov"),
    "AN225": ("Antonov An-225 Mriya", "Antonov"),
    "TU134": ("Tupolev Tu-134", "Tupolev"),
    "TU154": ("Tupolev Tu-154", "Tupolev"),
    "TU204": ("Tupolev Tu-204", "Tupolev"),
    "SU30": ("Sukhoi Su-30MKI", "Sukhoi"),
    "SU95": ("Sukhoi Superjet 100", "Sukhoi"),
    "SSJ1": ("Sukhoi Superjet 100", "Sukhoi"),
    "MIG29": ("Mikoyan MiG-29", "Mikoyan"),

    # Military & Transports
    "C130": ("Lockheed C-130 Hercules", "Lockheed Martin"),
    "C30J": ("Lockheed Martin C-130J Super Hercules", "Lockheed Martin"),
    "EUFI": ("Eurofighter Typhoon", "Eurofighter"),
    "DO228": ("Dornier 228", "Dornier"),
    "D228": ("Dornier 228", "Dornier"),

    # Helicopters
    "B06": ("Bell 206 JetRanger", "Bell"),
    "B407": ("Bell 407", "Bell"),
    "B412": ("Bell 412", "Bell"),
    "B429": ("Bell 429 GlobalRanger", "Bell"),
    "EC35": ("Eurocopter EC135 / H135", "Airbus Helicopters"),
    "EC45": ("Eurocopter EC145 / H145", "Airbus Helicopters"),
    "AS50": ("Eurocopter AS350 Ecureuil", "Airbus Helicopters"),
    "AS55": ("Eurocopter AS355 Ecureuil 2", "Airbus Helicopters"),
    "EC25": ("Eurocopter EC225 Super Puma", "Airbus Helicopters"),
    "A139": ("AgustaWestland AW139", "Leonardo"),
    "A169": ("AgustaWestland AW169", "Leonardo"),
    "A189": ("AgustaWestland AW189", "Leonardo"),
    "A109": ("AgustaWestland AW109", "Leonardo"),
    "S76": ("Sikorsky S-76", "Sikorsky"),
    "S92": ("Sikorsky S-92", "Sikorsky"),
    "UH60": ("Sikorsky UH-60 Black Hawk", "Sikorsky"),
    "MI8": ("Mil Mi-8 / Mi-17", "Mil"),
    "MI17": ("Mil Mi-17", "Mil"),
}

# Known carrier primary fleets (used when raw ADS-B has not broadcast type message yet)
FLEET_FALLBACK_MAP = {
    'AKJ': ('B38M', 'Boeing 737 MAX 8', 'Boeing', 'Akasa Air'),
    'LLR': ('AT76', 'ATR 72-600', 'ATR', 'Alliance Air'),
    'FLG': ('AT76', 'ATR 72-600', 'ATR', 'FlyBig'),
    'SDG': ('E175', 'Embraer E175', 'Embraer', 'Star Air'),
    'BDA': ('B738', 'Boeing 737-800(BCF)', 'Boeing', 'Blue Dart Aviation'),
    'ICG': ('DO228', 'Dornier 228', 'Dornier', 'Indian Coast Guard'),
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
            # Join aircraft and aircraft_enrichment so all metadata is loaded
            query = """
            SELECT 
                a.icao_hex,
                COALESCE(NULLIF(e.registration, ''), NULLIF(a.registration, '')) as registration,
                COALESCE(NULLIF(e.icao_aircraft_type, ''), NULLIF(e.type_code, ''), NULLIF(e.aircraft_type, ''), NULLIF(a.aircraft_type, '')) as aircraft_type,
                COALESCE(NULLIF(e.manufacturer, ''), NULLIF(a.manufacturer, '')) as manufacturer,
                COALESCE(NULLIF(e.model, ''), NULLIF(a.model, '')) as model,
                COALESCE(NULLIF(e.operator_name, ''), NULLIF(a.operator, '')) as operator,
                COALESCE(NULLIF(e.country, ''), '') as country,
                e.type_code,
                e.icao_aircraft_type
            FROM aircraft a
            LEFT JOIN aircraft_enrichment e ON a.id = e.aircraft_id
            """
            cur.execute(query)
            for row in cur.fetchall():
                hex_c = (row["icao_hex"] or "").strip().upper()
                if hex_c:
                    self.db_aircraft[hex_c] = dict(row)
            conn.close()
            logger.info("Loaded %d aircraft from relational DB with joined enrichment", len(self.db_aircraft))
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
        if any(k in text for k in ["AIRBUS", "A318", "A319", "A320", "A321", "A330", "A340", "A350", "A380", "A20N", "A21N", "A332", "A333", "A359", "A388"]):
            return "Airbus"
        if any(k in text for k in ["BOEING", "B737", "B738", "B739", "B38M", "B39M", "B744", "B748", "B752", "B763", "B772", "B77W", "B77L", "B788", "B789", "B78X"]):
            return "Boeing"
        if any(k in text for k in ["EMBRAER", "E145", "E170", "E175", "E190", "E195", "E290", "E295", "ERJ", "PHENOM"]):
            return "Embraer"
        if any(k in text for k in ["BOMBARDIER", "CRJ", "CL60", "GLOBAL", "DHC8", "Q400", "CHALLENGER"]):
            return "Bombardier"
        if any(k in text for k in ["CESSNA", "C172", "C182", "C208", "C550", "C560", "C680", "C750", "CITATION"]):
            return "Cessna"
        if any(k in text for k in ["BEECH", "KING AIR", "BE20", "BE30", "BE90", "BE9L", "B350"]):
            return "Beechcraft"
        if any(k in text for k in ["GULFSTREAM", "GLF", "G150", "G280", "G450", "G550", "G650"]):
            return "Gulfstream"
        if any(k in text for k in ["DASSAULT", "FALCON", "FA7X", "FA8X", "FA50", "FA20", "RAFALE", "MIRAGE"]):
            return "Dassault"
        if any(k in text for k in ["ATR", "AT43", "AT45", "AT46", "AT72", "AT75", "AT76"]):
            return "ATR"
        if any(k in text for k in ["ANTONOV", "AN12", "AN24", "AN26", "AN32", "AN72", "AN124", "AN225"]):
            return "Antonov"
        if any(k in text for k in ["ILYUSHIN", "IL76", "IL62", "IL96", "IL114"]):
            return "Ilyushin"
        if any(k in text for k in ["TUPOLEV", "TU134", "TU154", "TU204", "TU214"]):
            return "Tupolev"
        if any(k in text for k in ["SUKHOI", "SU30", "SU95", "SSJ100"]):
            return "Sukhoi"
        if any(k in text for k in ["LOCKHEED", "C130", "C30J"]):
            return "Lockheed Martin"
        if any(k in text for k in ["BELL"]):
            return "Bell"
        if any(k in text for k in ["SIKORSKY", "UH60", "S76", "S92"]):
            return "Sikorsky"
        if any(k in text for k in ["EUROCOPTER", "EC135", "EC145", "AS350"]):
            return "Airbus Helicopters"
        if any(k in text for k in ["LEONARDO", "AGUSTA", "AW139", "AW169", "AW189"]):
            return "Leonardo"
        if any(k in text for k in ["PILATUS", "PC12", "PC24"]):
            return "Pilatus"
        if any(k in text for k in ["DORNIER", "DO228", "D228"]):
            return "Dornier"

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
        hex_u = (item.get("icao_hex") or item.get("id") or item.get("hex") or "").strip().upper()
        callsign = (item.get("callsign") or item.get("flight") or "-").strip()
        reg = item.get("registration") or item.get("r") or "-"
        ac_type = (
            item.get("aircraft_type") 
            or item.get("type_code") 
            or item.get("icao_aircraft_type") 
            or item.get("t") 
            or item.get("type") 
            or "-"
        )
        mfr = item.get("manufacturer") or "-"
        model = item.get("model") or item.get("description") or "-"
        op = item.get("operator") or item.get("operator_name") or "-"

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

        # 1. Check relational DB (a + e joined)
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

        # 2. Check AlertLookup (special / military / VIP database)
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

        # 3. Check Reference CSV (625,000+ ICAO aircraft)
        csv_match = self.csv_aircraft.get(hex_u)
        if csv_match:
            if csv_match.get("registration") and reg in ("-", hex_u, ""):
                reg = csv_match["registration"]
            if csv_match.get("type_code") and ac_type in ("-", "Unknown", ""):
                ac_type = csv_match["type_code"]
            if csv_match.get("model_name") and model in ("-", "Unknown", ""):
                model = csv_match["model_name"]

        # 4. Check ICAO_TYPE_MAP for known type code expansion
        type_upper = ac_type.upper().strip() if ac_type and ac_type != "-" else ""
        if type_upper in ICAO_TYPE_MAP:
            mapped_model, mapped_mfr = ICAO_TYPE_MAP[type_upper]
            if model in ("-", "Unknown", "", type_upper):
                model = mapped_model
            if mfr in ("-", "Unknown", ""):
                mfr = mapped_mfr

        # 5. Check Fleet profiling from Callsign prefix (e.g. AKJ -> B38M Boeing 737 MAX 8)
        callsign_prefix = ""
        if callsign and callsign != "-":
            c_match = re.match(r"^([A-Z]{3})", callsign.upper())
            if c_match:
                callsign_prefix = c_match.group(1)

        if callsign_prefix in FLEET_FALLBACK_MAP:
            fb_type, fb_model, fb_mfr, fb_op = FLEET_FALLBACK_MAP[callsign_prefix]
            if ac_type in ("-", "Unknown", ""):
                ac_type = fb_type
            if model in ("-", "Unknown", ""):
                model = fb_model
            if mfr in ("-", "Unknown", ""):
                mfr = fb_mfr
            if op in ("-", "Unknown Operator", ""):
                op = fb_op

        # 6. Extract Manufacturer if missing
        if mfr in ("-", "Unknown", "") and model not in ("-", "Unknown", ""):
            mfr = self.extract_manufacturer(model, ac_type)

        # 7. Resolve Operator from callsign
        if (op in ("-", "Unknown Operator", "") or not op) and callsign_prefix:
            if callsign_prefix in OPERATOR_MAP:
                op = OPERATOR_MAP[callsign_prefix][0]

        # 8. Expand operator abbreviation if 3-letter ICAO or mapped code
        op = self.expand_operator_name(op)

        # 9. Cross-populate model <-> ac_type if one is still missing
        if (model in ("-", "Unknown", "") or not model) and ac_type and ac_type != "-":
            model = ac_type
        if (ac_type in ("-", "Unknown", "") or not ac_type) and model and model != "-":
            ac_type = model

        resolved_reg = reg if reg and reg != "-" else hex_u
        country = self.get_country_from_registration(resolved_reg, item.get("country") or "Unknown")

        final_ac_type = ac_type if ac_type and ac_type != "-" else "Unknown"
        final_mfr = mfr if mfr and mfr != "-" else "Unknown"
        final_model = model if model and model != "-" else (final_ac_type if final_ac_type != "Unknown" else "Unknown")

        item["registration"] = resolved_reg
        item["aircraft_type"] = final_ac_type
        item["type_code"] = final_ac_type
        item["icao_aircraft_type"] = final_ac_type
        item["manufacturer"] = final_mfr
        item["model"] = final_model
        item["operator"] = op
        item["country"] = country
        item["is_enriched"] = (item["manufacturer"] != "Unknown" or item["operator"] != "Unknown Operator" or item["aircraft_type"] != "Unknown")

        # Keep nested identity in sync if present
        if "identity" in item and isinstance(item["identity"], dict):
            item["identity"]["icao_hex"] = hex_u
            item["identity"]["registration"] = resolved_reg
            item["identity"]["callsign"] = callsign
            item["identity"]["aircraft_type"] = final_ac_type
            item["identity"]["type_code"] = final_ac_type
            item["identity"]["icao_aircraft_type"] = final_ac_type
            item["identity"]["manufacturer"] = final_mfr
            item["identity"]["model"] = final_model
            item["identity"]["operator"] = op
            item["identity"]["country"] = country

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
