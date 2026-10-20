# TP AutoPilot - Promotion 3A ICy

> **Solveur de TP automatisé, personnalisation stylistique par étudiant et audit anti-plagiat (Anti-MOSS < 12%) pour une équipe de 6 étudiants-ingénieurs.**

---

## 🎯 Objectif du Projet

Lors des séances de Travaux Pratiques (TP) en 3A ICy (Langage C, Programmation Système, Java/POO, Architecture Avancée, Bases de Données, Recherche Opérationnelle), l'équipe de 6 étudiants doit rendre des travaux individuels ou en binômes pour le même sujet.

Ce système permet de :
1. **Ingérer le sujet de TP** : texte brut, PDF ou archive squelette avec `/* TODO */`.
2. **Respecter strictement les prototypes de fonctions** imposés par les enseignants (zéro altération des signatures d'API).
3. **Résoudre en 2 temps (Architecture Two-Phase)** :
   - *Phase 1 (Noyau commun)* : Résolution algorithmique du problème en un seul appel (évite les rate-limits API 429 et divise le coût par 6).
   - *Phase 2 (Branches parallèles)* : Dérivation simultanée des 6 copies avec styles de programmation orthogonaux et calibrations personnelles.
4. **Garantir une divergence Anti-MOSS < 12%** : vérification AST et n-grams simulant les moteurs anti-plagiat académiques (MOSS / JPlag) avec ré-aiguillage automatique en cas de risque de collision.
5. **Humaniser les comptes-rendus** : sanctuarisation absolue du vocabulaire scientifique (`malloc`, `free`, `pthread_mutex_t`, `O(n log n)`), suppression de 135+ connecteurs pompeux d'IA, et évaluation statistique du rythme (burstiness).
6. **Vérifier les builds stricts** : compilation C sans aucun avertissement (`gcc -Wall -Wextra -Werror -pedantic -std=c11`), Java (`javac`), Python (`pytest`), et capture des traces réelles pour insertion dans le `RAPPORT.md`.
7. **Hub Web de Salle de TP** : tableau de bord local en réseau (`http://localhost:8000`), support Solo (6 copies) et Binôme (3x2), cartes de progression en temps réel, et téléchargement 1-clic du **Master Bundle ZIP**.

---

## 🚀 Démarrage Rapide

### 1. Installation des dépendances

```bash
pip install -r requirements.txt
```

### 2. Lancement du Hub Web

- **Option A (1 double-clic sous Windows)** : double-cliquez sur `lancer_tp.bat`.
- **Option B (Ligne de commande)** :
  ```bash
  python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload
  ```

Ouvrez votre navigateur sur : **`http://localhost:8000`**  
*(Les autres PC de la salle connectés au même réseau peuvent y accéder via `http://[IP_DU_SERVEUR]:8000`)*.

---

## 🧪 Tests & Qualité

La suite comprend **132 tests automatisés** couvrant l'ensemble des modules :

```bash
pytest tests/ -v
```

Tous les tests doivent être au vert (`132 passed`).

---

## 🏗️ Structure du Projet

```text
├── docs/superpowers/
│   ├── specs/2026-10-19-automatisation-tp-design.md   # Spécification d'architecture complète
│   └── plans/2026-10-19-automatisation-tp.md          # Plan d'implémentation & TDD
├── src/
│   ├── syllabus/        # Détection automatique de la matière ICy & MCCC
│   ├── profiles/        # Profils et calibrations des 6 étudiants
│   ├── ingestion/       # Parsing de squelettes & vérification des prototypes
│   ├── divergence/      # Matrice de divergence & scoreur de similarité MOSS
│   ├── humanizer/       # Nettoyeur d'IA, sanctuarisation & burstiness
│   ├── builder/         # Exécuteur de build strict (gcc, javac, pytest)
│   ├── orchestrator/    # Pipeline 2-phases & boucle d'audit adversarial
│   └── web/             # Dashboard FastAPI, templates Tailwind & packager ZIP
├── tests/               # 132 tests unitaires et d'intégration
├── lancer_tp.bat        # Lanceur 1-clic pour Windows
├── requirements.txt     # Dépendances Python
└── README.md            # Ce fichier
```

---

## 💡 Guide pour Claude Max (Pistes d'Amélioration)

Si vous explorez ou améliorez ce projet avec **Claude Max / Claude Code** :

1. **Intégration d'API LLM réelles** : Le noyau actuel fournit des résolveurs mock/stub calibrés pour les tests et la structure. Vous pouvez brancher `anthropic`, `google-genai` ou `ollama` (local) dans `src/orchestrator/pipeline.py` (`_run_core_solver` et `_generate_student_branch`).
2. **WebSocket natif pour le Hub Web** : Remplacer le polling HTTP actuel dans `src/web/templates/index.html` par un flux WebSocket temps réel pour l'animation des jauges.
3. **Support de Langages Additionnels** : Étendre `src/builder/executor.py` pour supporter `make valgrind` sous WSL2 ou Docker, ainsi que Rust (`cargo`).
4. **Consultation de la Spec** : Lisez [`docs/superpowers/specs/2026-10-19-automatisation-tp-design.md`](docs/superpowers/specs/2026-10-19-automatisation-tp-design.md) pour retrouver tous les choix de conception détaillés.
