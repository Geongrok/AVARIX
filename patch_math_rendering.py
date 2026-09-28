from pathlib import Path
import re

LLM_FILE = Path("app/llm.py")


def _patch():
    text = LLM_FILE.read_text(encoding="utf-8")

    if "_format_db_math" in text:
        print("[PATCH] Math formatter already present.")
        return

    anchor = '''    # ------------------------------------------------------------------ #
    # Database relevance validation
    # ------------------------------------------------------------------ #
'''

    if anchor not in text:
        raise RuntimeError(
            "Could not find the database relevance validation anchor in llm.py"
        )

    helper = r'''    # ------------------------------------------------------------------ #
    # Mathematical formatting for DB/extractive answers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_db_math(text: str) -> str:
        """
        Restore MathJax delimiters around raw LaTeX extracted from PDFs.

        PDF extraction frequently produces raw commands such as:
            \\frac{dA}{A}
            \\left(M^2-1\\right)
            \\sqrt{...}

        These are not rendered by MathJax unless they are enclosed in
        mathematical delimiters.

        Existing $, $$, \\(...\\), and \\[...\\] expressions are preserved.
        """

        if not text:
            return text

        # Protect already-delimited mathematics.
        protected = []

        def protect(match):
            token = f"__INTELLEX_MATH_{len(protected)}__"
            protected.append(match.group(0))
            return token

        text = re.sub(
            r"\$\$.*?\$\$|\$[^$\n]+\$|\\\(.*?\\\)|\\\[.*?\\\]",
            protect,
            text,
            flags=re.S,
        )

        # --------------------------------------------------------------
        # 1. Handle common complete LaTeX commands with balanced braces.
        # --------------------------------------------------------------
        commands = (
            r"frac",
            r"dfrac",
            r"tfrac",
            r"sqrt",
            r"text",
            r"mathrm",
            r"mathbf",
            r"mathit",
            r"overline",
            r"underline",
            r"vec",
            r"hat",
            r"bar",
        )

        command_re = re.compile(
            r"\\(?:" + "|".join(commands) + r")\b"
        )

        def consume_group(s, pos):
            if pos >= len(s) or s[pos] != "{":
                return pos

            depth = 0
            i = pos

            while i < len(s):
                ch = s[i]

                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i + 1

                i += 1

            return pos

        def format_command(match):
            start = match.start()
            end = match.end()

            # Consume one or more brace arguments.
            while end < len(text):
                while end < len(text) and text[end].isspace():
                    end += 1

                if end < len(text) and text[end] == "{":
                    new_end = consume_group(text, end)
                    if new_end == end:
                        break
                    end = new_end
                else:
                    break

            expr = text[start:end].strip()

            if not expr:
                return match.group(0)

            return f"${expr}$"

        # We cannot safely use re.sub with changing indexes, so process
        # left-to-right.
        pieces = []
        cursor = 0

        for match in command_re.finditer(text):
            if match.start() < cursor:
                continue

            pieces.append(text[cursor:match.start()])

            start = match.start()
            end = match.end()

            while end < len(text):
                probe = end

                while probe < len(text) and text[probe].isspace():
                    probe += 1

                if probe < len(text) and text[probe] == "{":
                    new_end = consume_group(text, probe)
                    if new_end == probe:
                        break
                    end = new_end
                else:
                    break

            expr = text[start:end].strip()

            # Avoid double wrapping.
            if expr:
                pieces.append(f"${expr}$")
            else:
                pieces.append(text[start:end])

            cursor = end

        pieces.append(text[cursor:])
        text = "".join(pieces)

        # --------------------------------------------------------------
        # 2. Handle \\left ... \\right groups.
        # --------------------------------------------------------------
        text = re.sub(
            r"(?<!\$)(\\left\b.*?\\right\b)(?!\$)",
            lambda m: f"${m.group(1).strip()}$",
            text,
            flags=re.S,
        )

        # --------------------------------------------------------------
        # 3. Restore protected existing mathematics.
        # --------------------------------------------------------------
        for i, original in enumerate(protected):
            text = text.replace(
                f"__INTELLEX_MATH_{i}__",
                original,
            )

        return text

'''

    text = text.replace(anchor, helper + anchor, 1)

    # Format the final extractive DB answer only.
    old = '''        return answer.strip()
'''

    new = '''        # Restore MathJax delimiters after extracting technical text.
        # This affects presentation only; routing and DB evidence are unchanged.
        return LLMEngine._format_db_math(answer.strip())
'''

    # Only replace the occurrence belonging to _db_extractive_answer.
    marker = '    def _db_extractive_answer('
    start = text.find(marker)

    if start == -1:
        raise RuntimeError(
            "Could not find _db_extractive_answer() in llm.py"
        )

    end = text.find(
        '    # ------------------------------------------------------------------ #',
        start + len(marker),
    )

    if end == -1:
        raise RuntimeError(
            "Could not find the end of _db_extractive_answer()"
        )

    section = text[start:end]

    if old not in section:
        raise RuntimeError(
            "Could not find the final return in _db_extractive_answer()"
        )

    section = section.replace(old, new, 1)
    text = text[:start] + section + text[end:]

    LLM_FILE.write_text(text, encoding="utf-8")

    print("[PATCH] app/llm.py updated successfully.")
    print("[PATCH] DB math rendering restored.")
    print("[PATCH] No database/cache/routing changes made.")


if __name__ == "__main__":
    _patch()