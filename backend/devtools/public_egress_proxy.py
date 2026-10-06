"""Small public-only HTTP CONNECT proxy for the local FlareSolverr preview.

The browser runs on an internal Docker network. This dual-homed proxy is its
only path out and pins each outbound connection to a DNS-validated public IP.
It is deliberately limited to ordinary web ports and has no host-published port.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


def choose_public_address(records) -> str:
    addresses = [record[4][0] for record in records]
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Non-public destination")
    return next((ip for ip in addresses if ":" not in ip), addresses[0])


async def public_address(host: str, port: int) -> str:
    records = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM)
    return choose_public_address(records)


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    upstream = None
    try:
        request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = request.decode("iso-8859-1").split("\r\n")
        method, target, version = lines[0].split(" ", 2)
        if version not in {"HTTP/1.0", "HTTP/1.1"}:
            raise ValueError("Invalid request version")
        if method == "CONNECT":
            parsed = urlsplit("//" + target)
            if not parsed.hostname or parsed.port != 443 or parsed.username or parsed.password:
                raise ValueError("CONNECT requires a public HTTPS host")
            host, port = parsed.hostname, 443
            initial = b""
        elif method in {"GET", "HEAD"}:
            parsed = urlsplit(target)
            if parsed.scheme != "http" or not parsed.hostname or parsed.port not in {None, 80} or parsed.username or parsed.password:
                raise ValueError("Only public HTTP web requests are allowed")
            host, port = parsed.hostname, 80
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            safe_headers = [line for line in lines[1:] if line and not line.lower().startswith(
                ("proxy-authorization:", "proxy-connection:"))]
            initial = (f"{method} {path} {version}\r\n" + "\r\n".join(safe_headers) +
                       "\r\nConnection: close\r\n\r\n").encode("iso-8859-1")
        else:
            raise ValueError("Unsupported proxy method")

        ip = await asyncio.wait_for(public_address(host, port), 10)
        upstream_reader, upstream = await asyncio.wait_for(asyncio.open_connection(ip, port), 10)
        if method == "CONNECT":
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        else:
            upstream.write(initial)
            await upstream.drain()
        await writer.drain()
        tasks = [asyncio.create_task(relay(reader, upstream)),
                 asyncio.create_task(relay(upstream_reader, writer))]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
    except (ValueError, OSError, asyncio.TimeoutError, asyncio.LimitOverrunError):
        writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        try:
            await writer.drain()
        except ConnectionError:
            pass
    finally:
        if upstream:
            upstream.close()
        writer.close()


async def forward_api(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Expose only FlareSolverr's API to the development host via this gateway."""
    upstream = None
    try:
        upstream_reader, upstream = await asyncio.open_connection("flaresolverr", 8191)
        tasks = [asyncio.create_task(relay(reader, upstream)),
                 asyncio.create_task(relay(upstream_reader, writer))]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
    finally:
        if upstream:
            upstream.close()
        writer.close()


async def main() -> None:
    proxy = await asyncio.start_server(handle, "0.0.0.0", 8118, limit=16384)
    api = await asyncio.start_server(forward_api, "0.0.0.0", 8191)
    async with proxy, api:
        await asyncio.gather(proxy.serve_forever(), api.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
