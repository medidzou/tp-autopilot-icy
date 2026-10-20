"""FastAPI Web Hub for TP Classroom Sessions.

Features:
- GET / : Interactive Classroom Dashboard with Tailwind CSS, Solo/Binôme toggle,
  drag-and-drop zone, live progress badges, and 1-click bundle downloads.
- GET /api/profiles : Lists registered student profiles (default 6 students).
- POST /api/tp/submit : Starts batch generation from subject text or uploaded skeleton.
- GET /api/tp/status/{batch_id} : Returns real-time progress and student states.
- GET /api/tp/download/{batch_id} : Downloads the complete cohort bundle (.zip).
- GET /api/tp/download/{batch_id}/{student} : Downloads individual student .zip.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.orchestrator.audit import AuditReport, StudentDeliverable
from src.orchestrator.pipeline import BatchPipeline, BatchResult
from src.profiles.manager import ProfileManager
from src.profiles.models import StudentProfile
from src.web.packaging import BundlePackager

# Base directory for storing generated zip bundles
OUTPUT_DIR = Path("deliverables_packaged")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory batch store and concurrency lock
BATCH_STORE: Dict[str, Dict[str, Any]] = {}
_store_lock = threading.Lock()

# Default cohort of 6 students
DEFAULT_COHORT = [
    {"name": "Noah", "calibration_answers": {}, "samples": []},
    {"name": "Mehdi", "calibration_answers": {}, "samples": []},
    {"name": "Malo", "calibration_answers": {}, "samples": []},
    {"name": "Aymen", "calibration_answers": {}, "samples": []},
    {"name": "Rayyan", "calibration_answers": {}, "samples": []},
    {"name": "Taha", "calibration_answers": {}, "samples": []},
]


def ensure_default_profiles(manager: ProfileManager) -> None:
    """Ensures the 6 standard student profiles are seeded in ProfileManager."""
    existing = set(manager.list_profiles())
    for item in DEFAULT_COHORT:
        if item["name"] not in existing:
            manager.create_or_update_profile(
                name=item["name"],
                calibration_answers=item["calibration_answers"],
                samples=item["samples"],
            )


def get_pipeline() -> BatchPipeline:
    """Returns a BatchPipeline instance."""
    if hasattr(app.state, "pipeline") and app.state.pipeline is not None:
        return app.state.pipeline
    return BatchPipeline(profile_manager=ProfileManager())


app = FastAPI(
    title="Hub Web de Salle de TP ICy",
    description="Automate de génération, dérivation et audit anti-MOSS pour cohortes de TP",
    version="1.0.0",
)


class SubmitBatchRequest(BaseModel):
    subject_text: Optional[str] = Field(default="", description="Texte ou consignes du sujet de TP")
    student_names: Optional[List[str]] = Field(
        default_factory=lambda: ["Noah", "Mehdi", "Malo", "Aymen", "Rayyan", "Taha"]
    )
    matiere_id: Optional[str] = Field(default="langage_c")
    mode: Optional[str] = Field(default="solo", description="'solo' ou 'binome'")
    skeleton_files: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Background Task Runner
# ---------------------------------------------------------------------------

def _run_batch_worker(
    batch_id: str,
    subject_text: str,
    student_names: List[str],
    skeleton_files: Optional[Dict[str, str]],
    matiere_id: Optional[str],
    mode: str,
) -> None:
    """Worker function that runs the batch pipeline and packages deliverables."""
    with _store_lock:
        batch_info = BATCH_STORE.get(batch_id)
        if not batch_info:
            return

    try:
        pipeline = get_pipeline()

        # Step 1: Update statuses to "Analyse noyau"
        with _store_lock:
            for sname in student_names:
                if sname in batch_info["students"]:
                    batch_info["students"][sname]["status"] = "Analyse noyau"
            batch_info["progress"] = 20

        # Step 2: Update statuses to "Dérivation style"
        with _store_lock:
            for sname in student_names:
                if sname in batch_info["students"]:
                    batch_info["students"][sname]["status"] = "Dérivation style"
            batch_info["progress"] = 40

        # Step 3: Run pipeline
        # If in binome mode, handle pair strategy
        actual_names = list(student_names)
        result: BatchResult = pipeline.run_batch(
            subject_text=subject_text,
            student_names=actual_names,
            skeleton_files=skeleton_files,
            matiere_id=matiere_id,
        )

        # In binome mode: if students were paired, we can ensure pair deliverables
        deliverables = dict(result.student_deliverables)
        if mode == "binome":
            # For each pair (i, i+1), customize report to mention both partners
            for i in range(0, len(student_names) - 1, 2):
                p1 = student_names[i]
                p2 = student_names[i + 1]
                if p1 in deliverables and p2 in deliverables:
                    # Update report headers to highlight binome collaboration
                    joint_header = f"# Rapport de TP (Binôme : {p1} & {p2})\n\n"
                    if not deliverables[p1].report_markdown.startswith("# Rapport de TP (Binôme"):
                        deliverables[p1].report_markdown = joint_header + deliverables[p1].report_markdown
                    if not deliverables[p2].report_markdown.startswith("# Rapport de TP (Binôme"):
                        deliverables[p2].report_markdown = joint_header + deliverables[p2].report_markdown

        # Step 4: Update statuses to "Audit anti-MOSS"
        with _store_lock:
            for sname in student_names:
                if sname in batch_info["students"]:
                    batch_info["students"][sname]["status"] = "Audit anti-MOSS"
            batch_info["progress"] = 80

        # Package deliverables into student zips and master bundle
        matiere_clean = matiere_id or "TP"
        bundle_path = BundlePackager.create_bundle(
            batch_id=batch_id,
            deliverables=deliverables,
            output_dir=OUTPUT_DIR,
            similarity_matrix=result.similarity_matrix,
            audit_report=result.audit_report,
            matiere_nom=matiere_clean,
        )

        batch_dir = OUTPUT_DIR / batch_id
        clean_matiere = BundlePackager._sanitize_filename(matiere_clean)
        student_zip_paths = {}
        for sname in deliverables:
            expected_name = f"{BundlePackager._sanitize_filename(sname)}_{clean_matiere}.zip"
            student_zip_paths[sname] = batch_dir / expected_name

        # Populate similarity metrics
        max_sim = 0.0
        pairs_data = {}
        if result.similarity_matrix is not None:
            sim_items = result.similarity_matrix.items() if hasattr(result.similarity_matrix, "items") else getattr(result.similarity_matrix, "matrix", {}).items()
            for pair, val in sim_items:
                if isinstance(pair, (tuple, list)) and len(pair) == 2:
                    pairs_data[f"{pair[0]}_{pair[1]}"] = val
                else:
                    pairs_data[str(pair)] = val
                if isinstance(val, (int, float)) and val > max_sim:
                    max_sim = val

        # Step 5: Update to "Prêt" and complete batch
        with _store_lock:
            for sname, deliv in deliverables.items():
                if sname in batch_info["students"]:
                    batch_info["students"][sname]["status"] = "Prêt"
                    batch_info["students"][sname]["compilation_success"] = deliv.compilation_success
                    batch_info["students"][sname]["burstiness_score"] = deliv.burstiness_score

            batch_info["progress"] = 100
            batch_info["status"] = "completed"
            batch_info["bundle_path"] = bundle_path
            batch_info["student_zip_paths"] = student_zip_paths
            batch_info["similarity_matrix"] = {
                "max_similarity": max_sim,
                "pairs": pairs_data,
            }
            batch_info["audit_report"] = {
                "passed": result.audit_report.passed if result.audit_report else True,
                "flagged_pairs": result.audit_report.flagged_pairs if result.audit_report else [],
            }

    except Exception as exc:
        with _store_lock:
            batch_info["status"] = "failed"
            batch_info["error"] = str(exc)
            for sname in student_names:
                if sname in batch_info["students"]:
                    batch_info["students"][sname]["status"] = "Erreur"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def get_dashboard() -> HTMLResponse:
    """Renders the main web dashboard."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.is_file():
        content = template_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content, status_code=200)
    return HTMLResponse(
        content="<html><body><h1>Hub Web de Salle de TP</h1><p>Template introuvable.</p></body></html>",
        status_code=200,
    )


@app.get("/api/profiles")
def get_profiles() -> List[Dict[str, Any]]:
    """Returns the list of 6 registered student profiles."""
    pm = ProfileManager()
    ensure_default_profiles(pm)

    profiles_list = []
    for name in pm.list_profiles():
        prof = pm.get_profile(name)
        profiles_list.append(prof.model_dump())

    return profiles_list


@app.post("/api/tp/submit")
async def submit_tp(
    request: Request,
    background_tasks: BackgroundTasks,
    skeleton_file: Optional[UploadFile] = File(None),
) -> Dict[str, Any]:
    """Submits a TP subject for batch generation and packaging."""
    content_type = request.headers.get("content-type", "")
    skeleton_files: Optional[Dict[str, str]] = None
    subject_text = ""
    student_names = ["Noah", "Mehdi", "Malo", "Aymen", "Rayyan", "Taha"]
    matiere_id = "langage_c"
    mode = "solo"

    if "application/json" in content_type:
        body = await request.json()
        subject_text = body.get("subject_text", "")
        if "student_names" in body:
            raw_names = body["student_names"]
            if isinstance(raw_names, list):
                student_names = raw_names
            elif isinstance(raw_names, str):
                student_names = [n.strip() for n in raw_names.split(",") if n.strip()]
        matiere_id = body.get("matiere_id", "langage_c")
        mode = body.get("mode", "solo")
        if "skeleton_files" in body and isinstance(body["skeleton_files"], dict):
            skeleton_files = body["skeleton_files"]

    else:
        # Multipart / Form data
        form = await request.form()
        subject_text = str(form.get("subject_text", ""))
        raw_names = form.get("student_names")
        if raw_names:
            if isinstance(raw_names, list):
                student_names = [str(n) for n in raw_names]
            else:
                student_names = [n.strip() for n in str(raw_names).split(",") if n.strip()]
        matiere_id = str(form.get("matiere_id", "langage_c"))
        mode = str(form.get("mode", "solo"))

        # Process uploaded skeleton file if provided
        upload_file_obj = form.get("skeleton_file")
        if upload_file_obj and hasattr(upload_file_obj, "read"):
            content_bytes = await upload_file_obj.read()
            filename = getattr(upload_file_obj, "filename", "skeleton.txt")

            if filename.endswith(".zip"):
                skeleton_files = {}
                with zipfile.ZipFile(io.BytesIO(content_bytes), "r") as zf:
                    for name in zf.namelist():
                        if not name.endswith("/"):
                            norm_name = name.replace("\\", "/")
                            p = Path(norm_name)
                            if p.is_absolute() or bool(p.root) or ".." in p.parts:
                                continue
                            try:
                                skeleton_files[norm_name] = zf.read(name).decode("utf-8")
                            except UnicodeDecodeError:
                                pass
            else:
                try:
                    skeleton_files = {filename: content_bytes.decode("utf-8")}
                except UnicodeDecodeError:
                    pass

    batch_id = uuid.uuid4().hex[:8]

    # Initialize batch status
    with _store_lock:
        BATCH_STORE[batch_id] = {
            "batch_id": batch_id,
            "status": "processing",
            "progress": 0,
            "subject_text": subject_text,
            "matiere_id": matiere_id,
            "mode": mode,
            "student_names": student_names,
            "students": {
                sname: {
                    "status": "En attente",
                    "compilation_success": None,
                    "burstiness_score": 0.0,
                }
                for sname in student_names
            },
            "similarity_matrix": {},
            "audit_report": None,
            "bundle_path": None,
            "student_zip_paths": {},
            "error": None,
        }

    # Queue worker in BackgroundTasks (executes synchronously in Starlette TestClient, async in live server)
    background_tasks.add_task(
        _run_batch_worker,
        batch_id=batch_id,
        subject_text=subject_text,
        student_names=student_names,
        skeleton_files=skeleton_files,
        matiere_id=matiere_id,
        mode=mode,
    )

    return {
        "batch_id": batch_id,
        "status": "processing",
        "mode": mode,
        "student_count": len(student_names),
    }


@app.get("/api/tp/status/{batch_id}")
def get_batch_status(batch_id: str) -> Dict[str, Any]:
    """Returns the current progress, status, and metrics of a batch session."""
    with _store_lock:
        batch_info = BATCH_STORE.get(batch_id)
        if not batch_info:
            raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

        return {
            "batch_id": batch_info["batch_id"],
            "status": batch_info["status"],
            "progress": batch_info["progress"],
            "mode": batch_info.get("mode", "solo"),
            "students": dict(batch_info.get("students", {})),
            "similarity_matrix": dict(batch_info.get("similarity_matrix", {})),
            "audit_report": batch_info.get("audit_report"),
            "error": batch_info.get("error"),
        }


@app.get("/api/tp/download/{batch_id}")
def download_bundle(batch_id: str):
    """Downloads the complete cohort bundle (.zip) containing all individual archives and AUDIT_SUMMARY.md."""
    with _store_lock:
        batch_info = BATCH_STORE.get(batch_id)
        if not batch_info:
            raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

        bundle_path = batch_info.get("bundle_path")
        if not bundle_path or not Path(bundle_path).is_file():
            raise HTTPException(status_code=404, detail="Bundle archive is not ready yet.")

        bundle_file = Path(bundle_path)

    return FileResponse(
        path=bundle_file,
        media_type="application/zip",
        filename=bundle_file.name,
    )


@app.get("/api/tp/download/{batch_id}/{student}")
def download_student_zip(batch_id: str, student: str):
    """Downloads an individual student's packaged .zip deliverable."""
    with _store_lock:
        batch_info = BATCH_STORE.get(batch_id)
        if not batch_info:
            raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")

        student_zip_paths = batch_info.get("student_zip_paths", {})
        student_zip = student_zip_paths.get(student)
        matiere_id = batch_info.get("matiere_id", "TP")

    if not student_zip or not Path(student_zip).is_file():
        # Fallback check inside batch directory
        fallback_path = OUTPUT_DIR / batch_id / f"{student}_{matiere_id}.zip"
        if fallback_path.is_file():
            student_zip = fallback_path
        else:
            raise HTTPException(status_code=404, detail=f"Deliverable for student '{student}' not found.")

    zip_file = Path(student_zip)
    return FileResponse(
        path=zip_file,
        media_type="application/zip",
        filename=zip_file.name,
    )
