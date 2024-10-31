"""Generate mermaid diagrams from typing tree data structures.

See <https://mermaid.js.org/> for more information about the Mermaid language.

Notes:
    - Mermaid diagrams are generated as strings.
    - We only use a subset of the mermaid language to ensure compatibility with Whimsical import
      feature.
"""

from pathways.typing.tree import Node, SurveyNode


def _left(node: Node) -> Node:
    """Get the left child of a node."""
    n = None
    for child in node.children:
        if child.data["is_left_child"]:
            n = child
            break
    return n


def _right(node: Node) -> Node:
    """Get the right child of a node."""
    n = None
    for child in node.children:
        if child.data["is_right_child"]:
            n = child
            break
    return n


def _shape(shape_id: str, title: str, description: str, shape_type: str = "rectangle") -> str:
    """Draw mermaid shape.

    Args:
        shape_id (str): shape id
        title (str): shape title (displayed at the top of the shape)
        description (str): shape description (displayed at the bottom of the shape)
        shape_type (str): shape type (default: "rectangle"). Available shape types are:
            "rectangle", "round_edges", "stadium", "hexagon", "parallelogram", and "circle".

    Returns:
        str: mermaid shape
    """
    SHAPES = {
        "rectangle": ("[", "]"),
        "round_edges": ("(", ")"),
        "stadium": ("([", "])"),
        "circle": ("((", "))"),
        "hexagon": ("{{", "}}"),
        "parallelogram": ("[/", "/]"),
    }

    shp = SHAPES[shape_type]

    for char in ["[", "]", "(", ")", "_", "\n"]:
        description = description.replace(char, " ")

    return f"{shape_id}{shp[0]}{title}\\n{description}{shp[1]}"


def _link(id_a: str, id_b: str, label: str = None) -> str:
    """Draw mermaid link between two shapes."""
    if label:
        for char in ["/", "_"]:
            label = label.replace(char, " ")
        return f"{id_a} -->|{label}| {id_b}"
    return f"{id_a} --> {id_b}"


def _name(node: Node) -> str:
    """Generate unique name for a node.

    Node name is a combination of the strata and the cart index (ex: "R12" or "U24").
    """
    name = "N"
    if node.strata:
        name += node.strata[0].upper()
    return name + str(node.data.get("cart_index", 0))


def cart_diagram(root: Node) -> str:
    """Generate a diagram of the CART tree with the Mermaid language.

    Args:
        root (Node): root node of the CART tree

    Returns:
        str: Mermaid diagram of the CART tree
    """
    diagram = "flowchart TD\n"

    # draw one shape per node
    for n in root.preorder():
        name = _name(n)

        # label is cluster number for leaf nodes
        if n.data.get("is_leaf"):
            label = f"Cluster {n.data['cart_cluster']}"
            shape_type = "circle"
        # label is split rule for non-leaf nodes
        else:
            label = f"{_left(n).data['cart_rule']}"
            shape_type = "rectangle"

        diagram += "\t" + _shape(name, name, label, shape_type) + "\n"

    # draw links between shapes
    # we iterate over the tree in preorder and draw a link from parent to left & right childs
    for n in root.preorder():
        parent = _name(n)

        if _left(n):
            child = _name(_left(n))
            diagram += "\t" + _link(parent, child, "yes") + "\n"

        if _right(n):
            child = _name(_right(n))
            diagram += "\t" + _link(parent, child, "no") + "\n"

    return diagram


def form_diagram(root: SurveyNode) -> str:
    """Generate a diagram of the form tree with the Mermaid language.

    Args:
        root (Node): root node of the form tree

    Returns:
        str: Mermaid diagram of the form tree
    """
    diagram = "flowchart TD\n"

    for n in root.preorder():
        name = n.uid

        if n.is_leaf:
            shape_type = "hexagon"
        elif n.type == "calculate":
            shape_type = "parallelogram"
        else:
            shape_type = "rectangle"

        if n.is_leaf:
            label = n.calculation
            diagram += "\t" + _shape(name, "Segment", label, shape_type) + "\n"

        else:
            label = n.label["label::English (en)"]
            diagram += "\t" + _shape(name, name, label, shape_type) + "\n"

    for n in root.preorder():
        for child in n.children:
            if child.data.get("parent_choices"):
                label = ", ".join([f"'{c}'" for c in child.data["parent_choices"]])
            else:
                label = None
            diagram += "\t" + _link(id_a=n.uid, id_b=child.uid, label=label) + "\n"

    return diagram
