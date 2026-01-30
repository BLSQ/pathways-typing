
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

FORM_SHAPE_TYPES = {
    "segment": "stadium",
    "select_one": "rectangle",
    "select_multiple": "rectangle",
    "calculate": "parallelogram",
    "integer": "trapezoid",
    "decimal": "trapezoid_alt",
    "text": "circle",
    "note": "parallelogram_alt",
}

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

def draw_link(shape_a: str, shape_b: str, label: str | None = None, *, dotted: bool = False) -> str:
    """Print mermaid link between two shapes. Either a straight or dotted link"""
    arrow_style = "-.->" if dotted else "-->"
    if label:
        label = clean_label(label)
        return f"{shape_a} {arrow_style}|{label}| {shape_b}"
    return f"{shape_a} {arrow_style} {shape_b}"

def _link_label(node: Node) -> str:
    ope = node.cart_rule.operator
    value = node.cart_rule.value
    if ope == "in":
        return ", ".join(value)
    if ope in [">", "<"]:
        return f"{ope} {value}"
    msg = f"Unsupported operator: {ope}"
    raise MermaidError(msg)

def build_cluster_to_node_mapping(root: Node) -> dict[str, Node]:
    """Build a mapping from cluster name to Node."""
    mapping = {}
    for node in root.preorder():
        if hasattr(node, "cart") and hasattr(node.cart, "cluster"):
            mapping[node.cart.cluster] = node
    return mapping

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
    node: Node,
    probabilities: dict[str, float],
    shape_type: str = "stadium",
    *,
    low_confidence: bool = False,
    cluster_to_node: dict[str, Node] = None,
    language: str = "English (en)"
) -> tuple[list[str], list[str]]:
    """
    Create stacked shapes and links for segment probabilities.

    Args:
        node (Node): The node representing the segment.
        probabilities (dict[str, float]): Probabilities for each segment.
        shape_type (str): The shape type to use for the stack (default: "stadium").
        low_confidence (bool): If True, marks shapes/links as low confidence (default: False).

        cluster_to_segment (dict): Mapping from cluster name to segment name.

    Returns:
        tuple[list[str], list[str]]: (list of shape strings, list of link strings)
    """
    shapes = []
    links = []
    items = [(seg, p) for seg, p in probabilities.items() if p and p > 0]
    if not items:
        return shapes, links
    items.sort(key=lambda x: x[1], reverse=True)

    # Top row (highest probability)
    prefix = "*" if low_confidence else ""
    prev_id = node.uid
    top_seg, top_prob = items[0]
    if cluster_to_node and top_seg in cluster_to_node:
        segment_label = get_form_shape_label(cluster_to_node[top_seg], language)
    else:
        segment_label = top_seg
    top_label = f"{prefix}{segment_label} ({top_prob * 100:.0f}%)"
    top_shape = draw_shape(prev_id, top_label, shape_type)
    shapes.append(top_shape)

    # Remaining rows (lower probabilities)
    for i, (seg, prob) in enumerate(items[1:], start=2):
        new_id = f"{node.uid}_prob_{i}"
        if cluster_to_node and seg in cluster_to_node:
            segment_label = get_form_shape_label(cluster_to_node[seg], language)
        else:
            segment_label = seg
        new_label = f"{prefix}{segment_label} ({prob * 100:.0f}%)"
        new_shape = draw_shape(new_id, new_label, shape_type)
        shapes.append(new_shape)

        stacked_link = draw_link(prev_id, new_id, dotted=low_confidence)
        links.append(stacked_link)
        prev_id = new_id

    return shapes, links

def create_default_form_diagram(root: Node, *, skip_notes: bool = False, threshold: float = 0.0) -> str:
    """
    Create a simple mermaid diagram for a typing form tree.

    Args:
        root (Node): The root node of the form tree.
        skip_notes (bool): If True, skip nodes of type "note" (default: False).
        threshold (float): Probability threshold for low confidence (default: 0.0, as percent).

    Returns:
        str: Mermaid diagram as a string.
    """
    header = "flowchart TD"
    threshold = threshold / 100.0
    shapes_lst = []
    links = []
    for node in root.preorder():
        if skip_notes and node.question.type == "note":
            continue

        is_segment_leaf = node.name == "segment"
        probabilities = node.class_probabilities
        is_low_confidence = False
        
        if is_segment_leaf and probabilities:
            max_prob = max(probabilities.values())
            is_low_confidence = max_prob < threshold

            shape_label = get_form_shape_label(node)
            if is_low_confidence:
                shape_label = f"*{shape_label}"  
            shape = draw_shape(node.uid, shape_label, "circle")
            shapes_lst.append(shape)
        else:
            shape_type = "circle" if is_segment_leaf else FORM_SHAPE_TYPES[node.question.type]
            shape_label = get_form_shape_label(node)
            shape = draw_shape(node.uid, shape_label, shape_type)
            shapes_lst.append(shape)

        if node.is_root:
            continue

        link_label = get_form_link_label(node)
        link = draw_link(node.parent.question.name, node.question.name, link_label, dotted=is_low_confidence)
        links.append(link)

    return "\n\t".join([header, *shapes_lst, *links])


def create_detailed_form_diagram(root: Node, *, skip_notes: bool = False, threshold: float = 0.0) -> str:
    """
    Create a detailed mermaid diagram with stacked probabilities for a typing form tree.

    Args:
        root (Node): The root node of the form tree.
        skip_notes (bool): If True, skip nodes of type "note" (default: False).
        threshold (float): Probability threshold for low confidence (default: 0.0, as percent).

    Returns:
        str: Mermaid diagram as a string.
    """
    header = "flowchart TD"
    threshold = threshold / 100.0
    shapes_lst = []
    links = []
    cluster_to_node = build_cluster_to_node_mapping(root)
    for node in root.preorder():
        if skip_notes and node.question.type == "note":
            continue

        is_segment_leaf = node.name == "segment"
        probabilities = node.class_probabilities
        is_low_confidence = False
        
        if is_segment_leaf and probabilities:
            max_prob = max(probabilities.values())
            is_low_confidence = max_prob < threshold

            prob_shapes, prob_links = create_segment_probability_stack(
                node, probabilities, "circle", low_confidence=is_low_confidence, cluster_to_node=cluster_to_node
            )
            shapes_lst.extend(prob_shapes)
            links.extend(prob_links)
        else:
            shape_type = "circle" if is_segment_leaf else FORM_SHAPE_TYPES[node.question.type]
            shape_label = get_form_shape_label(node)
            shape = draw_shape(node.uid, shape_label, shape_type)
            shapes_lst.append(shape)

        if node.is_root:
            continue

        link_label = get_form_link_label(node)
        link = draw_link(node.parent.question.name, node.question.name, link_label, dotted=is_low_confidence)
        links.append(link)

    return "\n\t".join([header, *shapes_lst, *links])
