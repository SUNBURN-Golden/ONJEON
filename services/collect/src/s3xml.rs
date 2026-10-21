//! The slice of S3 XML this client reads: `<Key>`/`<IsTruncated>`/`<NextContinuationToken>`
//! out of ListObjectsV2 and `<Code>` out of an error body. It is a tag-text extractor — the
//! endpoints are the local Compose store, a test stub, or R2, so no namespace handling is
//! needed; the five entities S3 may emit are unescaped.

/// Text content of every `<name>...</name>` element in `xml`, in document order.
pub fn texts(xml: &str, name: &str) -> Vec<String> {
    let open = format!("<{name}>");
    let open_attr = format!("<{name} ");
    let close = format!("</{name}>");
    let mut out = Vec::new();
    let mut rest = xml;
    while let Some(mut i) = rest.find(&open).or_else(|| rest.find(&open_attr)) {
        if rest[i..].starts_with(&open_attr) {
            // skip the attributes to the '>'
            i += match rest[i..].find('>') {
                Some(j) => j + 1,
                None => break,
            };
        } else {
            i += open.len();
        }
        let end = match rest[i..].find(&close) {
            Some(j) => i + j,
            None => break,
        };
        out.push(unescape(&rest[i..end]));
        rest = &rest[end + close.len()..];
    }
    out
}

/// First `<name>` text, if any.
pub fn text(xml: &str, name: &str) -> Option<String> {
    texts(xml, name).into_iter().next()
}

fn unescape(s: &str) -> String {
    s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&amp;", "&")
}
