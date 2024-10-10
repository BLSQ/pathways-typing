"""Read configuration from a google spreadsheet."""

import gspread
import yaml
from oauth2client.service_account import ServiceAccountCredentials

from pathways.typing.exceptions import ConfigError


def read_spreadsheet(url: str, credentials: dict) -> dict:
    """Read configuration spreadsheet from Google Sheets.

    Args:
        url (str): URL of the Google Sheets document
        credentials (dict): Google API credentials

    Returns:
        dict: configuration data with worksheet title as key and worksheet content as value
    """
    SCOPE = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(url)

    data = {}
    for worksheet in spreadsheet.worksheets():
        if worksheet.title in [
            "questions",
            "choices",
            "options",
            "settings",
            "screening",
            "segments",
        ]:
            data[worksheet.title] = worksheet.get_all_records(head=2)

    return data


def get_questions(data: dict) -> dict:
    """Get questions from the configuration spreadsheet.

    Args:
        data (dict): configuration data from the spreadsheet

    Returns:
        dict: questions with question id as keys and question data as values
    """
    questions = {}

    for row in data["questions"]:
        name = row["question_name"]

        questions[name] = {
            "type": row["question_type"],
            "label": {col: row[col] for col in row if col.startswith("label")},
            "hint": {col: row[col] for col in row if col.startswith("hint")},
            "choice_list": row["choice_list"],
        }

    return questions


def get_choices(data: dict) -> dict:
    """Get choices from the configuration spreadsheet.

    Args:
        data (dict): configuration data from the spreadsheet

    Returns:
        dict: choices with choice list id as keys and choices as values
    """
    choices = {}

    for row in data["choices"]:
        choice_list = row["choice_list"]

        if choice_list not in choices:
            choices[choice_list] = []

        # at this point, all cart values corresponding to choices should be string except for the
        # "yesno" binary choice list where 0 = no and 1 = yes. The forced conversion to strings is
        # needed because some of the categorical values in the CART dataset are integer-like
        # strings, which are automatically converted to integer data types in the google
        # spreadsheet
        target_value = row["target_value"]
        if choice_list != "yesno":
            target_value = str(target_value)

        choices[choice_list].append(
            {
                "name": row["name"],
                "label": {col: row[col] for col in row if col.startswith("label")},
                "target_value": target_value,
            }
        )

    return choices


def get_options(data: dict) -> list[dict]:
    """Get options from the configuration spreadsheet.

    Args:
        data (dict): configuration data from the spreadsheet
    Returns:
        dict: form generation options as a list of dict
    """
    options = []

    for row in data["options"]:
        options.append(
            {
                "option": row["option"],
                "config": yaml.safe_load(row["config"]),
            }
        )

    return options


def get_settings(data: dict) -> dict:
    """Get form-level settings from the configuration spreadsheet.

    Args:
        data (dict): configuration data from the spreadsheet
    Returns:
        dict: form-level settings
    """
    settings = {}

    if "settings" not in data:
        return None

    for row in data["settings"]:
        settings[row["key"]] = row["value"]

    return settings


def get_screening(data: dict) -> list[dict]:
    """Get screening questions from the configuration spreadsheet.

    Args:
        data (dict): configuration data from the spreadsheet
    Returns:
        list[dict]: screening config with one dict per screening question
    """
    return data.get("screening")


def validate_config(config_data: dict, cart_urban: list[dict], cart_rural: list[dict]):
    """Validate config data from spreadsheet."""
    # are all CART variables included in the config?
    for node in cart_urban + cart_rural:
        var = node["var"].replace(".", "_").lower()
        if var != "<leaf>":
            if var not in config_data["questions"]:
                raise ConfigError("Missing question data for CART variable `{}`".format(var))

    # are all additional questions from options included in the config?
    for option in config_data["options"]:
        for entry, value in option["config"].items():
            if entry.startswith("dst_question") or entry.startswith("src_question"):
                if value not in config_data["questions"]:
                    raise ConfigError(
                        "Missing question data for additional question `{}`".format(value)
                    )

    for name, question in config_data["questions"].items():
        # check question types
        if question.get("type") not in [
            "calculate",
            "select_one",
            "select_multiple",
            "integer",
            "decimal",
        ]:
            raise ConfigError(
                "Unspported question type `{}` for question `{}`".format(question.get("type"), name)
            )
