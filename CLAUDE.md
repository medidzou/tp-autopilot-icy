# CLAUDE.md — Instructions pour Claude Code (3A ICy)

Ce fichier guide automatiquement **Claude Code** dans ce projet.

## Contexte du Projet
Projet d'automatisation et de résolution de TPs d'école d'ingénieurs (3A Informatique & Cybersécurité - ICy).
L'équipe est composée de 6 étudiants organisés en 3 binômes officiels :
- **Binôme 1 :** Mehdi & Aymen
- **Binôme 2 :** Noah & Taha
- **Binôme 3 :** Malo & Rayyan

---

## Règle Absolue : Résolution Multi-Agents Autonome
Lorsque l'utilisateur soumet un sujet de TP (énoncé PDF, texte ou code squelette) :

> [!CRITICAL]
> **Ne JAMAIS générer les copies des binômes en une seule passe linéaire ou avec une structure identique.**
> Les profs et les détecteurs académiques (style Argon) traquent les matrices identiques, les ordres de contraintes copiés, et les commentaires jumeaux.

### Protocole Obligatoire :
1. **Étape 1 : Résolution du Noyau (Core Solver)**
   - Résoudre mathématiquement et techniquement chaque exercice/fonction.
   - Vérifier en local que le code tourne avec zéro erreur et zéro warning (`exit code 0`).
   - Respecter les contraintes spécifiques des bibliothèques de l'école (ex: `linprog` qui n'accepte que `(0, None)` en bornes).

2. **Étape 2 : Dérivation Décorrélée des 3 Binômes (Agents Distincts)**
   Générer les 3 copies avec une véritable divergence d'implémentation :
   - **Mehdi & Aymen :** Approche directe par blocs fonctionnels, variables standard du sujet, justification axée sur la saturation des ressources et les budgets.
   - **Noah & Taha :** Approche chronologique / temporelle (réordonnancement complet des matrices et contraintes), justification chiffrée sur les arbitrages et les coûts de possession.
   - **Malo & Rayyan :** Approche par regroupement alternatif (stocks d'abord, exclusions en tête), justification axée sur le coût d'opportunité et la rentabilité marginale.

3. **Étape 3 : Audit Adversarial Automatique (Rôle Argon)**
   Avant de présenter le travail à l'utilisateur, exécuter un audit impitoyable :
   - Vérifier qu'**aucune phrase d'explication ou commentaire** ($> 30$ caractères) n'est partagée mot pour mot entre deux binômes.
   - Éliminer **tous les marqueurs d'IA** :
     - Pas de tiret cadratin (`—`) dans le code ou les commentaires.
     - Pas de formatage artificiel `0.00` sur des entiers.
     - Pas de métacommentaires du genre *"# Contraintes ordonnées..."*.
     - Pas de clichés de transition LLM (*"Il convient de noter", "Force est de constater"*).
   - Vérifier le nommage strict des fichiers imposé par le sujet (ex: `TP1_NOM_Prenom.py`).

4. **Étape 4 : Boucle d'Auto-Correction Fermée**
   - Si un marqueur d'IA ou une ressemblance de structure est détectée, **corriger automatiquement en boucle sans attendre que l'utilisateur le demande**, jusqu'à ce que le résultat soit 100% propre, indétectable et exécutable.
