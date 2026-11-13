# ruff: noqa: E402 -- import ordering is intentional for resource/network guards.
"""Test-only egress observation and prevention; mounted, never shipped in the image."""

import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

OBS = Path("/observations")


def observe(event, **values):
    if OBS.is_dir():
        with (OBS / "network_attempts.jsonl").open("a") as file:
            file.write(
                json.dumps(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "pid": os.getpid(),
                        "event": event,
                        **values,
                    }
                )
                + "\n"
            )


def local(host):
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
        observe("blocked_socket_connect")
        raise RuntimeError("External network forbidden by smoke harness")
    return _connect(sock, address)


def connect_ex(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not local(address[0]):
        observe("blocked_socket_connect_ex")
        raise RuntimeError("External network forbidden by smoke harness")
    return _connect_ex(sock, address)


def getaddrinfo(host, *args, **kwargs):
    if not local(host):
        observe("blocked_dns")
        raise RuntimeError("External DNS forbidden by smoke harness")
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo

import httpx

_sync_send, _async_send = httpx.Client.send, httpx.AsyncClient.send


def send(client, request, *args, **kwargs):
    if not local(request.url.host):
        observe("blocked_httpx_send")
        raise RuntimeError("External HTTP forbidden by smoke harness")
    return _sync_send(client, request, *args, **kwargs)


async def asend(client, request, *args, **kwargs):
    if not local(request.url.host):
        observe("blocked_httpx_async_send")
        raise RuntimeError("External HTTP forbidden by smoke harness")
    return await _async_send(client, request, *args, **kwargs)


httpx.Client.send, httpx.AsyncClient.send = send, asend

if OBS.is_dir():
    with (OBS / "guard_loaded.jsonl").open("a") as file:
        file.write(json.dumps({"pid": os.getpid(), "guard_loaded": True}) + "\n")
