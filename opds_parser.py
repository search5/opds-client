import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

from calibre.web.feeds.feedparser import parse as feedparser_parse

load_translations()

# ET fallback — publisher 추출 전용
_ATOM_NS = 'http://www.w3.org/2005/Atom'


@dataclass
class NavEntry:
    title: str
    url: str
    content: str = ''


@dataclass
class BookEntry:
    title: str
    authors: List[str] = field(default_factory=list)
    formats: List[dict] = field(default_factory=list)   # [{'type': 'epub', 'url': '...', 'size': 0}]
    summary: str = ''
    cover_url: str = ''
    publisher: str = ''


@dataclass
class NavigationFeed:
    title: str
    entries: List[NavEntry] = field(default_factory=list)


@dataclass
class AcquisitionFeed:
    title: str
    entries: List[BookEntry] = field(default_factory=list)
    next_url: Optional[str] = None
    total_results: int = 0


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _is_navigation_link_type(mime: str) -> bool:
    return 'application/atom+xml' in mime


def _is_acquisition_link_type(mime: str) -> bool:
    download_types = (
        'application/epub+zip',
        'application/pdf',
        'application/x-mobipocket-ebook',
        'application/vnd.amazon.mobi8-ebook',
        'application/fb2',
        'application/zip',
        'application/x-cbz',
        'application/x-cbr',
    )
    return any(mime.startswith(t) for t in download_types)


def _ext_from_mime(mime: str) -> str:
    mapping = {
        'application/epub+zip':              'epub',
        'application/pdf':                   'pdf',
        'application/x-mobipocket-ebook':    'mobi',
        'application/vnd.amazon.mobi8-ebook':'azw3',
        'application/fb2':                   'fb2',
        'application/zip':                   'zip',
        'application/x-cbz':                 'cbz',
        'application/x-cbr':                 'cbr',
    }
    for k, v in mapping.items():
        if mime.startswith(k):
            return v
    return mime.split('/')[-1]


def _detect_feed_type(result) -> str:
    """
    우선순위:
    1. entry에 acquisition rel 링크 → acquisition
    2. feed self 링크 type → acquisition / navigation
    3. entry link mime → navigation
    """
    for entry in result.entries:
        for link in entry.get('links', []):
            rel = link.get('rel', '')
            mime = link.get('type', '')
            if rel.startswith('http://opds-spec.org/acquisition') or (
                not rel and _is_acquisition_link_type(mime)
            ):
                return 'acquisition'

    for link in result.feed.get('links', []):
        if link.get('rel') == 'self':
            t = link.get('type', '')
            if 'kind=acquisition' in t:
                return 'acquisition'
            if 'kind=navigation' in t:
                return 'navigation'

    for entry in result.entries:
        for link in entry.get('links', []):
            if _is_navigation_link_type(link.get('type', '')):
                return 'navigation'

    return 'navigation'


def _atom_publishers(xml_bytes: bytes) -> List[str]:
    """
    feedparser가 처리 못하는 <publisher><name>...</name></publisher>
    (Calibre-Web 방식) 을 ET로 보완. entry 순서대로 반환.
    """
    try:
        root = ET.fromstring(xml_bytes)
        result = []
        for entry in root.findall('{%s}entry' % _ATOM_NS):
            pub_el = entry.find('{%s}publisher' % _ATOM_NS)
            if pub_el is not None:
                name_el = pub_el.find('{%s}name' % _ATOM_NS)
                result.append(
                    (name_el.text if name_el is not None else pub_el.text) or ''
                )
            else:
                result.append('')
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def parse_feed(xml_bytes: bytes):
    """
    XML 바이트를 파싱해 NavigationFeed 또는 AcquisitionFeed를 반환.
    calibre.web.feeds.feedparser 사용 (불량 XML에 대한 복구 내장).
    """
    result = feedparser_parse(xml_bytes)

    # feedparser가 파싱 실패하고 entry도 없으면 오류 전달
    if result.get('bozo') and not result.entries:
        exc = result.get('bozo_exception')
        raise ValueError(
            _('Failed to parse OPDS feed: %s') % str(exc)
        )

    feed_title = result.feed.get('title', '')
    feed_type = _detect_feed_type(result)

    if feed_type == 'navigation':
        return _parse_navigation(result, feed_title)
    else:
        return _parse_acquisition(result, feed_title, xml_bytes)


def _parse_navigation(result, feed_title: str) -> NavigationFeed:
    entries = []
    for entry in result.entries:
        title = entry.get('title', _('(no title)'))
        summary = entry.get('summary', '')

        url = ''
        for link in entry.get('links', []):
            rel = link.get('rel', 'alternate')
            if rel in ('alternate', 'subsection',
                       'http://opds-spec.org/subsection'):
                url = link.get('href', '')
                break
        if not url and entry.get('links'):
            url = entry['links'][0].get('href', '')

        entries.append(NavEntry(title=title, url=url, content=summary))

    return NavigationFeed(title=feed_title, entries=entries)


def _parse_acquisition(result, feed_title: str,
                        xml_bytes: bytes) -> AcquisitionFeed:
    # 페이지네이션
    next_url = None
    for link in result.feed.get('links', []):
        if link.get('rel') == 'next':
            next_url = link.get('href')

    total_results = 0
    try:
        total_results = int(result.feed.get('os_totalresults', 0) or 0)
    except (ValueError, TypeError):
        pass

    # ET fallback으로 Atom <publisher><name> 미리 수집
    atom_pubs = _atom_publishers(xml_bytes)

    entries = []
    for i, entry in enumerate(result.entries):
        title = entry.get('title', _('(no title)'))

        authors = [
            a['name'] for a in entry.get('authors', []) if a.get('name')
        ]

        summary = entry.get('summary', '')

        # 출판사: dcterms_publisher 우선, 없으면 ET 결과
        publisher = entry.get('dcterms_publisher', '') or ''
        if not publisher and i < len(atom_pubs):
            publisher = atom_pubs[i]

        cover_url = ''
        formats = []
        for link in entry.get('links', []):
            rel  = link.get('rel', '')
            mime = link.get('type', '')
            href = link.get('href', '')

            if rel in ('http://opds-spec.org/image',
                       'http://opds-spec.org/cover'):
                cover_url = href
            elif rel == 'http://opds-spec.org/image/thumbnail':
                if not cover_url:
                    cover_url = href
            elif (rel.startswith('http://opds-spec.org/acquisition')
                  and _is_acquisition_link_type(mime)):
                size = 0
                try:
                    size = int(link.get('length', 0) or 0)
                except (ValueError, TypeError):
                    pass
                formats.append({
                    'type': _ext_from_mime(mime),
                    'mime': mime,
                    'url':  href,
                    'size': size,
                })
            elif not rel and _is_acquisition_link_type(mime):
                size = 0
                try:
                    size = int(link.get('length', 0) or 0)
                except (ValueError, TypeError):
                    pass
                formats.append({
                    'type': _ext_from_mime(mime),
                    'mime': mime,
                    'url':  href,
                    'size': size,
                })

        entries.append(BookEntry(
            title=title,
            authors=authors,
            formats=formats,
            summary=summary,
            cover_url=cover_url,
            publisher=publisher,
        ))

    return AcquisitionFeed(
        title=feed_title,
        entries=entries,
        next_url=next_url,
        total_results=total_results,
    )
