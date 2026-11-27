"""Lease loopback test ports across parallel suites, including server subprocesses; share browsers."""

import asyncio
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

    def __init__(self, shared, key):
        self._shared, self._key, self._mine = shared, key, []

    def _open(self, make):
        made = self._shared.open(self._key, make)
        self._mine.append(made.context if hasattr(made, "context") else made)
        return made

    def new_context(self, **options):
        return self._open(lambda browser: browser.new_context(**options))

    def new_page(self, **options):
        # The real new_page, so page.close() still closes the context it made.
        return self._open(lambda browser: browser.new_page(**options))

    def close(self):
        for context in self._mine:
            context.close()

    def __getattr__(self, name):
        return getattr(self._shared.browser(self._key), name)


class SharedPlaywright:
    """Stands in for sync_playwright()'s runner: one driver, one browser per (engine, launch options)."""

    def __init__(self, start, error):
        self._start, self._error, self._runner, self._browsers, self._options = start, error, None, {}, {}
        self.opened = []
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
        self._options[key] = (engine, options)
        self.browser(key)  # launch now, so a missing WebKit still raises here and its tests skip
        return _Borrowed(self, key)

    def browser(self, key):
        browser = self._browsers.get(key)
        if browser is None or not browser.is_connected():
            engine, options = self._options[key]
            browser = self._browsers[key] = getattr(self._playwright(), engine).launch(**options)
        return browser

    def open(self, key, make):
        try:
            made = make(self.browser(key))
        except self._error:
            if self._browsers[key].is_connected():
                raise
            made = make(self.browser(key))  # it crashed while idle, before Playwright noticed: relaunch once
        self.opened.append(made.context if hasattr(made, "context") else made)
        return made

    def close_contexts(self):
        # Close every context the test left open, then fail that test with the first error.
        contexts = self.opened[:]
        self.opened.clear()
        failures = []
        for context in contexts:
            try:
                context.close()
            except Exception as failure:
                failures.append(failure)
        if failures:
            raise failures[0]

    def stop(self):
        try:
            self.close_contexts()
        finally:
            try:
                if self._runner is not None:
                    self._runner.stop()
            finally:
                asyncio._set_running_loop(None)  # an interrupted sync call can leave Playwright's loop set


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
        _shared = SharedPlaywright(sync_api.sync_playwright, sync_api.Error)
    shared = _shared
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: contextlib.nullcontext(shared))
    yield
    shared.close_contexts()


def _stop_shared():
    global _shared
    shared, _shared = _shared, None
    if shared is not None:
        shared.stop()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    # A live sync Playwright leaves its loop running, which breaks asyncio.run in tests outside this folder.
    # tests/browser is not a package, so a package-scoped fixture would only stop at session end.
    try:
        return (yield)
    finally:
        if nextitem is None or Path(__file__).parent not in nextitem.path.parents:
            _stop_shared()


def pytest_sessionfinish(session):
    _stop_shared()  # a run cut short (-x, Ctrl-C) never reaches the last teardown above


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
