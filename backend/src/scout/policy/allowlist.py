"""Domain allowlist and SSRF checks.

The policy fails closed: an unparseable URL, a missing host, a private IP, a
metadata address, or an unresolvable hostname is rejected. Tests can disable
DNS resolution when they use synthetic hostnames.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class AllowlistVerdict:
    allowed: bool
    reason: str = ""
    host: str = ""


def host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    host = host.lower().strip(".")
    for allowed in allowed_hosts:
        allowed = allowed.lower().strip(".")
        if host == allowed or host.endswith(f".{allowed}"):
            return True
    return False


def is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_reserved,
            address.is_multicast,
            address.is_unspecified,
        )
    )


def _default_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0] not in addresses:
            addresses.append(str(sockaddr[0]))
    return addresses


class AllowlistPolicy:
    def __init__(
        self,
        allowed_hosts: Iterable[str],
        *,
        verify_dns: bool = True,
        allow_http_local: bool = False,
        allowed_ports: Iterable[int] = (80, 443),
        resolver: Callable[[str, int], list[str]] = _default_resolver,
    ) -> None:
        self.allowed_hosts = tuple(host.lower().strip(".") for host in allowed_hosts)
        self.verify_dns = verify_dns
        self.allow_http_local = allow_http_local
        self.allowed_ports = set(allowed_ports)
        self._resolver = resolver

    def check(self, url: str) -> AllowlistVerdict:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return AllowlistVerdict(False, f"unsupported scheme: {parsed.scheme}")
        if parsed.username or parsed.password:
            return AllowlistVerdict(False, "credentials in URL are not allowed")
        host = (parsed.hostname or "").lower().strip(".")
        if not host:
            return AllowlistVerdict(False, "missing host")

        is_local = host in LOCAL_HOSTS
        if parsed.scheme == "http" and not (self.allow_http_local and is_local):
            return AllowlistVerdict(False, "http is only allowed for localhost in dev", host)
        if not host_allowed(host, self.allowed_hosts):
            return AllowlistVerdict(False, f"host is not in the allowlist: {host}", host)

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in self.allowed_ports and not (self.allow_http_local and is_local):
            return AllowlistVerdict(False, f"port is not allowed: {port}", host)

        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            if is_blocked_ip(host):
                return AllowlistVerdict(False, f"private or reserved IP: {host}", host)
            return AllowlistVerdict(True, "", host)

        if self.verify_dns:
            try:
                addresses = self._resolver(host, port)
            except OSError as exc:
                return AllowlistVerdict(False, f"DNS resolution failed: {exc}", host)
            if not addresses:
                return AllowlistVerdict(False, "DNS returned no addresses", host)
            for address in addresses:
                if is_blocked_ip(address):
                    return AllowlistVerdict(
                        False,
                        f"host resolves to a private or reserved IP: {address}",
                        host,
                    )
        return AllowlistVerdict(True, "", host)
