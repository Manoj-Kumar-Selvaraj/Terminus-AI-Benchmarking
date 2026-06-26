package Broker::Rotation;
use strict; use warnings;
use Broker::Util qw(state_path read_json write_json canonical_json sha256_hex);
sub rotate { my($r,$now)=@_; my $ks=read_json(state_path('broker-keys.json'),{}); my $old=$ks->{active_signer}; $ks->{keys}{$old}{status}='verify_only'; $ks->{keys}{$r->{target_key}}{status}='active'; $ks->{active_signer}=$r->{target_key}; $ks->{security_generation}=$r->{target_generation}; write_json(state_path('broker-keys.json'),$ks); my $st={schema_version=>1,phase=>'COMPLETED',generation=>$r->{target_generation},operation_id=>$r->{operation_id},request_hash=>sha256_hex(canonical_json($r)),request=>$r,result=>{status=>'completed',active_signer=>$r->{target_key},generation=>$r->{target_generation}}}; write_json(state_path('rotation.json'),$st); return $st->{result}; }
sub rollback { my($op)=@_; my $ks=read_json(state_path('broker-keys.json'),{}); $ks->{keys}{'broker-v1'}{status}='active'; $ks->{active_signer}='broker-v1'; write_json(state_path('broker-keys.json'),$ks); return {status=>'rolled_back'}; }
sub recover { return {status=>'noop'}; }
1;
