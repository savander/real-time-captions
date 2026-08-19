use std::env;
use std::io::{self, Write};
use std::thread;
use std::time::Duration;

use flexaudio::{OutputFormat, ProcessMode, SourceKind, StreamConfig, open};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let pid: u32 = env::args().nth(1).ok_or("missing target PID")?.parse()?;
    let mut stream = open(StreamConfig {
        kind: SourceKind::ProcessLoopback,
        chunk_ms: 20,
        target_pid: Some(pid),
        mode: ProcessMode::Include,
        output: OutputFormat {
            sample_rate: 48_000,
            channels: 2,
        },
        ..Default::default()
    })?;
    stream.start()?;
    let stdout = io::stdout();
    let mut output = stdout.lock();
    loop {
        let mut received = false;
        while let Some(chunk) = stream.poll_chunk() {
            received = true;
            for sample in chunk.data {
                if let Err(error) = output.write_all(&sample.to_le_bytes()) {
                    if error.kind() == io::ErrorKind::BrokenPipe {
                        stream.stop();
                        return Ok(());
                    }
                    return Err(error.into());
                }
            }
            output.flush()?;
        }
        while let Some(event) = stream.poll_event() {
            eprintln!("{event:?}");
        }
        if !received {
            thread::sleep(Duration::from_millis(5));
        }
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
