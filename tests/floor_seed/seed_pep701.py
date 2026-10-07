"""Seeds a PEP 701 f-string. Python 3.12+ only; the 3.22 floor ships 3.8.

This is the exact mistake that made fiberq/core/validation_report.py a hard
SyntaxError on QGIS 3.22 in seven places, through a green CI.
"""


def _tr(text):
    return text


def _esc(value):
    return str(value)


def title():
    # Single quotes inside a single-quoted f-string.
    return f'<h2>{_esc(_tr('Run'))}</h2><div class="meta">'
