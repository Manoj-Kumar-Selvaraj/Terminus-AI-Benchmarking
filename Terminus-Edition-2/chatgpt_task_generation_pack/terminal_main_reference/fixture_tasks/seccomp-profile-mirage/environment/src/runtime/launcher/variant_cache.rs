use std::sync::Mutex;

static CACHE: Mutex<Vec<String>> = Mutex::new(Vec::new());

pub fn cache_variant(scenario: &str, tag: &str) {
    if let Ok(mut guard) = CACHE.lock() {
        guard.push(format!("{scenario}:{tag}"));
    }
}
