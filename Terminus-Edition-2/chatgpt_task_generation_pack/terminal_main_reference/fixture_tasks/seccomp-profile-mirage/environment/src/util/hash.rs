pub fn simple_hash(input: &str) -> u64 {
    let mut acc: u64 = 1469598103934665603;
    for b in input.as_bytes() {
        acc ^= *b as u64;
        acc = acc.wrapping_mul(1099511628211);
    }
    acc
}
