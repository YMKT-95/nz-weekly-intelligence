"""Small, sequential collector for public NZ economic and labour-market pages."""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from protego import Protego

from src.config import Settings
from src.models import ResearchBatch, SourceDocument, SourceFailure, SourceLink

logger = logging.getLogger(__name__)
USER_AGENT = "NZWeeklyIntelligence/0.2 (+https://github.com/YMKT-95/nz-weekly-intelligence)"
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 3


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    category: str
    url: str
    expected_text: str
    parser: Literal["html", "stats", "seek_newsroom"] = "html"


SOURCES = (
    Source("stats_unemployment", "Stats NZ", "NZ Labour Market",
           "https://www.stats.govt.nz/indicators/unemployment-rate/", "unemployment", "stats"),
    Source("stats_cpi", "Stats NZ", "NZ Economy",
           "https://www.stats.govt.nz/indicators/consumers-price-index-cpi/", "price index", "stats"),
    Source("rbnz_ocr", "RBNZ", "NZ Economy",
           "https://www.rbnz.govt.nz/monetary-policy/monetary-policy-decisions", "OCR"),
    Source("mbie_jobs_online", "MBIE", "NZ Labour Market",
           "https://www.mbie.govt.nz/business-and-employment/employment-and-skills/"
           "labour-market-reports-data-and-analysis/jobs-online", "Jobs Online"),
    Source("seek_newsroom", "SEEK NZ", "NZ Labour Market",
           "https://nz.seek.com/about/news", "Employment reports", "seek_newsroom"),
)


class SourceUnavailable(ValueError):
    """A source could not be collected safely or did not contain useful text."""


class DirectFetcher:
    """Share robots policies and per-origin request timing during one run."""

    def __init__(self, client: httpx.Client):
        self.client = client
        self.policies: dict[str, Protego | str] = {}
        self.last_request: dict[str, float] = {}

    def _request(self, url: str, delay: float = 1.0) -> httpx.Response:
        origin = _origin(url)
        remaining = delay - (time.monotonic() - self.last_request.get(origin, -float("inf")))
        if remaining > 0:
            time.sleep(remaining)
        try:
            with self.client.stream("GET", url, follow_redirects=False) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise SourceUnavailable("Response exceeds the 2 MB collection limit")
                # iter_bytes decompresses the response; retain only relevant headers.
                headers = {key: response.headers[key] for key in ("content-type", "location")
                           if key in response.headers}
                return httpx.Response(response.status_code, headers=headers,
                                      content=bytes(body), request=response.request)
        finally:
            self.last_request[origin] = time.monotonic()

    def _policy(self, origin: str) -> Protego:
        if origin not in self.policies:
            try:
                response = self._request(origin + "/robots.txt")
                if response.status_code in (404, 410):
                    self.policies[origin] = Protego.parse("")
                elif response.status_code != 200:
                    raise SourceUnavailable(f"robots.txt unavailable (HTTP {response.status_code})")
                elif "<html" in response.text.lower() or "<script" in response.text.lower():
                    raise SourceUnavailable("robots.txt returned HTML instead of access rules")
                else:
                    self.policies[origin] = Protego.parse(response.text)
            except (httpx.HTTPError, SourceUnavailable) as exc:
                self.policies[origin] = str(exc) or type(exc).__name__
        policy = self.policies[origin]
        if isinstance(policy, str):
            raise SourceUnavailable(policy)
        return policy

    def fetch(self, url: str) -> tuple[str, str]:
        origin = _origin(url)
        for _ in range(MAX_REDIRECTS + 1):
            policy = self._policy(origin)
            if not policy.can_fetch(url, USER_AGENT):
                raise SourceUnavailable("Collection disallowed by robots.txt")
            delay = max(1.0, policy.crawl_delay(USER_AGENT) or 0)
            rate = policy.request_rate(USER_AGENT)
            if policy.visit_time(USER_AGENT) or (rate and (rate.start_time or rate.end_time)):
                raise SourceUnavailable("Time-restricted robots policy requires manual source review")
            if rate:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 60:
                raise SourceUnavailable("Required crawl interval exceeds the 60-second run limit")
            response = self._request(url, delay)
            if response.is_redirect:
                target = urljoin(url, response.headers.get("location", ""))
                if not response.headers.get("location") or _origin(target) != origin:
                    raise SourceUnavailable("Redirect outside the configured origin; review the source URL")
                url = target
                continue
            if response.status_code != 200:
                raise SourceUnavailable(f"Source returned HTTP {response.status_code}")
            media_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type not in ("text/html", "application/xhtml+xml"):
                raise SourceUnavailable(f"Unsupported content type: {media_type or 'missing'}")
            return url, response.text
        raise SourceUnavailable("Too many redirects")


def _origin(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.username or parts.password:
        raise SourceUnavailable("Only public HTTPS source URLs without credentials are supported")
    return f"{parts.scheme}://{parts.netloc}"


def _plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, nav, header, footer, form, [hidden], [aria-hidden=true]"):
        tag.decompose()
    # Separate cells explicitly so table headings and values remain readable.
    for row in soup.select("tr"):
        row.replace_with("\n" + " | ".join(cell.get_text(" ", strip=True)
                         for cell in row.find_all(["th", "td"], recursive=False)) + "\n")
    return "\n".join(line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip())


def _stats_text(soup: BeautifulSoup) -> tuple[str, str | None, dict]:
    node = soup.select_one("#pageViewData[data-value]")
    if node is None:
        raise SourceUnavailable("Stats NZ embedded page data was not found")
    try:
        payload = json.loads(node["data-value"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise SourceUnavailable("Stats NZ embedded page data is invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("PageBlocks"), list):
        raise SourceUnavailable("Stats NZ page data has an unsupported structure")
    parts = [_plain_text(str(payload.get("Title", ""))),
             _plain_text(str(payload.get("FeaturedText", "")))]
    updated = None
    has_indicator = False
    # Preserve original array positions and exact indicator fields for evidence pointers.
    structured = {"PageBlocks": []}
    for block in payload["PageBlocks"]:
        structured["PageBlocks"].append(None)
        if not isinstance(block, dict):
            continue
        if block.get("ClassName") == "IndicatorBlock":
            has_indicator = True
            keys = {"ClassName", "Name", "LastUpdatedDate", "NextUpdatedDate", "CorrectedDate"}
            keys.update(key + suffix for suffix in ("", "2", "3", "4", "5", "6")
                        for key in ("Description", "Value", "Period"))
            structured["PageBlocks"][-1] = {key: value for key, value in block.items() if key in keys}
            parts.append(str(block.get("Name", "")))
            for suffix in ("", "2", "3", "4", "5", "6"):
                for key in ("Description", "Value", "Period"):
                    value = block.get(key + suffix)
                    if value is not None:
                        parts.append(f"{key}{suffix}: {value}")
            for key in ("LastUpdatedDate", "NextUpdatedDate", "CorrectedDate"):
                if block.get(key):
                    parts.append(f"{key}: {block[key]}")
            updated = block.get("LastUpdatedDate") or updated
        elif block.get("ClassName") == "TextBlock":
            parts.append(_plain_text(str(block.get("Content", ""))))
        elif block.get("ClassName") == "GraphTableBlock":
            parts.append(str(block.get("GraphHeading") or block.get("Title", "")))
            for series in block.get("SeriesData") or []:
                if isinstance(series, dict) and series.get("GraphCsvData"):
                    parts.append(str(series["GraphCsvData"]))
    if not has_indicator:
        raise SourceUnavailable("Stats NZ page no longer contains an indicator block")
    return "\n".join(part for part in parts if part), updated, structured


def parse_document(source: Source, url: str, html: str, retrieved_at: datetime) -> SourceDocument:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find("title") or soup.find("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    root = soup.select_one("main, [role=main], article") or soup.body or soup
    updated = None
    structured = None
    if source.parser == "stats":
        text, updated, structured = _stats_text(soup)
    else:
        text = _plain_text(str(root))
    challenge_titles = ("access denied", "just a moment", "website unavailable", "verify you are human")
    if (not title or any(marker in title.lower() for marker in challenge_titles)
            or len(text) < 100 or source.expected_text.lower() not in text.lower()):
        raise SourceUnavailable("No usable source content; possible access challenge or changed page layout")
    links = []
    seen = set()
    for anchor in root.select("a[href]"):
        target = urldefrag(urljoin(url, anchor["href"]))[0]
        parts = urlsplit(target)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password:
            continue
        if target not in seen:
            seen.add(target)
            links.append(SourceLink(label=anchor.get_text(" ", strip=True), url=target))
    published = soup.select_one('meta[property="article:published_time"], meta[itemprop="datePublished"]')
    modified = soup.select_one('meta[property="article:modified_time"], meta[itemprop="dateModified"]')
    return SourceDocument(
        source_id=source.id, source=source.name, category=source.category,
        requested_url=source.url, source_url=url, title=title, text=text,
        retrieved_at=retrieved_at,
        published_at_raw=published.get("content") if published else None,
        updated_at_raw=updated or (modified.get("content") if modified else None),
        collection_method="embedded_page_json" if source.parser == "stats" else "html",
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), links=links,
        structured_data=structured,
        structured_sha256=hashlib.sha256(json.dumps(
            structured, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest() if structured is not None else None,
    )


def collect_research(settings: Settings, report_week: str, week_start: date, week_end: date,
                     *, sources: tuple[Source, ...] = SOURCES,
                     transport: httpx.BaseTransport | None = None) -> ResearchBatch:
    started = datetime.now(settings.timezone)
    documents = []
    failures = []
    queue = list(sources)
    with httpx.Client(timeout=settings.research_timeout_seconds, transport=transport,
                      headers={"User-Agent": USER_AGENT}) as client:
        fetcher = DirectFetcher(client)
        for source in queue:
            logger.info("Researching %s: %s", source.category, source.id)
            attempted = datetime.now(settings.timezone)
            try:
                url, html = fetcher.fetch(source.url)
                document = parse_document(source, url, html, datetime.now(settings.timezone))
                documents.append(document)
                logger.info("Collected %s (%d characters)", source.id, len(document.text))
                if source.parser == "seek_newsroom":
                    # Follow only the first employment report listed by the newsroom.
                    # Its position is not proof that it was published this week.
                    candidate = next((link for link in document.links
                                      if _is_seek_report(str(link.url), source.url)), None)
                    if candidate is None:
                        raise SourceUnavailable("SEEK newsroom has no discoverable employment report link")
                    queue.append(replace(source, id="seek_employment_report", url=str(candidate.url),
                                         expected_text="job ad", parser="html"))
            except (httpx.HTTPError, ValueError) as exc:
                reason = str(exc) or type(exc).__name__
                failures.append(SourceFailure(source_id=source.id, source=source.name,
                                              source_url=source.url, attempted_at=attempted, reason=reason))
                logger.warning("%s unavailable: %s", source.id, reason)
    return ResearchBatch(report_week=report_week, week_start=week_start, week_end=week_end,
                         started_at=started, completed_at=datetime.now(settings.timezone),
                         documents=documents, failures=failures)


def _is_seek_report(url: str, newsroom_url: str) -> bool:
    parts = urlsplit(url)
    newsroom = urlsplit(newsroom_url)
    return (parts.scheme == "https" and parts.netloc == newsroom.netloc
            and parts.path.startswith("/about/news/article/")
            and "employment-report" in parts.path and not parts.query)


def save_research(batch: ResearchBatch, directory: Path) -> Path:
    # A separate file per run preserves successful snapshots after failed reruns.
    week_dir = directory / batch.report_week
    week_dir.mkdir(parents=True, exist_ok=True)
    stamp = batch.started_at.strftime("%Y%m%dT%H%M%S%f%z")
    destination = week_dir / f"{stamp}.json"
    with destination.open("x", encoding="utf-8") as file:
        file.write(batch.model_dump_json(indent=2) + "\n")
    return destination
