import markdown as md_lib
import nh3

_EXTENSIONS = [
    "markdown.extensions.fenced_code",
    "markdown.extensions.attr_list",
]

_ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "em",
    "code", "pre",
    "blockquote",
    "a", "br",
    "hr",
    "table", "thead", "tbody", "tr", "th", "td",
    "dl", "dt", "dd",
}

_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "th": {"align"},
    "td": {"align"},
    "code": {"class"},
    "pre": {"class"},
}


def render_markdown(text: str) -> str:
    html = md_lib.markdown(text, extensions=_EXTENSIONS)
    return nh3.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRIBUTES)
