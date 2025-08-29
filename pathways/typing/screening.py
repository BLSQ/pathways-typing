def _required(question_type: str) -> str | None:
    if question_type in ["select_one", "text", "integer", "decimal"]:
        return "TRUE"
    elif question_type in ["select_multiple"]:
        return "FALSE"
    else:
        return None


def add_screening_questions(
    survey_worksheet: list[dict], screening_config: list[dict], settings_config: dict
) -> list[dict]:
    """Add screening questions to the survey worksheet.

    Args:
        survey_worksheet (list[dict]): survey worksheet
        screening_config (list[dict]): screening configuration data with one dict per screening
            question
        settings_config (dict): form-level settings
    Returns:
        list[dict]: updated survey worksheet
    """
    begin = []
    end = []

    for question in screening_config:
        required = _required(question["type"])
        question_type = question["type"]

        if question_type in ["select_one", "select_multiple"]:
            question_type = f"{question_type} {question['choice_list']}"

        row = {
            "type": question_type,
            "name": question["name"],
            "calculation": question.get("calculation"),
            "relevant": question.get("relevant"),
            "required": required,
        }

        # multi-language "required" messages
        # column for required_message can be either:
        #   - required_message
        #   - required_message::English (en)
        #   - required_message::French (fr)
        #   - etc
        if required == "TRUE":
            for key, value in settings_config.items():
                if key.startswith("required_message"):
                    row[key] = value

        for label_column in [key for key in question.keys() if key.startswith("label")]:
            row[label_column] = question[label_column]

        for hint_column in [key for key in question.keys() if key.startswith("hint")]:
            row[hint_column] = question[hint_column]

        if question["where"] == "begin":
            begin.append(row)
        else:
            end.append(row)

    new_worksheet = begin + survey_worksheet + end
    return new_worksheet


def add_screening_choices(
    choices_worksheet: list[dict], screening_config: list[dict], choices_config: dict
) -> list[dict]:
    """Add screening choices to the choices worksheet.

    Args:
        choices_worksheet (list[dict]): choices worksheet
        screening_config (list[dict]): screening configuration data with one dict per screening
            question
        choices_config (dict): choices configuration data with choice list name as key
    Returns:
        list[dict]: updated choices worksheet
    """
    for question in screening_config:
        choice_list = question.get("choice_list")

        if choice_list:
            for choice in choices_config[choice_list]:
                row = {
                    "list_name": choice_list,
                    "value": choice["name"],
                }

                for label_column, label in choice["label"].items():
                    row[label_column] = label

                if row not in choices_worksheet:
                    choices_worksheet.append(row)

    return choices_worksheet
