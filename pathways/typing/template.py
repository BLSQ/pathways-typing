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


def get_cart_variables(frame: list[dict]) -> list[str]:
    """Get the list of CART variables used as primary splits.

    Args:
        frame (list[dict]): frame output of CART model (tree$frame in R) as a json-like list of dict

    Returns:
        list[str]: list of CART variables
    """
    variables = []
    for split in frame:
        var = split["var"]
        if var != "<leaf>" and var not in variables:
            variables.append(var)
    return sorted(variables)


def get_unique_values(df: pl.DataFrame, variables: list[str]) -> dict:
    """Get unique values for all segmentation variables.

    Args:
        df (Dataframe): input segmentation data
        variables (list[str]): variables of interest

    Returns:
        dict: unique values with variable names as keys
    """
    values = {}
    for var in variables:
        values[var] = list([v for v in df[var].unique() if v is not None])
    return values


def guess_data_types(unique_values: dict) -> dict:
    """Guess data type of each variable based on their unique values.

    Args:
        unique_values (dict): variables unique values

    Returns:
        dict: guessed data type for each variable.
    """
    dtypes = {}
    for var, values in unique_values.items():
        if sorted(values) == [0, 1]:
            dt = "binary"
        elif all([isinstance(v, int) for v in values]):
            dt = "int"
        elif all([isinstance(v, float) for v in values]):
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
    dst = dst.replace("__", "_")

    return dst


def questions_worksheet(vars: list[str], dtypes: dict[str, str]) -> list[dict]:
    """Create questions worksheet template from CART variables.

    Args:
        vars (list[str]): list of CART variables
        dtypes (dict[str, str]): guessed data types for each variable

    Returns:
        list[dict]: questions worksheet template as a list of JSON-like dict (one dict per row)
    """
    LANGUAGES = ["English (en)"]

    rows = []

    for var in sorted(vars):
        dtype = dtypes[var]
        row = {}

        # xlsform question id
        name = var.replace(".", "_").lower()
        name = to_ascii(name)
        row["question_name"] = name

        # question labels
        for lang in LANGUAGES:
            row[f"label::{lang}"] = ""

        # question hints
        for lang in LANGUAGES:
            row[f"hint::{lang}"] = ""

        # question type
        QTYPES = {"binary": "select_one", "str": "select_one", "int": "integer", "float": "decimal"}
        qtype = QTYPES[dtype]
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
    vars: list[str], unique_values: dict[str, list], dtypes: dict[str, str]
) -> list[dict]:
    """Create choice lists worksheet template from CART variables.

    Args:
        vars (list[str]): list of CART variables
        unique_values (dict[str, list]): unique values for each variable
        dtypes (dict[str, str]): guessed data types for each variable

    Returns:
        list[dict]: choice lists worksheet template as a list of JSON-like dict (one dict per row)
    """
    LANGUAGES = ["English (en)"]

    rows = []

    # "yesno" choice list for binary variables
    for name in ["yes", "no"]:
        row = {}
        row["choice_list"] = "yesno"
        row["name"] = name
        for lang in LANGUAGES:
            row[f"label::{lang}"] = ""

        # binary variables in CART are 0 or 1 integers
        row["target_value"] = str(int(name == "yes"))

        rows.append(row)

    for var in sorted(vars):
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
            for lang in LANGUAGES:
                row[f"label::{lang}"] = ""
            row["target_value"] = value
            rows.append(row)

    return rows
