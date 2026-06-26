use strict;
use warnings;
use Test::More;
use FindBin;
use lib $FindBin::Bin;
use Harness;
use JSON::PP ();
use POSIX qw(:sys_wait_h);

ok(protected_ok(), 'protected runtime and baselines are intact');

sub ex {
    my (%a) = @_;
    my $t = $a{assertion} // sign_assertion(
        jti    => $a{jti} // 'jti-x',
        actors => $a{actors} // '',
    );
    my $p = request_file(
        assertion        => $t,
        operation_id     => $a{op} // 'op-x',
        requested_scopes => $a{scopes} // ['profile:read'],
        ttl_seconds      => $a{ttl} // 120,
    );
    return ($p, broker('exchange', '--request', $p, '--now', $a{now} // 1900000000));
}

subtest 'first exchange mints one independently verifiable capability' => sub {
    reset_state();
    my ($p, $rc, $o) = ex(jti => 'm3-first', op => 'm3-first');
    is($rc, 0);
    my $r = JSON::PP::decode_json($o);
    is($r->{status}, 'committed');
    my ($vr, $v) = verify_cap($r->{token});
    is($vr, 0, 'signature verified');
    is($v->{claims}{assertion_jti}, 'm3-first', 'provenance');
};

subtest 'same operation retry returns exact token' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm3-retry');
    my $p = request_file(assertion => $t, operation_id => 'op-retry');
    my ($a, $oa) = broker('exchange', '--request', $p, '--now', '1900000000');
    my ($b, $ob) = broker('exchange', '--request', $p, '--now', '1900000000');
    is($a, 0);
    is($b, 0);
    is(
        JSON::PP::decode_json($oa)->{token},
        JSON::PP::decode_json($ob)->{token},
        'stable token',
    );
};

subtest 'operation id cannot be rebound' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm3-op-conflict');
    my $p1 = request_file(
        assertion => $t, operation_id => 'same-op',
        requested_scopes => ['profile:read'],
    );
    my $p2 = request_file(
        assertion => $t, operation_id => 'same-op',
        requested_scopes => ['profile:export'],
    );
    is((broker('exchange', '--request', $p1, '--now', '1900000000'))[0], 0);
    isnt((broker('exchange', '--request', $p2, '--now', '1900000000'))[0], 0);
};

subtest 'assertion jti cannot move to another operation' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm3-jti-conflict');
    my $p1 = request_file(assertion => $t, operation_id => 'op-a');
    my $p2 = request_file(assertion => $t, operation_id => 'op-b');
    is((broker('exchange', '--request', $p1, '--now', '1900000000'))[0], 0);
    isnt((broker('exchange', '--request', $p2, '--now', '1900000000'))[0], 0);
};

subtest 'concurrent processes converge on one mint' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm3-race');
    my $p = request_file(assertion => $t, operation_id => 'op-race');
    my @files;
    for my $i (1 .. 4) {
        my $f = "/tmp/race-$i.out";
        push @files, $f;
        my $pid = fork();
        if (!$pid) {
            my ($rc, $o, $e) = broker('exchange', '--request', $p, '--now', '1900000000');
            open my $h, '>', $f;
            print {$h} "$rc\n$o";
            close $h;
            exit 0;
        }
    }
    1 while wait() > 0;

    my %tok;
    for my $f (@files) {
        open my $h, '<', $f;
        my $rc = <$h>;
        chomp $rc;
        local $/;
        my $o = <$h>;
        close $h;
        is($rc, 0, 'worker succeeded');
        $tok{ JSON::PP::decode_json($o)->{token} }++;
    }
    is(scalar keys %tok, 1, 'one token');
    my $st = read_json('/app/state/replay.json');
    is($st->{next_serial}, 1002, 'one serial consumed');
};

subtest 'crash after reservation resumes same operation' => sub {
    reset_state();
    lab('inject-failure', '--point', 'AFTER_REPLAY_RESERVE');
    my $t = sign_assertion(jti => 'm3-reserve');
    my $p = request_file(assertion => $t, operation_id => 'op-reserve');
    is((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 75, 'injected exit');
    my ($rc, $o) = broker('exchange', '--request', $p, '--now', '1900000000');
    is($rc, 0, 'resumed');
    is(JSON::PP::decode_json($o)->{serial}, 1001, 'original serial boundary');
};

subtest 'crash after mint preserves allocated token' => sub {
    reset_state();
    lab('inject-failure', '--point', 'AFTER_TOKEN_MINT');
    my $t = sign_assertion(jti => 'm3-mint');
    my $p = request_file(assertion => $t, operation_id => 'op-mint');
    is((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 75);
    my $st = read_json('/app/state/replay.json');
    my $minted = $st->{operations}{'op-mint'}{token};
    my ($rc, $o) = broker('exchange', '--request', $p, '--now', '1900000000');
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{token}, $minted, 'same minted token');
};

subtest 'lost response after commit is idempotent' => sub {
    reset_state();
    lab('inject-failure', '--point', 'AFTER_EXCHANGE_COMMIT');
    my $t = sign_assertion(jti => 'm3-lost');
    my $p = request_file(assertion => $t, operation_id => 'op-lost');
    is((broker('exchange', '--request', $p, '--now', '1900000000'))[0], 75);
    my $st = read_json('/app/state/replay.json');
    my $tok = $st->{operations}{'op-lost'}{token};
    my ($rc, $o) = broker('exchange', '--request', $p, '--now', '1900000000');
    is($rc, 0);
    is(JSON::PP::decode_json($o)->{token}, $tok);
};

subtest 'restart reconstructs missing replay state from journal' => sub {
    reset_state();
    my ($p, $rc, $o) = ex(jti => 'm3-recover', op => 'op-recover');
    is($rc, 0);
    unlink '/app/state/replay.json';
    my ($rr, $ro) = broker('recover');
    is($rr, 0);
    my $st = read_json('/app/state/replay.json');
    is($st->{operations}{'op-recover'}{status}, 'COMMITTED');
};

subtest 'torn final journal record is ignored' => sub {
    reset_state();
    ex(jti => 'm3-torn', op => 'op-torn');
    open my $f, '>>', '/app/state/exchange-journal.jsonl';
    print {$f} '{"kind":"exchange"';
    close $f;
    unlink '/app/state/replay.json';
    is((broker('recover'))[0], 0, 'recovery succeeds');
    is(read_json('/app/state/replay.json')->{operations}{'op-torn'}{status}, 'COMMITTED');
};

subtest 'interior journal corruption blocks recovery' => sub {
    reset_state();
    ex(jti => 'm3-corrupt-a', op => 'op-ca');
    ex(jti => 'm3-corrupt-b', op => 'op-cb');
    my $s = state_text('exchange-journal.jsonl');
    like($s, qr/"checksum"/, 'journal entries include checksum field');
    $s =~ s/"operation_id":"op-ca"/"operation_id":"op-cx"/;
    open my $f, '>', '/app/state/exchange-journal.jsonl';
    print {$f} $s;
    close $f;
    unlink '/app/state/replay.json';
    isnt((broker('recover'))[0], 0, 'checksum detects content drift');
};

subtest 'serials are monotonic and bounded by actual mints' => sub {
    reset_state();
    my (undef, undef, $o1) = ex(jti => 'm3-s1', op => 'op-s1');
    my (undef, undef, $o2) = ex(jti => 'm3-s2', op => 'op-s2');
    my $a = JSON::PP::decode_json($o1);
    my $b = JSON::PP::decode_json($o2);
    is($a->{serial}, 1001);
    is($b->{serial}, 1002);
    cmp_ok($b->{serial}, '<', 2000, 'no arbitrary inflation');
};

done_testing();
