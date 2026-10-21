use onjeon_collect::{archive, store, Listing};

fn run() -> Result<bool, Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.as_slice() {
        [cmd, target, metadata, file, content_type] if cmd == "observe" => {
            let obs = serde_json::from_slice(&std::fs::read(metadata)?)?;
            archive::observe(&store::local(target)?, &obs, &std::fs::read(file)?, content_type)?;
            Ok(true)
        }
        [cmd, src] if cmd == "listing" => {
            let listing = Listing::from_store(&store::local(src)?)?;
            use std::io::Write;
            std::io::stdout().write_all(&listing.to_bytes())?;
            Ok(true)
        }
        [cmd, src, dst] if cmd == "copy" => {
            archive::copy(&store::local(src)?, &store::local(dst)?)?;
            Ok(true)
        }
        [cmd, expected, dst] if cmd == "verify-copy" => {
            let listing = Listing::parse(&std::fs::read(expected)?)?;
            let report = archive::verify_copy(&listing, "pinned-listing", &store::local(dst)?, false)?;
            use std::io::Write;
            std::io::stdout().write_all(&report.to_bytes())?;
            Ok(report.passed(false))
        }
        _ => Err("usage: onjeon-collect listing file:///dir | copy file:///src file:///dst | verify-copy listing.json file:///dst".into()),
    }
}

fn main() {
    match run() {
        Ok(true) => (),
        Ok(false) => std::process::exit(1),
        Err(_) => {
            eprintln!("archive operation failed; no upstream details emitted");
            std::process::exit(1);
        }
    }
}
