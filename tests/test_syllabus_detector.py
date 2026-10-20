"""Tests for SyllabusDetector and ICy 3A course detection."""

import pytest
from src.syllabus.detector import CourseNotFoundError, SyllabusDetector
from src.syllabus.models import MatiereInfo


def test_detect_langage_c_matiere():
    """Verify detection of Langage C niveau 2 course as specified in brief."""
    detector = SyllabusDetector()
    subject_sample = "TP3: Allocation dynamique, pointeurs et structures en Langage C avec Makefile."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "langage_c"
    assert matiere.nom == "Langage C niveau 2"
    assert matiere.notebook_url.startswith("https://notebook.google.com/")


def test_detect_java_poo_matiere():
    """Verify detection of Java & POO."""
    detector = SyllabusDetector()
    subject_sample = "TP1 Java: Saisie avec Scanner, manipulation de tableaux et programmation orientée objet."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "java_poo"
    assert "Java" in matiere.nom
    assert matiere.notebook_url == "https://notebook.google.com/notebook/ccf1363b-5524-4dc2-918e-e540c1cbd715"
    assert matiere.compilation_rules["compiler"] == "javac"


def test_detect_prog_systeme_matiere():
    """Verify detection of Programmation Système (fork, tube, signaux, threads)."""
    detector = SyllabusDetector()
    subject_sample = "TP Système: Communication inter-processus via tube anonyme (pipe) et gestion de processus avec fork() et waitpid."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "prog_systeme"
    assert matiere.nom == "Programmation Système"
    assert matiere.notebook_url == "https://notebook.google.com/notebook/469511b3-6eaa-49ba-ba49-5127bc960269"
    assert "-pthread" in matiere.compilation_rules.get("flags", [])


def test_detect_archi_avancee_matiere():
    """Verify detection of Architecture Avancée."""
    detector = SyllabusDetector()
    subject_sample = "TP Architecture Avancée: Analyse du pipeline processeur, conflits de données et écriture de routines en assembleur NASM."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "archi_avancee"
    assert matiere.nom == "Architecture Avancée"
    assert matiere.notebook_url == "https://notebook.google.com/notebook/5b27e3a4-92b5-47a6-a594-dc32d26dcf27"


def test_detect_bdd_matiere():
    """Verify detection of Bases de Données."""
    detector = SyllabusDetector()
    subject_sample = "TP Base de Données: Création de schéma relationnel SQL avec clés étrangères et requêtes SELECT avec jointures."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "bdd"
    assert "Données" in matiere.nom
    assert matiere.notebook_url == "https://notebook.google.com/notebook/be17f448-f6a4-4c50-8af8-a67802c0d759"


def test_detect_prog_lineaire_matiere():
    """Verify detection of Programmation Linéaire."""
    detector = SyllabusDetector()
    subject_sample = "TP Optimisation: Résolution d'un problème de transport par l'algorithme du simplexe sous forme canonique."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "prog_lineaire"
    assert matiere.nom == "Programmation Linéaire"
    assert matiere.notebook_url == "https://notebook.google.com/notebook/7d7aec10-c4c6-4178-9dd6-7d29314506af"


def test_detect_complexite_matiere():
    """Verify detection of Complexité Algorithmique."""
    detector = SyllabusDetector()
    subject_sample = "TP Complexité: Étude asymptotique en grand O (O(n log n)), pire des cas et preuve de NP-complétude."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "complexite"
    assert matiere.nom == "Complexité"
    assert matiere.notebook_url == "https://notebook.google.com/notebook/814e812f-534b-4dff-88e9-88cf8eda1277"


def test_get_notebook_url():
    """Verify direct retrieval of NotebookLM URL by matiere ID."""
    detector = SyllabusDetector()
    url = detector.get_notebook_url("langage_c")
    assert url == "https://notebook.google.com/notebook/7d7aec10-c4c6-4178-9dd6-7d29314506af"

    url_java = detector.get_notebook_url("java_poo")
    assert url_java == "https://notebook.google.com/notebook/ccf1363b-5524-4dc2-918e-e540c1cbd715"


def test_get_notebook_url_invalid_raises():
    """Verify invalid matiere ID raises CourseNotFoundError (subclass of KeyError)."""
    detector = SyllabusDetector()
    with pytest.raises(CourseNotFoundError):
        detector.get_notebook_url("non_existent_matiere")
    with pytest.raises(KeyError):
        detector.get_notebook_url("non_existent_matiere")


def test_detect_matiere_unknown_raises():
    """Verify completely unrelated subject text raises ValueError."""
    detector = SyllabusDetector()
    with pytest.raises(ValueError):
        detector.detect_matiere("Recette de cuisine pour tarte aux pommes au caramel.")


def test_list_all_matieres():
    """Verify listing all 3A ICy subjects."""
    detector = SyllabusDetector()
    all_matieres = detector.list_matieres()
    ids = [m.id for m in all_matieres]
    assert "langage_c" in ids
    assert "java_poo" in ids
    assert "prog_systeme" in ids
    assert "archi_avancee" in ids
    assert "bdd" in ids
    assert "prog_lineaire" in ids
    assert "complexite" in ids
    assert len(all_matieres) >= 7


def test_get_matiere():
    """Verify get_matiere returns MatiereInfo and raises CourseNotFoundError."""
    detector = SyllabusDetector()
    m = detector.get_matiere("langage_c")
    assert isinstance(m, MatiereInfo)
    assert m.nom == "Langage C niveau 2"
    assert m.enseignant == "C. Wilbaut"

    with pytest.raises(CourseNotFoundError):
        detector.get_matiere("inconnue")
    with pytest.raises(KeyError):
        detector.get_matiere("inconnue")


def test_detect_archi_avancee_branchement_keyword():
    """Verify detection of Architecture Avancée using the branchement keyword."""
    detector = SyllabusDetector()
    sample = "TP: Étude des pénalités de branchement et de la prédiction de branchement dans le pipeline du processeur."
    matiere = detector.detect_matiere(sample)
    assert matiere.id == "archi_avancee"


def test_detect_with_unaccented_input():
    """Verify detection works even if the subject text lacks French accents."""
    detector = SyllabusDetector()
    sample = "tp complexite: analyse asymptotique, pire des cas et reduction polynomiale."
    matiere = detector.detect_matiere(sample)
    assert matiere.id == "complexite"

    sample_bdd = "tp bases de donnees: creation de tables et requetes avec cle etrangere."
    matiere_bdd = detector.detect_matiere(sample_bdd)
    assert matiere_bdd.id == "bdd"


def test_disambiguation_c_vs_prog_systeme():
    """Verify that a C project using fork/pipe is detected as prog_systeme rather than langage_c."""
    detector = SyllabusDetector()
    # Code in C but with fork and pipe -> System Programming
    sample_sys = "Ce TP en C consiste à créer un serveur multiprocessus avec fork(), pipe et synchronisation par mutex."
    matiere = detector.detect_matiere(sample_sys)
    assert matiere.id == "prog_systeme"

    # Code in C with dynamic memory and Makefile -> Langage C niveau 2
    sample_c = "Ce TP de programmation C porte sur l'allocation dynamique avec malloc/free, les listes chaînées et la compilation avec Makefile."
    matiere_c = detector.detect_matiere(sample_c)
    assert matiere_c.id == "langage_c"


def test_empty_or_whitespace_subject_raises():
    """Verify empty or whitespace-only subject text raises ValueError."""
    detector = SyllabusDetector()
    with pytest.raises(ValueError):
        detector.detect_matiere("")
    with pytest.raises(ValueError):
        detector.detect_matiere("   \n\t  ")


def test_custom_data_path_and_missing_file(tmp_path):
    """Verify SyllabusDetector can load from custom path and raises on missing file."""
    fake_file = tmp_path / "non_existent.json"
    with pytest.raises(FileNotFoundError):
        SyllabusDetector(data_path=fake_file)

