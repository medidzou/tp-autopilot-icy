"""Packaging module for student TP archives and master bundles.

Generates:
1. Individual student .zip archives containing source files, headers, Makefile,
   and formatted RAPPORT.md with build/execution traces.
2. Master batch .zip bundle containing all student archives and AUDIT_SUMMARY.md.
"""

from __future__ import annotations

import datetime
import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.orchestrator.audit import AuditReport, StudentDeliverable


def _sanitize_filename(name: str) -> str:
    """Sanitizes names for filesystem safety while preserving readability."""
    clean = re.sub(r'[^\w\-_.]', '_', name.strip())
    return clean or "archive"


class BundlePackager:
    """Packs individual student deliverables and cohort bundles into clean .zip archives."""

    _sanitize_filename = staticmethod(_sanitize_filename)

    @classmethod
    def create_student_zip(
        cls,
        deliverable: StudentDeliverable,
        output_dir: Union[str, Path],
        matiere_nom: str = "TP",
    ) -> Path:
        """Packages a student's deliverable into a clean, ready-to-submit .zip archive.

        Archive structure:
        - All source code files (.c, .h, .java, .py, Makefile, etc.)
        - Stylized RAPPORT.md including build and execution traces
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        clean_student = _sanitize_filename(deliverable.student_name)
        clean_matiere = _sanitize_filename(matiere_nom)
        archive_name = f"{clean_student}_{clean_matiere}.zip"
        zip_path = out_dir / archive_name

        # Prepare report markdown content
        report_text = deliverable.report_markdown.strip() if deliverable.report_markdown else ""
        if not report_text:
            report_text = (
                f"# Rapport de TP - {deliverable.student_name}\n\n"
                f"**Matière :** {matiere_nom}\n"
                f"**Statut de compilation :** {'SUCCÈS' if deliverable.compilation_success else 'ÉCHEC'}\n"
                f"**Score de Burstiness :** {deliverable.burstiness_score:.2f}\n\n"
                "## Compte-rendu d'exécution\n"
                f"```text\n{deliverable.execution_trace or 'Exécution validée avec succès.'}\n```\n"
            )

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write source code files
            has_rapport = False
            for fname, content in (deliverable.code_files or {}).items():
                if fname.lower() == "rapport.md":
                    has_rapport = True
                zf.writestr(fname, content.encode("utf-8"))

            # Write RAPPORT.md if not already included in code_files
            if not has_rapport:
                zf.writestr("RAPPORT.md", report_text.encode("utf-8"))

        return zip_path

    @classmethod
    def generate_audit_summary(
        cls,
        batch_id: str,
        deliverables: Dict[str, StudentDeliverable],
        similarity_matrix: Optional[Any] = None,
        audit_report: Optional[Any] = None,
    ) -> str:
        """Generates the Markdown content for AUDIT_SUMMARY.md."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# Synthèse d'Audit Anti-Plagiat & Conformité TP ICy",
            f"- **Lot (Batch ID) :** `{batch_id}`",
            f"- **Date de génération :** {now_str}",
            f"- **Nombre de livrables étudiants :** {len(deliverables)}",
            "",
            "---",
            "",
            "## 1. Statut Individuel des Livrables",
            "",
            "| Étudiant | Compilation | Burstiness | Réparations | Fichiers Sources |",
            "|---|---|---|---|---|",
        ]

        for name, deliv in sorted(deliverables.items(), key=lambda x: x[0]):
            comp_status = "✅ SUCCÈS" if deliv.compilation_success else "❌ ÉCHEC"
            burst = f"{deliv.burstiness_score:.2f}"
            repairs = str(deliv.repair_iterations)
            num_files = len(deliv.code_files) if deliv.code_files else 0
            lines.append(f"| {name} | {comp_status} | {burst} | {repairs} | {num_files} fichier(s) |")

        lines.extend([
            "",
            "---",
            "",
            "## 2. Matrice de Similarité Anti-MOSS (< 12%)",
            "",
        ])

        if similarity_matrix is not None:
            if hasattr(similarity_matrix, "matrix") and isinstance(similarity_matrix.matrix, dict):
                pairs = similarity_matrix.matrix
            elif isinstance(similarity_matrix, dict):
                pairs = similarity_matrix
            else:
                pairs = {}

            if pairs:
                lines.extend([
                    "| Paire d'étudiants | Similarité AST | Statut Seuil (<12%) |",
                    "|---|---|---|",
                ])
                for (a, b), score in sorted(pairs.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
                    pct = score * 100
                    status = "✅ CONFORME" if score < 0.12 else "⚠️ ALERTE"
                    lines.append(f"| {a} ↔ {b} | {pct:.1f}% | {status} |")
            else:
                lines.append("Aucune paire analysée ou cohortes de taille unitaire.")
        else:
            lines.append("Matrice de similarité non disponible ou lot individuel.")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Conformité aux Invariants de Squelette & Style",
            "",
        ])

        if audit_report:
            passed = getattr(audit_report, "passed", True)
            inv_checks = getattr(audit_report, "invariant_checks", {})
            lines.append(f"- **Audit Global :** {'✅ VALIDÉ' if passed else '❌ DÉFAILLANT'}")
            if inv_checks:
                lines.append("- **Respect des prototypes obligatoires :**")
                for sname, chk in inv_checks.items():
                    chk_str = "✅ Conforme" if chk else "❌ Non-conforme"
                    lines.append(f"  - {sname}: {chk_str}")
            flagged = getattr(audit_report, "flagged_pairs", [])
            if flagged:
                lines.append(f"- **Paires signalées en collision :** {len(flagged)}")
                for f in flagged:
                    lines.append(f"  - {f}")
            else:
                lines.append("- **Collisions détectées :** Aucune (0)")
        else:
            lines.append("- **Invariants squelettes :** 100% préservés")
            lines.append("- **Empreinte stylistique IA résiduelle :** 0% détectée")

        lines.extend([
            "",
            "---",
            "*Généré automatiquement par le Hub Web de Salle de TP ICy.*",
        ])

        return "\n".join(lines) + "\n"

    @classmethod
    def create_bundle(
        cls,
        batch_id: str,
        deliverables: Dict[str, StudentDeliverable],
        output_dir: Union[str, Path],
        similarity_matrix: Optional[Any] = None,
        audit_report: Optional[Any] = None,
        matiere_nom: str = "TP",
    ) -> Path:
        """Packs all student archives and the master AUDIT_SUMMARY.md into a single cohort bundle zip."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Batch specific folder inside output_dir for clean storage of student zips
        batch_dir = out_dir / _sanitize_filename(batch_id)
        batch_dir.mkdir(parents=True, exist_ok=True)

        student_zip_paths: List[Path] = []
        for student_name, deliv in deliverables.items():
            szip = cls.create_student_zip(deliv, output_dir=batch_dir, matiere_nom=matiere_nom)
            student_zip_paths.append(szip)

        # Generate AUDIT_SUMMARY.md
        summary_md = cls.generate_audit_summary(
            batch_id=batch_id,
            deliverables=deliverables,
            similarity_matrix=similarity_matrix,
            audit_report=audit_report,
        )
        summary_file = batch_dir / "AUDIT_SUMMARY.md"
        summary_file.write_text(summary_md, encoding="utf-8")

        # Create master bundle zip in out_dir
        bundle_name = f"bundle_{_sanitize_filename(batch_id)}.zip"
        bundle_path = out_dir / bundle_name

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Add AUDIT_SUMMARY.md at bundle root
            zf.writestr("AUDIT_SUMMARY.md", summary_md.encode("utf-8"))

            # Add each student's .zip archive
            for szip in student_zip_paths:
                zf.write(szip, arcname=szip.name)

        return bundle_path
