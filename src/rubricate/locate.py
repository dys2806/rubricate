"""Map a location inside parsed YAML (like criteria[0].scale) back to a line number."""

from __future__ import annotations  # modern type hints on Python 3.10

from collections.abc import Sequence  # type for the list of path steps

import yaml  # PyYAML: compose() builds a node tree that remembers line positions


def compose(text: str) -> yaml.Node | None:  # parse YAML into nodes instead of plain dicts
    return yaml.compose(text, Loader=yaml.SafeLoader)  # SafeLoader: no arbitrary Python objects


def line_for(root: yaml.Node | None, parts: Sequence[str | int]) -> int | None:  # 1-based line
    node = root  # start at the top of the document
    for part in parts:  # walk one step of the path at a time
        if isinstance(node, yaml.MappingNode):  # at a mapping (dict)...
            match = None  # the value node for this key, once found
            for key_node, value_node in node.value:  # ...look through its key/value pairs
                if str(key_node.value) == str(part):  # keys compare as strings ("1" == 1)
                    match = value_node  # found the key
                    break  # stop scanning this mapping
            if match is None:  # key not present (e.g. a required field is missing)
                break  # stay on the parent node, which is the closest real location
            node = match  # move down into the value
        elif isinstance(node, yaml.SequenceNode) and isinstance(part, int):  # at a list...
            if part >= len(node.value):  # index past the end
                break  # stay on the list itself
            node = node.value[part]  # ...move to the item at that index
        else:  # a scalar can't be walked into
            break  # stop at the deepest node we reached
    if node is None:  # empty document
        return None  # no line to report
    return node.start_mark.line + 1  # PyYAML lines are 0-based; editors count from 1
