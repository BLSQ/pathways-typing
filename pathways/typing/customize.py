"""Additional post-processing operations for the typing tree."""

from pathways.typing.tree import SurveyNode


def split(
    root: SurveyNode,
    src_question: str,
    dst_question_a: str,
    dst_question_b: str,
    calculation: str,
    questions_config: dict,
    choices_config: dict,
) -> SurveyNode:
    """Split a source question into two destination questions.

    Args:
        root (SurveyNode): root node of the typing tree
        src_question (str): source question name
        dst_question_a (str): new question name
        dst_question_b (str): new question name
        calculation (str): new xpath calculate formula for src_question
        questions_config (dict): questions configuration data
        choices_config (dict): choices configuration data

    Returns:
        SurveyNode: root node of the typing tree
    """
    for node in root.preorder():
        if node.name == src_question:
            dst_a = SurveyNode(name=dst_question_a, parent=node.parent)

            dst_b = SurveyNode(name=dst_question_b, parent=dst_a)

            # chain the 3 questions together
            # the newly created questions need to be asked before the old one,
            # as the modified old question will aggregate the values of the new questions
            dst_a.children = [dst_b]

            # update children of parent nodes:
            #   - add dst_a as child
            #   - remove old node from children
            node.parent.children.insert(node.child_index, dst_a)
            node.parent.children.remove(node)

            # also update choice data stored for mermaid diagram generation
            if node.data.get("parent_choices"):
                dst_a.data["parent_choices"] = node.data["parent_choices"]
                node.data["parent_choices"] = None

            # insert dst_b node as child of dst_a
            dst_b.children = [node]
            node.parent = dst_b

            # initialize question data from config spreadsheet
            dst_a.from_config(questions_config, choices_config)
            dst_b.from_config(questions_config, choices_config)

            # newly created questions use same relevance rules as the old question
            dst_a.relevant = node.relevant
            dst_b.relevant = node.relevant

            # modify old question to aggregate the values of the new questions
            node.type = "calculate"
            node.calculation = calculation.format(**{dst_a.name: dst_a.uid, dst_b.name: dst_b.uid})

    return root


def calculate(
    root: SurveyNode,
    src_question: str,
    dst_question: str,
    calculation: str,
    questions_config: dict,
    choices_config: dict,
) -> SurveyNode:
    """Replace an existing question with a new calculated question.

    Args:
        root (SurveyNode): root node of the typing tree
        src_question (str): source question name (used for calculation)
        dst_question (str): new question name (will store calculation result)
        calculation (str): new xpath calculate formula for dst_question
        questions_config (dict): questions configuration data
        choices_config (dict): choices configuration data

    Returns:
        SurveyNode: root node of the typing tree
    """
    for node in root.preorder():
        # dst_question should already exist in the tree
        if node.name == dst_question:
            # new question
            new = SurveyNode(name=src_question, parent=node.parent)
            new.children = [node]
            new.relevant = node.relevant

            # update children of parent nodes:
            #   - add new question as child
            #   - remove old node from children
            node.parent.children.insert(node.child_index, new)
            node.parent.children.remove(node)

            # also update choice data stored for mermaid diagram generation
            if node.data.get("parent_choices"):
                new.data["parent_choices"] = node.data["parent_choices"]
                node.data["parent_choices"] = None

            # initialize question data from config spreadsheet
            new.from_config(questions_config, choices_config)

            # modify dst_question to store calculation result
            node.parent = new
            node.type = "calculate"
            node.calculation = calculation.format(**{new.name: new.uid})

    return root
