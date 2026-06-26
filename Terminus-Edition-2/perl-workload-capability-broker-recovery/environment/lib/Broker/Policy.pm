package Broker::Policy;
use strict; use warnings;
use Broker::Util qw(runtime_config state_path read_json write_json);
sub authorize { my($claims,$requested,$aud)=@_; my $p=read_json(runtime_config('policy.json'),{}); my $cache=read_json(state_path('policy-cache.json'),{entries=>{}}); my $key=$claims->{sub}; if($cache->{entries}{$key}){ return $cache->{entries}{$key}; } my $t=$p->{tenants}{$claims->{tenant}} or die 'unknown tenant'; my $s=$t->{subjects}{$claims->{sub}} or die 'unknown subject'; my %allow=map{$_=>1}@{$s->{allow}||[]}; my @granted=grep{$allow{$_}} @$requested; my $d={tenant=>$claims->{tenant},subject=>$claims->{sub},scopes=>\@granted,policy_generation=>$p->{generation}}; $cache->{entries}{$key}=$d; write_json(state_path('policy-cache.json'),$cache); return $d; }
1;
