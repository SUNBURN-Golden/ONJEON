use onjeon_collect::{
    s3::{Credentials, S3Store},
    store::StoredSha,
    Store,
};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;

#[test]
fn local_s3_wire_put_head_get_list_and_precondition() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    let server = std::thread::spawn(move || {
        for operation in ["PUT", "HEAD", "GET", "GET", "PUT"] {
            let (socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                .unwrap();
            let mut input = BufReader::new(socket);
            let mut line = String::new();
            input.read_line(&mut line).unwrap();
            assert!(line.starts_with(operation));
            let listing = line.contains("list-type=2");
            let mut headers = Vec::new();
            loop {
                line.clear();
                input.read_line(&mut line).unwrap();
                if line == "\r\n" {
                    break;
                }
                headers.push(line.trim().to_ascii_lowercase());
            }
            assert_eq!(headers.iter().filter(|h| h.starts_with("host:")).count(), 1);
            assert!(headers
                .iter()
                .any(|h| h.starts_with("authorization:") && h.contains("host;")));
            if operation == "PUT" {
                assert!(headers.contains(&"if-none-match: *".into()));
                let mut body = [0; 12];
                input.read_exact(&mut body).unwrap();
                assert_eq!(&body, b"fixture_only");
            }
            let body = if listing {
                b"<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>prefix/k</Key></Contents></ListBucketResult>".as_slice()
            } else {
                b"fixture_only"
            };
            let status = if operation == "PUT"
                && headers
                    .iter()
                    .any(|h| h == "content-type: conflict/fixture_only")
            {
                412
            } else {
                200
            };
            let response = format!(
                "HTTP/1.1 {status} fixture_only\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            );
            input.get_mut().write_all(response.as_bytes()).unwrap();
            if operation != "HEAD" {
                input.get_mut().write_all(body).unwrap();
            }
        }
    });
    let store = S3Store::new(
        "s3://fixture-only/prefix",
        Some(&endpoint),
        Credentials {
            access_key: "fixture_only".into(),
            secret_key: "fixture_only".into(),
        },
        None,
        None,
    )
    .unwrap();
    store.put_new("k", b"fixture_only", "text/plain").unwrap();
    assert_eq!(store.stored_sha256("k").unwrap(), StoredSha::NoChecksum);
    assert_eq!(store.get("k").unwrap(), b"fixture_only");
    assert_eq!(store.list("").unwrap(), vec!["k"]);
    assert_eq!(
        store
            .put_new("k", b"fixture_only", "conflict/fixture_only")
            .unwrap_err()
            .kind,
        "exists"
    );
    server.join().unwrap();
}
