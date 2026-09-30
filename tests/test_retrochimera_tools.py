"""Input-validation tests for the retrochimera retrosynthesis tool.

Real planning needs syntheseus + the RetroChimera model stack and checkpoints,
which are baked into the server's Docker image but absent from the test
environment. These tests therefore exercise the input validation, which raises
before any model is touched.
"""

import pytest
from retrochimera_tools.retrosynthesis import predict_retrosynthesis


def test_inventory_path_requires_user_configuration(monkeypatch):
    from retrochimera_tools import _model

    monkeypatch.delenv("RETROCHIMERA_INVENTORY_PATH", raising=False)

    with pytest.raises(RuntimeError, match="RETROCHIMERA_INVENTORY_PATH"):
        _model._inventory_path()


def test_inventory_path_rejects_missing_file(monkeypatch, tmp_path):
    from retrochimera_tools import _model

    missing = tmp_path / "missing.smi"
    monkeypatch.setenv("RETROCHIMERA_INVENTORY_PATH", str(missing))

    with pytest.raises(FileNotFoundError, match="inventory file does not exist"):
        _model._inventory_path()


def test_inventory_path_accepts_user_file(monkeypatch, tmp_path):
    from retrochimera_tools import _model

    inventory = tmp_path / "inventory.smi"
    inventory.write_text("CCO\n", encoding="utf-8")
    monkeypatch.setenv("RETROCHIMERA_INVENTORY_PATH", str(inventory))

    assert _model._inventory_path() == inventory


def test_retrosynthesis_num_results_bounds():
    with pytest.raises(ValueError):
        predict_retrosynthesis("CCO", num_results=0)
    with pytest.raises(ValueError):
        predict_retrosynthesis("CCO", num_results=51)


def test_retrosynthesis_empty_smiles():
    with pytest.raises(ValueError):
        predict_retrosynthesis("")


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_retrosynthesis_proxies_to_service(monkeypatch):
    """When the sidecar URL is set, the wrapper POSTs and returns its JSON."""
    import json
    import urllib.request

    captured = {}
    expected = {"status": "ok", "routes": [], "message": "done"}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps(expected).encode("utf-8"))

    monkeypatch.setenv("RETROCHIMERA_MODEL_SERVICE_URL", "http://127.0.0.1:8901")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = predict_retrosynthesis("CCO", num_results=3)

    assert {key: result[key] for key in expected} == expected
    assert set(result) == set(expected) | {"provenance"}
    assert result["provenance"]["tool"]["name"] == "predict_retrosynthesis"
    assert result["provenance"]["configuration"]["inference_backend"] == "sidecar"
    assert result["provenance"]["input"]["values"] == {"smiles": "CCO", "num_results": 3}
    assert captured["url"] == "http://127.0.0.1:8901/predict"
    assert captured["body"] == {"smiles": "CCO", "num_results": 3}


def test_retrosynthesis_service_400_raises_value_error(monkeypatch):
    """A 400 from the service is surfaced as ValueError (input semantics)."""
    import io
    import urllib.error
    import urllib.request

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b"bad smiles"))

    monkeypatch.setenv("RETROCHIMERA_MODEL_SERVICE_URL", "http://127.0.0.1:8901")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ValueError):
        predict_retrosynthesis("CCO")


# --------------------------------------------------------------------------- #
# Upstream rule-application worker teardown.
#
# RetroChimera 1.3.0 escalates from SIGTERM to SIGKILL when a worker remains
# alive. The model package's top-level import eagerly imports torch, so the
# fixture loads the lightweight chemistry submodule directly from the installed
# distribution. These tests skip when RetroChimera is not installed.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def upstream_rule_application_server():
    import importlib
    import sys
    import types
    from importlib.metadata import PackageNotFoundError, distribution
    from pathlib import Path

    from packaging.version import Version

    try:
        installed = distribution("retrochimera")
    except PackageNotFoundError:
        pytest.skip("RetroChimera is not installed in the lightweight test environment")

    assert Version(installed.version) >= Version("1.3.0")
    package_dir = Path(installed.locate_file("retrochimera"))
    original_modules = {name: sys.modules.get(name) for name in ("retrochimera", "retrochimera.chem")}
    existing_modules = set(sys.modules)

    package = types.ModuleType("retrochimera")
    package.__path__ = [str(package_dir)]
    chemistry = types.ModuleType("retrochimera.chem")
    chemistry.__path__ = [str(package_dir / "chem")]
    sys.modules.update(
        {
            "retrochimera": package,
            "retrochimera.chem": chemistry,
        }
    )

    try:
        yield importlib.import_module("retrochimera.chem.rule_application_server")
    finally:
        for name in set(sys.modules) - existing_modules:
            if name == "retrochimera" or name.startswith("retrochimera."):
                sys.modules.pop(name, None)
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _spawn_unkillable_worker():
    """Start a child that ignores SIGTERM, emulating a worker stuck in RDKit."""
    import multiprocessing as mp
    import signal
    import time

    def _worker(conn):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(0.5)

    ctx = mp.get_context("fork")
    parent_conn, child_conn = ctx.Pipe()
    process = ctx.Process(target=_worker, args=(child_conn,))
    process.start()
    return process, parent_conn


def test_finalize_sigkills_worker_that_ignores_sigterm(
    upstream_rule_application_server,
):
    """Upstream cleanup reaps a SIGTERM-proof worker instead of abandoning it."""
    import os

    process, parent_conn = _spawn_unkillable_worker()
    pid = process.pid
    try:
        upstream_rule_application_server.RuleApplicationServer._finalize_server({0: process}, {0: parent_conn})

        # A successful teardown ends in Process.close(), after which the Process
        # object refuses further queries — so assert on the OS, which is the real
        # question anyway: was the worker reaped, or merely detached and leaked?
        assert process._closed, "Process.close() did not succeed; worker was abandoned"
        assert not os.path.exists(f"/proc/{pid}"), f"pid {pid} leaked"
    finally:
        if os.path.exists(f"/proc/{pid}"):
            import signal as _signal

            os.kill(pid, _signal.SIGKILL)


def test_finalize_does_not_leak_process_objects(upstream_rule_application_server):
    """Repeated teardowns must not grow multiprocessing's global _children set."""
    from multiprocessing.process import _children

    before = len(_children)
    for _ in range(3):
        process, parent_conn = _spawn_unkillable_worker()
        upstream_rule_application_server.RuleApplicationServer._finalize_server({0: process}, {0: parent_conn})

    assert len(_children) == before, "Process objects leaked into multiprocessing._children"
