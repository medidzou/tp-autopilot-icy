# Automatisation TP & Stylisation Étudiante (ICy 3A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Développer un système complet d'automatisation de TP pour un groupe de 6 étudiants (3A ICy), capable de générer simultanément à partir d'un sujet ou code squelette 6 solutions fonctionnelles, rigoureusement divergentes (anti-plagiat MOSS), adaptées au style de chaque membre, compilées sans warning et auditées par un dialogue croisé multi-modèles (Gemini + Claude).

**Architecture:** Moteur central modulaire en Python orchestrant : (1) Ingestion sujet & code squelette, (2) Extraction syllabus ICy (Notion/NotebookLM), (3) Résolution du noyau commun (Gemini), (4) Matrice de divergence & humaniseur de style, (5) Validation de build stricte (`gcc -Wall -Werror`, `valgrind`), (6) Auditeur adversarial (Claude) avec contrôle croisé anti-MOSS, et (7) Hub Web local léger pour la salle de TP.

**Tech Stack:** Python 3.11+, FastAPI / Uvicorn, SQLite/JSON pour les profils, GCC / Make / Valgrind / Javac pour les builds locaux, Jinja2 / Tailwind CSS pour le Hub Web, Google GenAI SDK (Gemini) + Anthropic SDK (Claude).

**Spec:** [docs/superpowers/specs/2026-10-19-automatisation-tp-design.md](file:///C:/ICY/PROJET/docs/superpowers/specs/2026-10-19-automatisation-tp-design.md)

## Global Constraints

- Respect strict des prototypes de fonctions imposés par le code squelette du professeur (interdiction de modifier les signatures d'API).
- Sanctuarisation absolue des termes techniques et du vocabulaire scientifique (`malloc`, `free`, `pthread_mutex_t`, `O(n log n)`, `SQL`).
- Zéro warning de compilation en C (`gcc -Wall -Wextra -Werror -pedantic -std=c11`).
- Similarité inter-copies (Anti-MOSS AST) strictement inférieure à 12% entre les membres de l'équipe.
- Temps de génération total inférieur à 3 minutes pour le lot des 6 copies (optimisation en 2 phases : noyau résolu une fois, 6 déclinaisons légères).

## Review Focus

1. **Code squelette altéré :** L'IA modifie par erreur la signature d'une fonction imposée dans un fichier `.h` -> Le test de préservation d'AST doit rejeter tout diff touchant aux signatures d'origine.
2. **Rate Limit 429 API en pleine séance :** 6 appels lourds en simultané épuisent le quota -> Le plan force un pool de concurrence avec délai exponentiel et réutilisation du noyau commun.
3. **Fausse divergence violant le sujet :** Une consigne impose une boucle itérative et l'IA produit une récursion pour diverger -> Le module d'extraction de contraintes verrouille les impératifs du sujet comme invariants.
4. **Perte de sens lors de l'humanisation :** Une phrase d'explication perd son argument technique causal -> L'audit vérifie la préservation des mots-clés de causalité technique avant de valider.
5. **Absence d'un outil local (gcc, valgrind) sur le PC hôte :** Le script plante en cours de séance -> Un health check au démarrage vérifie la présence de tous les compilateurs nécessaires.

---

### Task 1: Gestionnaire des Profils Étudiants & Questionnaire d'Étalonnage

**Files:**
- Create: `src/profiles/manager.py`
- Create: `src/profiles/models.py`
- Test: `tests/test_profiles_manager.py`

**Interfaces:**
- Produces: `ProfileManager.get_profile(name: str) -> StudentProfile`, `ProfileManager.list_profiles() -> List[str]`, `ProfileManager.create_or_update_profile(name: str, calibration_answers: dict, samples: list[str]) -> StudentProfile`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profiles_manager.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profiles_manager.py -v`  
Expected: FAIL (ModuleNotFoundError ou ProfileManager not defined)

- [ ] **Step 3: Implement `StudentProfile` and `ProfileManager` in `src/profiles/`**

Créer `src/profiles/models.py` avec dataclass / Pydantic `StudentProfile` (nom, métriques de verbosité, réponses d'étalonnage, échantillons). Implémenter la persistance sur disque (dossiers `profiles/<nom>/` avec `profile.json`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_profiles_manager.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/profiles tests/test_profiles_manager.py
git commit -m "feat(profiles): add student profile manager and calibration storage"
```

---

### Task 2: Détection Matière & Référentiel Syllabus ICy 3A

**Files:**
- Create: `src/syllabus/detector.py`
- Create: `src/syllabus/data/mccc_icy.json`
- Test: `tests/test_syllabus_detector.py`

**Interfaces:**
- Consumes: None
- Produces: `SyllabusDetector.detect_matiere(subject_text: str) -> MatiereInfo`, `SyllabusDetector.get_notebook_url(matiere_id: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_syllabus_detector.py
from src.syllabus.detector import SyllabusDetector

def test_detect_langage_c_matiere():
    detector = SyllabusDetector()
    subject_sample = "TP3: Allocation dynamique, pointeurs et structures en Langage C avec Makefile."
    matiere = detector.detect_matiere(subject_sample)
    assert matiere.id == "langage_c"
    assert matiere.nom == "Langage C niveau 2"
    assert matiere.notebook_url.startswith("https://notebook.google.com/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_syllabus_detector.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `SyllabusDetector` and `mccc_icy.json`**

Encoder les matières de 3A ICy (Langage C, Java & POO, Programmation Système, Architecture Avancée, Bases de Données, Programmation Linéaire, Complexité) avec mots-clés, règles de compilation et liens NotebookLM extraits de Notion.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_syllabus_detector.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/syllabus tests/test_syllabus_detector.py
git commit -m "feat(syllabus): add ICy 3A subject detector and Notion NotebookLM mapping"
```

---

### Task 3: Ingestion de Sujet & Préservation de Code Squelette (`// TODO`)

**Files:**
- Create: `src/ingestion/parser.py`
- Create: `src/ingestion/skeleton.py`
- Test: `tests/test_skeleton_parser.py`

**Interfaces:**
- Consumes: None
- Produces: `SkeletonParser.extract_skeleton(zip_path: str) -> SkeletonProject`, `SkeletonProject.get_todo_locations() -> List[TodoSlot]`, `SkeletonProject.validate_signatures_preserved(modified_files: dict) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skeleton_parser.py
from src.ingestion.skeleton import SkeletonParser

def test_preserve_skeleton_signatures(tmp_path):
    parser = SkeletonParser()
    c_header = "int compute_checksum(const char *buffer, size_t len);\n"
    c_source = "int compute_checksum(const char *buffer, size_t len) {\n    /* TODO: implement */\n    return 0;\n}\n"
    
    project = parser.parse_files({"checksum.h": c_header, "checksum.c": c_source})
    assert len(project.todo_slots) == 1
    assert project.todo_slots[0].function_name == "compute_checksum"
    
    # Test valid implementation keeping signature
    valid_mod = {"checksum.c": "int compute_checksum(const char *buffer, size_t len) {\n    return 42;\n}\n"}
    assert project.validate_signatures(valid_mod) is True
    
    # Test invalid modification breaking signature
    invalid_mod = {"checksum.c": "int compute_checksum(int bad_param) { return 0; }"}
    assert project.validate_signatures(invalid_mod) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skeleton_parser.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `SkeletonParser` in `src/ingestion/skeleton.py`**

Implémenter l'analyseur syntaxique léger pour le C et Java qui repère les balises `TODO` et verrouille les prototypes des fonctions imposées.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skeleton_parser.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ingestion tests/test_skeleton_parser.py
git commit -m "feat(ingestion): add skeleton code parser and signature enforcement"
```

---

### Task 4: Matrice de Divergence Anti-Collision & Scoreur MOSS Inter-Copies

**Files:**
- Create: `src/divergence/matrix.py`
- Create: `src/divergence/similarity.py`
- Test: `tests/test_divergence_matrix.py`

**Interfaces:**
- Consumes: `List[StudentProfile]`
- Produces: `DivergenceMatrix.assign_strategies(students: List[str]) -> Dict[str, StrategyDirective]`, `SimilarityChecker.compute_pairwise_similarity(solutions: Dict[str, str]) -> Dict[Tuple[str, str], float]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_divergence_matrix.py
from src.divergence.matrix import DivergenceMatrix
from src.divergence.similarity import SimilarityChecker

def test_divergence_assigns_orthogonal_strategies():
    dm = DivergenceMatrix()
    students = ["Marc", "Thomas", "Sophie", "Julien", "Lea", "Alex"]
    strategies = dm.assign_strategies(students)
    assert len(strategies) == 6
    # S'assurer que les stratégies allouées sont distinctes
    paradigms = [s.primary_paradigm for s in strategies.values()]
    assert len(set(paradigms)) >= 4

def test_similarity_checker_detects_duplicate_code():
    checker = SimilarityChecker()
    code_a = "int sum(int *arr, int n) { int s = 0; for(int i=0; i<n; i++) s += arr[i]; return s; }"
    code_b = "int total(int *t, int len) { int acc = 0; for(int j=0; j<len; j++) acc += t[j]; return acc; }"
    code_diff = "int sum_rec(int *a, int n) { if (n <= 0) return 0; return a[0] + sum_rec(a+1, n-1); }"
    
    sim_high = checker.calculate_ast_similarity(code_a, code_b)
    sim_low = checker.calculate_ast_similarity(code_a, code_diff)
    assert sim_high > 0.70  # Même structure de boucle
    assert sim_low < 0.30   # Itératif vs récursif
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_divergence_matrix.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `DivergenceMatrix` and `SimilarityChecker` in `src/divergence/`**

Implémenter l'attribution de stratégies (pointeurs vs index, statiques vs modulaires, itératif vs accumulateur) et le calcul de similarité par n-grammes de tokens normalisés.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_divergence_matrix.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/divergence tests/test_divergence_matrix.py
git commit -m "feat(divergence): add anti-MOSS strategy matrix and AST similarity checker"
```

---

### Task 5: Moteur d'Humanisation Technique & Scoreur Statistique (Burstiness)

**Files:**
- Create: `src/humanizer/burstiness.py`
- Create: `src/humanizer/cleaner.py`
- Test: `tests/test_humanizer.py`

**Interfaces:**
- Consumes: `StudentProfile`
- Produces: `BurstinessScorer.calculate_score(text: str) -> float`, `HumanizerCleaner.clean_ai_tells(text: str, preserved_terms: set) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_humanizer.py
from src.humanizer.burstiness import BurstinessScorer
from src.humanizer.cleaner import HumanizerCleaner

def test_clean_ai_tells_and_preserve_technical_terms():
    cleaner = HumanizerCleaner()
    ai_text = "Il convient de noter que l'utilisation de malloc est essentielle pour allouer le tableau. En conclusion, cette approche est optimale."
    sanctuary = {"malloc", "tableau"}
    
    cleaned = cleaner.clean_ai_tells(ai_text, preserved_terms=sanctuary)
    assert "Il convient de noter que" not in cleaned
    assert "En conclusion" not in cleaned
    assert "malloc" in cleaned
    assert "tableau" in cleaned

def test_burstiness_scorer():
    scorer = BurstinessScorer()
    # Texte artificiel régulier (basse burstiness)
    monotone = "La fonction alloue la mémoire. Le pointeur est vérifié ensuite. La boucle traite chaque élément. La mémoire est libérée après."
    # Texte humain dynamique (haute burstiness)
    bursty = "On alloue la mémoire avec malloc. S'il n'y a plus de place sur le tas, la fonction renvoie NULL immédiatement. Ensuite on boucle."
    
    assert scorer.calculate_sentence_variance(bursty) > scorer.calculate_sentence_variance(monotone)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_humanizer.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `BurstinessScorer` and `HumanizerCleaner`**

Supprimer la liste noire de connecteurs d'IA, sanctuariser les termes techniques passés en argument, et calculer l'écart-type de longueur des phrases.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_humanizer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/humanizer tests/test_humanizer.py
git commit -m "feat(humanizer): add technical term sanctuarization and burstiness evaluator"
```

---

### Task 6: Exécuteur de Build Strict & Capture de Traces Réelles

**Files:**
- Create: `src/builder/executor.py`
- Test: `tests/test_builder_executor.py`

**Interfaces:**
- Consumes: None
- Produces: `BuildExecutor.build_and_test(project_dir: str, matiere_id: str) -> BuildResult`

- [x] **Step 1: Write the failing test**

```python
# tests/test_builder_executor.py
from src.builder.executor import BuildExecutor

def test_c_strict_build_success(tmp_path):
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\nclean:\n\trm -f test_bin\n"
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)
    
    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is True
    assert result.warnings_count == 0

def test_c_strict_build_fails_on_warning(tmp_path):
    executor = BuildExecutor()
    # Code avec variable inutilisée provoquant une erreur avec -Werror
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\n"
    c_code = "int main(void) { int unused = 42; return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)
    
    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is False
    assert "error: unused variable" in result.stderr
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_builder_executor.py -v`  
Expected: FAIL

- [x] **Step 3: Implement `BuildExecutor` in `src/builder/executor.py`**

Exécution des commandes `make all`, capture des codes de retour et des logs `stdout`/`stderr`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_builder_executor.py -v`  
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/builder tests/test_builder_executor.py
git commit -m "feat(builder): add strict -Wall -Werror build runner and stdout capture"
```

---

### Task 7: Orchestrateur de Lot Parallèle & Boucle d'Audit Adversarial

**Files:**
- Create: `src/orchestrator/pipeline.py`
- Create: `src/orchestrator/audit.py`
- Test: `tests/test_pipeline_orchestrator.py`

**Interfaces:**
- Consumes: `ProfileManager`, `SkeletonParser`, `DivergenceMatrix`, `BuildExecutor`
- Produces: `BatchPipeline.run_batch(subject_path: str, student_names: List[str]) -> BatchResult`

- [x] **Step 1: Write the failing test**

```python
# tests/test_pipeline_orchestrator.py
from unittest.mock import MagicMock
from src.orchestrator.pipeline import BatchPipeline

def test_pipeline_runs_core_then_branches():
    mock_llm_core = MagicMock(return_value={"core_algorithm": "valid_logic"})
    mock_llm_branch = MagicMock(return_value={"code": "divergent_code", "report": "rapport"})
    pipeline = BatchPipeline(core_solver=mock_llm_core, branch_solver=mock_llm_branch)
    
    result = pipeline.execute_session(
        subject_text="TP3 Langage C",
        student_names=["Marc", "Thomas"]
    )
    assert result.success is True
    assert len(result.student_deliverables) == 2
    # Vérifier que le solveur central n'a été appelé qu'une seule fois
    assert mock_llm_core.call_count == 1
    # Et les branches appelées pour chaque élève
    assert mock_llm_branch.call_count == 2
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_orchestrator.py -v`  
Expected: FAIL

- [x] **Step 3: Implement `BatchPipeline` and `AuditLoop`**

Mettre en place l'orchestration en deux temps (noyau commun &rarr; N branches parallèles), l'intégration de la validation de build et le contrôle croisé anti-MOSS.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_orchestrator.py -v`  
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/orchestrator tests/test_pipeline_orchestrator.py
git commit -m "feat(orchestrator): implement two-phase batch generator with adversarial audit"
```

---

### Task 8: Hub Web de Salle de TP & Packaging des Archives (.ZIP)

**Files:**
- Create: `src/web/app.py`
- Create: `src/web/templates/index.html`
- Create: `src/web/packaging.py`
- Test: `tests/test_web_endpoints.py`

**Interfaces:**
- Consumes: `BatchPipeline`
- Produces: FastAPI Web Server (`POST /api/tp/submit`, `GET /api/tp/download/{batch_id}`, `GET /api/tp/download/{batch_id}/{student}`)

- [x] **Step 1: Write the failing test**

```python
# tests/test_web_endpoints.py
from fastapi.testclient import TestClient
from src.web.app import app

client = TestClient(app)

def test_get_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "TP AutoPilot" in response.text
    assert "Marc" in response.text

def test_packaging_bundle(tmp_path):
    from src.web.packaging import BundlePackager
    packager = BundlePackager()
    bundle_zip = packager.create_bundle(
        batch_id="batch_123",
        deliverables={"Marc": tmp_path, "Thomas": tmp_path},
        output_dir=tmp_path
    )
    assert bundle_zip.endswith(".zip")
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_endpoints.py -v`  
Expected: FAIL

- [x] **Step 3: Implement Web App and BundlePackager**

Développer l'application FastAPI servant l'interface HTML/Tailwind conforme à la maquette validée (`batch-generation.html`), la gestion de la dropzone, le suivi WebSocket de l'avancement, et la création de l'archive ZIP groupée.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_endpoints.py -v`  
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/web tests/test_web_endpoints.py
git commit -m "feat(web): add classroom web hub dashboard and multi-student bundle packager"
```

