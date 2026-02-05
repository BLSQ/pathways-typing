"""Apply custom modifications to the form."""

import copy

from .tree import Node, Question, create_split_question, update_xpath_variables, xpath_condition


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
    # node.question.trigger = update_xpath_variables(node, "${" + option_config["dst_question"] + "}")
    if default := option_config.get("default"):
        node.question.default = str(default)
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


def apply_hide_option(node: Node, option_config: dict) -> None:
    """Apply hide option to form node."""
    # append relevance condition
    relevant = option_config["relevant"]
    relevant = update_xpath_variables(node, relevant)
    if relevant not in node.question.conditions:
        node.question.conditions.append(relevant)

    # remove from relevance conditions in children
    for child in node.preorder():
        for condition in child.question.conditions:
            if node.name in condition:
                child.question.conditions.remove(condition)


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
    strata = node.cart.strata if node.cart.strata else "any"
    mapping = segments_config.get(strata) if segments_config else None
    if mapping and segment in mapping:
        segment = mapping[segment]
    label = {key: value.format(segment=segment) for key, value in note_label.items()}

    new_node = Node(name="segment_note")
    note = Question(name=new_node.uid, type="note", label=label)
    new_node.question = note
    new_node.question.conditions = node.question.conditions

    node.insert_after(new_node)


def add_segment_notes(
    root: Node,
    settings_config: dict,
    segments_config: dict | None = None,
    low_confidence_threshold: float = 0.0,
) -> Node:
    """Add notes once segments are assigned.

    If confidence_threshold is provided (percentage), calculate max probability. If max_probability < threshold,
    segment + low confidence note will be applied. Otherwise, only segment note is applied.
    """
    low_confidence_threshold = low_confidence_threshold / 100
    new_root = copy.deepcopy(root)
    note_label = {
        key.replace("segment_note", "label"): value.replace("\\n", "\n")
        if isinstance(value, str)
        else value
        for key, value in settings_config.items()
        if key.startswith("segment_note")
    }
    low_conf_label = {
        key.replace("low_confidence_note", "label"): value.replace("\\n", "\n")
        if isinstance(value, str)
        else value
        for key, value in settings_config.items()
        if key.startswith("low_confidence_note")
    }

    for node in new_root.preorder():
        if node.is_leaf and node.name == "segment":
            use_low_conf = False
            if low_confidence_threshold > 0 and node.class_probabilities:
                max_prob = max(node.class_probabilities.values())
                use_low_conf = max_prob < low_confidence_threshold
            final_label = note_label.copy()
            if use_low_conf:
                for key, seg_note in final_label.items():
                    low_conf_note = low_conf_label.get(
                        key,
                        "\n[Low segment assignment confidence]\n"
                        "We recommend stopping this survey and starting with a new respondent.",
                    )
                    final_label[key] = seg_note + low_conf_note

            add_segment_note(node, final_label, segments_config)

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

    choices = []
    for choice in node.question.choices:
        if choice.cart_value in node.cart.left.not_present:
            choices.append(choice)
        elif str(choice.cart_value) in node.cart.left.not_present:
            choices.append(choice)

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


def mark_as_required(root: Node) -> Node:
    """Mark questions as required by default."""
    new_root = copy.deepcopy(root)
    for node in new_root.preorder():
        if node.question.type in ("integer", "decimal", "select_one", "text"):
            node.question.required = True
        else:
            node.question.required = False
    return new_root


def exit_deadends(
    root: Node, segments_config: dict, settings_config: dict, choices_config: dict
) -> Node:
    """When the tree reaches a deadend, assign to most probable segment."""
    new_root = copy.deepcopy(root)

    deadends_identified: list[str] = []

    for node in new_root.preorder():
        if not node.cart_rule:
            continue
        if node.cart and node.cart.left and node.cart.left.not_present:
            deadend_choices = node.cart.left.not_present
            if deadend_choices:
                var = node.name
                if var not in deadends_identified:
                    print(f"Detected dead-end at question '{var}'")
                    deadends_identified.append(var)

                # Get the list of choices leading to deadends
                deadend_choices_xlsform = []
                for cart_value in deadend_choices:
                    for choice in choices_config[var]:
                        if str(choice["target_value"]) == str(cart_value):
                            deadend_choices_xlsform.append(choice["name"])
                assert len(deadend_choices_xlsform) == len(deadend_choices), (
                    "Some deadend choices were not found in choices_config"
                )
                deadend_choices = deadend_choices_xlsform

                # Get segment name from cluster number
                segment = str(node.cart.cluster)
                strata = node.cart.strata if node.cart.strata else "any"
                mapping = segments_config.get(strata) if segments_config else None
                if mapping and segment in mapping:
                    segment = mapping[segment]

                # Create a new leaf node to assign the segment
                new_node = Node(name="segment")
                new_node.question = Question(
                    name=new_node.uid, type="calculate", required=True, calculation=f"'{segment}'"
                )
                node.add_child(new_node)
                new_node.question.conditions = node.question.conditions.copy()

                if len(deadend_choices) > 1:
                    conditions = [xpath_condition(var, "=", v) for v in deadend_choices]
                    expression = " or ".join(conditions)
                else:
                    expression = xpath_condition(var, "=", deadend_choices[0])
                expression = update_xpath_variables(new_node, expression)
                new_node.question.conditions.append(expression)

                # create note for segment
                note_label = {
                    key.replace("segment_note", "label"): value
                    for key, value in settings_config.items()
                    if key.startswith("segment_note")
                }
                label = {key: value.format(segment=segment) for key, value in note_label.items()}

                # create note for low confidence
                low_confidence_label = {
                    key.replace("low_confidence_note", "label"): value.replace("\\n", "\n")
                    if isinstance(value, str)
                    else value
                    for key, value in settings_config.items()
                    if key.startswith("low_confidence_note")
                }

                for key in label:
                    if key in low_confidence_label:
                        label[key] += low_confidence_label[key]
                    else:
                        label[key] += (
                            "\n[Low segment assignment confidence]\nWe recommend stopping this survey and starting with a new respondent."
                        )

                note_node = Node(name="segment_note")
                note = Question(name=note_node.uid, type="note", label=label)
                note_node.question = note
                note_node.question.conditions = new_node.question.conditions.copy()
                new_node.add_child(note_node)

    return new_root
