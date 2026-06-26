package Broker::Replay;
use strict; use warnings;
use Broker::Util qw(state_path read_json write_json canonical_json sha256_hex);
use Broker::Assertion; use Broker::Policy; use Broker::Token;
sub exchange { my($r,$now)=@_; my $claims=Broker::Assertion::verify($r->{assertion},$now,'profile-export'); my $d=Broker::Policy::authorize($claims,$r->{requested_scopes},$r->{audience}); my $st=read_json(state_path('replay.json'),{next_serial=>1001,assertions=>{},operations=>{}}); my $serial=$st->{next_serial}++; my $token=Broker::Token::mint(claims=>$claims,scopes=>$d->{scopes},audience=>$r->{audience},operation_id=>$r->{operation_id},serial=>$serial,now=>$now,ttl=>$r->{ttl_seconds}); $st->{assertions}{$claims->{jti}}=$r->{operation_id}; $st->{operations}{$r->{operation_id}}={status=>'COMMITTED',token=>$token,request_hash=>sha256_hex(canonical_json($r)),serial=>$serial,jti=>$claims->{jti}}; write_json(state_path('replay.json'),$st); return {status=>'committed',token=>$token,serial=>$serial,operation_id=>$r->{operation_id}}; }
sub recover { return {status=>'noop'}; }
1;
