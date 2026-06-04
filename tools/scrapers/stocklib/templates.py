"""
Shared Jinja2 environment for the page builders.

autoescape is the whole point: values interpolated into a template (nursery
titles, URLs with query strings, anything from the scraped data) are
HTML-escaped, so an `&`, `<`, `>`, or quote in the data produces valid markup
instead of a broken attribute or element. The builders historically used bare
f-strings, which escape nothing -- a title like "Fig & Olive" or a UTM URL
with `&` went into the HTML raw.

Templates live in stocklib/templates/ (loaded by name, e.g.
"treesmith_page.html.j2").

keep_trailing_newline=True so a template's trailing newline survives rendering.
That lets a migrated builder's output stay byte-identical to its old f-string
*except for the escaping*, which keeps the golden diff readable: it shows the
entity-escaping and nothing else. trim_blocks/lstrip_blocks keep `{% %}` block
tags from leaving stray blank lines in the output of the loop-heavy builders
migrated later.

The VPS build runs system Python with jinja2 installed via apt (python3-jinja2);
locally, `pip install jinja2`. See requirements.txt.
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def get_env() -> Environment:
    """The shared, autoescaping Jinja2 Environment (for filters/globals tweaks)."""
    return _env


def render(template_name: str, **context) -> str:
    """Render a template from stocklib/templates/ with the given context."""
    return _env.get_template(template_name).render(**context)
