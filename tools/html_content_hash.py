#!/usr/bin/env python3
"""Versioned content hash for dynamic HTML disclosure pages (auxiliary change signal only).

Some disclosure pages embed a session id and a server-node marker that change on every request,
so their byte hash differs on every fetch. This module computes a second hash over what a reader
sees, so that a refetch whose only differences are those volatile tokens is not mistaken for a
new document version.

It is an AUXILIARY signal. It never stands in for byte identity: the raw bytes and their SHA-256
are always archived and reported separately, and "content hash equal" is reported as
`bytes_changed_content_same`, never as identical or verified.

Rule html-visible-text-v3 (bump the version for any change to these steps):
 1. decode: <meta charset> / http-equiv charset if declared, else utf-8, then euc-kr, then cp949
 2. drop HTML comments, <script>, <style> (session ids live in scripts)
 3. keep <title> text, minus host-specific volatile markers listed in VOLATILE_TITLE
 4. parse HTML attributes (quoted or unquoted, case-insensitive names); keep a href, iframe src,
    embed src, object data and form action targets as "[link:...]",
    minus session parameters. ";jsessionid=" path parameters and the unambiguous query names in
    SESSION_PARAMS (jsessionid, sessionid, phpsessid) are removed on every host. Query names that
    other sites use as real identifiers (sid, _t, _, ts, timestamp) are removed only on hosts
    listed in HOST_VOLATILE_PARAMS; on any other host they are kept, because a changed `sid=`
    can be a different document. The host is the link's own host, else the page host.
 5. keep every nonempty onclick attribute as "[onclick:...]" on any element. Preserve the whole
    handler conservatively, including computed targets; do not execute JavaScript or guess which
    strings are file names. Handler session tokens/code changes can therefore change the hash.
 6. strip remaining tags, decode HTML entities once, collapse every run of whitespace to one space
 7. SHA-256 of the UTF-8 result

History: v1 stripped sid/_t/_/ts/timestamp from every link on every host, so a site using `sid`
as a document id reported a changed link as unchanged. v2 scoped them per host but missed unquoted
targets and onclick handlers. v3 parses attributes and preserves handlers. Hashes under older
rules are not comparable (verify_sources.py only compares equal rule names, so they count as
`changed` until re-baselined); adding a host to HOST_VOLATILE_PARAMS needs a new version.

Meaningful changes that MUST change the hash (tools/tests/test_html_content_hash.py): title,
product name, effective date, price, payout condition, linked document file name, table rows.
"""
import hashlib
import re
import sys
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

RULE = "html-visible-text-v3"
# host suffix -> regex removed from <title> text
VOLATILE_TITLE = {"kbinsure.co.kr": re.compile(r"\s*\[[A-Z]\]\s*$")}
# query names that only ever carry a session id: removed on every host
SESSION_PARAMS = {"jsessionid", "sessionid", "phpsessid"}
# host suffix -> extra query names that are volatile only on that host. KB's `_t` is the one seen in
# the fixture; whether the live page also varies sid/_/ts per fetch is unchecked (needs the R2 originals).
HOST_VOLATILE_PARAMS = {"kbinsure.co.kr": {"_t"}}
LINK_ATTRIBUTES = {"a": "href", "iframe": "src", "embed": "src", "object": "data", "form": "action"}


def decode(raw):
    m = re.search(rb"<meta[^>]+charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", raw[:4096], re.I)
    tried = ([m.group(1).decode("ascii", "ignore")] if m else []) + ["utf-8", "euc-kr", "cp949"]
    for enc in tried:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace"), "utf-8-replace"


def host_matches(host, suffix):
    host = host.lower().rsplit("@", 1)[-1].split(":", 1)[0]
    return host == suffix or host.endswith("." + suffix)


def volatile_params(host):
    names = set(SESSION_PARAMS)
    for suffix, extra in HOST_VOLATILE_PARAMS.items():
        if host_matches(host, suffix):
            names |= extra
    return names


def clean_link(url, host=""):
    url = re.sub(r";jsessionid=[^?#]*", "", url, flags=re.I)
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    drop = volatile_params(parts.netloc or host)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in drop]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


class _ContentParser(HTMLParser):
    """Read attributes as HTML, without evaluating handlers or fetching their targets."""

    def __init__(self, host):
        super().__init__(convert_charrefs=True)
        self.host = host
        self.parts = []
        self.hidden = None
        self.title_parts = None

    def finish_title(self):
        if self.title_parts is None:
            return
        title = "".join(self.title_parts)
        for suffix, pat in VOLATILE_TITLE.items():
            if host_matches(self.host, suffix):
                title = pat.sub("", title)
        self.parts.append(f" {title} ")
        self.title_parts = None

    def handle_starttag(self, tag, attrs):
        if self.hidden:
            return
        self.handle_data(" ")
        if tag in {"script", "style"}:
            self.hidden = tag
            return
        if tag == "title":
            self.title_parts = []
        for name, value in attrs:
            if value is None:
                continue
            if name == LINK_ATTRIBUTES.get(tag):
                self.parts.append(f" [link:{clean_link(value, self.host)}] ")
            elif name == "onclick" and value.strip():
                self.parts.append(f" [onclick:{value}] ")

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden:
                self.hidden = None
            return
        if tag == "title":
            self.finish_title()
        self.handle_data(" ")

    def handle_data(self, data):
        if not self.hidden:
            (self.title_parts if self.title_parts is not None else self.parts).append(data)

    def handle_comment(self, data):
        self.handle_data(" ")


def normalized_text(raw, host=""):
    text, _ = decode(raw)
    parser = _ContentParser(host)
    parser.feed(text)
    parser.close()
    parser.finish_title()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def content_sha256(raw, host=""):
    return hashlib.sha256(normalized_text(raw, host).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # usage: html_content_hash.py FILE HOST
    with open(sys.argv[1], "rb") as f:
        print(RULE, content_sha256(f.read(), sys.argv[2] if len(sys.argv) > 2 else ""))
