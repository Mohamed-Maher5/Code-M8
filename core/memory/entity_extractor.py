# core/memory/entity_extractor.py
# Enhanced entity extraction for memory system

import re
from typing import List, Dict, Any, Set


def extract_entities(
    user_message: str, results: List[Dict], final_answer: str = ""
) -> Dict[str, Any]:
    """
    Extract files, functions, classes, concepts from turn.

    Returns:
        Dict with keys: files, functions, classes, concepts
    """
    all_text = " ".join(
        [user_message, final_answer, " ".join([r.get("output", "") for r in results])]
    )

    files = _extract_files(all_text)
    functions = _extract_functions(all_text)
    classes = _extract_classes(all_text)
    concepts = _extract_concepts(user_message, all_text)

    # Normalize file paths - prefer relative paths
    normalized_files = _normalize_file_paths(files)

    return {
        "files": normalized_files,
        "functions": functions,
        "classes": classes,
        "concepts": concepts,
    }


def _extract_files(text: str) -> List[str]:
    """Extract file paths from text."""
    file_pattern = re.compile(
        r"[\w\-./\\]+\.(?:py|js|ts|jsx|tsx|html|css|json|yaml|yml|toml|xml|sql|sh|bash|go|rs|java|c|cpp|h|cs|swift|kt|php|rb|env|cfg|ini|md|txt|csv|pdf|png|jpg|lock|log)"
    )
    matches = file_pattern.findall(text)
    # Filter short matches
    return [f for f in matches if len(f) > 3]


def _extract_functions(text: str) -> List[str]:
    """Extract function names from code."""
    # Match def function_name( or async def function_name(
    patterns = [
        r"\bdef\s+(\w+)\s*\(",
        r"\basync\s+def\s+(\w+)\s*\(",
        r"\bfunction\s+(\w+)\s*\(",
        r"\bconst\s+(\w+)\s*=\s*(?:async\s+)?\(",
    ]

    functions = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        functions.update(matches)

    # Filter common non-function words
    exclude = {
        "if",
        "else",
        "for",
        "while",
        "class",
        "try",
        "except",
        "with",
        "return",
        "yield",
    }
    return list(functions - exclude)


def _extract_classes(text: str) -> List[str]:
    """Extract class names from code."""
    pattern = r"\bclass\s+(\w+)"
    matches = re.findall(pattern, text)
    return list(set(matches))


def _extract_concepts(user_message: str, text: str) -> List[str]:
    """Extract concepts/keywords from text."""
    # Technical concepts to look for
    concept_patterns = {
        "api": r"\bapi\b|\bAPI\b",
        "database": r"\bdatabase\b|\bdb\b|\bSQL\b|\bNeo4j\b",
        "auth": r"\bauth\b|\bauthentication\b|\blogin\b|\btoken\b|\bjwt\b",
        "memory": r"\bmemory\b|\bsession\b|\bcontext\b",
        "search": r"\bsearch\b|\bfind\b|\bquery\b",
        "file": r"\bfile\b|\bpath\b|\bdirectory\b",
        "error": r"\berror\b|\bbug\b|\bfix\b|\bexception\b",
        "test": r"\btest\b|\bunittest\b|\bpytest\b",
        "config": r"\bconfig\b|\bsettings\b|\benv\b",
        "web": r"\bweb\b|\bhttp\b|\brequest\b|\bresponse\b",
    }

    found_concepts = []
    text_lower = text.lower()

    for concept, pattern in concept_patterns.items():
        if re.search(pattern, text_lower):
            found_concepts.append(concept)

    return found_concepts


def _normalize_file_paths(files: List[str]) -> List[str]:
    """Normalize file paths - prefer relative paths."""
    normalized = []
    seen = set()

    for f in files:
        # Skip if already processed (avoid duplicates)
        if f in seen:
            continue

        # Extract just filename
        filename = f.split("/")[-1].split("\\")[-1]

        # Prefer short relative path
        if filename not in seen:
            normalized.append(filename)
            seen.add(filename)

    return normalized


def extract_code_changes(results: List[Dict]) -> List[Dict]:
    """Extract code changes from coder results."""
    changes = []

    for result in results:
        task = result.get("task", {})
        agent = task.get("agent", "")

        # Only process coder results
        if agent != "coder":
            continue

        output = result.get("output", "")
        success = result.get("success", False)

        # Detect change type from output
        change_type = None
        if "created" in output.lower() or "wrote" in output.lower():
            change_type = "file_created"
        elif (
            "edited" in output.lower()
            or "modified" in output.lower()
            or "updated" in output.lower()
        ):
            change_type = "file_modified"
        elif "deleted" in output.lower() or "removed" in output.lower():
            change_type = "file_deleted"

        # Extract file names - look for patterns in output
        file_patterns = [
            r"(?:created|edited|deleted|wrote|modified|updated):\s*([^\n]+)",
            r"file[:\s]+([^\n]+)",
            r"([\w\-./]+\.(?:py|js|ts|jsx|tsx|html|css|json|yaml|yml))",
        ]

        files_found = []
        for pattern in file_patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            files_found.extend(matches)

        # Add change for each file found
        for file in files_found:
            file = file.strip()
            if file and len(file) > 1:
                changes.append(
                    {
                        "type": change_type or "unknown",
                        "file": file,
                        "success": success,
                        "agent": agent,
                        "instruction": task.get("instruction", ""),
                    }
                )

        # If no files found but change detected, add generic
        if not files_found and change_type:
            changes.append(
                {
                    "type": change_type,
                    "file": "unknown",
                    "success": success,
                    "agent": agent,
                    "instruction": task.get("instruction", ""),
                }
            )
            change_type = "file_deleted"

        # Extract file names
        file_pattern = r"(?:created|edited|deleted|wrote):\s*([^\n]+)"
        file_matches = re.findall(file_pattern, output, re.IGNORECASE)

        for match in file_matches:
            changes.append(
                {
                    "type": change_type or "unknown",
                    "file": match.strip(),
                    "success": result.get("success", False),
                }
            )

    return changes


def detect_errors(results: List[Dict], final_answer: str) -> List[Dict]:
    """Detect errors from agent results and answers."""
    errors = []

    # Check for failed agents
    for result in results:
        success = result.get("success", True)
        output = result.get("output", "")
        task = result.get("task", {})
        agent = task.get("agent", "unknown")

        # If agent failed
        if not success:
            errors.append(
                {
                    "source": f"agent_{agent}",
                    "type": "agent_failure",
                    "details": output[:200] if output else "No output",
                }
            )

        # Check output for error keywords even if marked as success
        output_lower = output.lower() if output else ""
        answer_lower = final_answer.lower() if final_answer else ""

        # Error keywords in output
        if any(
            word in output_lower
            for word in ["error", "failed", "exception", "could not"]
        ):
            errors.append(
                {
                    "source": f"agent_{agent}_output",
                    "type": "error_in_output",
                    "details": output[:200] if output else "",
                }
            )

    # Check for error keywords in answer (only if no errors found yet)
    if not errors:
        error_patterns = [
            (r"error[:\s]+([^\n]+)", "error_message"),
            (r"failed[:\s]+([^\n]+)", "failure"),
            (r"exception[:\s]+([^\n]+)", "exception"),
            (r"could not[:\s]+([^\n]+)", "could_not"),
            (r"not found[:\s]+([^\n]+)", "not_found"),
            (r"doesn't exist", "not_found"),
            (r"does not exist", "not_found"),
        ]

        for pattern, error_type in error_patterns:
            matches = re.findall(pattern, final_answer, re.IGNORECASE)
            for match in matches:
                errors.append(
                    {
                        "source": "final_answer",
                        "type": error_type,
                        "details": match.strip()[:200],
                    }
                )

    return errors
