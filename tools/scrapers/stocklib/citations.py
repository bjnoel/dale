"""
Shared inline-citation rendering for the curated guide builders.

The guide pages (when-to-plant, bare-root season) cite authoritative Australian
sources inline as small bracketed links. One definition lives here so the
builders cannot drift on the rel/target/styling contract.
"""


def inline_cite(label: str, url: str) -> str:
    """A small bracketed citation link to an authoritative source."""
    safe = url.replace("&", "&amp;")
    return (f' <a href="{safe}" rel="noopener nofollow" target="_blank" '
            f'class="text-xs text-green-700 hover:underline whitespace-nowrap">[{label}]</a>')
