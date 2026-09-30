import asyncio

import pytest

import briefcase.network as network_module
from briefcase.network import (
    Mode,
    NetworkController,
    NetworkError,
    NmcliBackend,
    SimulatedBackend,
    split_terse,
    validate_new_network,
)


@pytest.fixture(autouse=True)
def no_switch_delay(monkeypatch):
    monkeypatch.setattr(network_module, "SWITCH_DELAY_SEC", 0)


async def wait_until_switched(controller: NetworkController) -> None:
    for _ in range(100):
        await asyncio.sleep(0.01)
        if not controller._switching:
            return
    raise AssertionError("the mode change did not finish")


def test_split_terse_handles_escaped_colons():
    assert split_terse(r"My\:Net:802-11-wireless:5") == [
        "My:Net",
        "802-11-wireless",
        "5",
    ]


@pytest.mark.parametrize(
    ("ssid", "password"),
    [("", "password1"), ("x" * 33, "password1"), ("Home", "short")],
)
def test_validate_new_network_rejects_bad_values(ssid, password):
    with pytest.raises(NetworkError):
        validate_new_network(ssid, password)


def test_validate_new_network_accepts_open_network():
    validate_new_network("Cafe", "")


async def test_starts_in_hotspot_mode():
    controller = NetworkController(SimulatedBackend(), 60)
    status = await controller.status()
    assert status.mode is Mode.HOTSPOT
    assert status.address == "10.42.0.1"
    assert status.known_networks == ["HomeWifi"]


async def test_client_mode_connects_to_known_network():
    backend = SimulatedBackend()
    controller = NetworkController(backend, 60)
    controller.request_mode(Mode.CLIENT)
    assert (await controller.status()).mode is Mode.SWITCHING

    await wait_until_switched(controller)
    status = await controller.status()
    assert status.mode is Mode.CLIENT
    assert status.connection == "HomeWifi"
    assert status.hostname == "rickroll-briefcase"


async def test_client_mode_without_network_in_range_returns_to_hotspot():
    backend = SimulatedBackend(reachable=set())
    controller = NetworkController(backend, 60)
    controller.request_mode(Mode.CLIENT)
    await wait_until_switched(controller)

    status = await controller.status()
    assert status.mode is Mode.HOTSPOT
    assert "No known Wi-Fi network" in status.message


async def test_lost_connection_falls_back_to_hotspot():
    backend = SimulatedBackend()
    controller = NetworkController(backend, 0.05)
    controller.request_mode(Mode.CLIENT)
    await wait_until_switched(controller)
    assert backend.client == "HomeWifi"

    backend.client = None
    await controller.check_fallback()
    assert not backend.hotspot_active
    await asyncio.sleep(0.06)
    await controller.check_fallback()
    assert backend.hotspot_active
    assert (await controller.status()).mode is Mode.HOTSPOT


async def test_back_to_hotspot():
    backend = SimulatedBackend()
    controller = NetworkController(backend, 60)
    controller.request_mode(Mode.CLIENT)
    await wait_until_switched(controller)
    controller.request_mode(Mode.HOTSPOT)
    await wait_until_switched(controller)
    assert backend.hotspot_active


async def test_add_and_forget_network():
    backend = SimulatedBackend()
    controller = NetworkController(backend, 60)
    await controller.add_network("Office", "office-password")
    assert "Office" in (await controller.status()).known_networks
    await controller.forget_network("Office")
    assert "Office" not in backend.networks
    with pytest.raises(NetworkError):
        await controller.forget_network("Office")


async def test_unavailable_without_backend():
    controller = NetworkController(None, 60)
    assert (await controller.status()).mode is Mode.UNAVAILABLE
    with pytest.raises(NetworkError):
        controller.request_mode(Mode.CLIENT)


class RecordingNmcli(NmcliBackend):
    def __init__(self, outputs):
        super().__init__("briefcase-hotspot", "wlan0")
        self.outputs = outputs
        self.calls = []

    async def _nmcli(self, *args, check=True):
        self.calls.append(args)
        for key, output in self.outputs.items():
            if key in args:
                if isinstance(output, Exception):
                    raise output
                return output
        return ""


async def test_nmcli_active_hotspot():
    backend = RecordingNmcli(
        {
            "device": "GENERAL.STATE:100 (connected)\n"
            "GENERAL.CONNECTION:briefcase-hotspot\n"
            "IP4.ADDRESS[1]:10.42.0.1/24\n"
        }
    )
    state = await backend.active()
    assert state.hotspot_active
    assert state.address == "10.42.0.1"


async def test_nmcli_active_client():
    backend = RecordingNmcli(
        {
            "device": "GENERAL.STATE:100 (connected)\n"
            "GENERAL.CONNECTION:HomeWifi\n"
            "IP4.ADDRESS[1]:192.168.1.20/24\n"
        }
    )
    state = await backend.active()
    assert state.client_connection == "HomeWifi"
    assert not state.hotspot_active


async def test_nmcli_known_networks_skip_hotspot_and_wired():
    backend = RecordingNmcli(
        {
            "NAME,TYPE,AUTOCONNECT-PRIORITY": "briefcase-hotspot:802-11-wireless:100\n"
            "HomeWifi:802-11-wireless:0\n"
            "Wired connection 1:802-3-ethernet:-999\n"
        }
    )
    assert await backend.known_networks() == ["HomeWifi"]


async def test_nmcli_add_network_uses_wpa_psk():
    backend = RecordingNmcli({"NAME,TYPE,AUTOCONNECT-PRIORITY": ""})
    await backend.add_network("Office", "office-password")
    add_call = backend.calls[-1]
    assert add_call[:2] == ("connection", "add")
    assert "wpa-psk" in add_call
    assert "office-password" in add_call
