import ipaddress
import re
import socket
from email.message import Message
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 500 * 1024
TIMEOUT_SECONDS = 20
REDIRECT_LIMIT = 5
TEXT_APPLICATION_TYPES = {
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/javascript",
    "application/ld+json",
}


class FetchError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str):
        if tag.lower() in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str):
        if not self.hidden_depth:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def _is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address in ipaddress.ip_network("127.0.0.0/8") or address in ipaddress.ip_network("169.254.0.0/16")


def _check_url(url: str, internal: bool) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise FetchError(f"Invalid URL: {error}") from error
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise FetchError("Only http and https URLs are allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise FetchError("URLs containing credentials are not allowed.")
    if not internal:
        hostname = parsed.hostname.rstrip(".")
        addresses = [hostname] if _is_blocked_ip(hostname) else []
        if not addresses:
            try:
                addresses = list(
                    {result[4][0] for result in socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)}
                )
            except OSError:
                addresses = []
        if any(_is_blocked_ip(address) for address in addresses):
            raise FetchError("Loopback and link-local destinations require internal=1.", 403)
    return url


def _is_text_content_type(content_type: str) -> bool:
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return media_type.startswith("text/") or media_type in TEXT_APPLICATION_TYPES


def _decode_body(data: bytes, content_type: str) -> str:
    message = Message()
    message["content-type"] = content_type
    charset = message.get_content_charset() or "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def _extract_text(text: str, content_type: str) -> str:
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        parser = TextExtractor()
        parser.feed(text)
        parser.close()
        return parser.text()
    return text.strip()


async def fetch_url(url: str, internal: bool = False) -> dict[str, str | int]:
    current_url = _check_url(url, internal)
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        for redirect_count in range(REDIRECT_LIMIT + 1):
            try:
                async with client.stream("GET", current_url, headers={"User-Agent": "ResearchHub/0.1"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirect response did not include a location.", 502)
                        if redirect_count == REDIRECT_LIMIT:
                            raise FetchError("Too many redirects.", 502)
                        current_url = _check_url(urljoin(current_url, location), internal)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if not _is_text_content_type(content_type):
                        raise FetchError(f"Rejected non-text content type: {content_type or 'missing'}.", 415)
                    body = bytearray()
                    truncated = False
                    length_header = response.headers.get("content-length")
                    if length_header and length_header.isdigit() and int(length_header) > MAX_BYTES:
                        truncated = True
                    async for chunk in response.aiter_bytes():
                        remaining = MAX_BYTES - len(body)
                        if remaining <= 0:
                            truncated = True
                            break
                        body.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            truncated = True
                            break
                    raw = bytes(body)
                    text = _extract_text(_decode_body(raw, content_type), content_type)
                    note = "Response truncated at 500 KiB." if truncated else ""
                    return {"text": text, "bytes": len(raw), "note": note}
            except httpx.TimeoutException as error:
                raise FetchError("Fetch timed out after 20 seconds.", 504) from error
            except httpx.HTTPStatusError as error:
                raise FetchError(f"Upstream returned HTTP {error.response.status_code}.", 502) from error
            except httpx.RequestError as error:
                raise FetchError(f"Fetch failed: {error.__class__.__name__}.", 502) from error
    raise FetchError("Too many redirects.", 502)
