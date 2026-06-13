"""Mock org-systems endpoint — proves CarbonShift's live data path.

This stands in for the organization's real travel booking app and compute scheduler.
Run it, then point CarbonShift at it:

    python scripts/mock_org_api.py        # serves on http://127.0.0.1:8077

    # in .env (or your shell):
    TRAVEL_APP_API=http://127.0.0.1:8077/travel/bookings
    JOBS_API=http://127.0.0.1:8077/scheduler/jobs

CarbonShift will then pull trips and jobs from here instead of the bundled demo data.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

TRAVEL_BOOKINGS = {
    "bookings": [
        {"name": "Board meeting, Edinburgh", "distance_km": 530.0, "mode": "car_petrol",
         "passengers": 1, "round_trip": True, "essential": False},
        {"name": "Factory commissioning, Leeds", "distance_km": 270.0, "mode": "car_petrol",
         "passengers": 2, "round_trip": True, "essential": True},
        {"name": "Regulator hearing, London", "distance_km": 180.0, "mode": "car_petrol",
         "passengers": 1, "round_trip": True, "essential": True},
        {"name": "Team offsite, Bristol", "distance_km": 95.0, "mode": "car_petrol",
         "passengers": 4, "round_trip": True, "essential": False},
        {"name": "Vendor demo (remote-friendly)", "distance_km": 240.0, "mode": "car_petrol",
         "passengers": 1, "round_trip": True, "essential": False},
    ]
}

SCHEDULER_JOBS = {
    "jobs": [
        {"name": "Recommender retrain (GPU)", "power_kw": 160.0, "duration_hours": 5.0,
         "deadline_hours": 16, "flexible": True},
        {"name": "Genomics batch pipeline", "power_kw": 80.0, "duration_hours": 3.0,
         "deadline_hours": 11, "flexible": True},
        {"name": "Depot EV charging", "power_kw": 320.0, "duration_hours": 6.0,
         "deadline_hours": 13, "flexible": True},
        {"name": "Nightly analytics ETL", "power_kw": 40.0, "duration_hours": 2.0,
         "deadline_hours": 9, "flexible": True},
        {"name": "Realtime fraud API (always on)", "power_kw": 18.0, "duration_hours": 1.0,
         "deadline_hours": 1, "flexible": False},
    ]
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path.startswith("/travel/bookings"):
            body = TRAVEL_BOOKINGS
        elif self.path.startswith("/scheduler/jobs"):
            body = SCHEDULER_JOBS
        else:
            self.send_error(404, "Not found")
            return
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep the console quiet
        pass


def main() -> None:
    server = HTTPServer(("127.0.0.1", 8077), _Handler)
    print("Mock org API on http://127.0.0.1:8077")
    print("  GET /travel/bookings")
    print("  GET /scheduler/jobs")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
