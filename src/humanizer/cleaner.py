"""Humanizer Cleaner: removes AI tells and cliches while sanctuarizing technical terms."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple
from src.profiles.models import StudentProfile


class SanctuaryViolationError(Exception):
    """Raised when a protected technical term is inadvertently modified or dropped."""
    pass


DEFAULT_PRESERVED_TERMS: Set[str] = {
    # C Standard Library & Memory
    "malloc", "free", "calloc", "realloc", "sizeof", "NULL", "size_t", "ssize_t",
    "printf", "scanf", "fprintf", "fscanf", "sprintf", "snprintf",
    "memcpy", "memmove", "memset", "memcmp", "strlen", "strcpy", "strncpy",
    # System programming & concurrency
    "pthread_mutex_t", "pthread_mutex_lock", "pthread_mutex_unlock", "pthread_mutex_init",
    "pthread_mutex_destroy", "pthread_create", "pthread_join", "pthread_t",
    "sémaphore", "semaphore", "sem_t", "sem_wait", "sem_post", "sem_init", "sem_destroy",
    "fork", "pipe", "execve", "waitpid", "dup2", "sigaction", "kill", "signal",
    "socket", "bind", "listen", "accept", "connect", "send", "recv",
    # Complexity & Algorithms
    "O(1)", "O(n)", "O(n log n)", "O(n^2)", "O(log n)", "O(2^n)", "qsort", "bsearch",
    # C types and structures
    "struct", "typedef", "enum", "union", "void", "int", "char", "float", "double", "bool",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
    "tas", "pile", "heap", "stack", "pointeur", "pointeurs", "adresse", "adresses",
    # Java & OOP
    "public", "private", "protected", "static", "final", "abstract", "interface",
    "class", "extends", "implements", "override", "null", "new", "this", "super",
    "JVM", "bytecode", "garbage collector",
    # Database & SQL
    "SQL", "SELECT", "INSERT", "UPDATE", "DELETE", "JOIN", "WHERE", "GROUP BY", "ORDER BY",
    # Build & Tooling
    "Makefile", "gcc", "clang", "valgrind", "gdb", "javac", "make",
    "AST", "MOSS", "JPlag",
}


class HumanizerCleaner:
    """Cleans typical LLM writing cliches and artificial transitional markers

    while strictly preserving scientific and technical terminology.
    """

    # Comprehensive French AI tells and academic connectors (80+ patterns)
    FR_AI_TELLS: List[str] = [
        # AI Opening Cliches & Meta-commentary
        r"[Ii]l convient de noter que\s*",
        r"[Ii]l est (?:important|essentiel|crucial|primordial|fondamental) de noter que\s*",
        r"[Ii]l convient de souligner que\s*",
        r"[Ii]l est (?:important|essentiel|crucial|primordial|fondamental) de souligner que\s*",
        r"[Ii]l est à (?:noter|souligner) que\s*",
        r"[Ff]orce est de constater que\s*",
        r"[Ii]l s'avère que\s*",
        r"[Ii]l va sans dire que\s*",
        r"[Ii]l va de soi que\s*",
        r"[Ii]l est indéniable que\s*",
        r"[Ii]l ne fait aucun doute que\s*",
        r"[Nn]ul doute que\s*",
        r"[Ii]l est manifeste que\s*",
        r"[Ii]l est clair que\s*",
        r"[Ii]l est évident que\s*",
        r"[Ii]l est patent que\s*",
        r"[Ii]l apparaît (?:clairement|nettement) que\s*",
        r"[Ii]l importe de (?:noter|souligner|rappeler) que\s*",
        r"[Ii]l est opportun de (?:noter|souligner|rappeler) que\s*",
        r"[Ii]l est utile de préciser que\s*",
        r"[Ii]l est bon de rappeler que\s*",
        r"[Ii]l est séant de rappeler que\s*",
        r"[Ii]l mérite d'être mentionné que\s*",
        r"[Ii]l faut garder à l'esprit que\s*",
        r"[Gg]ardons à l'esprit que\s*",
        r"[Nn]'oublions pas que\s*",
        r"[Ii]l ne faut pas oublier que\s*",
        r"[Ss]oulignons que\s*",
        r"[Nn]otons que\s*",
        r"[Rr]appelons que\s*",
        r"[Pp]récisons que\s*",
        r"[Cc]onstatons que\s*",
        r"[Nn]ous pouvons en déduire que\s*",
        r"[Nn]ous pouvons constater que\s*",
        r"[Ii]l est intéressant de (?:noter|constater|souligner) que\s*",

        # Overused Transitions & Connectors
        r"[Dd]e surcroît,?\s*",
        r"[Pp]ar ailleurs,?\s*",
        r"[Dd]ès lors,?\s*",
        r"[Ee]n outre,?\s*",
        r"[Dd]'une part,?\s*",
        r"[Dd]'autre part,?\s*",
        r"[Dd]e plus,?\s*",
        r"[Ee]n premier lieu,?\s*",
        r"[Ee]n second lieu,?\s*",
        r"[Ee]n dernier lieu,?\s*",
        r"[Tt]out d'abord,?\s*",
        r"[Ee]n effet,?\s*",
        r"[Dd]e ce fait,?\s*",
        r"[Pp]ar conséquent,?\s*",
        r"[Cc]'est pourquoi,?\s*",
        r"[ÀA] ce titre,?\s*",
        r"[Ss]ur cette base,?\s*",
        r"[Dd]ans ce contexte,?\s*",
        r"[Dd]ans cette optique,?\s*",
        r"[ÀA] cet égard,?\s*",
        r"[Ee]n l'occurrence,?\s*",
        r"[Ee]n substance,?\s*",
        r"[Ee]n d'autres termes,?\s*",
        r"[Aa]utrement dit,?\s*",
        r"[Dd]'ores et déjà,?\s*",
        r"[Qq]ui plus est,?\s*",
        r"[Ee]n tout état de cause,?\s*",
        r"[Pp]ar voie de conséquence,?\s*",
        r"[Dd]e manière générale,?\s*",
        r"[Gg]lobalement parlant,?\s*",
        r"[Ee]n grande partie,?\s*",
        r"[Aa]vant toute chose,?\s*",
        r"[Pp]our ainsi dire,?\s*",

        # Academic Stock Phrases & Fluff
        r"[Cc]omme mentionné précédemment,?\s*",
        r"[Cc]omme nous l'avons vu,?\s*",
        r"[Cc]omme indiqué plus haut,?\s*",
        r"[Cc]omme expliqué précédemment,?\s*",
        r"[Cc]omme exposé ci-dessus,?\s*",
        r"[Aa]insi que nous l'avons souligné,?\s*",
        r"[Aa]u regard de ce qui précède,?\s*",
        r"[Cc]ompte tenu de ce qui précède,?\s*",
        r"[Dd]ans le cadre de cette étude,?\s*",
        r"[Dd]ans la présente analyse,?\s*",
        r"[Jj]oue un rôle (?:crucial|majeur|clé|prépondérant|déterminant)\s*",
        r"[Pp]ierre angulaire\s*",
        r"[Aa]u cœur de\s*",
        r"[Tt]émoigne de\s*",
        r"[Ss]ans l'ombre d'un doute,?\s*",
        r"[ÀA] vrai dire,?\s*",

        # Concluding Cliches
        r"[Ee]n conclusion,?\s*",
        r"[Pp]our conclure,?\s*",
        r"[Ee]n somme,?\s*",
        r"[Ee]n résumé,?\s*",
        r"[Tt]out bien considéré,?\s*",
        r"[Ee]n définitive,?\s*",
        r"[Aa]u terme de cette analyse,?\s*",
        r"[Ee]n guise de conclusion,?\s*",
        r"[Pp]our résumer,?\s*",
    ]

    # English AI tells & academic connectors (40+ patterns)
    EN_AI_TELLS: List[str] = [
        # AI Meta Cliches
        r"[Ii]t is important to note that\s*",
        r"[Ii]t is worth noting that\s*",
        r"[Ii]t should be noted that\s*",
        r"[Ii]t is crucial to note that\s*",
        r"[Ii]t is essential to note that\s*",
        r"[Ii]t is paramount to note that\s*",
        r"[Ii]t is clear that\s*",
        r"[Ii]t is evident that\s*",
        r"[Ii]t is apparent that\s*",
        r"[Nn]eedless to say,?\s*",
        r"[Ii]t goes without saying that\s*",
        r"[Ii]t is interesting to note that\s*",
        r"[Ii]t is worth mentioning that\s*",

        # Transitions & Overused Markers
        r"[Ff]urthermore,?\s*",
        r"[Mm]oreover,?\s*",
        r"[Ii]n addition,?\s*",
        r"[Aa]dditionally,?\s*",
        r"[Cc]onsequently,?\s*",
        r"[Tt]herefore,?\s*",
        r"[Hh]ence,?\s*",
        r"[Tt]hus,?\s*",
        r"[Ff]irst and foremost,?\s*",
        r"[Ll]ast but not least,?\s*",
        r"[Uu]ltimately,?\s*",
        r"[Aa]ll in all,?\s*",

        # References & Clichés
        r"[Aa]s mentioned previously,?\s*",
        r"[Aa]s discussed earlier,?\s*",
        r"[Aa]s stated above,?\s*",
        r"[Aa]s seen before,?\s*",
        r"[Dd]elve into\s*",
        r"[Aa] tapestry of\s*",
        r"[Ss]erves as a testament to\s*",
        r"[Pp]lays a crucial role in\s*",
        r"[Cc]ornerstone of\s*",

        # Concluding Tells
        r"[Ii]n conclusion,?\s*",
        r"[Tt]o conclude,?\s*",
        r"[Tt]o summarize,?\s*",
        r"[Ii]n summary,?\s*",
        r"[Ii]n a nutshell,?\s*",
        r"[Tt]o sum up,?\s*",
    ]

    # Chat fluff patterns - anchored strictly to document start (\A) or closing
    CHAT_FLUFF_PATTERNS: List[str] = [
        r"\A(?:Voici|Ci-dessous)[^\n:]*:\s*\n*",
        r"\A(?:Certainement|Bien sûr)\s*!\s*\n*",
        r"\A(?:Here is|Below is)[^\n:]*:\s*\n*",
        r"\A(?:Certainly|Sure)!\s*\n*",
        r"J'espère que (?:cela|cette explication) vous (?:aidera|sera utile)[^\n.]*[.]\s*",
        r"N'hésitez pas (?:à poser|si vous avez)[^\n.]*[.]\s*",
        r"En espérant que ces détails vous éclaireront[^\n.]*[.]\s*",
        r"Feel free to ask[^\n.]*[.]\s*",
        r"Hope this helps[^\n.]*[.]\s*",
    ]

    def __init__(self, additional_tells: Optional[List[str]] = None) -> None:
        self.ai_tells = list(self.FR_AI_TELLS) + list(self.EN_AI_TELLS)
        if additional_tells:
            self.ai_tells.extend(additional_tells)

    def _protect_sanctuary(
        self, text: str, preserved_terms: Set[str]
    ) -> Tuple[str, Dict[str, str]]:
        """Replaces preserved technical terms with unique placeholders so they cannot

        be modified, corrupted, or deleted during cleaning.
        """
        placeholder_map: Dict[str, str] = {}
        protected_text = text

        # Sort terms by descending length so substrings don't preempt longer compound terms
        sorted_terms = sorted(preserved_terms, key=lambda t: len(t), reverse=True)

        for idx, term in enumerate(sorted_terms):
            if not term:
                continue
            token = f"__SANCT_TERM_{idx}__"
            # Use word boundaries if term consists purely of word characters;
            # otherwise escape term literally (e.g. for O(n log n))
            if re.match(r"^\w+$", term):
                pattern = re.compile(rf"\b{re.escape(term)}\b")
            else:
                pattern = re.compile(re.escape(term))

            if pattern.search(protected_text):
                placeholder_map[token] = term
                protected_text = pattern.sub(token, protected_text)

        return protected_text, placeholder_map

    def _restore_sanctuary(self, text: str, placeholder_map: Dict[str, str]) -> str:
        """Restores all preserved technical terms from their placeholders."""
        restored = text
        for token, term in placeholder_map.items():
            restored = restored.replace(token, term)
        return restored

    def _recapitalize_sentences(self, text: str) -> str:
        """Fixes capitalization at the beginning of sentences after stripping leading AI cliches."""
        # Handle French contractions like L', D', S', C' at sentence start
        def _cap_contraction(m: re.Match[str]) -> str:
            prefix = m.group(1)
            contraction = m.group(2)
            letter = m.group(3)
            return f"{prefix}{contraction[0].upper()}{contraction[1:]}{letter}"

        re_contraction = re.compile(r"(^|[.!?]\s+)(l'|d'|s'|c'|qu'|j'|m'|t'|n')([a-zà-öø-ÿ])", re.IGNORECASE)
        fixed = re_contraction.sub(_cap_contraction, text)

        # Handle normal first letters
        def _cap_normal(m: re.Match[str]) -> str:
            prefix = m.group(1)
            letter = m.group(2)
            return f"{prefix}{letter.upper()}"

        re_normal = re.compile(r"(^|[.!?]\s+)([a-zà-öø-ÿ])")
        fixed = re_normal.sub(_cap_normal, fixed)

        return fixed

    def clean_ai_tells(self, text: str, preserved_terms: Optional[Set[str]] = None) -> str:
        """Removes AI cliches and robotic transitional tells from text,

        while strictly preserving all designated technical terms.
        """
        if not text:
            return ""

        effective_sanctuary = set(DEFAULT_PRESERVED_TERMS)
        if preserved_terms:
            effective_sanctuary.update(preserved_terms)

        # Step 1: Protect all sanctuary terms
        protected_text, placeholder_map = self._protect_sanctuary(text, effective_sanctuary)

        # Step 2: Handle paired binary constructs like "Non seulement... mais aussi"
        # Replaces artificial correlatives with human-sounding connectors
        cleaned = re.sub(r"\b[Nn]on seulement\s+", "", protected_text)
        cleaned = re.sub(r",?\s*\bmais aussi\s+", " ainsi que ", cleaned)
        cleaned = re.sub(r",?\s*\bmais encore\s+", " ainsi que ", cleaned)
        cleaned = re.sub(r"\b[Nn]ot only\s+", "", cleaned)
        cleaned = re.sub(r",?\s*\bbut also\s+", " as well as ", cleaned)

        # Step 3: Remove AI tells at sentence boundaries or within text
        for tell_pattern in self.ai_tells:
            # Pattern at sentence start: (^|[.!?]\s+)TELL
            # Keep the preceding punctuation/whitespace (\1) and drop the tell
            sentence_start_re = re.compile(rf"(^|[.!?]\s+)(?:{tell_pattern})", re.IGNORECASE | re.MULTILINE)
            cleaned = sentence_start_re.sub(r"\1", cleaned)

            # Pattern inside sentence (e.g. ", en conclusion, " or " en conclusion ")
            inside_re = re.compile(rf",?\s*(?:{tell_pattern}),?\s*", re.IGNORECASE)
            cleaned = inside_re.sub(" ", cleaned)

        # Step 4: Clean up whitespace and punctuation artifacts
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\s+([,;.!?])", r"\1", cleaned)
        cleaned = re.sub(r",\s*,+", ",", cleaned)
        cleaned = re.sub(r"^[;,.\s]+", "", cleaned)
        cleaned = cleaned.strip()

        # Step 5: Fix sentence capitalization
        cleaned = self._recapitalize_sentences(cleaned)

        # Step 6: Restore preserved sanctuary terms
        restored = self._restore_sanctuary(cleaned, placeholder_map)

        return restored.strip()

    def clean_markdown_formatting(self, text: str) -> str:
        """Removes conversational AI wrappers, preamble headers, and closing salutations

        without stripping legitimate mid-document section titles.
        """
        if not text:
            return ""
        cleaned = text.strip()
        for pattern in self.CHAT_FLUFF_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def inject_execution_trace(self, text: str, stdout: str, stderr: Optional[str] = None) -> str:
        """Injects terminal execution logs into the report to provide empirical proof

        that the code was compiled and executed locally.
        """
        trace_section = ["\n\n### Trace d'Exécution Réelle (Terminal)"]
        trace_section.append("```text")
        if stdout and stdout.strip():
            trace_section.append(stdout.strip())
        else:
            trace_section.append("[Programme exécuté sans sortie standard]")
        if stderr and stderr.strip():
            trace_section.append("\n# Sortie d'erreur standard (stderr):")
            trace_section.append(stderr.strip())
        trace_section.append("```\n")
        return text.rstrip() + "\n" + "\n".join(trace_section)

    def verify_sanctuary_preservation(
        self, cleaned_text: str, original_text: str, preserved_terms: Set[str]
    ) -> bool:
        """Verifies that all sanctuary terms present in original_text remain intact in cleaned_text."""
        for term in preserved_terms:
            if not term:
                continue
            if term in original_text and term not in cleaned_text:
                return False
        return True

    def humanize_report(
        self,
        report_text: str,
        preserved_terms: Optional[Set[str]] = None,
        profile: Optional[StudentProfile] = None,
        execution_logs: Optional[str] = None,
    ) -> str:
        """Full humanization pipeline: cleans chat fluff, removes AI tells, verifies sanctuary,

        and optionally embeds real terminal execution traces.
        """
        # Step 1: Remove chat fluff
        fluff_free = self.clean_markdown_formatting(report_text)

        # Step 2: Clean AI tells with sanctuary protection
        cleaned = self.clean_ai_tells(fluff_free, preserved_terms=preserved_terms)

        # Step 3: Inject execution logs if provided
        if execution_logs:
            cleaned = self.inject_execution_trace(cleaned, stdout=execution_logs)

        # Step 4: Sanctuary sanity check
        if preserved_terms and not self.verify_sanctuary_preservation(cleaned, report_text, preserved_terms):
            missing = [t for t in preserved_terms if t in report_text and t not in cleaned]
            raise SanctuaryViolationError(
                f"Sanctuary violation: technical term(s) {missing} were altered or removed."
            )

        return cleaned
