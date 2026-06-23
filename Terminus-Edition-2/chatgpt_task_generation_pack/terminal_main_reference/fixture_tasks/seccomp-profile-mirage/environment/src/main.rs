use seccomp_profile_mirage::util::io::write_report;
use seccomp_profile_mirage::{execute_all, load_runtime_config};

fn main() {
    let cfg = load_runtime_config("/app/config/runtime.toml").expect("runtime config");
    let report = execute_all(&cfg).expect("execute scenarios");
    write_report(&cfg.output_file, &report).expect("write report");
}
