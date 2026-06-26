use strict;
use warnings;
use Test::More;
use FindBin;
use lib $FindBin::Bin;
use Harness;
use JSON::PP ();

ok(protected_ok(), 'protected runtime intact');

sub ack2 {
    lab('ack-node', '--node', 'broker-a', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
    lab('ack-node', '--node', 'broker-b', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
}

subtest 'A valid assertion exchange and rotation converge' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'e2e-a');
    my $p = request_file(
        assertion => $t, operation_id => 'e2e-a',
        requested_scopes => ['profile:export'],
    );
    my ($rc, $o) = broker('exchange', '--request', $p, '--now', '1900000000');
    is($rc, 0);
    is((verify_cap(JSON::PP::decode_json($o)->{token}))[0], 0);
    ack2();
    my $r = rotation_file(operation_id => 'e2e-rot');
    is((broker('rotate', '--request', $r, '--now', '1900000400'))[0], 0);
};

subtest 'B forged issuer stays blocked before authorization' => sub {
    reset_state();
    my $t = sign_assertion(
        signing_issuer => 'partner-ci',
        claim_issuer   => 'profile-ci',
        tenant         => 'acme',
        jti            => 'e2e-b',
    );
    my $p = request_file(assertion => $t, operation_id => 'e2e-b');
    isnt((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 0);
    is(read_json('/app/state/replay.json')->{next_serial}, 1001);
};

subtest 'C delegated deny stays blocked without replay reservation' => sub {
    reset_state();
    my $t = sign_assertion(
        jti => 'e2e-c', actors => 'svc-support', scopes => 'profile:export',
    );
    my $p = request_file(
        assertion => $t, operation_id => 'e2e-c',
        requested_scopes => ['profile:export'],
    );
    isnt((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 0);
    is_deeply(read_json('/app/state/replay.json')->{operations}, {});
};

subtest 'D concurrent replay has one capability serial' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'e2e-d');
    my $p = request_file(assertion => $t, operation_id => 'e2e-d');
    my @pids;
    for (1 .. 3) {
        my $pid = fork();
        if (!$pid) {
            broker('exchange', '--request', $p, '--now', '1900000000');
            exit 0;
        }
        push @pids, $pid;
    }
    waitpid($_, 0) for @pids;
    my $s = read_json('/app/state/replay.json');
    is($s->{next_serial}, 1002);
    is(scalar keys %{$s->{operations}}, 1);
};

subtest 'E crash and restart preserve one-time ownership' => sub {
    reset_state();
    lab('inject-failure', '--point', 'AFTER_TOKEN_MINT');
    my $t = sign_assertion(jti => 'e2e-e');
    my $p = request_file(assertion => $t, operation_id => 'e2e-e');
    broker('exchange', '--request', $p, '--now', '1900000000');
    unlink '/app/state/replay.json';
    is((broker('recover'))[0], 0);
    is((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 0);
    is(read_json('/app/state/replay.json')->{next_serial}, 1002);
};

subtest 'F stale quorum cannot activate target signer' => sub {
    reset_state();
    lab('ack-node', '--node', 'broker-a', '--generation', '42', '--bundle-hash', 'bundle-42-a8d9');
    my $r = rotation_file(operation_id => 'e2e-f');
    broker('rotate', '--request', $r, '--now', '1900000000');
    is(read_json('/app/state/broker-keys.json')->{active_signer}, 'broker-v1');
};

subtest 'G compromised old key remains revoked after forward recovery' => sub {
    reset_state();
    ack2();
    lab('inject-failure', '--point', 'AFTER_SIGNER_SWITCH');
    my $r = rotation_file(operation_id => 'e2e-g');
    broker('rotate', '--request', $r, '--now', '1900000400');
    lab('revoke-key', '--key', 'broker-v1');
    broker('rotation-rollback', '--operation-id', 'e2e-g');
    is(read_json('/app/state/broker-keys.json')->{keys}{'broker-v1'}{status}, 'revoked');
};

subtest 'H repeated completed workflow is stable' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'e2e-h');
    my $p = request_file(assertion => $t, operation_id => 'e2e-h');
    my ($a, $oa) = broker('exchange', '--request', $p, '--now', '1900000000');
    my ($b, $ob) = broker('exchange', '--request', $p, '--now', '1900000000');
    is(JSON::PP::decode_json($oa)->{token}, JSON::PP::decode_json($ob)->{token});
    ack2();
    my $r = rotation_file(operation_id => 'e2e-h-rot');
    broker('rotate', '--request', $r, '--now', '1900000400');
    my $j1 = state_text('rotation-journal.jsonl');
    broker('rotate', '--request', $r, '--now', '1900000400');
    is(state_text('rotation-journal.jsonl'), $j1, 'no duplicate rotation phases');
    my $k = read_json('/app/state/broker-keys.json');
    is(scalar(grep { $k->{keys}{$_}{status} eq 'active' } keys %{$k->{keys}}), 1);
};

done_testing();
