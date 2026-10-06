"""Guarded public HTTP transport and source diagnostics (REQ-004–006)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
import httpcore
from httpcore._backends.auto import AutoBackend

class UnsafeSource(ValueError):
    pass


async def _public_addresses(host: str, port: int) -> list[str]:
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeSource("Host could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
        raise UnsafeSource("Local, private, or reserved network targets are not allowed.")
    return [record[4][0] for record in addresses]


async def validate_public_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeSource("Invalid source URL.") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise UnsafeSource("Only public HTTP(S) URLs without credentials are allowed.")
    if port and port not in {80, 443}:
        raise UnsafeSource("Only standard web ports are allowed.")
    await _public_addresses(parts.hostname, port or (443 if parts.scheme == "https" else 80))
    return url


class PublicNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve and pin a validated public IP at the actual TCP connection."""
    def __init__(self):
        self._backend = AutoBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = await _public_addresses(host, port)
        return await self._backend.connect_tcp(addresses[0], port, timeout=timeout,
                                               local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeSource("Unix sockets are not allowed.")

    async def sleep(self, seconds):
        await self._backend.sleep(seconds)


class PublicHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(), network_backend=PublicNetworkBackend(),
            max_connections=5, max_keepalive_connections=0)


async def safe_get(url: str, *, max_bytes: int = 256_000) -> tuple[int, str, bytes, dict[str, str]]:
    """Fetch a public page with explicit redirect checks and bounded body."""
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False,
                                transport=PublicHTTPTransport(),
                                headers={"User-Agent": "UrlMediaTracker/2.0"}) as client:
        current = url
        for _ in range(5):
            await validate_public_url(current)
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return response.status_code, current, b"", dict(response.headers)
                    current = urljoin(current, location)
                    continue
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    remaining = max_bytes - len(body)
                    if remaining <= 0:
                        break
                    body.extend(chunk[:remaining])
                return response.status_code, str(response.url), bytes(body), dict(response.headers)
    raise UnsafeSource("Too many redirects.")


def _challenge(status_code: int, body: bytes, headers: dict[str, str]) -> bool:
    lower = body[:32_768].lower()
    return (b"cf-chl" in lower or b"challenge-platform" in lower or
            b"checking your browser" in lower or
            (status_code in {403, 503} and "cf-ray" in headers))


async def diagnose_url(url: str) -> dict:
    try:
        status_code, final_url, body, headers = await safe_get(url, max_bytes=65_536)
        if _challenge(status_code, body, headers):
            state = "LIKELY_CLOUDFLARE"
        elif 200 <= status_code < 300:
            state = "REACHABLE"
        elif status_code >= 400:
            state = "HTTP_ERROR"
        else:
            state = "INCONCLUSIVE"
        return {"state": state, "status_code": status_code, "final_url": final_url}
    except (httpx.TimeoutException, asyncio.TimeoutError):
        return {"state": "TIMEOUT", "status_code": None, "final_url": None}
    except UnsafeSource as exc:
        return {"state": "REJECTED", "status_code": None, "final_url": None,
                "detail": str(exc)[:200]}
    except httpx.RequestError as exc:
        return {"state": "INCONCLUSIVE", "status_code": None, "final_url": None,
                "detail": str(exc)[:200]}
