"""Apply custom modifications to the form."""

import copy

from .tree import Node, Question, create_split_question, update_xpath_variables


def apply_calculate_option(
    node: Node, option_config: dict, questions_config: dict, choices_config: dict
) -> None:
    """Apply calculate option to form node."""
    new_node = Node(name=option_config["dst_question"])
    new_question = create_split_question(new_node, questions_config, choices_config)
    new_node.question = new_question
    node.insert_before(new_node)
    node.question.type = "calculate"
    node.question.calculation = update_xpath_variables(node, option_config["calculation"])
    new_node.question.conditions = node.question.conditions
    new_node.question.choices_from_parent = node.question.choices_from_parent
    node.question.choices_from_parent = None
    new_node.cart = node.cart


def apply_split_option(
    node: Node, option_config: dict, questions_config: dict, choices_config: dict
) -> None:
    """Apply split option to form node."""
    node_a = Node(name=option_config["dst_question_a"])
    node_b = Node(name=option_config["dst_question_b"])
    node.insert_before(node_a)
    node.insert_before(node_b)

    question_a = create_split_question(node_a, questions_config, choices_config)
    question_b = create_split_question(node_b, questions_config, choices_config)
    node_a.question = question_a
    node_b.question = question_b

    node.question.type = "calculate"
    node.question.calculation = update_xpath_variables(node, option_config["calculation"])
    node_a.question.conditions = node.question.conditions
    node_b.question.conditions = node.question.conditions
    node_a.question.choices_from_parent = node.question.choices_from_parent
    node_b.question.choices_from_parent = node.question.choices_from_parent
    node.question.choices_from_parent = None
    node_a.cart = node.cart
    node_b.cart = node.cart


def apply_options(
    root: Node, options_config: list[dict], questions_config: dict, choices_config: dict
) -> Node:
    """Apply custom options to form tree."""
    new_root = copy.deepcopy(root)
    for option in options_config:
        for node in new_root.preorder():
            src_question = option["config"]["src_question"]
            if option["option"] == "calculate" and node.name == src_question:
                apply_calculate_option(node, option["config"], questions_config, choices_config)
            if option["option"] == "split" and node.name == src_question:
                apply_split_option(node, option["config"], questions_config, choices_config)
    return new_root


def add_segment_note(
    node: Node, note_label: dict[str, str], segments_config: dict | None = None
) -> None:
    """Add note once segment is assigned."""
    segment = str(node.cart.cluster)
    mapping = segments_config.get(node.cart.strata) if segments_config else None
    if mapping and segment in mapping:
        segment = mapping[segment]
    label = {key: value.format(segment=segment) for key, value in note_label.items()}

    new_node = Node(name="segment_note")
    note = Question(name=new_node.uid, type="note", label=label)
    new_node.question = note
    new_node.question.conditions = node.question.conditions

    node.insert_after(new_node)


def add_segment_notes(
    root: Node, settings_config: dict, segments_config: dict | None = None
) -> Node:
    """Add notes once segments are assigned."""
    new_root = copy.deepcopy(root)
    note_label = {
        key.replace("segment_note", "label"): value
        for key, value in settings_config.items()
        if key.startswith("segment_note")
    }
    for node in new_root.preorder():
        if node.is_leaf and node.name == "segment":
            add_segment_note(node, note_label, segments_config)
    return new_root


def enforce_relevance(root: Node) -> Node:
    """Enforce relevance rules for the node.

    Instead of considering just the parent for the relevance rule, join relevance rules from all
    parent nodes. This is needed to make sure that the form is behaving correctly when the user
    answers questions and goes backward / change previous responses.
    """
    new_root = copy.deepcopy(root)

    # use relevance rule from parent by default
    for node in new_root.preorder():
        if not node.is_root and not node.question.conditions:
            node.question.conditions = node.parent.question.conditions

    # join relevance rules from all parent nodes
    for node in new_root.preorder():
        if node.is_root:
            continue

        # parent question answer should not be null, except if it's a select_multiple question
        if node.parent.question.type != "select_multiple":
            node.question.conditions.append(f"${{{node.parent.question.name}}} != ''")

        # all parent relevance rules
        for parent in node.parents:
            if parent.question.relevant:
                node.question.conditions += parent.question.conditions

        # avoid duplicate rules
        node.question.conditions = list(set(node.question.conditions))

    return new_root


def get_choice_filter(node: Node) -> str | None:
    """Get choice filter expression for node question based on CART data."""
    if not node.cart.left.not_present or not node.question.choices:
        return None

    choices = [
        choice
        for choice in node.question.choices
        if choice.cart_value in node.cart.left.not_present
    ]

    # also remove choice from children list of parent choices
    # nb: this attribute is only used for mermaid generation
    for child in node.children:
        if child.question.choices_from_parent:
            for choice in choices:
                if choice in child.question.choices_from_parent:
                    child.question.choices_from_parent.remove(choice)

    return " and ".join([f"name != '{choice.name}'" for choice in choices])


def set_choice_filters(root: Node) -> Node:
    """Set choice filters for all questions based on CART data.

    In the configuration, multiple questions can use the same choice list. This is to avoid
    displaying choices that are not used in the model (for example, because there was no population
    with this categorical value at the split).
    """
    new_root = copy.deepcopy(root)
    for node in new_root.preorder():
        if node.cart and node.question.type.startswith("select"):
            node.question.choice_filter = get_choice_filter(node)
    return new_root


def skip_duplicate_questions(root: Node) -> Node:
    """Skip questions that have already been asked in parent nodes.

    When a question in a node has already been asked in parent nodes, convert it to a `calculate`
    type to use the response of the parent question instead. This is to avoid asking the same
    question twice in the form, even if they refer to different split nodes in the CART.
    """
    new_root = copy.deepcopy(root)

    for node in new_root.preorder():
        if not node.question or node.is_root:
            continue

        for parent in node.parents:
            if not parent.question:
                continue

            if node.name == parent.name and not node.name.startswith("segment"):
                node.question.type = "calculate"
                node.question.choice_list = None
                node.question.calculation = f"${{{parent.question.name}}}"

    return new_root
