from typing import Any


def _required(question_type: str) -> str | None:
    if question_type in ["select_one", "text", "integer", "decimal"]:
        return "TRUE"
    elif question_type in ["select_multiple"]:
        return "FALSE"
    else:
        return None


def merge_rows(
    rows_a: list[dict[str, str | None]], rows_b: list[dict[str, str | None]]
) -> list[dict[str, str | None]]:
    """Merge two lists of rows with the union of their keys."""
    keys: set[str] = set()
    for row in rows_a + rows_b:
        keys.update(row.keys())

    merge: list[dict[str, str | None]] = []
    for src_row in rows_a + rows_b:
        merged_row = {key: src_row.get(key) for key in keys}
        merge.append(merged_row)

    return merge


def add_screening_questions(
    survey_worksheet: list[dict], screening_questions: list[dict], settings_config: dict
) -> list[dict]:
    """Add screening questions to the survey worksheet.

    Args:
        survey_worksheet (list[dict]): survey worksheet
        screening_questions (list[dict]): screening configuration data with one dict per screening
            question
        settings_config (dict): form-level settings
    Returns:
        list[dict]: updated survey worksheet
    """
    screening_rows: list[dict[str, Any]] = []

    for question in screening_questions:
        row = question.copy()
        if not row.get("required"):
            row["required"] = _required(question["type"])

        # multi-language "required" messages
        # column for required_message can be either:
        #   - required_message
        #   - required_message::English (en)
        #   - required_message::French (fr)
        #   - etc
        if row["required"] == "TRUE":
            for key, value in settings_config.items():
                if key.startswith("required_message"):
                    row[key] = value

        screening_rows.append(row)

    return merge_rows(screening_rows, survey_worksheet)


def add_screening_choices(
    choices_worksheet: list[dict],
    screening_choices: list[dict],
) -> list[dict]:
    """Add screening choices to the choices worksheet.

    Args:
        choices_worksheet (list[dict]): choices worksheet
        screening_choices (list[dict]): screening configuration data with one dict per choice

    Returns:
        list[dict]: updated choices worksheet
    """
    return merge_rows(screening_choices, choices_worksheet)
