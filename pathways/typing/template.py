"""Generate configuration spreadsheet template from CART model output.

The main use of the configuration spreadsheet is to provide a mapping between the segmentation
variables used in the CART model and the corresponding questions that are going to be asked in the
typing tool.

To pre-fill the configuration spreadsheet, CART output is used to retrieve the list of variables
used as primary splits. The CART output (`frame`) is a JSON-like list of dictionaries as returned by
`tree$frame` in R, with tree being the `rpart` object.

Segmentation dataframe `df` is used to retrieve the unique values associated with each variable.
These unique values are used to pre-fill the possible answers for each question in the configuration
spreadsheet (choice lists).
"""

import polars as pl
import unidecode
import xlsxwriter


def get_variables(cart: dict) -> list[str]:
    """Get list of CART variables used as primary splits."""
    variables = []
    for node in cart["nodes"]:
        var = node["var"]
        if var != "<leaf>" and var not in variables:
            variables.append(var)
    return sorted(variables)


def get_unique_values(df: pl.DataFrame, variables: list[str]) -> dict:
    """Get unique values for all segmentation variables."""
    unique = {}
    for var in variables:
        unique[var] = [v for v in df[var].unique() if v is not None]
    return unique


def guess_data_types(unique_values: dict) -> dict:
    """Guess data type of each variable based on their unique values."""
    dtypes = {}
    for var, values in unique_values.items():
        if sorted(values) == [0, 1]:
            dt = "binary"
        elif all(isinstance(v, int) for v in values):
            dt = "int"
        elif all(isinstance(v, float) for v in values):
            dt = "float"
        else:
            dt = "str"
        dtypes[var] = dt
    return dtypes


def to_ascii(src: str) -> str:
    """Convert string to ASCII and replace non-alphanumeric characters with underscores."""
    src = unidecode.unidecode(src)
    dst = ""

    for c in src:
        if c.isalnum():
            dst += c
        else:
            dst += "_"

    if dst[0].isnumeric():
        dst = "_" + dst

    dst = dst.strip()
    dst = dst.lower()
    return dst.replace("__", "_")


def questions_worksheet(variables: list[str], dtypes: dict[str, str]) -> list[dict]:
    """Create questions worksheet template from CART variables."""
    languages = ["English (en)"]

    rows = []

    for var in sorted(variables):
        dtype = dtypes[var]
        row = {}

        # xlsform question id
        name = var.replace(".", "_").lower()
        name = to_ascii(name)
        row["question_name"] = name

        # question labels
        for lang in languages:
            row[f"label::{lang}"] = ""

        # question hints
        for lang in languages:
            row[f"hint::{lang}"] = ""

        # question type
        qtypes = {"binary": "select_one", "str": "select_one", "int": "integer", "float": "decimal"}
        qtype = qtypes[dtype]
        row["question_type"] = qtype

        # choice list name, same name as question by default except if binary ("yesno" choice list)
        if qtype == "select_one":
            if dtype == "binary":
                row["choice_list"] = "yesno"
            else:
                row["choice_list"] = name
        else:
            row["choice_list"] = ""

        rows.append(row)

    return rows


def choices_worksheet(
    variables: list[str],
    unique_values: dict[str, list],
    dtypes: dict[str, str],
) -> list[dict]:
    """Create choice lists worksheet template from CART variables."""
    languages = ["English (en)"]

    rows = []

    # "yesno" choice list for binary variables
    for name in ["yes", "no"]:
        row = {}
        row["choice_list"] = "yesno"
        row["name"] = name
        for lang in languages:
            row[f"label::{lang}"] = ""

        # binary variables in CART are 0 or 1 integers
        row["target_value"] = str(int(name == "yes"))

        rows.append(row)

    for var in sorted(variables):
        var_name = var.replace(".", "_").lower()
        unique = unique_values[var]
        dtype = dtypes[var]

        # no choice list if question type is "integer" or "decimal"
        if dtype != "str":
            continue

        # create on choice per unique value
        for value in sorted(unique):
            row = {}
            row["choice_list"] = var_name
            row["name"] = to_ascii(value)
            for lang in languages:
                row[f"label::{lang}"] = ""
            row["target_value"] = value
            rows.append(row)

    return rows


HELP_FMT = {
    "font_name": "Barlow",
    "font_size": 10,
    "valign": "top",
    "font_color": "#183e88",
    "bg_color": "#fcfcf7",
    "text_wrap": True,
}

HEADER_FMT = {
    "font_name": "Barlow",
    "font_size": 10,
    "bold": True,
}

DEFAULT_FMT = {
    "font_name": "Barlow",
    "font_size": 10,
}


def write_questions(
    workbook: xlsxwriter.Workbook, variables: list[str], dtypes: dict[str, str]
) -> None:
    """Write questions worksheet template to workbook.

    Parameters
    ----------
    workbook: xlsxwriter.Workbook
        Workbook to write to.
    variables: list[str]
        List of CART variables.
    dtypes: dict[str, str]
        Data types for each variable.
    """
    rows = questions_worksheet(variables, dtypes)
    worksheet = workbook.add_worksheet("questions")

    help_fmt = workbook.add_format(HELP_FMT)
    header_fmt = workbook.add_format(HEADER_FMT)
    default_fmt = workbook.add_format(DEFAULT_FMT)

    description = """
    This sheet lists the questions that will compose the ODK form.

    Usage:
        - Default question names, question types and choice lists should not be modified. They have
          been automatically generated from the CART output.
        - Question labels and hints can be modified freely. Additionnal languages can also be added
          by adding new columns as needed.
        - If additionnal questions are needed, they can be added at the end of the sheet (ex: if a
          question should be split in two or recoded).
    """

    header = list(rows[0].keys())

    worksheet.merge_range(0, 0, 0, len(header) - 1, description, cell_format=help_fmt)
    worksheet.write_row(1, 0, header, cell_format=header_fmt)

    row_i = 2

    for row in rows:
        worksheet.write_row(row_i, 0, list(row.values()), cell_format=default_fmt)
        row_i += 1

    worksheet.write_row(
        row_i,
        0,
        ["location", "Location", "", "select_one", "location"],
        cell_format=default_fmt,
    )

    worksheet.set_row(0, 120)
    worksheet.set_column(0, 0, 40)
    worksheet.set_column(1, 1, 50)
    worksheet.set_column(2, 2, 50)
    worksheet.set_column(3, 3, 30)
    worksheet.set_column(4, 4, 40)


def write_choices(
    workbook: xlsxwriter.Workbook, variables: list[str], unique_values: dict, dtypes: dict[str, str]
) -> None:
    """Write choice lists worksheet template to workbook.

    Parameters
    ----------
    workbook: xlsxwriter.Workbook
        Workbook to write to.
    variables: list[str]
        List of CART variables.
    unique_values: dict[str, list]
        Unique values for each variable.
    dtypes: dict[str, str]
        Data types for each variable.
    """
    rows = choices_worksheet(variables, unique_values, dtypes)
    worksheet = workbook.add_worksheet("choices")

    help_fmt = workbook.add_format(HELP_FMT)
    header_fmt = workbook.add_format(HEADER_FMT)
    default_fmt = workbook.add_format(DEFAULT_FMT)

    description = """
    This sheet lists question choices (one row per choice). The "choice_list" colum refers to the
    "choice_list" column in the questions sheet.

    Usage:
        - Choice names are automatically generated from the unique values in the segmentation
          dataset. They can be modified as needed (note: if those choices are referenced in the
          "options" sheet, the corresponding formulas should also be updated).
        - Labels can be modified and additionnal languages can be added by creating new columns as
          needed.
        - The "target_value" column contains the CART value corresponding to the choice. These
          values should not be modified as they should always match the model values.
        - If you are adding choices for a question you manually added, setting the target value is
          not needed.
    """

    header = list(rows[0].keys())

    worksheet.merge_range(0, 0, 0, len(header) - 1, description, cell_format=help_fmt)
    worksheet.write_row(1, 0, header, cell_format=header_fmt)

    row_i = 2

    for row in rows:
        worksheet.write_row(row_i, 0, list(row.values()), cell_format=default_fmt)
        row_i += 1

    worksheet.write_row(row_i, 0, ["location", "rural", "Rural", "rural"], cell_format=default_fmt)
    worksheet.write_row(
        row_i + 1, 0, ["location", "urban", "Urban", "urban"], cell_format=default_fmt
    )

    worksheet.set_row(0, 140)
    worksheet.set_column(0, 0, 40)
    worksheet.set_column(1, 1, 50)
    worksheet.set_column(2, 2, 50)
    worksheet.set_column(3, 3, 50)


def write_options(workbook: xlsxwriter.Workbook) -> None:
    """Write options worksheet template to workbook.

    Parameters
    ----------
    workbook: xlsxwriter.Workbook
        Workbook to write to.
    """
    worksheet = workbook.add_worksheet("options")

    help_fmt = workbook.add_format(HELP_FMT)
    header_fmt = workbook.add_format(HEADER_FMT)

    description = """
    This sheet contains custom options used in form generation to support the questions that have
    been manually added (splits, recodes, etc). Bluesquare is responsible to keep it up-to-date.
    """

    header = ["option", "config"]
    worksheet.merge_range(0, 0, 0, len(header) - 1, description, cell_format=help_fmt)
    worksheet.write_row(1, 0, header, cell_format=header_fmt)

    worksheet.set_row(0, 50)
    worksheet.set_column(0, 0, 50)
    worksheet.set_column(1, 1, 100)


def write_segments(
    workbook: xlsxwriter.Workbook, ylevels_rural: list[str], ylevels_urban: list[str]
) -> None:
    """Write segments worksheet template to workbook.

    Parameters
    ----------
    workbook: xlsxwriter.Workbook
        Workbook to write to.
    ylevels_rural: list[str]
        List of segment names for rural clusters (from cart output)
    ylevels_urban: list[str]
        List of segment names for urban clusters (from cart output)
    """
    worksheet = workbook.add_worksheet("segments")

    description = """
    This sheet contains a mapping between the segment names stored in the CART output and the names
    displayed in the form. This mapping is needed when the segment names in the CART output do not
    match the names that should be displayed in the form (ex: "1" and "2" instead of U-1 and U-1.1).

    If the segment column is empty for a given segment, the mapping is ignored.
    """

    header = ["strata", "cluster", "segment"]

    help_fmt = workbook.add_format(HELP_FMT)
    header_fmt = workbook.add_format(HEADER_FMT)
    default_fmt = workbook.add_format(DEFAULT_FMT)

    worksheet.merge_range(0, 0, 0, len(header) - 1, description, cell_format=help_fmt)
    worksheet.write_row(1, 0, header, cell_format=header_fmt)

    row_i = 2

    for cluster in ylevels_rural:
        worksheet.write_row(row_i, 0, ["rural", cluster, ""], cell_format=default_fmt)
        row_i += 1

    for cluster in ylevels_urban:
        worksheet.write_row(row_i, 0, ["urban", cluster, ""], cell_format=default_fmt)
        row_i += 1

    worksheet.set_row(0, 100)
    worksheet.set_column(0, 0, 40)
    worksheet.set_column(1, 1, 40)
    worksheet.set_column(2, 2, 40)


def write_form_settings(workbook: xlsxwriter.Workbook) -> None:
    """Write form settings worksheet template to workbook.

    Parameters
    ----------
    workbook: xlsxwriter.Workbook
        Workbook to write to.
    """
    worksheet = workbook.add_worksheet("settings")

    help_fmt = workbook.add_format(HELP_FMT)
    header_fmt = workbook.add_format(HEADER_FMT)
    default_fmt = workbook.add_format(DEFAULT_FMT)

    description = """
    This sheet contains various form settings. They are added to the "settings" sheet in the
    generated XLSForm.

    Notes:
        - The "form_id" should be consistent across all form versions pushed to IASO.
        - Typing group label and required message for additionnal languages can be added by
          inserting new rows (e.g. "required_message::French (fr)").
    """

    header = ["key", "value"]

    worksheet.merge_range(0, 0, 0, len(header) - 1, description, cell_format=help_fmt)
    worksheet.write_row(1, 0, header, cell_format=header_fmt)

    worksheet.write_row(2, 0, ["form_title", "Typing tool"], cell_format=default_fmt)
    worksheet.write_row(3, 0, ["form_id", "pathways_"], cell_format=default_fmt)
    worksheet.write_row(4, 0, ["default_language", "English (en)"], cell_format=default_fmt)
    worksheet.write_row(5, 0, ["allow_form_duplicates", "yes"], cell_format=default_fmt)
    worksheet.write_row(6, 0, ["typing_group_relevant", ""], cell_format=default_fmt)
    worksheet.write_row(
        7,
        0,
        ["typing_group_label::English (en)", "Typing tool"],
        cell_format=default_fmt,
    )
    worksheet.write_row(
        8,
        0,
        ["required_message::English (en)", "Sorry, this response is required!"],
        cell_format=default_fmt,
    )
    worksheet.write_row(
        9,
        0,
        ["segment_note::English (en)", "Respondent belongs to segment {segment}."],
        cell_format=default_fmt,
    )

    worksheet.set_row(0, 125)
    worksheet.set_column(0, 0, 50)
    worksheet.set_column(1, 1, 50)
