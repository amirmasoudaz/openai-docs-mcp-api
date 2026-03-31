from __future__ import annotations

from dataclasses import dataclass
from bs4 import BeautifulSoup, NavigableString
from markdownify import markdownify as _markdownify

from .sources import get_source
from .text import normalize_whitespace


@dataclass(frozen=True)
class ExtractedContent:
    section: str | None
    title: str | None
    raw_html: str
    raw_body_text: str | None
    main_html: str | None
    markdown: str | None
    plain_text: str


def infer_section(url: str) -> str | None:
    """Infer section through the configured source adapter."""
    return get_source().infer_section(url)


def _pick_main_node(soup: BeautifulSoup):
    candidates = []

    def add(node):
        if not node:
            return
        text = node.get_text(" ", strip=True)
        if text:
            candidates.append((len(text), node))

    add(soup.find("main"))
    add(soup.find("article"))
    add(soup.find(attrs={"role": "main"}))

    for cls in ("prose", "markdown", "md", "content"):
        add(soup.find(class_=cls))

    for id_ in ("content", "main-content", "docs-content"):
        add(soup.find(id=id_))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return soup.find("body") or soup


def _strip_syntax_line_number_spans(main_node) -> None:
    """
    Remove gutter spans (e.g. react-syntax-highlighter-line-number) so they
    are not merged into <pre> text as 1\\n2\\n3\\n runs.
    """
    if not main_node:
        return
    for span in main_node.find_all("span"):
        classes = span.get("class") or []
        if not classes:
            continue
        if any("line-number" in str(c).lower() for c in classes):
            span.decompose()


def _flatten_syntax_highlighting(main_node) -> None:
    """
    Docs use hljs/shiki with one <span> per token. get_text(\"\\n\") then inserts
    a newline between every span, producing unusable one-token-per-line output.
    Replace each <pre> / standalone <code> subtree with a single text node.
    """
    if not main_node:
        return
    for pre in main_node.find_all("pre"):
        flat = pre.get_text(separator="", strip=False)
        pre.clear()
        pre.append(NavigableString(flat))
    for code in main_node.find_all("code"):
        if code.find_parent("pre") is not None:
            continue
        flat = code.get_text(separator="", strip=False)
        code.clear()
        code.append(NavigableString(flat))


def extract_from_cached_html(
    *,
    url: str,
    title: str | None,
    raw_html: str,
    raw_body_text: str | None,
    make_markdown: bool = False,
    keep_main_html: bool = True,
) -> ExtractedContent:
    section = infer_section(url)
    soup = BeautifulSoup(raw_html, "lxml")

    main_node = _pick_main_node(soup)
    if main_node:
        for tag in main_node.find_all(
            [
                "script",
                "style",
                "noscript",
                "svg",
                "canvas",
                "iframe",
                "header",
                "footer",
                "nav",
                "aside",
            ]
        ):
            tag.decompose()

        _strip_syntax_line_number_spans(main_node)
        _flatten_syntax_highlighting(main_node)

    main_html = str(main_node) if (keep_main_html and main_node) else None

    plain_text = ""
    if main_node:
        plain_text = main_node.get_text("\n", strip=True)
    plain_text = normalize_whitespace(plain_text)

    markdown = None
    if make_markdown and main_html:
        markdown = _markdownify(main_html, heading_style="ATX")
        markdown = normalize_whitespace(markdown)

    return ExtractedContent(
        section=section,
        title=title,
        raw_html=raw_html,
        raw_body_text=raw_body_text,
        main_html=main_html,
        markdown=markdown,
        plain_text=plain_text,
    )
