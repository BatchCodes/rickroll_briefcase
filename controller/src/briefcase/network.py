"""Wi-Fi mode: the briefcase access point, or a client of a known network.

Rules:

- The Pi starts in hotspot mode at each boot. NetworkManager does this,
  because the hotspot connection has the highest autoconnect priority.
- Client mode is temporary. If no known network connects within the fallback
  time, or the connection drops for that time, the hotspot starts again.
  Thus a user cannot lose access to the briefcase.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Protocol

from briefcase.config import AppConfig

LOGGER = logging.getLogger(__name__)

POLL_SEC = 5.0
SWITCH_DELAY_SEC = 1.5
COMMAND_TIMEOUT_SEC = 45.0
CONNECT_WAIT_SEC = 20


class NetworkError(RuntimeError):
    pass


class Mode(StrEnum):
    HOTSPOT = "hotspot"
    CLIENT = "client"
    SWITCHING = "switching"
    OFFLINE = "offline"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ActiveState:
    hotspot_active: bool
    client_connection: str | None
    address: str | None


@dataclass
class NetworkStatus:
    available: bool
    mode: Mode
    wanted_mode: Mode
    connection: str | None = None
    address: str | None = None
    hostname: str | None = None
    hotspot_name: str | None = None
    known_networks: list[str] = field(default_factory=list)
    fallback_sec: float = 0
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class NetworkBackend(Protocol):
    async def active(self) -> ActiveState: ...

    async def known_networks(self) -> list[str]: ...

    async def hotspot_ssid(self) -> str | None: ...

    async def hostname(self) -> str | None: ...

    async def start_hotspot(self) -> None: ...

    async def stop_hotspot(self) -> None: ...

    async def connect_known(self) -> str | None: ...

    async def add_network(self, ssid: str, password: str) -> None: ...

    async def forget_network(self, name: str) -> None: ...


def split_terse(line: str) -> list[str]:
    """Split one line of ``nmcli --terse`` output. ``\\:`` is a literal colon."""
    fields: list[str] = []
    current = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


class NmcliBackend:
    """Control the host NetworkManager through ``nmcli`` and the system D-Bus."""

    def __init__(self, hotspot_connection: str, interface: str) -> None:
        self._hotspot = hotspot_connection
        self._interface = interface

    async def _nmcli(self, *args: str, check: bool = True) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "nmcli",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise NetworkError(f"Cannot run nmcli: {error}") from error
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), COMMAND_TIMEOUT_SEC
            )
        except TimeoutError as error:
            process.kill()
            raise NetworkError(f"nmcli {' '.join(args)} did not finish") from error
        if check and process.returncode != 0:
            message = stderr.decode(errors="replace").strip()
            raise NetworkError(message or f"nmcli exited with {process.returncode}")
        return stdout.decode(errors="replace")

    async def _wifi_connections(self) -> list[tuple[str, int]]:
        output = await self._nmcli(
            "--terse",
            "--fields",
            "NAME,TYPE,AUTOCONNECT-PRIORITY",
            "connection",
            "show",
        )
        connections = []
        for line in output.splitlines():
            parts = split_terse(line)
            if len(parts) < 3 or parts[1] != "802-11-wireless":
                continue
            if parts[0] == self._hotspot:
                continue
            try:
                priority = int(parts[2])
            except ValueError:
                priority = 0
            connections.append((parts[0], priority))
        return connections

    async def active(self) -> ActiveState:
        output = await self._nmcli(
            "--terse",
            "--fields",
            "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS",
            "device",
            "show",
            self._interface,
        )
        values: dict[str, str] = {}
        for line in output.splitlines():
            key, _, value = line.partition(":")
            values.setdefault(key, value)
        connected = values.get("GENERAL.STATE", "").startswith("100")
        connection = values.get("GENERAL.CONNECTION") or None
        address = (values.get("IP4.ADDRESS[1]") or "").split("/")[0] or None
        if not connected or connection is None:
            return ActiveState(False, None, None)
        if connection == self._hotspot:
            return ActiveState(True, None, address)
        return ActiveState(False, connection, address)

    async def known_networks(self) -> list[str]:
        return sorted(name for name, _ in await self._wifi_connections())

    async def hotspot_ssid(self) -> str | None:
        output = await self._nmcli(
            "--get-values",
            "802-11-wireless.ssid",
            "connection",
            "show",
            self._hotspot,
            check=False,
        )
        return output.strip() or None

    async def hostname(self) -> str | None:
        output = await self._nmcli("general", "hostname", check=False)
        return output.strip() or None

    async def start_hotspot(self) -> None:
        await self._nmcli("connection", "up", self._hotspot)

    async def stop_hotspot(self) -> None:
        await self._nmcli("connection", "down", self._hotspot, check=False)

    async def connect_known(self) -> str | None:
        await self._nmcli(
            "device", "wifi", "rescan", "ifname", self._interface, check=False
        )
        await asyncio.sleep(3)
        connections = sorted(
            await self._wifi_connections(), key=lambda item: item[1], reverse=True
        )
        for name, _ in connections:
            LOGGER.info("Trying the Wi-Fi network %s", name)
            try:
                await self._nmcli(
                    "--wait",
                    str(CONNECT_WAIT_SEC),
                    "connection",
                    "up",
                    name,
                    "ifname",
                    self._interface,
                )
            except NetworkError as error:
                LOGGER.info("Cannot connect to %s: %s", name, error)
                continue
            return name
        return None

    async def add_network(self, ssid: str, password: str) -> None:
        if ssid in await self.known_networks():
            await self._nmcli("connection", "delete", ssid)
        args = [
            "connection",
            "add",
            "type",
            "wifi",
            "ifname",
            self._interface,
            "con-name",
            ssid,
            "ssid",
            ssid,
            "connection.autoconnect-priority",
            "0",
        ]
        if password:
            args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
        await self._nmcli(*args)

    async def forget_network(self, name: str) -> None:
        if name not in await self.known_networks():
            raise NetworkError(f"The network {name!r} is not known.")
        await self._nmcli("connection", "delete", name)


class SimulatedBackend:
    """A network for a laptop and for tests. It has no effect on the host."""

    def __init__(self, reachable: set[str] | None = None) -> None:
        self.hotspot_active = True
        self.client: str | None = None
        self.networks: dict[str, str] = {"HomeWifi": "secret-password"}
        self.reachable = reachable if reachable is not None else {"HomeWifi"}

    async def active(self) -> ActiveState:
        if self.hotspot_active:
            return ActiveState(True, None, "10.42.0.1")
        if self.client:
            return ActiveState(False, self.client, "192.168.1.50")
        return ActiveState(False, None, None)

    async def known_networks(self) -> list[str]:
        return sorted(self.networks)

    async def hotspot_ssid(self) -> str | None:
        return "RICKROLL-BRIEFCASE"

    async def hostname(self) -> str | None:
        return "rickroll-briefcase"

    async def start_hotspot(self) -> None:
        self.client = None
        self.hotspot_active = True

    async def stop_hotspot(self) -> None:
        self.hotspot_active = False

    async def connect_known(self) -> str | None:
        for name in sorted(self.networks):
            if name in self.reachable:
                self.client = name
                return name
        return None

    async def add_network(self, ssid: str, password: str) -> None:
        self.networks[ssid] = password

    async def forget_network(self, name: str) -> None:
        if name not in self.networks:
            raise NetworkError(f"The network {name!r} is not known.")
        del self.networks[name]


def validate_new_network(ssid: str, password: str) -> None:
    if not 1 <= len(ssid.encode()) <= 32:
        raise NetworkError("The network name must have 1 to 32 characters.")
    if password and not 8 <= len(password) <= 63:
        raise NetworkError(
            "The password must have 8 to 63 characters, or be empty for an "
            "open network."
        )


class NetworkController:
    """The Wi-Fi mode, with the automatic fallback to the hotspot."""

    def __init__(self, backend: NetworkBackend | None, fallback_sec: float) -> None:
        self._backend = backend
        self._fallback_sec = fallback_sec
        self._wanted = Mode.HOTSPOT
        self._switching = False
        self._message: str | None = None
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._offline_since: float | None = None

    @property
    def available(self) -> bool:
        return self._backend is not None

    def start(self) -> None:
        if self._backend is not None and self._task is None:
            self._task = asyncio.create_task(self._watch(), name="network-watch")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def status(self) -> NetworkStatus:
        if self._backend is None:
            return NetworkStatus(
                available=False, mode=Mode.UNAVAILABLE, wanted_mode=Mode.UNAVAILABLE
            )
        try:
            active = await self._backend.active()
            known = await self._backend.known_networks()
            hostname = await self._backend.hostname()
            hotspot_name = await self._backend.hotspot_ssid()
        except NetworkError as error:
            return NetworkStatus(
                available=True,
                mode=Mode.UNAVAILABLE,
                wanted_mode=self._wanted,
                message=str(error),
            )
        if self._switching:
            mode = Mode.SWITCHING
        elif active.hotspot_active:
            mode = Mode.HOTSPOT
        elif active.client_connection:
            mode = Mode.CLIENT
        else:
            mode = Mode.OFFLINE
        return NetworkStatus(
            available=True,
            mode=mode,
            wanted_mode=self._wanted,
            connection=active.client_connection
            or (hotspot_name if active.hotspot_active else None),
            address=active.address,
            hostname=hostname,
            hotspot_name=hotspot_name,
            known_networks=known,
            fallback_sec=self._fallback_sec,
            message=self._message,
        )

    def request_mode(self, mode: Mode) -> None:
        """Change the mode after a short delay, so the HTTP reply arrives first."""
        self._require_backend()
        if mode not in (Mode.HOTSPOT, Mode.CLIENT):
            raise NetworkError(f"The mode {mode} is not valid.")
        self._wanted = mode
        self._switching = True
        asyncio.get_running_loop().call_later(
            SWITCH_DELAY_SEC, lambda: asyncio.ensure_future(self._switch(mode))
        )

    async def add_network(self, ssid: str, password: str) -> None:
        validate_new_network(ssid, password)
        async with self._lock:
            await self._require_backend().add_network(ssid, password)

    async def forget_network(self, name: str) -> None:
        async with self._lock:
            await self._require_backend().forget_network(name)

    def _require_backend(self) -> NetworkBackend:
        if self._backend is None:
            raise NetworkError("Wi-Fi control is not available on this system.")
        return self._backend

    async def _switch(self, mode: Mode) -> None:
        backend = self._require_backend()
        async with self._lock:
            try:
                if mode is Mode.CLIENT:
                    await self._to_client(backend)
                else:
                    await self._to_hotspot(backend, "Hotspot mode is on.")
            except NetworkError as error:
                LOGGER.error("The Wi-Fi mode change failed: %s", error)
                self._message = str(error)
                await self._to_hotspot(backend, f"The change failed: {error}")
            finally:
                self._switching = False

    async def _to_client(self, backend: NetworkBackend) -> None:
        LOGGER.info("Changing to Wi-Fi client mode")
        await backend.stop_hotspot()
        try:
            name = await asyncio.wait_for(backend.connect_known(), self._fallback_sec)
        except TimeoutError:
            name = None
        if name is None:
            await self._to_hotspot(
                backend, "No known Wi-Fi network is in range. Hotspot mode is on."
            )
            return
        self._offline_since = None
        self._message = f"Connected to {name}."
        LOGGER.info("Connected to the Wi-Fi network %s", name)

    async def _to_hotspot(self, backend: NetworkBackend, message: str) -> None:
        LOGGER.info("Changing to hotspot mode")
        self._wanted = Mode.HOTSPOT
        self._offline_since = None
        try:
            await backend.start_hotspot()
        except NetworkError as error:
            LOGGER.error("Cannot start the hotspot: %s", error)
            self._message = f"Cannot start the hotspot: {error}"
            return
        self._message = message

    async def check_fallback(self) -> None:
        """Start the hotspot if client mode has had no connection for too long."""
        backend = self._backend
        if backend is None or self._switching or self._wanted is not Mode.CLIENT:
            return
        async with self._lock:
            try:
                active = await backend.active()
            except NetworkError as error:
                LOGGER.warning("Cannot read the Wi-Fi state: %s", error)
                return
            now = asyncio.get_running_loop().time()
            if active.client_connection:
                self._offline_since = None
                return
            if self._offline_since is None:
                self._offline_since = now
                return
            if now - self._offline_since >= self._fallback_sec:
                LOGGER.warning(
                    "No Wi-Fi connection for %.0f s. Starting the hotspot.",
                    self._fallback_sec,
                )
                await self._to_hotspot(
                    backend, "The Wi-Fi connection was lost. Hotspot mode is on."
                )

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(POLL_SEC)
            try:
                await self.check_fallback()
            except Exception:
                LOGGER.exception("The Wi-Fi fallback check failed")


def create_network(config: AppConfig) -> NetworkController:
    backend: NetworkBackend | None
    if config.network_backend == "nmcli":
        backend = NmcliBackend(config.hotspot_connection, config.wifi_interface)
    elif config.network_backend == "simulated":
        backend = SimulatedBackend()
    else:
        backend = None
    return NetworkController(backend, config.network_fallback_sec)
