use strict;
use warnings;
use Test::More;
use FindBin;
use lib $FindBin::Bin;
use Harness;
use JSON::PP ();

ok(protected_ok(), 'protected runtime and baselines are intact');

sub ack2 {
    lab('ack-node', '--node', 'broker-a', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
    lab('ack-node', '--node', 'broker-b', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
}

sub rot {
    my (%a) = @_;
    my $p = rotation_file(%a);
    return ($p, broker('rotate', '--request', $p, '--now', $a{now} // 1900000400));
}

subtest 'successful rotation requires quorum and commits generation' => sub {
    reset_state();
    ack2();
    my ($p, $rc, $o) = rot();
    is($rc, 0);
    my $r = JSON::PP::decode_json($o);
    is($r->{status}, 'completed');
    my $k = read_json('/app/state/broker-keys.json');
    is($k->{active_signer}, 'broker-v2');
    is($k->{security_generation}, 42);
};

subtest 'stale generation acknowledgement does not count' => sub {
    reset_state();
    lab('ack-node', '--node', 'broker-a', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
    lab('ack-node', '--node', 'broker-b', '--generation', '41', '--bundle-hash', 'bundle-42-a8d9');
    my (undef, $rc, $o) = rot(now => 1900000000, overlap_until => 1900000300);
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{status}, 'blocked');
    is(read_json('/app/state/broker-keys.json')->{active_signer}, 'broker-v1');
};

subtest 'wrong bundle acknowledgement does not count' => sub {
    reset_state();
    lab('ack-node', '--node', 'broker-a', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
    lab('ack-node', '--node', 'broker-b', '--generation', '42', '--bundle-hash', 'other');
    my (undef, $rc, $o) = rot(now => 1900000000);
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{status}, 'blocked');
};

subtest 'only one signer is active after switch' => sub {
    reset_state();
    ack2();
    rot();
    my $k = read_json('/app/state/broker-keys.json');
    my @a = grep { ($k->{keys}{$_}{status} // '') eq 'active' } keys %{$k->{keys}};
    is_deeply(\@a, ['broker-v2']);
};

subtest 'former signer remains verify only during overlap' => sub {
    reset_state();
    ack2();
    my (undef, $rc, $o) = rot(now => 1900000100, overlap_until => 1900000300);
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{status}, 'overlap');
    is(read_json('/app/state/broker-keys.json')->{keys}{'broker-v1'}{status}, 'verify_only');
};

subtest 'former signer retires after overlap' => sub {
    reset_state();
    ack2();
    rot(now => 1900000400, overlap_until => 1900000300);
    is(read_json('/app/state/broker-keys.json')->{keys}{'broker-v1'}{status}, 'retired');
};

subtest 'failure after prepare resumes without early switch' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_ROTATION_PREPARE');
    my $p = rotation_file();
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 75);
    is(read_json('/app/state/rotation.json')->{phase}, 'PREPARED');
    is(read_json('/app/state/broker-keys.json')->{active_signer}, 'broker-v1');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 0);
};

subtest 'failure after quorum resumes same operation' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_QUORUM');
    my $p = rotation_file(operation_id => 'rot-q');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 75);
    is(read_json('/app/state/rotation.json')->{phase}, 'QUORUM_VALIDATED');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 0);
};

subtest 'failure after signer switch never creates split signer' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_SIGNER_SWITCH');
    my $p = rotation_file(operation_id => 'rot-sw');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 75);
    my $k = read_json('/app/state/broker-keys.json');
    is(scalar(grep { $k->{keys}{$_}{status} eq 'active' } keys %{$k->{keys}}), 1);
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 0);
};

subtest 'lost completed response returns committed result' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_ROTATION_JOURNAL');
    my $p = rotation_file(operation_id => 'rot-lost');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 75);
    my ($rc, $o) = broker('rotate', '--request', $p, '--now', '1900000400');
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{active_signer}, 'broker-v2');
    my ($r2, $o2) = broker('rotate', '--request', $p, '--now', '1900000400');
    is($r2, 0);
    is(JSON::PP::decode_json($o2)->{active_signer}, 'broker-v2');
};

subtest 'conflicting rotation operation cannot join active state' => sub {
    reset_state();
    my $p1 = rotation_file(operation_id => 'rot-a');
    my $p2 = rotation_file(operation_id => 'rot-b');
    is((broker('rotate', '--request', $p1, '--now', '1900000000'))[0], 0);
    isnt((broker('rotate', '--request', $p2, '--now', '1900000000'))[0], 0);
};

subtest 'rollback before signer switch safely returns to idle' => sub {
    reset_state();
    my $p = rotation_file(operation_id => 'rot-rb');
    broker('rotate', '--request', $p, '--now', '1900000000');
    my ($rc, $o) = broker('rotation-rollback', '--operation-id', 'rot-rb');
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{status}, 'rolled_back');
    is(read_json('/app/state/broker-keys.json')->{active_signer}, 'broker-v1');
};

subtest 'rollback after switch does not resurrect revoked old key' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_SIGNER_SWITCH');
    my $p = rotation_file(operation_id => 'rot-forward');
    broker('rotate', '--request', $p, '--now', '1900000400');
    lab('revoke-key', '--key', 'broker-v1');
    my ($rc, $o) = broker('rotation-rollback', '--operation-id', 'rot-forward');
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{status}, 'forward_recovery_required');
    my $k = read_json('/app/state/broker-keys.json');
    is($k->{active_signer}, 'broker-v2');
    is($k->{keys}{'broker-v1'}{status}, 'revoked');
};

subtest 'restart reconstructs durable rotation phase and generation' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_QUORUM');
    my $p = rotation_file(operation_id => 'rot-recover');
    broker('rotate', '--request', $p, '--now', '1900000400');
    unlink '/app/state/rotation.json';
    my ($rc) = broker('recover');
    is($rc, 0);
    is(read_json('/app/state/rotation.json')->{phase}, 'QUORUM_VALIDATED');
    is((broker('rotate', '--request', $p, '--now', '1900000400'))[0], 0);
    is(read_json('/app/state/broker-keys.json')->{security_generation}, 42);
};

done_testing();
