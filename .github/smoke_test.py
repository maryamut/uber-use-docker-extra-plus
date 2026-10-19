import json
import subprocess
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "http://localhost"
PROJECT = "georide-ci"


def request(path, payload=None, expected=200):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=10) as response:
        assert response.status == expected, response.status
        return json.load(response)


def wait_for_api():
    for _ in range(60):
        try:
            request("/trip/2147483647")
        except HTTPError as error:
            if error.code == 404:
                data = json.loads(error.read())
                if data.get("error") == "Trip not found":
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise RuntimeError("API did not become ready")


wait_for_api()
suffix = uuid.uuid4().hex[:12]
driver_name = "CI-Driver-" + suffix

rider = request(
    "/register",
    {"name": "CI-Rider-" + suffix, "type": "rider"},
    expected=201,
)
driver = request(
    "/register",
    {"name": driver_name, "type": "driver"},
    expected=201,
)

location_code = (
    "import requests; "
    "r = requests.post("
    "'http://location:8081/update-location', "
    f"json=dict(driver_id={driver_name!r}, "
    "latitude=34.0522, longitude=-118.2437), timeout=10); "
    "r.raise_for_status(); print(r.text)"
)

subprocess.run(
    [
        "docker", "compose", "-p", PROJECT,
        "exec", "-T", "matcher", "python", "-c", location_code,
    ],
    check=True,
    timeout=30,
)

trip = request(
    "/request_ride",
    {
        "rider_id": rider["user_id"],
        "latitude": 34.0522,
        "longitude": -118.2437,
    },
    expected=202,
)

for _ in range(60):
    result = request(f"/trip/{trip['trip_id']}")
    if result["status"] == "assigned":
        assert result["driver_id"] == driver["user_id"], result
        print("PASS: registration, location update and driver assignment")
        break
    if result["status"] == "cancelled":
        raise AssertionError(f"Trip unexpectedly cancelled: {result}")
    time.sleep(2)
else:
    raise AssertionError("Driver assignment timed out")
