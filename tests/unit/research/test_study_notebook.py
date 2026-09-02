from __future__ import annotations

import json

from scripts.build_study_notebook import NOTEBOOK_PATH, build_notebook


def test_committed_notebook_matches_its_generator() -> None:
    assert NOTEBOOK_PATH.is_file()

    committed = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    assert committed == build_notebook()


def test_notebook_carries_no_stored_outputs_or_execution_counts() -> None:
    committed = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))

    code_cells = [cell for cell in committed["cells"] if cell["cell_type"] == "code"]

    assert code_cells
    assert all(cell["outputs"] == [] for cell in code_cells)
    assert all(cell["execution_count"] is None for cell in code_cells)


def test_notebook_enforces_the_three_preflight_gates() -> None:
    source = "\n".join(
        "".join(cell["source"])
        for cell in json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))["cells"]
    )

    assert "60000" in source
    assert '"status", "--porcelain"' in source
    assert "gate 3 failed: torch cannot see the GPU" in source
    assert "557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf" in source
    assert "scripts/capture_study_environment.py" in source


def test_notebook_never_imports_torch_in_the_kernel() -> None:
    cells = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))["cells"]
    code = [line for cell in cells if cell["cell_type"] == "code" for line in cell["source"]]

    assert code
    assert not any(line.lstrip().startswith(("import torch", "from torch")) for line in code)


def test_every_code_cell_is_syntactically_valid_python() -> None:
    cells = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))["cells"]

    code_cells = [cell for cell in cells if cell["cell_type"] == "code"]

    assert len(code_cells) == 12
    for index, cell in enumerate(code_cells):
        compile("".join(cell["source"]), f"<cell {index}>", "exec")


def test_notebook_never_stages_a_private_split() -> None:
    source = "\n".join(
        "".join(cell["source"])
        for cell in json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))["cells"]
    )

    assert 'not (DATA / category / "test_private").exists()' in source
