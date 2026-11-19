from http import HTTPStatus
from ipaddress import IPv4Address

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.status import WS_1008_POLICY_VIOLATION
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from markcom.own_origin import InvalidPortError, OwnOriginOnly, local_url

OWN = "http://127.0.0.1:8765"
LOCALHOST = "http://localhost:8765"
# Its websockets ignore base_url, so they take the whole address.
OWN_WEBSOCKET = "ws://127.0.0.1:8765/ws"


def page(_request):
    return PlainTextResponse("page")


async def greet(websocket):
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()


def guarded(host="127.0.0.1", port=8765):
    routes = [Route("/", page), WebSocketRoute("/ws", greet)]
    return OwnOriginOnly(Starlette(routes=routes), IPv4Address(host), port)


def test_local_url_is_the_server_address():
    assert str(local_url(IPv4Address("127.0.0.1"), 8765)) == "http://127.0.0.1:8765/"


@pytest.mark.parametrize(
    ("base", "headers", "status"),
    [
        (OWN, {}, HTTPStatus.OK),
        (OWN, {"Origin": OWN}, HTTPStatus.OK),
        (LOCALHOST, {"Origin": LOCALHOST}, HTTPStatus.OK),
        (OWN, {"Origin": "https://evil.example"}, HTTPStatus.FORBIDDEN),
        ("http://evil.example", {}, HTTPStatus.FORBIDDEN),
        ("http://127.0.0.1:9999", {}, HTTPStatus.FORBIDDEN),
    ],
)
def test_only_the_own_host_and_origin_reach_a_page(base, headers, status):
    with TestClient(guarded(), base_url=base) as browser:
        assert browser.get("/", headers=headers).status_code == status


def test_localhost_is_refused_when_not_serving_on_loopback():
    with TestClient(guarded("192.168.1.5"), base_url=LOCALHOST) as browser:
        assert browser.get("/").status_code == HTTPStatus.FORBIDDEN


def test_a_websocket_from_the_own_origin_connects():
    with (
        TestClient(guarded(), base_url=OWN) as browser,
        browser.websocket_connect(OWN_WEBSOCKET, headers={"Origin": OWN}) as websocket,
    ):
        assert websocket.receive_text() == "hello"


def test_a_websocket_from_another_origin_is_closed_before_it_connects():
    with TestClient(guarded(), base_url=OWN) as browser:
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            browser.websocket_connect(OWN_WEBSOCKET, headers={"Origin": "https://evil.example"}),
        ):
            pass
        assert refused.value.code == WS_1008_POLICY_VIOLATION


@pytest.mark.parametrize("headers", [{}, {"Origin": "http://127.0.0.1"}])
def test_on_the_default_port_a_host_without_the_port_reaches_a_page(headers):
    # Browsers leave port 80 out of Host and Origin.
    with TestClient(guarded(port=80), base_url="http://127.0.0.1") as browser:
        assert browser.get("/", headers=headers).status_code == HTTPStatus.OK


def test_port_zero_is_refused_as_it_is_never_the_real_port():
    with pytest.raises(InvalidPortError):
        guarded(port=0)
