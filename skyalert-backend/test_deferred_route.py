import os
import unittest
from unittest.mock import patch

# Set up test db before importing app modules
os.environ["SKYALERT_DB"] = "data/test_skyalert.db"
# Ensure we do not hit real APIs
os.environ["PROVIDERS_ADSBDB_ENABLED"] = "false"

from app.db import db
from app.collector import collector
from app.enrich import enricher

class TestDeferredRoute(unittest.TestCase):
    def setUp(self):
        if os.path.exists("data/test_skyalert.db"):
            os.remove("data/test_skyalert.db")
        db.init_schema()
        
    def tearDown(self):
        if os.path.exists("data/test_skyalert.db"):
            os.remove("data/test_skyalert.db")

    @patch.object(enricher, 'resolve_route')
    def test_missing_route_enrichment(self, mock_resolve_route):
        # Mock route response
        mock_resolve_route.return_value = {
            "origin_iata": "CCU",
            "origin_icao": "VECC",
            "origin_name": "Netaji Subhas Chandra Bose International Airport",
            "origin_city": "Kolkata",
            "origin_country": "India",
            "destination_iata": "DEL",
            "destination_icao": "VIDP",
            "destination_name": "Indira Gandhi International Airport",
            "destination_city": "New Delhi",
            "destination_country": "India"
        }
        
        conn = db.connect()
        cur = conn.cursor()
        
        # A. Session created with no callsign
        cur.execute("INSERT INTO aircraft (icao_hex, callsign) VALUES ('123456', '')")
        cur.execute("SELECT id FROM aircraft WHERE icao_hex='123456'")
        ac_id = cur.fetchone()[0]
        
        cur.execute(
            "INSERT INTO detection_sessions (aircraft_id, started_at, last_observed_at) VALUES (?, '2023-01-01', '2023-01-01')", 
            (ac_id,)
        )
        cur.execute("SELECT id FROM detection_sessions WHERE aircraft_id=?", (ac_id,))
        session_id = cur.fetchone()[0]
        conn.commit()
        
        # Run enrichment - should do nothing because callsign is empty
        collector._enrich_missing_routes()
        mock_resolve_route.assert_not_called()
        
        # B. Callsign appears later.
        cur.execute("UPDATE aircraft SET callsign='IGO123' WHERE id=?", (ac_id,))
        conn.commit()
        
        # C. Route lookup succeeds later.
        # D. Correct detection_sessions row is updated.
        collector._enrich_missing_routes()
        mock_resolve_route.assert_called_once_with('IGO123', '123456')
        
        # E. Origin/destination are actually persisted.
        cur.execute("SELECT origin_iata, destination_iata FROM detection_sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        self.assertEqual(row['origin_iata'], 'CCU')
        self.assertEqual(row['destination_iata'], 'DEL')
        
        # F. Provider returns no route.
        mock_resolve_route.reset_mock()
        mock_resolve_route.return_value = None
        
        cur.execute("INSERT INTO aircraft (icao_hex, callsign) VALUES ('654321', 'AIC456')")
        cur.execute("SELECT id FROM aircraft WHERE icao_hex='654321'")
        ac_id2 = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO detection_sessions (aircraft_id, started_at, last_observed_at) VALUES (?, '2023-01-01', '2023-01-01')", 
            (ac_id2,)
        )
        conn.commit()
        
        collector._enrich_missing_routes()
        mock_resolve_route.assert_called_once_with('AIC456', '654321')
        
        # Ensure it didn't write NULLs to something that didn't change (still NULL)
        cur.execute("SELECT origin_iata FROM detection_sessions WHERE aircraft_id=?", (ac_id2,))
        self.assertIsNone(cur.fetchone()[0])
        
        # H. Existing route is not overwritten.
        # Query shouldn't pick it up if it has a route.
        cur.execute("UPDATE detection_sessions SET origin_iata='BOM', origin_icao='VABB', destination_iata='DEL', destination_icao='VIDP' WHERE aircraft_id=?", (ac_id2,))
        conn.commit()
        
        mock_resolve_route.reset_mock()
        collector._enrich_missing_routes()
        mock_resolve_route.assert_not_called()
        
        conn.close()
    @patch.object(enricher, 'resolve_route')
    def test_partial_route_is_enriched(self, mock_resolve_route):
        mock_resolve_route.return_value = {
            "origin_iata": "CCU",
            "origin_icao": "VECC",
            "origin_name": "Netaji Subhas Chandra Bose International Airport",
            "origin_city": "Kolkata",
            "origin_country": "India",
            "destination_iata": "DEL",
            "destination_icao": "VIDP",
            "destination_name": "Indira Gandhi International Airport",
            "destination_city": "New Delhi",
            "destination_country": "India"
        }

        conn = db.connect()
        cur = conn.cursor()

        # Session has an origin but is missing its destination.
        cur.execute(
            "INSERT INTO aircraft (icao_hex, callsign) VALUES ('789ABC', 'IGO789')"
        )
        cur.execute(
            "SELECT id FROM aircraft WHERE icao_hex='789ABC'"
        )
        ac_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO detection_sessions
                (aircraft_id, started_at, last_observed_at,
                 origin_iata, origin_icao)
            VALUES (?, '2023-01-01', '2023-01-01', 'CCU', 'VECC')
            """,
            (ac_id,)
        )
        conn.commit()

        cur.execute(
            "SELECT id FROM detection_sessions WHERE aircraft_id=?",
            (ac_id,)
        )
        session_id = cur.fetchone()[0]

        # Deferred enrichment should still find this incomplete session.
        collector._enrich_missing_routes()

        mock_resolve_route.assert_called_once_with('IGO789', '789ABC')

        # Existing origin must remain, while destination is filled.
        cur.execute(
            """
            SELECT origin_iata, origin_icao,
                   destination_iata, destination_icao
            FROM detection_sessions
            WHERE id=?
            """,
            (session_id,)
        )
        row = cur.fetchone()

        self.assertEqual(row['origin_iata'], 'CCU')
        self.assertEqual(row['origin_icao'], 'VECC')
        self.assertEqual(row['destination_iata'], 'DEL')
        self.assertEqual(row['destination_icao'], 'VIDP')

        conn.close()
if __name__ == '__main__':
    unittest.main()
