"""Tests for Web Hub and Packaging endpoints (Task 8).

Verifies:
- BundlePackager unit tests:
  - Generates student .zip with code files, headers, Makefile, and RAPPORT.md.
  - Generates master bundle .zip with individual student zips and AUDIT_SUMMARY.md.
  - Handles missing or empty reports gracefully.
- FastAPI web endpoints:
  - GET / : Dashboard HTML with Tailwind CSS, mode toggle, dropzone, and 6 student cards.
  - GET /api/profiles : Lists registered student profiles (default 6 students).
  - POST /api/tp/submit : Accepts JSON or form data, launches batch pipeline.
  - GET /api/tp/status/{batch_id} : Returns real-time batch progress and student statuses.
  - GET /api/tp/download/{batch_id} : Downloads cohort bundle .zip.
  - GET /api/tp/download/{batch_id}/{student} : Downloads individual student's .zip.
  - 404 handling for invalid batch IDs or students.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.divergence.similarity import PairwiseSimilarityMatrix
from src.orchestrator.audit import AuditReport, StudentDeliverable
from src.orchestrator.pipeline import BatchPipeline, BatchResult
from src.web.app import app, BATCH_STORE
from src.web.packaging import BundlePackager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_deliverable() -> StudentDeliverable:
    return StudentDeliverable(
        student_name="Lucas",
        code_files={
            "main.c": "#include <stdio.h>\nint main(void) { printf(\"Hello Lucas\\n\"); return 0; }\n",
            "hash.h": "#ifndef HASH_H\n#define HASH_H\nint hash(const char *s);\n#endif\n",
            "Makefile": "all:\n\tgcc -o main main.c\n",
        },
        report_markdown="# Rapport de TP - Lucas\n\n## Exécution\nTraces d'exécution validées.",
        execution_trace="Execution trace: OK, returncode 0",
        compilation_success=True,
        burstiness_score=0.78,
        repair_iterations=0,
    )


@pytest.fixture
def cohort_deliverables() -> Dict[str, StudentDeliverable]:
    students = ["Lucas", "Emma", "Thomas", "Chloé", "Maxime", "Léa"]
    deliverables = {}
    for i, name in enumerate(students):
        deliverables[name] = StudentDeliverable(
            student_name=name,
            code_files={
                "main.c": f"// Variant {i+1} for {name}\nint main(void) {{ return {i}; }}\n",
                "hash.h": "// Header\n",
                "Makefile": "all:\n\tgcc -o prog main.c\n",
            },
            report_markdown=f"# Rapport de TP - {name}\n\nTravail personnel réalisé avec succès.",
            execution_trace=f"Trace {name}: OK",
            compilation_success=True,
            burstiness_score=0.75 + (i * 0.02),
            repair_iterations=0,
        )
    return deliverables


# ---------------------------------------------------------------------------
# BundlePackager Unit Tests
# ---------------------------------------------------------------------------

def test_bundle_packager_create_student_zip(tmp_path: Path, sample_deliverable: StudentDeliverable):
    """Verifies that create_student_zip creates a valid archive with source files and RAPPORT.md."""
    zip_path = BundlePackager.create_student_zip(
        deliverable=sample_deliverable,
        output_dir=tmp_path,
        matiere_nom="Langage_C",
    )

    assert zip_path.exists()
    assert zip_path.is_file()
    assert zip_path.suffix == ".zip"

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "main.c" in namelist
        assert "hash.h" in namelist
        assert "Makefile" in namelist
        assert "RAPPORT.md" in namelist

        # Check content integrity
        main_content = zf.read("main.c").decode("utf-8")
        assert "Hello Lucas" in main_content

        rapport_content = zf.read("RAPPORT.md").decode("utf-8")
        assert "Rapport de TP - Lucas" in rapport_content
        assert "Traces d'exécution validées." in rapport_content


def test_bundle_packager_handles_missing_report_gracefully(tmp_path: Path):
    """Verifies fallback report generation when deliverable has no markdown report."""
    deliverable = StudentDeliverable(
        student_name="Emma",
        code_files={"Main.java": "public class Main { public static void main(String[] args) {} }"},
        report_markdown="",
        compilation_success=True,
    )
    zip_path = BundlePackager.create_student_zip(
        deliverable=deliverable,
        output_dir=tmp_path,
        matiere_nom="Java",
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert "RAPPORT.md" in zf.namelist()
        content = zf.read("RAPPORT.md").decode("utf-8")
        assert "Emma" in content


def test_bundle_packager_create_bundle(tmp_path: Path, cohort_deliverables: Dict[str, StudentDeliverable]):
    """Verifies that create_bundle bundles all individual student archives and AUDIT_SUMMARY.md."""
    matrix = PairwiseSimilarityMatrix()
    matrix[("Lucas", "Emma")] = 0.05
    matrix[("Lucas", "Thomas")] = 0.07

    audit_rep = AuditReport(
        passed=True,
        invariant_checks={"Lucas": True, "Emma": True, "Thomas": True},
        similarity_matrix=matrix,
        flagged_pairs=[],
    )

    bundle_path = BundlePackager.create_bundle(
        batch_id="test_batch_001",
        deliverables=cohort_deliverables,
        output_dir=tmp_path,
        similarity_matrix=matrix,
        audit_report=audit_rep,
    )

    assert bundle_path.exists()
    assert bundle_path.is_file()
    assert "bundle_test_batch_001.zip" in bundle_path.name or "test_batch_001" in bundle_path.name

    with zipfile.ZipFile(bundle_path, "r") as zf:
        namelist = zf.namelist()
        assert "AUDIT_SUMMARY.md" in namelist

        # Should contain an archive for each student
        for student_name in cohort_deliverables:
            matching = [name for name in namelist if student_name in name and name.endswith(".zip")]
            assert len(matching) >= 1, f"Missing zip archive for student {student_name} in bundle"

        # Check content of AUDIT_SUMMARY.md
        summary_text = zf.read("AUDIT_SUMMARY.md").decode("utf-8")
        assert "test_batch_001" in summary_text
        assert "Lucas" in summary_text
        assert "Emma" in summary_text
        assert "Anti-MOSS" in summary_text or "Similarit" in summary_text


# ---------------------------------------------------------------------------
# FastAPI Endpoints Tests
# ---------------------------------------------------------------------------

def test_get_dashboard_html(client: TestClient):
    """GET / should render the classroom dashboard with Tailwind CSS and controls."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "Tailwind" in html or "tailwindcss" in html
    assert "Solo" in html
    assert "Binôme" in html or "Binome" in html
    assert "dropzone" in html.lower() or "drag" in html.lower() or "sujet" in html.lower()


def test_get_profiles(client: TestClient):
    """GET /api/profiles should return the list of registered student profiles."""
    response = client.get("/api/profiles")
    assert response.status_code == 200
    profiles = response.json()
    assert isinstance(profiles, list)
    assert len(profiles) >= 6

    names = [p.get("name") if isinstance(p, dict) else p for p in profiles]
    for expected_name in ["Noah", "Mehdi", "Malo", "Aymen", "Rayyan", "Taha"]:
        assert expected_name in names


def test_submit_tp_batch_json(client: TestClient, monkeypatch):
    """POST /api/tp/submit with JSON payload starts the batch pipeline and returns batch_id."""
    # Mock pipeline to return quickly with valid deliverables
    def mock_run_batch(*args, **kwargs):
        student_names = kwargs.get("student_names", ["Lucas", "Emma"])
        deliverables = {
            name: StudentDeliverable(
                student_name=name,
                code_files={"main.c": f"// Code for {name}\nint main() {{ return 0; }}\n"},
                report_markdown=f"# Rapport {name}\nDone.",
                compilation_success=True,
            )
            for name in student_names
        }
        return BatchResult(
            success=True,
            student_deliverables=deliverables,
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.1,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    payload = {
        "subject_text": "# TP 1 : Table de hachage en C\nImplémenter une table de hachage.",
        "student_names": ["Lucas", "Emma"],
        "matiere_id": "langage_c",
        "mode": "solo",
    }
    response = client.post("/api/tp/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert data.get("status") in ("processing", "completed")

    batch_id = data["batch_id"]

    # Verify status endpoint reflects batch
    status_response = client.get(f"/api/tp/status/{batch_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["batch_id"] == batch_id
    assert "students" in status_data
    assert "Lucas" in status_data["students"]
    assert "Emma" in status_data["students"]


def test_submit_tp_batch_multipart(client: TestClient, monkeypatch):
    """POST /api/tp/submit with multipart form data (file upload)."""
    def mock_run_batch(*args, **kwargs):
        return BatchResult(
            success=True,
            student_deliverables={
                "Lucas": StudentDeliverable(
                    student_name="Lucas",
                    code_files={"main.c": "int main() { return 0; }"},
                    report_markdown="# Rapport Lucas",
                    compilation_success=True,
                )
            },
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.05,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    form_data = {
        "subject_text": "Sujet via formulaire",
        "student_names": "Lucas",
        "matiere_id": "langage_c",
        "mode": "solo",
    }
    skeleton_content = b"#include <stdio.h>\n// skeleton"
    files = {
        "skeleton_file": ("skeleton.c", skeleton_content, "text/plain"),
    }

    response = client.post("/api/tp/submit", data=form_data, files=files)
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data


def test_get_batch_status_not_found(client: TestClient):
    """GET /api/tp/status/{batch_id} should return 404 for unknown batch."""
    response = client.get("/api/tp/status/non_existent_batch_xyz_123")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_download_cohort_bundle_and_individual_zip(client: TestClient, monkeypatch, tmp_path: Path):
    """Verifies GET /api/tp/download/{batch_id} and GET /api/tp/download/{batch_id}/{student}."""
    def mock_run_batch(*args, **kwargs):
        return BatchResult(
            success=True,
            student_deliverables={
                "Lucas": StudentDeliverable(
                    student_name="Lucas",
                    code_files={"main.c": "int main() { return 0; }"},
                    report_markdown="# Rapport Lucas\nTout fonctionne.",
                    compilation_success=True,
                ),
                "Emma": StudentDeliverable(
                    student_name="Emma",
                    code_files={"main.c": "int main() { return 1; }"},
                    report_markdown="# Rapport Emma\nValidé.",
                    compilation_success=True,
                ),
            },
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.1,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    # Submit batch
    payload = {
        "subject_text": "TP Téléchargement",
        "student_names": ["Lucas", "Emma"],
        "matiere_id": "langage_c",
    }
    submit_res = client.post("/api/tp/submit", json=payload)
    assert submit_res.status_code == 200
    batch_id = submit_res.json()["batch_id"]

    # 1. Download full bundle zip
    bundle_res = client.get(f"/api/tp/download/{batch_id}")
    assert bundle_res.status_code == 200
    assert bundle_res.headers["content-type"] in ("application/zip", "application/x-zip-compressed")

    bundle_zip_bytes = io.BytesIO(bundle_res.content)
    with zipfile.ZipFile(bundle_zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert "AUDIT_SUMMARY.md" in namelist
        assert any("Lucas" in name for name in namelist)
        assert any("Emma" in name for name in namelist)

    # 2. Download individual student zip (Lucas)
    lucas_res = client.get(f"/api/tp/download/{batch_id}/Lucas")
    assert lucas_res.status_code == 200
    assert lucas_res.headers["content-type"] in ("application/zip", "application/x-zip-compressed")

    lucas_zip_bytes = io.BytesIO(lucas_res.content)
    with zipfile.ZipFile(lucas_zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert "main.c" in namelist
        assert "RAPPORT.md" in namelist
        content = zf.read("RAPPORT.md").decode("utf-8")
        assert "Lucas" in content

    # 3. Download unknown student
    unknown_res = client.get(f"/api/tp/download/{batch_id}/UnknownStudent")
    assert unknown_res.status_code == 404

    # 4. Download invalid batch ID
    invalid_res = client.get("/api/tp/download/bad_batch_id_999")
    assert invalid_res.status_code == 404


def test_binome_mode_submission(client: TestClient, monkeypatch):
    """Verifies that binôme mode groups students or generates pair deliverables."""
    def mock_run_batch(*args, **kwargs):
        names = kwargs.get("student_names", [])
        return BatchResult(
            success=True,
            student_deliverables={
                name: StudentDeliverable(
                    student_name=name,
                    code_files={"main.c": f"// Binome code for {name}"},
                    report_markdown=f"# Binome Report - {name}",
                    compilation_success=True,
                )
                for name in names
            },
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.1,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    payload = {
        "subject_text": "TP Binôme Réseaux",
        "student_names": ["Lucas", "Emma", "Thomas", "Chloé", "Maxime", "Léa"],
        "matiere_id": "prog_systeme",
        "mode": "binome",
    }
    response = client.post("/api/tp/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"]
    assert data["mode"] == "binome"


def test_submit_tp_batch_with_skeleton_zip_archive(client: TestClient, monkeypatch):
    """Verifies that an uploaded .zip skeleton archive is unpacked and passed to the pipeline."""
    passed_skeleton = {}

    def mock_run_batch(*args, **kwargs):
        nonlocal passed_skeleton
        passed_skeleton = kwargs.get("skeleton_files", {})
        return BatchResult(
            success=True,
            student_deliverables={
                "Lucas": StudentDeliverable(
                    student_name="Lucas",
                    code_files={"main.c": "int main() { return 0; }"},
                    report_markdown="# Rapport Lucas",
                    compilation_success=True,
                )
            },
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.05,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    # Create in-memory zip archive containing skeleton files
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("include/lib.h", "#define VAL 42\n")
        zf.writestr("src/stub.c", "void stub(void) {}\n")
        zf.writestr("Makefile", "all:\n\t@echo build\n")
    zip_bytes = zip_buffer.getvalue()

    form_data = {
        "subject_text": "TP avec squelette compressé",
        "student_names": "Lucas",
        "matiere_id": "langage_c",
    }
    files = {
        "skeleton_file": ("skeleton_project.zip", zip_bytes, "application/zip"),
    }

    response = client.post("/api/tp/submit", data=form_data, files=files)
    assert response.status_code == 200
    assert "include/lib.h" in passed_skeleton
    assert "src/stub.c" in passed_skeleton
    assert "Makefile" in passed_skeleton


def test_bundle_packager_instance_and_unicode_handling(tmp_path: Path):
    """Verifies BundlePackager works when instantiated and handles unicode names and nested paths."""
    packager = BundlePackager()
    deliv = StudentDeliverable(
        student_name="Éléonore-Chloé",
        code_files={
            "src/core.c": "#include \"core.h\"\nint calc() { return 1; }\n",
            "include/core.h": "int calc(void);\n",
        },
        report_markdown="# Rapport - Éléonore-Chloé\nAccentuation préservée.",
        compilation_success=True,
        burstiness_score=0.91,
    )

    # Test instance call
    zip_path = packager.create_student_zip(deliv, output_dir=tmp_path, matiere_nom="Langage_C")
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "src/core.c" in namelist
        assert "include/core.h" in namelist
        assert "RAPPORT.md" in namelist
        rapport = zf.read("RAPPORT.md").decode("utf-8")
        assert "Éléonore-Chloé" in rapport
        assert "Accentuation préservée." in rapport

    # Test create_bundle instance call
    bundle_path = packager.create_bundle(
        batch_id="batch_unicode",
        deliverables={"Éléonore-Chloé": deliv},
        output_dir=tmp_path,
    )
    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path, "r") as zf:
        namelist = zf.namelist()
        assert "AUDIT_SUMMARY.md" in namelist
        assert any("Éléonore-Chloé" in name for name in namelist)


def test_download_pending_or_missing_bundle_raises_404(client: TestClient):
    """Verifies that attempting to download a batch whose bundle is not ready returns 404."""
    fake_batch_id = "pending_batch_123"
    BATCH_STORE[fake_batch_id] = {
        "batch_id": fake_batch_id,
        "status": "processing",
        "progress": 30,
        "bundle_path": None,
        "student_zip_paths": {},
    }

    resp = client.get(f"/api/tp/download/{fake_batch_id}")
    assert resp.status_code == 404
    assert "not ready" in resp.json().get("detail", "").lower()

    student_resp = client.get(f"/api/tp/download/{fake_batch_id}/Lucas")
    assert student_resp.status_code == 404


def test_submit_tp_with_zip_slip_skeleton(client: TestClient, monkeypatch):
    """Verify that uploading a skeleton zip with traversal paths does not extract unsafe paths."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("../../etc/shadow", "dangerous")
        zf.writestr("/tmp/evil.c", "evil")
        zf.writestr("src/safe.c", "int safe() { return 1; }")
    bio.seek(0)

    passed_skeleton = {}

    def mock_run_batch(*args, **kwargs):
        nonlocal passed_skeleton
        passed_skeleton = kwargs.get("skeleton_files", {})
        return BatchResult(
            success=True,
            student_deliverables={},
            similarity_matrix=PairwiseSimilarityMatrix(),
            audit_report=AuditReport(passed=True),
            duration_sec=0.1,
        )

    monkeypatch.setattr(BatchPipeline, "execute_session", mock_run_batch)
    monkeypatch.setattr(BatchPipeline, "run_batch", mock_run_batch)

    resp = client.post(
        "/api/tp/submit",
        data={"subject_text": "Test zip slip", "student_names": "Lucas"},
        files={"skeleton_file": ("skeleton.zip", bio.getvalue(), "application/zip")},
    )
    assert resp.status_code == 200
    assert "src/safe.c" in passed_skeleton
    assert "../../etc/shadow" not in passed_skeleton
    assert "/tmp/evil.c" not in passed_skeleton


def test_batch_store_thread_safety(client: TestClient):
    """Verify concurrent reads and writes to BATCH_STORE do not raise race condition errors."""
    import threading

    def worker(worker_id: int):
        bid = f"thread_batch_{worker_id}"
        from src.web.app import BATCH_STORE, _store_lock
        with _store_lock:
            BATCH_STORE[bid] = {
                "batch_id": bid,
                "status": "processing",
                "progress": 50,
                "students": {"Lucas": {"status": "Prêt"}},
            }
        resp = client.get(f"/api/tp/status/{bid}")
        assert resp.status_code == 200

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


