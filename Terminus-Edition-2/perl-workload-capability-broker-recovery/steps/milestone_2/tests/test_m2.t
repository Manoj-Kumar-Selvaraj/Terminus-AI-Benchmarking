use strict;
use warnings;
use Test::More;
use FindBin;
use lib $FindBin::Bin;
use Harness;
use JSON::PP ();

ok(protected_ok(), 'protected runtime and baselines are intact');

sub claims {
    my (%x) = @_;
    return {
        iss                     => 'profile-ci',
        sub                     => $x{sub} // 'svc-exporter',
        tenant                  => $x{tenant} // 'acme',
        act                     => $x{act} // [],
        assertion_fingerprint   => $x{fp} // 'fp-test',
    };
}

sub auth {
    my ($c, $s, $aud) = @_;
    my ($fh, $p) = File::Temp::tempfile(
        'claims-XXXX', DIR => '/tmp', SUFFIX => '.json', UNLINK => 0,
    );
    close $fh;
    write_json($p, $c);
    return broker(
        'authorize', '--claims', $p,
        '--scopes', JSON::PP->new->encode($s),
        '--audience', $aud // 'profile-export-api',
    );
}

subtest 'direct grants preserve exact requested scopes' => sub {
    reset_state();
    my ($rc, $o) = auth(claims(), ['profile:read']);
    is($rc, 0, 'authorized');
    is_deeply(JSON::PP::decode_json($o)->{scopes}, ['profile:read'], 'exact scope');
};

subtest 'subject deny overrides allow' => sub {
    reset_state();
    my ($rc) = auth(claims(sub => 'svc-support'), ['profile:export']);
    isnt($rc, 0, 'denied despite allow');
};

subtest 'tenant decisions cannot bleed through cache' => sub {
    reset_state();
    is((auth(claims(tenant => 'acme'), ['profile:export']))[0], 0, 'acme allowed');
    isnt((auth(claims(tenant => 'globex'), ['profile:export']))[0], 0, 'globex denied');
};

subtest 'documented delegation chain is accepted' => sub {
    reset_state();
    my ($rc, $o) = auth(
        claims(act => ['svc-root', 'svc-orchestrator']),
        ['profile:export'],
    );
    is($rc, 0, 'delegation accepted');
    is_deeply(
        JSON::PP::decode_json($o)->{actors},
        ['svc-root', 'svc-orchestrator'],
        'chain retained',
    );
};

subtest 'delegation edge limits scopes' => sub {
    reset_state();
    my ($rc) = auth(claims(act => ['svc-support']), ['profile:export']);
    isnt($rc, 0, 'edge scope blocks export');
};

subtest 'delegation cycles fail closed' => sub {
    reset_state();
    my ($rc) = auth(claims(act => ['svc-exporter']), ['profile:read']);
    isnt($rc, 0, 'cycle rejected');
};

subtest 'delegation depth boundary is enforced' => sub {
    reset_state();
    my ($rc) = auth(
        claims(act => ['svc-root', 'svc-orchestrator', 'svc-support']),
        ['profile:read'],
    );
    isnt($rc, 0, 'too deep rejected');
};

subtest 'policy generation invalidates stale decision' => sub {
    reset_state();
    is((auth(claims(), ['profile:export']))[0], 0, 'initial allow');
    mutate_json('/app/runtime/config/policy.json', sub {
        $_[0]{generation} = 42;
        $_[0]{tenants}{acme}{subjects}{'svc-exporter'}{deny} = ['profile:export'];
    });
    isnt((auth(claims(), ['profile:export']))[0], 0, 'new generation denies');
};

subtest 'requested scope ordering has one semantic cache identity' => sub {
    reset_state();
    my ($r1, $o1) = auth(claims(), ['profile:export', 'profile:read']);
    my ($r2, $o2) = auth(claims(), ['profile:read', 'profile:export']);
    is($r1, 0);
    is($r2, 0);
    my $a = JSON::PP::decode_json($o1);
    my $b = JSON::PP::decode_json($o2);
    is($a->{cache_key}, $b->{cache_key}, 'same key');
    is_deeply($a->{scopes}, $b->{scopes}, 'canonical scopes');
};

subtest 'audit records provenance without assertion secrets' => sub {
    reset_state();
    auth(claims(fp => 'fp-4242'), ['profile:read']);
    my $a = state_text('audit.jsonl');
    like($a, qr/fp-4242/, 'fingerprint recorded');
    like($a, qr/policy_generation/, 'generation recorded');
    unlike($a, qr/profile-rot17-secret|SWA1/, 'secret and assertion absent');
};

subtest 'unknown principal and malformed chain fail closed' => sub {
    reset_state();
    isnt((auth(claims(sub => 'missing'), ['profile:read']))[0], 0, 'unknown subject rejected');
    my $c = claims();
    $c->{act} = 'svc-root';
    isnt((auth($c, ['profile:read']))[0], 0, 'non-array chain rejected');
};

done_testing();
