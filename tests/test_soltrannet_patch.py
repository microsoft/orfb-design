"""Tests for the installed SolTranNet compatibility patch."""

from servers.soltrannet.patch_soltrannet import patch_predict_module


def test_patch_predict_module_replaces_pkg_resources(tmp_path):
    predict_module = tmp_path / "predict.py"
    predict_module.write_text(
        "import torch\n"
        "import pkg_resources, heapq\n"
        '_weights=pkg_resources.resource_filename(__name__,"soltrannet_aqsol_trained.weights")\n',
        encoding="utf-8",
    )

    assert patch_predict_module(predict_module)
    assert not patch_predict_module(predict_module)

    source = predict_module.read_text(encoding="utf-8")
    assert "pkg_resources" not in source
    assert 'Path(__file__).with_name("soltrannet_aqsol_trained.weights")' in source
