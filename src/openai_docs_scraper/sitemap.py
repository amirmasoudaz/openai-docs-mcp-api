from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class SitemapUrl:
    loc: str


def parse_sitemap_xml(xml_bytes: bytes) -> list[SitemapUrl]:
    root = ET.fromstring(xml_bytes)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[SitemapUrl] = []
    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not (loc_el.text or "").strip():
            continue
        urls.append(SitemapUrl(loc=loc_el.text.strip()))
    return urls

