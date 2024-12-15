"""Parse CART output from R rpart object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Operator = Literal[">", "<", "in"]


@dataclass
class CARTRule:
    """A split rule in a CART model."""

    var: str
    operator: Operator
    value: list[str] | int | float
    not_present: list[str] | None = None

    def __str__(self) -> str:
        return f"CARTRule(var={self.var}, operator={self.operator}, value={self.value})"


@dataclass
class CARTNode:
    """A CART node (split node or leaf)."""

    index: int
    cluster: str
    counts: dict[str, int]
    cluster_probabilities: dict[str, float]
    node_probability: float
    var: str
    left: CARTRule | None = None
    right: CARTRule | None = None
    strata: str | None = None

    def __repr__(self) -> str:
        return f"CARTNode(index={self.index}, var={self.var}, cluster={self.cluster})"

    @property
    def is_leaf(self) -> bool:
        """Is the node a leaf."""
        return self.var == "<leaf>"


def get_categorical_values(
    csplit_id: int,
    xlevels: list[str],
    csplit: list[list],
) -> tuple[list[str], list[str], list[str]]:
    """Extract categorical values for a split variable at a given node.

    In the rpart output, the `csplit` matrix contains the status of each
    categorical value for each node. The `index` column in the node output
    corresponds to the row index in the `csplit` matrix.

    Categorical variables at a given node can have 3 statuses:
    - 1: value leads to the left child
    - 2: value is not present at the node
    - 3: value leads to the right child
    """
    left = []
    right = []
    not_present = []

    for i, code in enumerate(csplit[csplit_id - 1]):
        if code == 1:
            left.append(xlevels[i])
        elif code == 2:
            if len(xlevels) > i:
                not_present.append(xlevels[i])
        elif code == 3:
            right.append(xlevels[i])

    return left, right, not_present


def get_operator(ncat: int) -> Operator:
    """Determine split rule comparison operator based on the value of `ncat`.

    In rpart objects, `ncat` is the number of categories in the split variable.
    For continuous variables, `ncat` is either 1 or -1. In that case, the sign
    of `ncat` determines the comparison operator.
    """
    if ncat == -1:
        return "<"
    if ncat == 1:
        return ">"
    return "in"


def get_rules(
    var: str,
    ncat: int,
    index: int,
    xlevels: list[str],
    csplit: list[list],
) -> tuple[CARTRule, CARTRule]:
    """Extract left & right split rules for a given node.

    Parameters
    ----------
    var : str
        Split variable name
    ncat : int
        Number of categories in the split variable (+/- 1 for continuous vars)
    index : int
        Index of the split variable in the `csplit` matrix (cutpoint for continuous vars)
    xlevels : list[str]
        Unique levels of the split variable
    csplit : list[list]
        Matrix of categorical values for each node

    Returns
    -------
    tuple[CARTRule, CARTRule]
        Left and right split rules (in that order)
    """
    operator = get_operator(ncat)

    if operator == "in":
        left, right, not_present = get_categorical_values(
            csplit_id=index, xlevels=xlevels, csplit=csplit
        )
        left_rule = CARTRule(var=var, operator=operator, value=left, not_present=not_present)
        right_rule = CARTRule(var=var, operator=operator, value=right, not_present=not_present)

    else:
        cutpoint = index
        left_rule = CARTRule(var=var, operator=">", value=cutpoint)
        right_rule = CARTRule(var=var, operator="<", value=cutpoint)
        if ncat == -1:
            left_rule, right_rule = right_rule, left_rule

    return left_rule, right_rule


def get_counts(yval2: list[int | float], ylevels: list[str]) -> dict[str, int]:
    """Extract cluster counts from yval2 array.

    Cluster counts are stored after the 1st element in the yval2 array (with one
    value per cluster).
    """
    counts = {}
    for i in range(len(ylevels)):
        cluster = ylevels[i]
        counts[cluster] = yval2[i + 1]
    return counts


def get_probs(yval2: list[int | float], ylevels: list[str]) -> dict[str, float]:
    """Extract cluster probabilities from yval2 array.

    Cluster probabilities are stored after the cluster counts in the yval2 array
    (with one value per cluster).
    """
    probs = {}
    for i in range(len(ylevels)):
        cluster = ylevels[i]
        probs[cluster] = yval2[i + 1 + len(ylevels)]
    return probs


def parse_nodes(cart: dict[str, Any]) -> dict[int, CARTNode]:
    """Parse CART nodes from the CART JSON output."""
    cart_nodes = {}

    for node in cart["nodes"]:
        cluster_name = cart["ylevels"][int(node["yval"]) - 1]
        counts = get_counts(node["yval2"], cart["ylevels"])
        cluster_probabilities = get_probs(node["yval2"], cart["ylevels"])

        if node["var"] != "<leaf>":
            left, right = get_rules(
                var=node["var"],
                ncat=node["ncat"],
                index=node["index"],
                xlevels=cart["xlevels"].get(node["var"]),
                csplit=cart["csplit"],
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
