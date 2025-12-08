"""Build typing tree from CART output."""

from __future__ import annotations

import copy
import random
import re
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from typing import TYPE_CHECKING, Literal, Self

from .cart import CARTNode, CARTRule, get_counts, get_probs, get_rules
from .exceptions import TypingFormError

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class Choice:
    """A form question choice."""

    list_name: str
    name: str
    label: dict[str, str]
    cart_value: str | int | float | None = None

    def to_xlsform(self) -> dict:
        """Convert to xlsform choices row."""
        row = {}
        row["list_name"] = self.list_name
        row["value"] = self.name

        for column, label in self.label.items():
            row[column] = label

        return row


@dataclass
class ChoiceList:
    """A form choice list."""

    list_name: str
    choices: list[Choice]


QuestionType = Literal[
    "select_one",
    "select_multiple",
    "integer",
    "decimal",
    "text",
    "calculate",
    "note",
    "range",
    "image",
    "hidden",
]

Strata = Literal["rural", "urban"]


@dataclass
class Question:
    """A form question."""

    name: str
    type: QuestionType | None
    label: dict[str, str] | None = None
    hint: dict[str, str] | None = None
    required: bool = False
    required_message: dict[str, str] | None = None
    conditions: list[str] | None = None
    calculation: str | None = None
    choices: list[Choice] | None = None
    choice_list: str | None = None
    choice_filter: str | None = None
    choices_from_parent: list[Choice] | None = None
    trigger: str | None = None
    default: str | None = None

    @property
    def relevant(self) -> str:
        """Build relevant xpath expression from conditions."""
        if not self.conditions:
            return None
        return " and ".join(f"({condition})" for condition in self.conditions)

    def to_xlsform(self) -> dict:
        """Convert to xlsform question row."""
        row = {}

        if self.type.startswith("select"):
            row["type"] = f"{self.type} {self.choice_list}"
        else:
            row["type"] = self.type

        row["name"] = self.name

        if self.label:
            for column, label in self.label.items():
                row[column] = label

        if self.hint:
            for column, hint in self.hint.items():
                row[column] = hint

        row["calculation"] = self.calculation
        row["relevant"] = self.relevant
        row["required"] = self.required
        row["choice_filter"] = self.choice_filter
        row["trigger"] = self.trigger
        row["default"] = self.default

        if self.required_message:
            for column, message in self.required_message.items():
                row[column] = message

        return row


def generate_uid(prefix: str) -> str:
    """Generate uid from node name."""
    suffix_length = 6
    chars = string.ascii_lowercase + string.digits
    suffix = "".join(random.choice(chars) for i in range(suffix_length))  # noqa: S311
    name = prefix.lower().replace(".", "_")
    return f"{name}_{suffix}"

# This is where I need to change to update the tree structure for the form 
# that the mermaid diagram will represent
class Node:
    """A node in the typing tree."""

    def __init__(
        self,
        name: str,
        parent: Self | None = None,
        children: list[Self] | None = None,
    ) -> None:
        self.name = name
        self.parent = parent
        self.children = [] if children is None else children
        self.cart: CARTNode | None = None
        self.cart_rule: CARTRule | None = None
        self.question: Question | None = None
        self.uid: str = generate_uid(name)
        self.conditions: list[str] = []
        self.class_probabilities: dict[str, float] | None = None

    def __repr__(self) -> str:
        return f"Node(name={self.name}, uid={self.uid})"

    @property
    def is_leaf(self) -> bool:
        """Node is a leaf (no children)."""
        return len(self.children) == 0

    @property
    def is_root(self) -> bool:
        """Node is the root of the tree (no parent)."""
        return self.parent is None

    @property
    def index(self) -> int | None:
        """Index of node in parent's list of children."""
        if not self.parent:
            return None
        return self.parent.children.index(self)

    def add_child(self, child: Self) -> None:
        """Add node as child."""
        self.children.append(child)
        child.parent = self

    def remove(self) -> None:
        """Remove node from the tree."""
        if self.parent:
            self.parent.children.remove(self)
        for child in self.children:
            child.parent = self.parent
        self.parent = None
        self.children = []

    def insert_after(self, node: Self) -> None:
        """Insert node after current node."""
        node.parent = self
        node.children = self.children
        self.children = [node]
        for child in node.children:
            child.parent = node

    def insert_before(self, node: Self) -> None:
        """Insert node before current node."""
        node.parent = self.parent
        node.parent.children.insert(self.index, node)
        node.parent.children.remove(self)
        node.children = [self]
        self.parent = node

    def _iter_parents(self) -> Iterator[Self]:
        """Iterate over all parent nodes."""
        node = self
        while node.parent:
            yield node.parent
            node = node.parent

    @property
    def parents(self) -> list[Self] | None:
        """List of parent nodes."""
        if not self.parent:
            return None
        return list(self._iter_parents())

    def preorder(self) -> Iterator[Self]:
        """Preorder tree traversal."""
        yield self
        for child in self.children:
            yield from child.preorder()

    def postorder(self) -> Iterator[Self]:
        """Postorder tree traversal."""
        for child in self.children:
            yield from child.postorder()
        yield self

# isn't this the same function of parse cart in cart.py?
def parse_rpart(
    nodes: list[dict], ylevels: list[str], xlevels: dict[str, list[str]], csplit: list[list]
) -> dict[int, CARTNode]:
    """Parse rpart output into typing nodes.

    Parameters
    ----------
    nodes : list[dict]
        List of nodes from rpart output
    ylevels : list[str]
        Cluster names from rpart output
    xlevels : dict[str, list[str]]
        Unique levels for each categorical variable
    csplit : list[list]
        Csplit matrix from rpart output

    Returns
    -------
    dict[int, CARTNode]
        A dict containing all CART nodes, with node binary index as key
    """
    cart_nodes = {}

    for node in nodes:
        # the yval2 array from the rpart output contains important information
        # that might be needed down the road, such as counts, class
        # probabilities, etc.
        cluster_name = ylevels[int(node["yval"]) - 1]
        counts = get_counts(node["yval2"], ylevels)
        cluster_probabilities = get_probs(node["yval2"], ylevels)

        # rpart uses the "<leaf>" value to indicate that a node doesn't have any
        # split rule (i.e., it's a leaf)
        if node["var"] != "<leaf>":
            left, right = get_rules(
                var=node["var"],
                ncat=node["ncat"],
                index=node["index"],
                xlevels=xlevels.get(node["var"]),
                csplit=csplit,
            )

        else:
            left, right = None, None

        n = CARTNode(
            index=int(node["node"]),
            cluster=cluster_name,
            counts=counts,
            cluster_probabilities=cluster_probabilities,
            node_probability=node["yval2"][-1],
            left=left,
            right=right,
            var=node["var"],
        )

        cart_nodes[n.index] = n

    return cart_nodes


def build_tree(cart_nodes: dict[int, CARTNode], strata: Strata) -> Node:
    """Build typing tree from CART nodes.

    We rely on the node binary index from the rpart output to build the tree.

    Parameters
    ----------
    cart_nodes : dict[int, CARTNode]
        A dict containing all CART nodes, with node binary index as key
    strata : Strata
        Strata name ("rural" or "urban")

    Returns
    -------
    Node
        The root node of the typing tree
    """
    nodes = {}
    for i, node in cart_nodes.items():
        name = "segment" if node.is_leaf else node.var.replace(".", "_").lower()
        n = Node(name=name)
        n.strata = node.strata
        n.cart = node
        n.cart.strata = strata
        n.class_probabilities = node.cluster_probabilities
        nodes[i] = n

    for i, node in nodes.items():
        # skip root node
        if i == 1:
            continue

        i_parent = floor(i / 2)
        node.parent = nodes[i_parent]
        nodes[i_parent].children.append(node)

        # node is a left child
        if i % 2 == 0:
            node.cart_rule = nodes[i_parent].cart.left

        # node is a right child
        elif i % 2 == 1:
            node.cart_rule = nodes[i_parent].cart.right

    return nodes[1]


def merge_trees(root_rural: Node, root_urban: Node) -> Node:
    """Merge rural and urban trees into a single tree."""
    # create virtual CART data for the new root node (split on location variable)
    left_rule = CARTRule(var="location", operator="in", value=["rural"])
    right_rule = CARTRule(var="location", operator="in", value=["urban"])
    cart = CARTNode(
        index=0,
        cluster=0,
        counts={},
        cluster_probabilities={},
        node_probability=0,
        var="location",
        left=left_rule,
        right=right_rule,
    )

    root = Node(name="location")
    root.cart = cart
    root.add_child(copy.deepcopy(root_rural))
    root.add_child(copy.deepcopy(root_urban))
    root.children[0].cart_rule = left_rule
    root.children[1].cart_rule = right_rule

    return root


def create_segment_question(node: Node, segments_config: dict | None = None) -> Question:
    """Create form question for a leaf node.

    Form questions for segments (tree leaves) are questions of type "calculate" with a default value
    equal to the segment name. This is to store the assigned segment name in the form data when this
    node is reached.
    """
    segment = node.cart.cluster

    mapping = segments_config.get(node.cart.strata) if segments_config else None
    if mapping and segment in mapping:
        segment = mapping[segment]

    return Question(name=node.uid, type="calculate", required=True, calculation=f"'{segment}'")


def create_split_question(node: Node, questions_config: dict, choices_config: dict) -> Question:
    """Create form question for a split node according to config."""
    question_config = questions_config[node.name]

    label = {key: value for key, value in question_config.items() if key.startswith("label")}
    hint = {key: value for key, value in question_config.items() if key.startswith("hint")}

    question = Question(
        name=node.uid,
        type=question_config["question_type"],
        label=label,
        hint=hint,
        choice_list=question_config.get("choice_list"),
    )

    if question.choice_list:
        choices = []
        for choice in choices_config[question.choice_list]:
            choices.append(
                Choice(
                    list_name=choice["choice_list"],
                    name=choice["name"],
                    label={key: value for key, value in choice.items() if key.startswith("label")},
                    cart_value=choice.get("target_value"),
                )
            )
        question.choices = choices

    return question


def create_node_question(
    node: Node, questions_config: dict, choices_config: dict, segments_config: dict | None = None
) -> Question:
    """Create form question for a given node (split or leaf) according to config.

    Split and leaf nodes are handled differently. Split nodes are associated with a form question
    according to the provided config. Leaf nodes are associated with a "calculate" question to store
    the value of the segment.

    Note that created questions will be missing a few attributes such as "relevant", "required" and
    "required_message", which are handled separately.
    """
    if node.is_leaf:
        return create_segment_question(node, segments_config)
    return create_split_question(node, questions_config, choices_config)


def xpath_condition(var: str, operator: str, value: str | float) -> str:
    """Generate xpath condition string.

    Lots of brackets enclosing the variable name because the string will be formatted again to
    replace variable names with actual UIDs of the parent nodes.
    """
    if isinstance(value, str):
        value = f"'{value}'"
    var = "${" + var + "}"
    return f"{var} {operator} {value}"


def extract_xpath_variables(expression: str) -> list[str] | None:
    """Extract all variables from an xpath expression."""
    pattern = r"\{(.*?)\}"
    matches = re.findall(pattern, expression)
    return list(set(matches)) if matches else None


def update_xpath_variables(node: Node, expression: str) -> str:
    """Replace variables names in xpath expression with actual UIDs found in parent nodes.

    Example: ${ed_lev3} -> ${ed_lev3_abc123}
    """
    variables = extract_xpath_variables(expression)

    if variables is None:
        return expression

    mapping = {}
    for var in variables:
        uid = None
        for parent in node.parents:
            if parent.name == var:
                uid = parent.uid
                break
        if not uid:
            msg = f"Variable '{var}' not found in parent nodes."
            raise TypingFormError(msg)
        mapping[var] = "{" + uid + "}"
    return expression.format(**mapping)


def find_cart_parent(node: Node) -> Node:
    """Find the parent node corresponding to the variable in the node CART rule."""
    var = node.cart_rule.var.replace(".", "_").lower()
    parent = None
    for p in node.parents:
        if p.name == var:
            parent = p
            break
    if not parent:
        msg = f"No parent found for variable {var} in node {node.uid}."
        raise TypingFormError(msg)
    return parent


def filter_choices(choices: list[Choice], cart_rule: CARTRule) -> list[Choice]:
    """Filter input choices based on a CART rule."""
    filtered = []

    if cart_rule.operator in [">", "<"] and not isinstance(cart_rule.value, (int | float)):
        msg = f"Value {cart_rule.value} is not a number."
        raise TypingFormError(msg)

    if cart_rule.operator == "in" and not isinstance(cart_rule.value, list):
        msg = f"Value {cart_rule.value} is not a list."
        raise TypingFormError(msg)

    for choice in choices:
        if cart_rule.operator == ">" and float(choice.cart_value) >= cart_rule.value:
            filtered.append(choice)
        if cart_rule.operator == "<" and float(choice.cart_value) < cart_rule.value:
            filtered.append(choice)
        if cart_rule.operator == "in" and str(choice.cart_value) in cart_rule.value:
            filtered.append(choice)

    return filtered


def get_xlsform_relevance(node: Node) -> str | None:
    """Generate relevance expression for a given node based on the CART rule."""
    if not node.cart_rule:
        return None

    if not node.question:
        msg = f"Node {node.uid} do not have any question."
        raise ValueError(msg)

    parent = find_cart_parent(node)
    if not parent.question:
        msg = f"Parent {parent.uid} of node {node.uid} does not have any question."
        raise ValueError(msg)

    value = node.cart_rule.value

    if parent.question.type.startswith("select"):
        if not parent.question.choices:
            msg = f"Question of node {node.uid} has a select type but no choices."
            raise ValueError(msg)

        choices = filter_choices(parent.question.choices, node.cart_rule)
        node.question.choices_from_parent = choices
        value = [choice.name for choice in choices]

    # Split variables are stored in the ed.lev3 format in the rpart output
    # We want the ed_lev3 format also used in the configuration and as xlsform question names
    # (dots are not supported in xlsform IDs)
    var = node.cart_rule.var.replace(".", "_").lower()

    if isinstance(value, list):
        conditions = [xpath_condition(var, "=", v) for v in value]
        expression = " or ".join(conditions)
    else:
        expression = xpath_condition(var, node.cart_rule.operator, value)

    return update_xpath_variables(node, expression)


def get_survey_rows(
    root: Node, typing_group_label: dict[str, str], typing_group_relevance: str | None = None
) -> list[dict]:
    """Generate XLSForm survey sheet rows from typing tree."""
    rows = []

    begin_group = {
        "type": "begin_group",
        "name": "typing_begin",
        "relevant": typing_group_relevance,
    }

    for label_column, label in typing_group_label.items():
        begin_group[label_column] = label

    rows.append(begin_group)

    for node in root.preorder():
        if node.question:
            rows.append(node.question.to_xlsform())

    end_group = {"type": "end_group", "name": "typing_end"}
    rows.append(end_group)

    return rows


def get_choices_rows(root: Node) -> list[dict]:
    """Generate XLSForm choices sheet rows from typing tree."""
    rows = []

    for node in root.preorder():
        if node.question:
            if not node.question.choices:
                continue
            for choice in node.question.choices:
                row = choice.to_xlsform()
                if row not in rows:
                    rows.append(row)

    return rows


def get_settings_rows(settings_config: dict) -> list[dict]:
    """Generate XLSForm settings sheet rows from settings config."""
    row = {
        "form_title": settings_config.get("form_title"),
        "form_id": settings_config.get("form_id"),
        "default_language": settings_config.get("default_language"),
        "allow_choice_duplicates": settings_config.get("allow_choice_duplicates"),
        "version": datetime.now(timezone.utc).strftime("%y%m%d%H%M"),
    }
    return [row]
