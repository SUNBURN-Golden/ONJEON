use onjeon_collect::{http::Response, s3::*, Store};
use std::sync::{Arc, Mutex};

struct FixtureTransport(Arc<Mutex<Vec<SignedRequest>>>, u16);
impl S3Transport for FixtureTransport {
    fn send(&self, req: &SignedRequest) -> Result<Response, onjeon_collect::StoreError> {
        self.0.lock().unwrap().push(SignedRequest {
            method: req.method,
            path: req.path.clone(),
            query: req.query.clone(),
            headers: req.headers.clone(),
            body: req.body.clone(),
        });
        Ok(Response {
            status: self.1,
            headers: vec![],
            body: vec![],
        })
    }
}
fn fixture_credentials() -> Credentials {
    Credentials {
        access_key: "fixture_only".into(),
        secret_key: "fixture_only".into(),
    }
}

#[test]
fn r2_and_aws_without_job_and_ledger_never_invoke_transport() {
    let requests = Arc::new(Mutex::new(Vec::new()));
    for endpoint in [
        None,
        Some("https://fixture-only.r2.cloudflarestorage.com"),
        Some("http://fixture-only.r2.cloudflarestorage.com"),
    ] {
        assert!(S3Store::with_transport(
            "s3://fixture-only",
            endpoint,
            fixture_credentials(),
            None,
            Box::new(FixtureTransport(requests.clone(), 200))
        )
        .is_err());
    }
    assert!(requests.lock().unwrap().is_empty());
}

#[test]
fn conditional_put_headers_and_precondition_conflict() {
    for status in [200, 412, 409, 503] {
        let requests = Arc::new(Mutex::new(Vec::new()));
        let store = S3Store::with_transport(
            "s3://fixture-only/prefix",
            Some("http://127.0.0.1:18333"),
            fixture_credentials(),
            None,
            Box::new(FixtureTransport(requests.clone(), status)),
        )
        .unwrap();
        let result = store.put_new("key", b"fixture_only", "text/plain");
        if status == 200 {
            assert!(result.is_ok());
        } else if status == 412 {
            assert_eq!(result.unwrap_err().kind, "exists");
        } else {
            assert!(result.is_err());
        }
        let reqs = requests.lock().unwrap();
        assert_eq!(reqs.len(), 1);
        assert_eq!(reqs[0].method, "PUT");
        assert_eq!(reqs[0].path, "/fixture-only/prefix/key");
        assert!(reqs[0]
            .headers
            .contains(&("if-none-match".into(), "*".into())));
        assert!(reqs[0]
            .headers
            .iter()
            .any(|(k, _)| k == "x-amz-checksum-sha256"));
        assert!(!reqs[0]
            .headers
            .iter()
            .any(|(k, _)| k == "x-amz-server-side-encryption"));
    }
}
