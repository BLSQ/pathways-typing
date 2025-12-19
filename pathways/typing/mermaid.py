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
    "parallelogram_alt",
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
    links = []

    for node in root.preorder():
        probabilities = node.class_probabilities

        if node.is_leaf and probabilities:
            prob_shapes, prob_links = create_segment_probability_stack(
                node, probabilities, "stadium"
            )
            shapes_lst.extend(prob_shapes)
            links.extend(prob_links)
        elif node.is_leaf:
            # Leaf without probabilities (fallback)
            label = node.cart.cluster
            shape = draw_shape(node.uid, label, "stadium")
            shapes_lst.append(shape)
        else:
            label = node.cart.left.var
            shape = draw_shape(node.uid, label, "rectangle")
            shapes_lst.append(shape)

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


def create_segment_probability_stack(
    node: Node, probabilities: dict[str, float], shape_type: str = "stadium"
) -> tuple[list[str], list[str]]:
    """Create stacked shapes and links for segment probabilities.

    Returns:
        tuple: (list of shapes, list of links between shapes)
    """
    shapes = []
    links = []
    items = [(seg, p) for seg, p in probabilities.items() if p and p > 0]
    if not items:
        return shapes, links
    items.sort(key=lambda x: x[1], reverse=True)

    # Top row (highest probability)
    prev_id = node.uid
    top_seg, top_prob = items[0]
    top_label = f"{top_seg} ({top_prob * 100:.0f}%)"
    top_shape = draw_shape(prev_id, top_label, shape_type)
    shapes.append(top_shape)

    # Remaining rows (lower probabilities)
    for i, (seg, prob) in enumerate(items[1:], start=2):
        new_id = f"{node.uid}_prob_{i}"
        new_label = f"{seg} ({prob * 100:.0f}%)"
        new_shape = draw_shape(new_id, new_label, shape_type)
        shapes.append(new_shape)

        stacked_link = draw_link(prev_id, new_id)
        links.append(stacked_link)
        prev_id = new_id

    return shapes, links


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
    for node in root.preorder():
        if skip_notes and node.question.type == "note":
            continue

        is_segment_leaf = node.name == "segment"
        probabilities = node.class_probabilities

        if is_segment_leaf and probabilities:
            prob_shapes, prob_links = create_segment_probability_stack(
                node, probabilities, "circle"
            )
            shapes_lst.extend(prob_shapes)
            links.extend(prob_links)
        else:
            shape_type = "circle" if is_segment_leaf else shapes[node.question.type]
            shape_label = get_form_shape_label(node)
            shape = draw_shape(node.uid, shape_label, shape_type)
            shapes_lst.append(shape)

        if node.is_root:
            continue
        link_label = get_form_link_label(node)
        link = draw_link(node.parent.question.name, node.question.name, link_label)
        links.append(link)

    return "\n\t".join([header, *shapes_lst, *links])
