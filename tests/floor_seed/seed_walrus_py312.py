"""Seeds a PEP 695 type-parameter list. Python 3.12+ only.

A second, unrelated syntax class, so the self-test does not rest on one feature.
"""


def first[T](items: list[T]) -> T:
    return items[0]
