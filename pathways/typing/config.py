"""Read configuration from a google spreadsheet."""

from pathlib import Path

import gspread
import polars as pl
import yaml
from oauth2client.service_account import ServiceAccountCredentials


def read_excel_spreadsheet(fp: Path) -> pl.DataFrame:
    """Read Excel spreadsheet.

    Parameters
    ----------
    fp : Path
        Path to Excel spreadsheet

    Returns
    -------
    pl.DataFrame
        DataFrame with data from the Excel spreadsheet
    """
    return pl.read_rexcel(
        fp, engine="calamine", read_options={"header_row": 1}, sheet_id=0, raise_if_empty=False
    )


def read_google_spreadsheet(url: str, credentials: dict) -> dict:
    """Read configuration spreadsheet from Google Sheets.

    Parameters
    ----------
    url : str
        URL of the Google Sheet
    credentials : dict
        Google service account credentials

    Returns
    -------
    dict
        Configuration data with worksheet title as key and worksheet content as value
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
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


def get_questions_config(rows: list[dict]) -> dict:
    """Get questions from the configuration spreadsheet.

    Parameters
    ----------
    rows : list[dict]
        Rows from the questions worksheet

    Returns
    -------
    dict
        Questions config with question id as keys
    """
    questions_config = {}
    for question in rows:
        questions_config[question["question_name"]] = question
    return questions_config


def get_choices_config(rows: list[dict]) -> dict:
    """Get choices from the configuration spreadsheet.

    Parameters
    ----------
    rows : list[dict]
        Rows from the choices worksheet

    Returns
    -------
    dict
        Choices config with choice list id as keys
    """
    choices_config = {}
    for choice in rows:
        choice_list = choice["choice_list"]
        if choice_list not in choices_config:
            choices_config[choice_list] = []
        choices_config[choice_list].append(choice)
    return choices_config


def get_options_config(rows: list[dict]) -> list[dict]:
    """Get options from the configuration spreadsheet.

    Parameters
    ----------
    rows : list[dict]
        Rows from the options worksheet

    Returns
    -------
    list[dict]
        Options config as a list of dict
    """
    options_config = []
    for option in rows:
        option["config"] = yaml.safe_load(option["config"])
        options_config.append(option)
    return options_config


def get_segments_config(rows: list[dict]) -> dict:
    """Get segments names from the configuration spreadsheet.

    Parameters
    ----------
    rows : list[dict]
        Rows from the segments worksheet

    Returns
    -------
    dict
        Segments config with source segment name as key and target segment name as value.
    """
    segments_config = {}
    for row in rows:
        strata = row["strata"]
        cluster = str(row["cluster"])
        segment = str(row["segment"])
        if strata not in segments_config:
            segments_config[strata] = {}
        segments_config[strata][cluster] = segment
    return segments_config


def get_settings(rows: list[dict]) -> dict:
    """Get form settings from the configuration spreadsheet.

    Parameters
    ----------
    rows : list[dict]
        Rows from the settings worksheet

    Returns
    -------
    dict
        Key:value settings as a dict
    """
    settings_config = {}
    for row in rows:
        settings_config[row["key"]] = row["value"]
    return settings_config


def get_config(spreadsheet: dict) -> dict:
    """Get configuration from the spreadsheet.

    Parameters
    ----------
    spreadsheet : dict
        Configuration spreadsheet data

    Returns
    -------
    dict
        Configuration data with worksheet title as key and worksheet content as value
    """
    config = {}
    config["questions"] = get_questions_config(spreadsheet["questions"])
    config["choices"] = get_choices_config(spreadsheet["choices"])
    config["options"] = get_options_config(spreadsheet["options"])
    config["segments"] = get_segments_config(spreadsheet["segments"])
    config["settings"] = get_settings(spreadsheet["settings"])
    return config
