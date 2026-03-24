from __future__ import annotations

import markdown as markdown_library
import nh3
from django.utils.safestring import mark_safe

MARKDOWN_EXTENSIONS = [
    'extra',
    'sane_lists',
]

ALLOWED_TAGS = set(nh3.ALLOWED_TAGS).union(
    {
        'p',
        'pre',
        'hr',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'table',
        'thead',
        'tbody',
        'tr',
        'th',
        'td',
        'img',
        'dl',
        'dt',
        'dd',
        'sup',
    }
)

ALLOWED_ATTRIBUTES = {
    **{tag: set(attributes) for tag, attributes in nh3.ALLOWED_ATTRIBUTES.items()},
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'title', 'loading'},
    'th': {'align'},
    'td': {'align'},
    'code': {'class'},
}

ALLOWED_PROTOCOLS = set(nh3.ALLOWED_URL_SCHEMES).union({'tel'})
STRIP_CONTENT_TAGS = {'script', 'style', 'iframe', 'object', 'embed'}


def render_markdown(content: str) -> str:
    raw_html = markdown_library.markdown(content or '', extensions=MARKDOWN_EXTENSIONS)
    sanitized_html = nh3.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        clean_content_tags=STRIP_CONTENT_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_PROTOCOLS,
        strip_comments=True,
        link_rel='noopener noreferrer',
    )
    return mark_safe(sanitized_html)
