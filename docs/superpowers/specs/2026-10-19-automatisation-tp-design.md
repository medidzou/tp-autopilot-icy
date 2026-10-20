# Conception Technique : Système d'Automatisation de TP & Stylisation Étudiante (ICy 3A)

**Date :** 19 Octobre 2026  
**Équipe Cible :** Groupe de 6 étudiants (3A ICy - Semestre 5)  
**Validation Empirique :** Workflow déjà éprouvé manuellement en séance réelle avec confrontation croisée de modèles (Gemini + Claude) et auto-audit impitoyable des cas de défaillance.  
**Statut :** Spécification Approuvée pour Planification  

---

## 1. Contexte & Intention (The Why)

En 3A ICy, les séances de Travaux Pratiques durent généralement 3 heures sur table (Langage C niveau 2, Java & POO, Programmation Système, Architecture Avancée, Bases de Données, Programmation Linéaire, Complexité). Les 6 membres du groupe sont présents simultanément dans la même salle et doivent rendre leur travail à la fin de la séance (en individuel ou en binômes).

L'automatisation brute pose des risques majeurs :
1. **Risque de collision / Plagiat intra-groupe (MOSS / JPlag) :** Si les 6 étudiants rendent une solution issue d'un même prompt, les arbres syntaxiques (AST) et les structures de code seront similaires, entraînant un flag de triche immédiat.
2. **Marqueurs de style IA (Perplexité & Burstiness) :** Vocabulaire artificiel, cadence métronomique de phrases, connecteurs formels redondants.
3. **Incohérence avec le syllabus ICy :** Utilisation de librairies hors programme non vues par les enseignants (Wilbaut, Anceau, etc.).
4. **Non-conformité de build & Exécution :** Rejet direct en cas de warning de compilation (`-Wall -Wextra -Werror`) ou de fuite mémoire sous Valgrind.

Le présent système automatise la chaîne complète en permettant à un étudiant de déposer le sujet ou l'archive de départ dès son ouverture à 14h00 sur une machine hôte en salle, pour déclencher la génération parallèle de **6 solutions rigoureusement divergentes**, personnalisées au style de chacun, vérifiées par compilation réelle et auditées par un dialogue croisé multi-modèles (Gemini / Claude).

---

## 2. Spécifications Fonctionnelles & Architecture de Performance

### 2.1. Ingestion de Sujet : Support du "Code Squelette"
- Le système accepte soit un document descriptif (PDF/Markdown), soit **une archive de code squelette** fournie par le professeur (fichiers `.c`, `.h`, `Makefile` avec des balises `/* TODO */`).
- **Verrou de signature :** Interdiction formelle de modifier les prototypes de fonctions, les types de retour, ou les structures imposées. L'IA n'intervient que dans le corps des fonctions à implémenter.

### 2.2. Optimisation en 2 Temps (Anti-Rate-Limit & Vitesse < 3 min)
Pour éviter de saturer les API (Erreurs 429) et de faire attendre l'équipe :
1. **Phase 1 - Noyau Algorithmique Commun (1 requête Gemini) :** Résolution brute de la logique de fond et des calculs mathématiques/système selon le syllabus.
2. **Phase 2 - Déclinaison Parallèle Légère (6 branches concurrentes) :** Chaque branche applique simultanément son approche de divergence, son empreinte stylistique, compile en local et passe l'audit de conformité.

### 2.3. Matrice de Divergence Anti-Collision Ciblée
La divergence ne s'applique que sur les **degrés de liberté autorisés** par le sujet :
- Choix de découpage en fonctions auxiliaires internes (`static`).
- Arithmétique de pointeurs vs indexation tableau.
- Nommage des variables intermédiaires selon les habitudes de l'étudiant.
- Ordre logique d'évaluation des cas simples.
- **Règle absolue :** Si le sujet impose une méthode spécifique (ex: *"résolution itérative sans récursion"*), cette contrainte est verrouillée et respectée par les 6 copies.
- Contrôle croisé AST (similarité inter-copies < 12%).

---

## 3. Humanisation & Détection IA : Maintien Absolu du Sens

### 3.1. Sanctuarisation Technique
- Tous les termes techniques (`malloc`, `free`, `pthread_mutex_t`, `O(n log n)`, `SQL`, `sémaphore`) sont sanctuarisés et intouchables.
- Aucun ajout artificiel de fautes d'orthographe ou de langage familier : le style vise la **prose sobre, directe et efficace d'un élève-ingénieur**.

### 3.2. Métriques Anti-Détection (Ciblage GPTZero / Turnitin)
- **Burstiness élevée :** Alternance volontaire de phrases courtes et de phrases explicatives détaillées.
- **Suppression des tics de LLM :** Bannissement des connecteurs pompeux (*"Il convient de noter", "En conclusion", "Non seulement... mais aussi"*).
- **Traces réelles :** Injection obligatoire des logs réels du terminal d'exécution (`stdout` / `stderr`) dans le compte-rendu pour attester que le code a tourné.

---

## 4. Pipeline & Validation d'Équipe (Salle de TP)

```
       [ Archive du Sujet déposée à 14h00 (.zip / code squelette / .pdf) ]
                                       │
                                       ▼
       ┌───────────────────────────────────────────────────────────────┐
       │ 1. Extraction Syllabus & Identification Matière (Notion ICy) │
       └───────────────────────────────┬───────────────────────────────┘
                                       │
                                       ▼
       ┌───────────────────────────────────────────────────────────────┐
       │ 2. Résolution du Noyau Algorithmique (Gemini) - 1 appel        │
       └───────────────────────────────┬───────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────┐                             ┌───────────────────────┐
│ Branche Étudiant 1    │      . . . (x6) . . .       │ Branche Étudiant 6    │
│ (Stratégie Alpha)     │                             │ (Stratégie Zeta)      │
├───────────────────────┤                             ├───────────────────────┤
│ 3. Déclinaison Code   │                             │ 3. Déclinaison Code   │
│ 4. Styliste & Humanize│                             │ 4. Styliste & Humanize│
│ 5. Compilation Locale │                             │ 5. Compilation Locale │
│    (gcc -Wall -Werror)│                             │    (gcc -Wall -Werror)│
│ 6. Audit Croisé       │                             │ 6. Audit Croisé       │
│    (Claude indépendant│                             │    (Claude indépendant│
└───────────┬───────────┘                             └───────────┬───────────┘
            │                                                     │
            └──────────────────────────┬──────────────────────────┘
                                       ▼
       ┌───────────────────────────────────────────────────────────────┐
       │ 7. Contrôle Croisé Anti-MOSS & Packaging                      │
       │    - Vérification similarité AST < 12%                        │
       │    - Bundle complet téléchargeable : 6 archives prêtes        │
       └───────────────────────────────────────────────────────────────┘
```

---

## 5. Composants Développés & Choix Techniques

1. **Kit CLI Local :** Skill Antigravity/Claude Code dans `.agents/skills/tp-autopilot/`.
2. **Hub Web Équipe :** Serveur léger Node.js/Python avec interface conforme à la maquette V2 (sélection Solo/Binômes, dropzone instantanée, vue d'avancement par membre, téléchargement unitaire ou groupé).
3. **Moteur d'Audit :** Claude évaluant la cohérence scientifique en priorité, puis la résistance statistique aux détecteurs.
4. **Base des Profils :** 6 dossiers `profiles/<nom>/` contenant le questionnaire d'étalonnage rapide (3 questions) et les textes de référence.
