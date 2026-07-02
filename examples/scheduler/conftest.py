import importlib.util
import sys
from pathlib import Path

# When running pytest directly from the project root, expose the reference
# oracle as `core` so the contract tests can be collected and run.
# holdtrue verify stages its own core.py; this conftest only fires for
# direct pytest runs where no core module exists yet.
_root = Path(__file__).parent
_private = _root / "contract_private"
_contract = _root / "contract"
if _private.is_dir():
    # models.py (pydantic types) lives in contract/; put it on sys.path first
    # so reference_impl.py can `from models import *` without error.
    if _contract.is_dir():
        sys.path.insert(0, str(_contract))
    sys.path.insert(0, str(_private))
    _spec = importlib.util.spec_from_file_location(
        "core", _private / "reference_impl.py")
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        sys.modules.setdefault("core", _mod)
