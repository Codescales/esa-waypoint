import markdown as md_lib

_EXTENSIONS = [
    "markdown.extensions.fenced_code",
    "markdown.extensions.attr_list",
]

def render_markdown(text: str) -> str:
    return md_lib.markdown(text, extensions=_EXTENSIONS)
