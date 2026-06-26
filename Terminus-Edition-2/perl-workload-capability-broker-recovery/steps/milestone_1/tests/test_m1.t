use strict;
use warnings;
use Test::More;
use FindBin;
use lib $FindBin::Bin;
use Harness;
use JSON::PP ();

ok(protected_ok(), 'protected runtime and baselines are intact');

subtest 'legitimate issuer assertion verifies' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm1-legit');
    my ($rc, $o) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    is($rc, 0, 'accepted');
    my $v = JSON::PP::decode_json($o);
    is($v->{iss}, 'profile-ci', 'issuer preserved');
};

subtest 'colliding partner key cannot impersonate production issuer' => sub {
    reset_state();
    my $t = sign_assertion(
        signing_issuer => 'partner-ci',
        claim_issuer   => 'profile-ci',
        tenant         => 'acme',
        jti            => 'm1-collision',
    );
    my ($rc, $o) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'rejected');
    like($o, qr/signature|key|issuer/i, 'trust failure reported');
};

subtest 'audience membership is exact' => sub {
    reset_state();
    my $t = sign_assertion(audience => 'profile-export-admin', jti => 'm1-aud');
    my ($rc) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'prefix audience rejected');
};

subtest 'tenant is bound to issuer' => sub {
    reset_state();
    my $t = sign_assertion(
        signing_issuer => 'partner-ci',
        claim_issuer   => 'partner-ci',
        tenant         => 'acme',
        source_epoch   => 3,
        jti            => 'm1-tenant',
    );
    my ($rc, $o) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'foreign tenant rejected');
    like($o, qr/tenant|issuer/i, 'tenant binding failure reported');
};

subtest 'source_epoch below issuer minimum is rejected' => sub {
    reset_state();
    my $t = sign_assertion(
        signing_issuer => 'profile-ci',
        claim_issuer   => 'profile-ci',
        tenant         => 'acme',
        source_epoch   => 6,
        jti            => 'm1-epoch-low',
    );
    my ($rc, $o) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'below-minimum epoch rejected');
    like($o, qr/epoch|stale|source/i, 'epoch failure reported');
};

subtest 'retired issuer key is not accepted' => sub {
    reset_state();
    my $t = sign_assertion(
        signing_issuer => 'legacy-ci',
        claim_issuer   => 'legacy-ci',
        kid            => 'legacy-1',
        tenant         => 'legacy',
        source_epoch   => 1,
        jti            => 'm1-retired',
    );
    my ($rc) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'retired key rejected');
};

subtest 'algorithm is constrained by contract' => sub {
    reset_state();
    my $t = sign_assertion(alg => 'HS512', jti => 'm1-alg');
    my ($rc) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'unsupported algorithm rejected');
};

subtest 'time boundaries honor configured skew' => sub {
    reset_state();
    my $inside = sign_assertion(
        exp => 1899999970,
        nbf => 1900000030,
        jti => 'm1-skew-in',
    );
    my ($r1) = broker(
        'verify', '--assertion', $inside,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    is($r1, 0, 'exact skew boundary accepted');

    my $iat_outside = sign_assertion(
        now => 1900000031,
        jti => 'm1-skew-iat-out',
    );
    my ($r3) = broker(
        'verify', '--assertion', $iat_outside,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($r3, 0, 'iat beyond future skew rejected');

    my $nbf_outside = sign_assertion(
        nbf => 1900000031,
        exp => 1900000300,
        jti => 'm1-skew-nbf-out',
    );
    my ($r4) = broker(
        'verify', '--assertion', $nbf_outside,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($r4, 0, 'nbf beyond future skew rejected');

    my $outside = sign_assertion(
        exp => 1899999969,
        nbf => 1899999900,
        jti => 'm1-skew-out',
    );
    my ($r2) = broker(
        'verify', '--assertion', $outside,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($r2, 0, 'outside expiry boundary rejected');
};

subtest 'payload tampering invalidates signature' => sub {
    reset_state();
    my $t = sign_assertion(jti => 'm1-tamper');
    my @p = split /\./, $t;
    substr($p[1], 5, 1) = substr($p[1], 5, 1) eq 'A' ? 'B' : 'A';
    my ($rc) = broker(
        'verify', '--assertion', join('.', @p),
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    isnt($rc, 0, 'tamper rejected');
};

subtest 'verification is read only and deterministic' => sub {
    reset_state();
    my $before = state_text('broker-keys.json') . state_text('replay.json');
    my $t = sign_assertion(jti => 'm1-repeat');
    my ($r1, $o1) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    my ($r2, $o2) = broker(
        'verify', '--assertion', $t,
        '--now', '1900000000',
        '--audience', 'profile-export',
    );
    is_deeply([$r1, $o1], [$r2, $o2], 'same result');
    is(
        state_text('broker-keys.json') . state_text('replay.json'),
        $before,
        'security state unchanged',
    );
};

done_testing();
