import re
import markdown as md
import bleach
from bs4 import BeautifulSoup

TAGS = "p br strong em b i u blockquote pre code h1 h2 h3 h4 h5 h6 ul ol li a img hr span".split()
ATTRS = {"a": ["href", "title", "rel"], "img": ["src", "alt", "title", "loading"]}
BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "ul", "ol", "figure"}


def sanitize(html):
    return re.sub(r"<img ", '<img loading="lazy" ', bleach.clean(html, tags=TAGS, attributes=ATTRS, strip=True))


def _para(el):
    txt = el.get_text(" ", strip=True) if hasattr(el, "get_text") else ""
    is_img = el.name == "img"
    if not txt and not is_img and not (hasattr(el, "find") and el.find("img")):
        return None
    h = sanitize(str(el)) if (el.name in BLOCKS or is_img or el.name == "hr") else f"<p>{sanitize(str(el))}</p>"
    return {"html": h, "plain": txt}


def html_paragraphs(html):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.body or soup
    out, seen = [], set()
    for el in container.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "figure", "img", "hr"]):
        if any(id(a) in seen for a in el.parents):
            continue
        seen.add(id(el))
        if (p := _para(el)):
            out.append(p)
    return out


def split_soup(soup):
    chapters, title, paras = [], None, []
    for el in list(soup.children):
        n = getattr(el, "name", None)
        if not n:
            continue
        if n in ("h1", "h2"):
            if paras or title:
                chapters.append((title, paras))
            title, paras = el.get_text(" ", strip=True), []
        elif (p := _para(el)):
            paras.append(p)
    if paras or title:
        chapters.append((title, paras))
    return chapters


def parse_markdown(text):
    return split_soup(BeautifulSoup(md.markdown(text, extensions=["extra", "sane_lists"]), "html.parser")) or [(None, [])]
