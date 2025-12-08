"""Generate mermaid diagrams from typing tree data structures.

See <https://mermaid.js.org/> for more information about the Mermaid language.

Notes
-----
    - Mermaid diagrams are generated as strings.
    - We only use a subset of the mermaid language to ensure compatibility with Whimsical import
      feature.
"""

from typing import Literal

from .exceptions import MermaidError
from .tree import Node, filter_choices

ShapeType = Literal[
    "rectangle",
    "stadium",
    "hexagon",
    "parallelogram",
    "prallelogram_alt",
    "circle",
    "trapezoid",
    "trapezoid_alt",
    "rhombus",
]


def clean_label(label: str) -> str:
    """Clean label string to not break whimsical import."""
    for char in ["(", ")", "[", "]"]:
        label = label.replace(char, " ")
    return label.replace("\n", "\\n")


def draw_shape(shape_id: str, label: str, shape_type: ShapeType = "rectangle") -> str:
    """Print mermaid shape."""
    shapes = {
        "rectangle": ("[", "]"),
        "stadium": ("([", "])"),
        "circle": ("((", "))"),
        "hexagon": ("{{", "}}"),
        "parallelogram": ("[/", "/]"),
        "parallelogram_alt": ("[\\", "\\]"),
        "trapezoid": ("[/", "\\]"),
        "trapezoid_alt": ("[\\", "/]"),
        "rhombus": ("{", "}"),
    }
    begin, end = shapes[shape_type]
    label = clean_label(label)
    return f"{shape_id}{begin}{label}{end}"


def draw_link(shape_a: str, shape_b: str, label: str | None = None) -> str:
    """Print mermaid link between two shapes."""
    if label:
        label = clean_label(label)
        return f"{shape_a} -->|{label}| {shape_b}"
    return f"{shape_a} --> {shape_b}"


def _link_label(node: Node) -> str:
    ope = node.cart_rule.operator
    value = node.cart_rule.value
    if ope == "in":
        return ", ".join(value)
    if ope in [">", "<"]:
        return f"{ope} {value}"
    msg = f"Unsupported operator: {ope}"
    raise MermaidError(msg)


def create_cart_diagram(root: Node) -> str:
    """Create mermaid diagram for CART."""
    header = "flowchart TD"

    shapes_lst = []
    for node in root.preorder():
        if node.is_leaf:
            label = node.cart.cluster
            shape_type = "stadium"
        else:
            label = node.cart.left.var
            shape_type = "rectangle"
        shape = draw_shape(node.uid, label, shape_type)
        shapes_lst.append(shape)

    links = []
    for node in root.preorder():
        if node.is_root:
            continue
        link = draw_link(node.parent.uid, node.uid, _link_label(node))
        links.append(link)

    return "\n\t".join([header, *shapes_lst, *links])


def get_form_shape_label(node: Node, language: str = "English (en)") -> str:
    """Get label for form shape."""
    if node.name == "segment":
        return node.question.calculation.replace("'", "")
    label = node.question.label.get(f"label::{language}")
    if label:
        return label
    return node.name


def get_form_link_label(node: Node, language: str = "English (en)") -> str:
    """Get label for form link between current node and its parent."""
    if node.question.choices_from_parent:
        choices = [
            choice.label[f"label::{language}"] for choice in node.question.choices_from_parent
        ]
        return ", ".join([str(choice) for choice in choices])

    if node.parent.question.type == "calculate" and node.cart_rule:
        for parent in node.parents:
            if parent.name == node.cart_rule.var.replace(".", "_").lower():
                if not parent.question.choices:
                    return ""
                choices = filter_choices(parent.question.choices, node.cart_rule)
                labels = [choice.label[f"label::{language}"] for choice in choices]
                return ", ".join(labels)

    if node.parent.question.type == "calculate" and node.cart_rule:
        return f"'{node.cart_rule.operator} {node.cart_rule.value}'"

    return ""

# My changes need to go here for the mermaid diagram
def create_form_diagram(root: Node, *, skip_notes: bool = False) -> str:
    """Create mermaid diagram for typing form."""
    header = "flowchart TD"

    shapes = {
        "segment": "stadium",
        "select_one": "rectangle",
        "select_multiple": "rectangle",
        "calculate": "parallelogram",
        "integer": "trapezoid",
        "decimal": "trapezoid_alt",
        "text": "circle",
        "note": "parallelogram_alt",
    }

    shapes_lst = []
    links = []
    drawn_segment_nodes: set[str] = set()
    for node in root.preorder():
        if skip_notes and node.question.type == "note":
            continue
        shape_type = "circle" if node.name == "segment" else shapes[node.question.type]
        shape_label = get_form_shape_label(node)
        shape = draw_shape(node.uid, shape_label, shape_type)
        shapes_lst.append(shape)

        if node.is_root:
            continue

        link_label = get_form_link_label(node)
        link = draw_link(
            shape_a=node.parent.question.name, shape_b=node.question.name, label=link_label
        )
        links.append(link)

        # for leaf nodes, draw arrows to all segments with prob > 0 ---
        if getattr(node, "class_probabilities", None) and node.is_leaf:
            for segment_name, prob in node.cluster_probabilities.items():
                if not prob or prob <= 0:
                    continue
                # ensure we have a shape for this segment "probability" node
                if segment_name not in drawn_segment_nodes:
                    segment_shape_type = shapes["segment"]
                    segment_label = segment_name
                    segment_shape = draw_shape(
                        segment_name,  # mermaid id for this segment node
                        segment_label,
                        segment_shape_type,
                    )
                    shapes_lst.append(segment_shape)
                    drawn_segment_nodes.add(segment_name)

                # link from this leaf node to the segment node, with probability as label
                prob_label = f"{prob:.2f}"  # or f"{prob*100:.0f}%" if you prefer %
                prob_link = draw_link(
                    shape_a=node.question.name,  # from this leaf node
                    shape_b=segment_name,        # to the segment node
                    label=prob_label,
                )
                links.append(prob_link)

    return "\n\t".join([header, *shapes_lst, *links])
