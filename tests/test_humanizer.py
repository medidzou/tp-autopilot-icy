"""Tests for HumanizerCleaner and BurstinessScorer (Task 5)."""

import pytest
from src.profiles.models import StudentProfile
from src.humanizer.burstiness import BurstinessScorer
from src.humanizer.cleaner import (
    HumanizerCleaner,
    SanctuaryViolationError,
    DEFAULT_PRESERVED_TERMS,
)


def test_clean_ai_tells_and_preserve_technical_terms():
    cleaner = HumanizerCleaner()
    ai_text = (
        "Il convient de noter que l'utilisation de malloc est essentielle pour allouer le tableau. "
        "En conclusion, cette approche est optimale."
    )
    sanctuary = {"malloc", "tableau"}

    cleaned = cleaner.clean_ai_tells(ai_text, preserved_terms=sanctuary)
    assert "Il convient de noter que" not in cleaned
    assert "En conclusion" not in cleaned
    assert "malloc" in cleaned
    assert "tableau" in cleaned


def test_burstiness_scorer():
    scorer = BurstinessScorer()
    # Texte artificiel régulier (basse burstiness)
    monotone = (
        "La fonction alloue la mémoire. "
        "Le pointeur est vérifié ensuite. "
        "La boucle traite chaque élément. "
        "La mémoire est libérée après."
    )
    # Texte humain dynamique (haute burstiness)
    bursty = (
        "On alloue la mémoire avec malloc. "
        "S'il n'y a plus de place sur le tas, la fonction renvoie NULL immédiatement. "
        "Ensuite on boucle."
    )

    assert scorer.calculate_sentence_variance(bursty) > scorer.calculate_sentence_variance(monotone)


def test_burstiness_scorer_calculate_score_and_ttr():
    scorer = BurstinessScorer()
    text = (
        "On teste le module. "
        "Lorsque la charge augmente considérablement sur le serveur de calcul distribué, "
        "plusieurs threads concurrents se disputent l'accès aux sémaphores système. "
        "C'est rapide."
    )
    score = scorer.calculate_score(text)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0

    ttr = scorer.calculate_ttr(text)
    assert isinstance(ttr, float)
    assert 0.0 < ttr <= 1.0


def test_cleaner_multiple_ai_cliches():
    cleaner = HumanizerCleaner()
    text = (
        "Il est important de noter que pthread_mutex_lock évite les courses. "
        "Il convient de souligner que la libération avec free est indispensable. "
        "En somme, le programme s'exécute sans fuite mémoire."
    )
    sanctuary = {"pthread_mutex_lock", "free"}
    cleaned = cleaner.clean_ai_tells(text, preserved_terms=sanctuary)

    assert "Il est important de noter que" not in cleaned
    assert "Il convient de souligner que" not in cleaned
    assert "En somme" not in cleaned
    assert "pthread_mutex_lock" in cleaned
    assert "free" in cleaned


def test_cleaner_preserves_complex_technical_symbols():
    cleaner = HumanizerCleaner()
    text = (
        "Il va sans dire que la complexité O(n log n) de qsort est meilleure que O(n^2). "
        "En résumé, nous utilisons pthread_mutex_t pour synchroniser."
    )
    sanctuary = {"O(n log n)", "O(n^2)", "pthread_mutex_t"}
    cleaned = cleaner.clean_ai_tells(text, preserved_terms=sanctuary)

    assert "Il va sans dire que" not in cleaned
    assert "En résumé" not in cleaned
    assert "O(n log n)" in cleaned
    assert "O(n^2)" in cleaned
    assert "pthread_mutex_t" in cleaned


def test_burstiness_against_student_profile():
    scorer = BurstinessScorer()
    profile = StudentProfile(
        name="Marc",
        calibration_answers={
            "explication_concept": "Un pointeur stocke une adresse. On alloue avec malloc.",
        },
        samples=[
            "On alloue le tableau avec malloc puis on itère sur les éléments.",
            "Si NULL alors on quitte direct.",
        ],
    )
    profile.refresh_metrics()

    candidate_text = (
        "On réserve la mémoire avec malloc. "
        "Si le pointeur reçu est NULL on sort immédiatement sans continuer le traitement. "
        "Puis on libère tout."
    )
    metrics = scorer.calculate_metrics(candidate_text)
    assert "sentence_variance" in metrics
    assert "ttr" in metrics
    assert "mean_sentence_length" in metrics

    fit_score = scorer.evaluate_profile_fit(candidate_text, profile)
    assert isinstance(fit_score, float)
    assert 0.0 <= fit_score <= 1.0


def test_cleaner_empty_and_whitespace():
    cleaner = HumanizerCleaner()
    assert cleaner.clean_ai_tells("") == ""
    assert cleaner.clean_ai_tells("   ") == ""
    assert cleaner.clean_markdown_formatting("") == ""


def test_cleaner_english_ai_tells():
    cleaner = HumanizerCleaner()
    text = (
        "It is important to note that malloc returns a void pointer. "
        "Furthermore, free must be called to prevent memory leaks. "
        "In conclusion, the execution is safe."
    )
    cleaned = cleaner.clean_ai_tells(text, preserved_terms={"malloc", "free"})
    assert "It is important to note that" not in cleaned
    assert "Furthermore" not in cleaned
    assert "In conclusion" not in cleaned
    assert "malloc" in cleaned
    assert "free" in cleaned


def test_cleaner_chat_fluff_and_markdown_cleaning():
    cleaner = HumanizerCleaner()
    dirty_report = (
        "Voici la solution demandée :\n\n"
        "Certainement !\n"
        "L'algorithme utilise un tableau statique de pointeurs.\n\n"
        "J'espère que cette explication vous sera utile. N'hésitez pas si vous avez des questions."
    )
    fluff_free = cleaner.clean_markdown_formatting(dirty_report)
    assert "Voici la solution demandée" not in fluff_free
    assert "Certainement !" not in fluff_free
    assert "J'espère que cette explication" not in fluff_free
    assert "N'hésitez pas" not in fluff_free
    assert "L'algorithme utilise un tableau statique de pointeurs." in fluff_free


def test_cleaner_inject_execution_trace():
    cleaner = HumanizerCleaner()
    base_text = "Le programme compile et s'exécute correctement."
    stdout = "Test 1: OK (valeur = 42)\nTest 2: OK (tableau trié)"
    stderr = "Valgrind: 0 errors from 0 contexts (suppressed: 0 from 0)"

    with_trace = cleaner.inject_execution_trace(base_text, stdout=stdout, stderr=stderr)
    assert base_text in with_trace
    assert "### Trace d'Exécution Réelle (Terminal)" in with_trace
    assert "Test 1: OK" in with_trace
    assert "Valgrind: 0 errors" in with_trace


def test_cleaner_humanize_report_full_pipeline():
    cleaner = HumanizerCleaner()
    raw_ai_report = (
        "Voici l'explication du TP :\n\n"
        "Il convient de noter que l'allocation avec malloc garantit un bloc continu sur le tas. "
        "En conclusion, l'espace mémoire est totalement libéré par free."
    )
    sanctuary = {"malloc", "free", "tas"}
    logs = "All tests passed. Exit code 0."

    humanized = cleaner.humanize_report(
        report_text=raw_ai_report,
        preserved_terms=sanctuary,
        execution_logs=logs,
    )
    assert "Voici l'explication" not in humanized
    assert "Il convient de noter que" not in humanized
    assert "En conclusion" not in humanized
    assert "malloc" in humanized
    assert "free" in humanized
    assert "tas" in humanized
    assert "All tests passed" in humanized


def test_cleaner_verify_sanctuary_preservation():
    cleaner = HumanizerCleaner()
    orig = "On appelle malloc et free."
    cleaned_good = "On appelle malloc et free proprement."
    cleaned_bad = "On appelle une fonction d'allocation."

    assert cleaner.verify_sanctuary_preservation(cleaned_good, orig, {"malloc", "free"}) is True
    assert cleaner.verify_sanctuary_preservation(cleaned_bad, orig, {"malloc", "free"}) is False


def test_burstiness_scorer_abbreviations_and_decimals():
    scorer = BurstinessScorer()
    text = (
        "Le coefficient vaut 3.14 environ. "
        "On teste le code dans main.c avec gcc etc. pour vérifier la conformité. "
        "Fin du test."
    )
    sentences = scorer.split_sentences(text)
    # Should not split on 3.14, main.c, or etc.
    assert len(sentences) == 3
    assert "3.14" in sentences[0]
    assert "main.c" in sentences[1]
    assert "etc." in sentences[1]


def test_burstiness_scorer_is_robotic_and_suggestions():
    scorer = BurstinessScorer()
    monotone = (
        "La fonction lit le fichier. "
        "Le buffer stocke la ligne. "
        "La boucle itère sans cesse. "
        "Le fichier ferme sans délai."
    )
    assert scorer.is_robotic_cadence(monotone, min_variance=3.0) is True
    suggestions = scorer.suggest_cadence_fixes(monotone)
    assert len(suggestions) > 0
    assert "Cadence trop monotone" in suggestions[0]


def test_burstiness_scorer_empty_and_edge_cases():
    scorer = BurstinessScorer()
    assert scorer.calculate_sentence_variance("") == 0.0
    assert scorer.calculate_sentence_variance("   ") == 0.0
    assert scorer.calculate_sentence_std_dev("") == 0.0
    assert scorer.calculate_ttr("") == 0.0
    assert scorer.calculate_score("") == 0.0

    single = "Une seule phrase dans ce document."
    assert scorer.calculate_sentence_variance(single) == 0.0
    score_single = scorer.calculate_score(single)
    assert 0.0 <= score_single <= 1.0


def test_default_preserved_terms_included():
    cleaner = HumanizerCleaner()
    text = "Il convient de noter que pthread_mutex_t protège la ressource."
    # Without explicitly passing pthread_mutex_t in preserved_terms, default preserved terms protect it
    cleaned = cleaner.clean_ai_tells(text)
    assert "Il convient de noter que" not in cleaned
    assert "pthread_mutex_t" in cleaned


# --- Tests for Review Fixes (Round 1) ---

def test_words_ending_in_al_do_not_suppress_sentence_splits():
    """Critical fix 1: Words ending in '-al.' (optimal., terminal., signal.) must not

    be falsely captured by abbreviation 'al.' and must split sentences normally.
    """
    scorer = BurstinessScorer()
    text = (
        "Le résultat de l'algorithme est optimal. "
        "La sortie s'affiche sur le terminal. "
        "Le processus reçoit le bon signal. "
        "L'article de Dupont et al. confirme cette observation."
    )
    sentences = scorer.split_sentences(text)
    # Should correctly split into 4 sentences
    assert len(sentences) == 4
    assert sentences[0] == "Le résultat de l'algorithme est optimal."
    assert sentences[1] == "La sortie s'affiche sur le terminal."
    assert sentences[2] == "Le processus reçoit le bon signal."
    assert "Dupont et al." in sentences[3]


def test_cleaner_expanded_academic_connectors():
    """Important fix 2: Expanded French academic connector blacklist."""
    cleaner = HumanizerCleaner()
    text = (
        "De surcroît, le temps d'exécution est réduit. "
        "Par ailleurs, la mémoire allouée avec malloc est continue. "
        "Dès lors, les accès sont optimisés. "
        "En outre, le compilateur gcc n'émet aucun warning. "
        "D'une part le verrou est posé, d'autre part la variable est mise à jour. "
        "Qui plus est, la solution respecte le sujet."
    )
    sanctuary = {"malloc", "gcc"}
    cleaned = cleaner.clean_ai_tells(text, preserved_terms=sanctuary)

    assert "De surcroît" not in cleaned
    assert "Par ailleurs" not in cleaned
    assert "Dès lors" not in cleaned
    assert "En outre" not in cleaned
    assert "D'une part" not in cleaned
    assert "Qui plus est" not in cleaned
    assert "malloc" in cleaned
    assert "gcc" in cleaned


def test_cleaner_non_seulement_mais_aussi():
    """Important fix 2: Non seulement... mais aussi / Not only... but also."""
    cleaner = HumanizerCleaner()
    fr_text = (
        "Non seulement malloc réserve le bloc mémoire sur le tas, "
        "mais aussi free garantit l'absence de fuite."
    )
    fr_cleaned = cleaner.clean_ai_tells(fr_text, preserved_terms={"malloc", "free", "tas"})
    assert "Non seulement" not in fr_cleaned
    assert "mais aussi" not in fr_cleaned
    assert "malloc" in fr_cleaned
    assert "free" in fr_cleaned
    assert "tas" in fr_cleaned

    en_text = (
        "Not only malloc allocates the buffer on the heap, "
        "but also free prevents memory corruption."
    )
    en_cleaned = cleaner.clean_ai_tells(en_text, preserved_terms={"malloc", "free", "heap"})
    assert "Not only" not in en_cleaned
    assert "but also" not in en_cleaned
    assert "malloc" in en_cleaned
    assert "free" in en_cleaned


def test_cleaner_preamble_vs_body_text_retention():
    r"""Important fix 3: Anchor preamble stripping to document start (\A),

    preserving legitimate section introductions within the report body.
    """
    cleaner = HumanizerCleaner()
    report = (
        "Voici la solution demandée :\n\n"
        "### Section 1: Analyse Algorithmique\n"
        "L'implémentation est optimisée.\n\n"
        "Voici les résultats du benchmark :\n"
        "- Test 1 : 12ms\n"
        "- Test 2 : 14ms"
    )
    cleaned = cleaner.clean_markdown_formatting(report)
    # The document-level opening preamble must be stripped
    assert "Voici la solution demandée :" not in cleaned
    # The legitimate section intro in the body must be preserved
    assert "Voici les résultats du benchmark :" in cleaned
    assert "Test 1 : 12ms" in cleaned


def test_sanctuary_violation_error_raised():
    """Minor fix 4: Raise explicit SanctuaryViolationError when a sanctuary term is lost."""
    cleaner = HumanizerCleaner()

    # Monkey-patch internal method or provide text where cleaner could drop term
    # cleaner with a custom tell that targets a technical word if not protected:
    # Here we simulate dropping by passing a custom cleaner that somehow drops the term
    class FaultyCleaner(HumanizerCleaner):
        def clean_ai_tells(self, text, preserved_terms=None):
            return "Texte altéré sans le mot magique."

    faulty = FaultyCleaner()
    with pytest.raises(SanctuaryViolationError) as exc_info:
        faulty.humanize_report(
            report_text="Utilisation de pthread_mutex_t essentielle.",
            preserved_terms={"pthread_mutex_t"},
        )
    assert "Sanctuary violation" in str(exc_info.value)
    assert "pthread_mutex_t" in str(exc_info.value)


def test_burstiness_empty_text_is_robotic_consistent():
    """Minor fix 5: In calculate_metrics(''), is_robotic is False to match is_robotic_cadence('')."""
    scorer = BurstinessScorer()
    metrics = scorer.calculate_metrics("")
    assert metrics["is_robotic"] is False
    assert scorer.is_robotic_cadence("") is False
