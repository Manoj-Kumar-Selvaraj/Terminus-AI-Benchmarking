package Broker::Token;
use strict; use warnings;
use Broker::Util qw(state_path read_json canonical_json b64u_enc sign_input parse_token secure_eq);
use Digest::SHA qw(hmac_sha256);
sub mint { my(%a)=@_; my $ks=read_json(state_path('broker-keys.json'),{}); my $kid=$ks->{active_signer}; my $k=$ks->{keys}{$kid} or die 'active signer missing'; die 'active signer unavailable' unless ($k->{status}//'') eq 'active'; my $h={alg=>'HS256',typ=>'CAP1',kid=>$kid}; my $p={iss=>'workload-capability-broker',sub=>$a{claims}{sub},tenant=>$a{claims}{tenant},aud=>$a{audience},scope=>$a{scopes},assertion_jti=>$a{claims}{jti},operation_id=>$a{operation_id},serial=>$a{serial},security_generation=>$ks->{security_generation},iat=>$a{now},exp=>$a{now}+$a{ttl}}; my $input=b64u_enc(canonical_json($h)).'.'.b64u_enc(canonical_json($p)); return $input.'.'.sign_input($input,$k->{secret}); }
1;
