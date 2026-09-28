from pathlib import Path

path = Path("app/llm.py")

text = path.read_text(encoding="utf-8")
lines = text.splitlines(True)

# ------------------------------------------------------------
# Locate the malformed mathematical formatter.
# ------------------------------------------------------------
formatter_marker = "    # Safe mathematical formatting"
formatter_index = next(
    i for i, line in enumerate(lines)
    if line.strip() == "# Safe mathematical formatting"
)

# The formatter currently starts with an incorrectly dedented
# @staticmethod / def and ends immediately before the
# "Database relevance validation" block.
db_marker_index = next(
    i for i, line in enumerate(lines[formatter_index + 1:], formatter_index + 1)
    if line.strip() == "# Database relevance validation"
)

print("Malformed formatter starts:", formatter_index + 1)
print("DB validation block starts:", db_marker_index + 1)

# ------------------------------------------------------------
# Everything before the formatter belongs to LLMEngine.
# ------------------------------------------------------------
prefix = lines[:formatter_index]

# ------------------------------------------------------------
# Extract formatter.
#
# It currently begins at column 0, so indent the entire
# formatter by 4 spaces to put it back inside LLMEngine.
# ------------------------------------------------------------
formatter = lines[formatter_index:db_marker_index]

formatter_fixed = []

for line in formatter:
    if line.strip():
        formatter_fixed.append("    " + line)
    else:
        formatter_fixed.append(line)

# ------------------------------------------------------------
# Extract the complete DB validation / remaining LLMEngine
# methods. These already have class-level indentation (4 spaces).
# ------------------------------------------------------------
db_block = lines[db_marker_index:]

# ------------------------------------------------------------
# Reconstruct:
#
# class LLMEngine:
#     existing methods
#     formatter
#     normalize_query
#     _normalise_term
#     _question_intent
#     ...
#     _generate_extractive
#
# ------------------------------------------------------------
new_lines = prefix + formatter_fixed + db_block

path.write_text("".join(new_lines), encoding="utf-8")

print()
print("================================================")
print("LLM STRUCTURE REPAIRED")
print("================================================")
print("Formatter moved back inside LLMEngine.")
print("Database/relevance methods restored to class scope.")
print("No database/cache/index changes made.")