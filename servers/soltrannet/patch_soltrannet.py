# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Remove SolTranNet's deprecated runtime dependency on pkg_resources."""

from importlib.util import find_spec
from pathlib import Path

_OLD_IMPORT = "import pkg_resources, heapq"
_NEW_IMPORT = "import heapq\nfrom pathlib import Path"
_OLD_WEIGHTS = '_weights=pkg_resources.resource_filename(__name__,"soltrannet_aqsol_trained.weights")'
_NEW_WEIGHTS = '_weights = str(Path(__file__).with_name("soltrannet_aqsol_trained.weights"))'


def patch_predict_module(path: Path) -> bool:
    """Patch a SolTranNet predict module, returning whether it changed."""
    source = path.read_text(encoding="utf-8")
    if _OLD_IMPORT not in source or _OLD_WEIGHTS not in source:
        if _NEW_IMPORT in source and _NEW_WEIGHTS in source:
            return False
        raise RuntimeError(f"Unexpected SolTranNet source in {path}")

    source = source.replace(_OLD_IMPORT, _NEW_IMPORT, 1)
    source = source.replace(_OLD_WEIGHTS, _NEW_WEIGHTS, 1)
    path.write_text(source, encoding="utf-8")
    return True


def main() -> None:
    """Locate and patch the installed SolTranNet package."""
    spec = find_spec("soltrannet")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("The installed SolTranNet package could not be located")

    package_dir = Path(next(iter(spec.submodule_search_locations)))
    patch_predict_module(package_dir / "predict.py")


if __name__ == "__main__":
    main()
