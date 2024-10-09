from __future__ import annotations

import math
import random
import re
import subprocess
import tempfile
from operator import contains, eq, ge, gt, le, lt
from pathlib import Path
from typing import Callable, Iterator

import polars as pl
import xlsxwriter

from pathways.typing.exceptions import CARTError, FormError


class CARTRule:
    """Parsed CART splitting rule.

    Attributes:
        rule (str): source CART rule (unparsed)
        var (str): variable name in CART
        operator (Callable): comparison operator
        values (list[str]): CART values
    """

    def __init__(self, rule: str):
        self.rule = rule
        self.var, self.operator, self.values = self.parse()

    def __str__(self):
        return self.rule

    def __repr__(self):
        return f"CARTRule('{self.rule}')"

    def parse(self) -> tuple[str, Callable, list[str] | float]:
        """Parse CART rule.

        Returns:
            str: variable name
            Callable: comparison operator
            list[str] or float: comparison value(s)
        """
        rule = self.rule

        # extract cart variable name
        m = re.search("([a-zA-Z0-9.]*)\W", rule)
        if m:
            var = m.group(1)
        else:
            raise CARTError(f"Unable to extract variable from CART rule `{self.rule}`")

        # possible operators are: =, >, >=, <, and <=
        # also remove the operator substring from the string
        rule = rule.replace(var, "", 1)
        if rule.startswith("="):
            ope = contains
            rule = rule.replace("=", "", 1)
        elif rule.startswith(">="):
            ope = ge
            rule = rule.replace(">=", "", 1)
        elif rule.startswith(">"):
            ope = gt
            rule = rule.replace(">", "", 1)
        elif rule.startswith("<="):
            ope = le
            rule = rule.replace("<=", "", 1)
        elif rule.startswith("<"):
            ope = lt
            rule = rule.replace("<", "", 1)
        else:
            raise CARTError(f"Unable to extract operator from CART rule `{self.rule}`")

        # variable name and operators have been removed from the string in previous steps
        # only the comma-separated list of values is remaining
        values = rule.split(",")
        values = [v.strip() for v in values]

        # if operator is >=, >, <=, or <, values should be converted to float and there should be
        # only one value
        if ope in [ge, gt, le, lt]:
            values = float(values[0])

        else:
            pass

        return var, ope, values


class Node:
    """Tree node. Nodes can have 0 or 1 parent, and 0 or more children.

    Attributes:
        name (str): node name
        parent (Node): parent node (None if root)
        data (dict): additional node data
        uid (str): node unique id, automatically generated from its name
        children (list[Node]): node children
    """

    def __init__(self, name: str, parent: Node = None, data: dict = None):
        self.name = name
        self.parent = parent
        if data:
            self.data = data
        else:
            self.data = {}
        self.uid = self.generate_uid()
        self.children = []

    def __str__(self):
        return f"Node('{self.uid}')"

    def __repr__(self):
        return f"Node('{self.uid}')"

    def generate_uid(self) -> str:
        """Generate uid from node name."""
        name = self.name.lower().replace(".", "_")
        return f"{name}_{format(random.getrandbits(32), 'x')}"

    def preorder(self) -> Iterator[Node]:
        """Pre-order tree traversal."""
        yield self
        for child in self.children:
            for node in child.preorder():
                yield node

    def postorder(self) -> Iterator[Node]:
        """Post-order tree traversal."""
        for child in self.children:
            for node in child.postorder():
                yield node
        yield self

    def parents(self) -> Iterator[Node]:
        """Iterate over all parents of the node."""
        parent = self.parent
        while parent:
            yield parent
            parent = parent.parent

    def remove(self):
        """Remove node from tree.

        1) Node is removed from its parent's children list.
        2) Node parent becomes parent of all node children.
        3) Node doesn't have any parent or children anymore.
        """
        if self.parent is not None:
            self.parent.children.remove(self)
            for child in self.children:
                child.parent = self.parent
                self.parent.children.append(child)
        self.parent = None
        self.children = []

    @property
    def is_leaf(self):
        return len(self.children) == 0

    @property
    def is_root(self):
        return self.parent is None

    @property
    def child_index(self) -> int | None:
        """Index of current node in its parent nodes.

        Value should be between 0 and (n_siblings - 1).
        """
        if not self.parent:
            return None
        for i, child in enumerate(self.parent.children):
            if child == self:
                return i


class SurveyNode(Node):
    def __init__(self, name: str, parent: Node = None, data: dict = None):
        super().__init__(name, parent, data)
        self.type: str = None
        self.label: dict[str, str] = None
        self.hint: dict[str, str] = None
        self.required: bool = False
        self.calculation: str = None
        self.relevant: str = None
        self.choice_list: str = None
        self.choices: list[dict] = None
        self.choice_filter: str = None

    def __str__(self):
        return f"SurveyNode('{self.uid}')"

    def __repr__(self):
        return f"SurveyNode('{self.uid}')"

    def from_config(self, questions_config: dict, choices_config: dict):
        """Set survey node attributes from config data."""
        var = self.name

        # node is a leaf, so no question will be asked instead, register cluster in a question of
        # type "calculate" with a default value equal to the cluster
        # this is to ensure that the cluster value is stored with the submission
        # nb: no value will be stored if the user does not reach that node
        if var == "segment":
            self.type = "calculate"
            self.calculation = str(self.data.get("cart_cluster"))

        # node is not a leaf: fetch associated question data from config
        else:
            question = questions_config.get(var)
            if question is None:
                raise FormError(f"Question for variable `{var}` not found in config")

            self.type = question.get("type")
            self.label = question.get("label")
            self.hint = question.get("hint")
            self.choice_list = question.get("choice_list")

            if self.type in ["select_one", "select_multiple"]:
                # append choice list name to type
                self.type = f"{self.type} {self.choice_list}"

                choices = choices_config.get(self.choice_list)
                if choices is None:
                    raise FormError(f"Choice list `{self.choice_list}` not found in config")
                self.choices = choices_config.get(self.choice_list)

    def xpath_condition(self) -> str:
        """Xpath expression used in the `relevant` XLSForm field.

        Xpath expression is based on the CART rule of the node.
        """
        rule = self.data.get("cart_rule")
        if rule is None:
            return None

        # if the parent node is a "select_one" or a "select_multiple" question, we need to test
        # against the selected choices
        if self.parent.type.startswith("select"):
            # single value in CART rule
            # ex: "floor.slum< 0.5"
            if not isinstance(rule.values, list):
                choices = []
                for choice in self.parent.choices:
                    if rule.operator(choice["target_value"], rule.values):
                        choices.append(choice["name"])

            # multiple values in CART rule
            # ex: "medical.transport=big problem,not a big problem"
            else:
                choices = []
                for choice in self.parent.choices:
                    if choice["target_value"] in rule.values:
                        choices.append(choice["name"])

            expression = create_xpath_condition(
                var=self.parent.uid, operator=contains, values=choices
            )

            # store list of valid parent choices in the node data
            self.data["parent_choices"] = [
                choice["label"]["label::English (en)"]
                for choice in self.parent.choices
                if choice["name"] in choices
            ]

        # if the parent node is a "calculate", "integer" or "decimal" question, we need to test
        # against a single value
        elif self.parent.type in ["calculate", "integer", "decimal"]:
            expression = create_xpath_condition(
                var=self.parent.uid, operator=rule.operator, values=rule.values
            )

            MAPPING = {
                gt: ">",
                ge: ">=",
                lt: "<",
                le: "<=",
                eq: "=",
                contains: "=",
            }

            # store str condition in the node data
            self.data["parent_choices"] = [f"{MAPPING[rule.operator]} {rule.values}"]

        else:
            raise FormError(f"Parent node type `{self.parent.type}` not supported")

        return expression


def merge_trees(root_urban: Node, root_rural: Node) -> Node:
    """Merge two trees into a single tree.

    Assumes that a new question about location will be asked at the root of the merged tree (urban
    vs. rural).

    Args:
        root_urban (Node): root node of the first tree
        root_rural (Node): root node of the second tree

    Returns:
        Node: root node of the merged tree
    """
    # create a new root node
    root = SurveyNode("location")

    # add the two trees as children of the root node
    root.children.append(root_urban)
    root.children.append(root_rural)

    # set the parent of the two trees to the new root node
    root_urban.parent = root
    root_rural.parent = root
    root_urban.data["is_left_child"] = True
    root_urban.data["is_right_child"] = False
    root_rural.data["is_right_child"] = True
    root_rural.data["is_left_child"] = False

    # manually add a new cart rule to add a split based on location
    root.data = {"cart_var": "location", "cart_index": "0"}
    root_urban.data["cart_rule"] = CARTRule("location=urban")
    root_rural.data["cart_rule"] = CARTRule("location=rural")

    return root


def create_xpath_condition(
    var: str, operator: Callable, values: list[str] | float | int | str
) -> str:
    """Create an xpath condition from a variable, operator, and value(s)."""
    select = f"${{{var}}}"

    MAPPING = {
        gt: ">",
        ge: ">=",
        lt: "<",
        le: "<=",
        eq: "=",
        contains: "=",
    }

    operator = MAPPING[operator]

    if isinstance(values, list):
        conditions = [f"{select} {operator} '{value}'" for value in values]
        expression = " or ".join(conditions)

    else:
        if isinstance(values, list):
            value = values[0]
        else:
            value = values
        if isinstance(value, str):
            value = f"'{value}'"

        expression = f"{select} {operator} {value}"

    return expression


def build_binary_tree(frame: list[dict], strata: str = None) -> Node:
    """Build binary tree from CART output.

    The function transforms a list of CART splits into Node objects, and assign parents and
    children accordingly. Additional data from CART are stored in the `data` attribute.

    Only the root node is returned.

    Args:
        frame (list[dict]): CART output as a list of dict, each dict representing one split

    Returns:
        Node: root node of the tree
    """
    # store all nodes in a dict using binary index as key
    nodes = {}
    for n in frame:
        # this is the binary index of the node, which is going to be needed to build the initial
        # binary tree structure
        i = int(n["node_index"])

        # store the CART data in a dict
        if n["label"] == "root":
            rule = None
        else:
            rule = CARTRule(n["label"])
        data = {
            "cart_index": i,
            "cart_var": n["var"].lower().replace(".", "_"),
            "cart_rule": rule,
            "cart_cluster": n["yval"],
            "cart_strata": strata,
        }

        # is this the root node?
        data["is_root"] = i == 1

        # is the node a leaf?
        # nb: rpart package in R uses "<leaf>" as the variable name for leaf nodes
        data["is_leaf"] = n["var"] == "<leaf>"

        if i != 1:
            # is the node a left child of its parent?
            data["is_left_child"] = i % 2 == 0

            # is the node a right child of its parent?
            data["is_right_child"] = i % 2 == 1

        # name the node after the variable used for splitting
        # for leaf nodes, use the name "segment"
        if n["var"] == "<leaf>":
            name = "segment"
        else:
            name = data["cart_var"]
        node = SurveyNode(name=name, data=data)

        nodes[i] = node

    # assign parent and children relationships based on the binary indexes of the nodes
    for i in nodes.keys():
        if i == 1:
            continue

        else:
            i_parent = math.floor(i / 2)
            nodes[i].parent = nodes[i_parent]
            nodes[i_parent].children.append(nodes[i])

    return nodes[1]


def survey_worksheet(root: Node, settings_config: dict) -> list[dict]:
    """Generate survey worksheet from a tree (one row per question)."""
    survey = []

    begin_group = {
        "type": "begin_group",
        "name": "typing",
        "relevant": settings_config.get("typing_group_relevant"),
    }

    # typing group labels from form settings
    for key, value in settings_config:
        if key.startswith("typing_group_label"):
            column = key.replace("typing_group_", "")
            begin_group[column] = value

    survey.append(begin_group)

    for node in root.preorder():
        row = {}
        row["type"] = node.type
        row["name"] = node.uid

        # labels and hints can have multiple columns (one column per language)
        if node.label is not None:
            for col, label in node.label.items():
                row[col] = label
        if node.hint is not None:
            for col, hint in node.hint.items():
                row[col] = hint

        row["choice_list"] = node.choice_list
        row["calculation"] = node.calculation
        row["relevant"] = node.relevant

        # by default, all questions are required except questions of type "select_multiple"
        if node.type in ["select_one", "integer", "decimal", "text"]:
            row["required"] = "TRUE"
        elif node.type in ["select_multiple"]:
            row["required"] = "FALSE"
        else:
            row["required"] = None

        # add required_message columns for all languages
        # required messages are always the same for all questions and are stored in the form settings
        if row["required"] == "TRUE":
            for key, value in settings_config.items():
                if key.startswith("required_message"):
                    row[key] = value

        survey.append(row)

        # add a note to notify user that a segment has been assigned
        if node.is_leaf:
            MSG = {
                "English (en)": "Respondent belongs to segment {}.",
                "French (fr)": "Le répondant appartient au segment {}.",
            }

            row = {
                "type": "note",
                "name": f"note_{node.uid}",
                "relevant": node.relevant,
            }

            for language in ["English (en)", "French (fr)"]:
                row[f"label::{language}"] = MSG[language].format(node.data["cart_cluster"])

            survey.append(row)

    end_group = {"type": "end_group", "name": "typing"}
    survey.append(end_group)

    return survey


def choices_worksheet(root: Node) -> list[dict]:
    """Generate choices worksheet from a tree (one row per choice)."""
    choices = []

    for node in root.preorder():
        if node.choices:
            for choice in node.choices:
                row = {
                    "list_name": node.choice_list,
                    "value": choice["name"],
                }

                for col, label in choice["label"].items():
                    row[col] = label

                if row not in choices:
                    choices.append(row)

    return choices


def build_xlsform(survey: list[dict], choices: list[dict], dst_file: Path):
    """Generate XLSForm from survey and choices rows."""
    with xlsxwriter.Workbook(dst_file) as wb:
        survey = pl.DataFrame(survey)
        survey.write_excel(
            workbook=wb, worksheet="survey", header_format={"bold": True}, autofit=True
        )

        choices = pl.DataFrame(choices)
        choices.write_excel(
            workbook=wb, worksheet="choices", header_format={"bold": True}, autofit=True
        )


def validate_xlsform(src_file: Path):
    """Validate xlsform with pyxform.

    Includes internal pyxform checks and ODK Validate.

    Raises:
        FormError: if validation fails
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        p = subprocess.run(["xls2xform", src_file, Path(tmp_dir, "form.xml")], capture_output=True)

        if p.returncode != 0:
            raise FormError(f"XLSForm validation failed: {p.stderr.decode()}")
