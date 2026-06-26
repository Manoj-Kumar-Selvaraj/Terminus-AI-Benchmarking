package Broker::Assertion;
use strict; use warnings;
use Broker::Util qw(runtime_config read_json parse_token b64u_enc secure_eq);
use Digest::SHA qw(hmac_sha256);
sub verify { my($token,$now,$wanted_aud)=@_; my($h,$c,$input,$sig)=parse_token($token); my $cfg=read_json(runtime_config('issuers.json'),{}); my %global; for my $iss (@{$cfg->{issuers}||[]}){ for my $k (@{$iss->{keys}||[]}){ $global{$k->{kid}}=$k; } } my $k=$global{$h->{kid}} or die 'unknown key'; my $expect=hmac_sha256($input,$k->{secret}); die 'bad signature' unless secure_eq($sig,$expect); die 'expired assertion' if ($c->{exp}//0)<$now; my $joined=join(',',@{$c->{aud}||[]}); die 'wrong audience' unless index($joined,$wanted_aud)>=0; return $c; }
1;
