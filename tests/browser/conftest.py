"""Lease loopback test ports across parallel suites, including server subprocesses; share browsers."""

import contextlib
import fcntl
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest


class _Borrowed:
    """One test's handle on a shared browser: its contexts are its own, and close() closes only them."""

    def __init__(self, browser, opened):
        self._browser, self._opened, self._mine = browser, opened, []

    def new_context(self, **options):
        context = self._browser.new_context(**options)
        self._mine.append(context)
        self._opened.append(context)
        return context

    def new_page(self, **options):
        return self.new_context(**options).new_page()

    def close(self):
        for context in self._mine:
            context.close()

    def __getattr__(self, name):
        return getattr(self._browser, name)


class SharedPlaywright:
    """Stands in for sync_playwright()'s runner: one driver, one browser per (engine, launch options)."""

    def __init__(self, start):
        self._start, self._runner, self._browsers, self.opened = start, None, {}, []
        self.chromium = SimpleNamespace(launch=lambda **options: self._launch("chromium", options))
        self.webkit = SimpleNamespace(launch=lambda **options: self._launch("webkit", options))

    @property
    def devices(self):
        return self._playwright().devices

    def _playwright(self):
        if self._runner is None:
            self._runner = self._start().start()
        return self._runner

    def _launch(self, engine, options):
        key = (engine, repr(sorted(options.items())))
        browser = self._browsers.get(key)
        if browser is None or not browser.is_connected():
            browser = self._browsers[key] = getattr(self._playwright(), engine).launch(**options)
        return _Borrowed(browser, self.opened)

    def close_contexts(self, error):
        while self.opened:
            with contextlib.suppress(error):  # its browser crashed; the test that saw it already failed
                self.opened.pop().close()

    def stop(self, error):
        self.close_contexts(error)
        if self._runner is not None:
            self._runner.stop()


_shared = None


@pytest.fixture(autouse=True)
def shared_browsers(monkeypatch):
    # cjb: each browser start on macOS costs tccd, syspolicyd and XProtect checks, so this folder launches
    # one per engine and launch options instead of one per test. Each test still gets fresh contexts,
    # closed when it ends.
    global _shared
    try:
        from playwright import sync_api
    except ImportError:
        yield
        return
    if _shared is None:
        _shared = SharedPlaywright(sync_api.sync_playwright)
    shared = _shared
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: contextlib.nullcontext(shared))
    yield
    shared.close_contexts(sync_api.Error)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    # A live sync Playwright leaves its loop running, which breaks asyncio.run in tests outside this folder.
    # tests/browser is not a package, so a package-scoped fixture would only stop at session end.
    global _shared
    try:
        return (yield)
    finally:
        if _shared is not None and (nextitem is None or Path(__file__).parent not in nextitem.path.parents):
            from playwright.sync_api import Error

            _shared.stop(Error)
            _shared = None


@pytest.fixture(autouse=True)
def sandbox_ports(monkeypatch):
    # Keep the lease after a free-port probe closes, until its test's servers stop.
    leases = {}
    directory = Path("/tmp") / f"annotate-browser-ports-{os.getuid()}"
    directory.mkdir(exist_ok=True, mode=0o700)
    original_bind = socket.socket.bind
    original_popen = subprocess.Popen
    children = []

    def bind(sock, address):
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "localhost"):
            return original_bind(sock, address)
        requested = address[1]
        if requested and not 18700 <= requested < 18800:
            raise OSError(f"browser server port outside sandbox: {requested}")
        if requested in leases:
            return original_bind(sock, address)
        for port in ([requested] if requested else range(18700, 18800)):
            lease = (directory / str(port)).open("a")
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                original_bind(sock, (address[0], port))
            except OSError:
                lease.close()
                continue
            leases[port] = lease
            return None
        raise OSError("no sandbox browser port available in 18700-18799")

    monkeypatch.setattr(socket.socket, "bind", bind)

    def start(command, *args, **kwargs):
        if not isinstance(command, (list, tuple)) or "agent_annotate.sync_server" not in command:
            return original_popen(command, *args, **kwargs)
        port = int(command[command.index("--port") + 1])
        assert 18700 <= port < 18800, f"browser server port outside sandbox: {port}"
        process = original_popen(command, *args, **kwargs)
        children.append(process)
        directory = str(Path(command[command.index("--slug-dir") + 1]).resolve())
        prefix = command[command.index("--public-base-path") + 1] if "--public-base-path" in command else ""
        request = urllib.request.Request(f"http://127.0.0.1:{port}{prefix}/api/capabilities",
                                         headers={"X-Annotate-Identity": "1"})
        observed = None
        deadline = time.monotonic() + 15
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    observed = json.load(response)
                if observed.get("pid") == process.pid and observed.get("slug_dir") == directory:
                    return process
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        raise AssertionError(f"test server identity failed: pid={process.pid} page={directory} port={port} observed={observed}")

    monkeypatch.setattr(subprocess, "Popen", start)
    yield
    for process in children:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    for lease in leases.values():
        lease.close()
