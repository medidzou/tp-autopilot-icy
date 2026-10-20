import pytest
from src.profiles.manager import ProfileManager
from src.profiles.models import StudentProfile


def test_create_and_load_student_profile(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    profile = mgr.create_or_update_profile(
        name="Marc",
        calibration_answers={
            "explication_concept": "Un pointeur c'est une variable qui stocke une adresse mémoire.",
            "style_code": "J'utilise souvent snake_case et des boucles while simples."
        },
        samples=["On alloue le tableau avec malloc puis on itère sur les éléments."]
    )
    assert isinstance(profile, StudentProfile)
    assert profile.name == "Marc"
    loaded = mgr.get_profile("Marc")
    assert loaded.name == "Marc"
    assert "malloc" in loaded.samples[0]


def test_list_profiles_empty_and_populated(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    assert mgr.list_profiles() == []

    mgr.create_or_update_profile(name="Marc", calibration_answers={}, samples=["Sample 1"])
    mgr.create_or_update_profile(name="Alice", calibration_answers={}, samples=["Sample 2"])

    profiles = mgr.list_profiles()
    assert profiles == ["Alice", "Marc"]


def test_create_or_update_existing_profile(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    mgr.create_or_update_profile(
        name="Marc",
        calibration_answers={"style_code": "snake_case"},
        samples=["Premier exemple"]
    )

    # Mise a jour du profil avec de nouveaux echantillons et reponses
    updated = mgr.create_or_update_profile(
        name="Marc",
        calibration_answers={"style_code": "camelCase", "gestion_erreurs": "assert()"},
        samples=["Premier exemple", "Deuxième exemple avec malloc"]
    )
    assert updated.calibration_answers["style_code"] == "camelCase"
    assert len(updated.samples) == 2

    # Verifier la persistance apres rechargement
    reloaded = mgr.get_profile("Marc")
    assert reloaded.calibration_answers["style_code"] == "camelCase"
    assert len(reloaded.samples) == 2


def test_get_nonexistent_profile_raises_not_found(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        mgr.get_profile("Inconnu")


def test_verbosity_metrics_computed(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    profile = mgr.create_or_update_profile(
        name="Thomas",
        calibration_answers={"explication_concept": "Un thread partage l'espace memoire."},
        samples=["Nous creons les threads avec pthread_create. Chaque thread execute la fonction worker."]
    )
    assert "avg_sentence_length" in profile.verbosity_metrics
    assert profile.verbosity_metrics["sample_count"] == 1


def test_delete_profile(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    mgr.create_or_update_profile(name="Sarah", calibration_answers={}, samples=[])
    assert mgr.profile_exists("Sarah") is True
    assert mgr.delete_profile("Sarah") is True
    assert mgr.profile_exists("Sarah") is False
    assert mgr.delete_profile("Sarah") is False


def test_unicode_accents_preserved(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    answer = "L'allocation dynamique avec malloc évite d'encombrer la pile d'exécution. Ça permet de gérer la mémoire."
    sample = "Voici un algorithme récursif avec condition d'arrêt immédiate."
    profile = mgr.create_or_update_profile(
        name="Éléonore",
        calibration_answers={"explication_concept": answer},
        samples=[sample]
    )
    loaded = mgr.get_profile("Éléonore")
    assert loaded.name == "Éléonore"
    assert loaded.calibration_answers["explication_concept"] == answer
    assert loaded.samples[0] == sample


def test_empty_profile_metrics(tmp_path):
    mgr = ProfileManager(storage_dir=tmp_path)
    profile = mgr.create_or_update_profile(name="Vide", calibration_answers={}, samples=[])
    assert profile.verbosity_metrics["sample_count"] == 0
    assert profile.verbosity_metrics["total_words"] == 0
    assert profile.verbosity_metrics["avg_sentence_length"] == 0.0

