package Harness;
use strict; use warnings; use Exporter 'import';
use JSON::PP (); use Digest::SHA qw(sha256_hex); use IPC::Open3; use Symbol qw(gensym); use File::Temp qw(tempfile); use File::Copy qw(copy);
our @EXPORT=qw(reset_state protected_ok run_cmd broker lab sign_assertion write_json read_json request_file rotation_file verify_cap mutate_json state_text);
our $ROOT=$ENV{APP_ROOT}||'/app'; our $LAB='/opt/task-tools/capability-lab'; our $MANIFEST_HASH='bb0e5bf6fb2f01151130e2ca713f6f4e032e25678b51e671118454baeb0598ec';
sub _capture { my(@cmd)=@_; my $err=gensym; my $pid=open3(undef,my $out,$err,@cmd); local $/; my $stdout=<$out>//''; my $stderr=<$err>//''; waitpid($pid,0); return ($?>>8,$stdout,$stderr); }
sub run_cmd { return _capture(@_); }
sub broker { return _capture('perl',"$ROOT/bin/brokerctl",@_); }
sub lab { return _capture($LAB,@_); }
sub reset_state { my($rc,$o,$e)=lab('reset'); die "reset failed: $e$o" if $rc; return 1; }
sub protected_ok { open my $f,'<:raw','/opt/task-tools/protected-manifest.sha256' or return 0; local $/; my $m=<$f>; close $f; return 0 unless sha256_hex($m) eq $MANIFEST_HASH; for my $line (split /\n/,$m){ next unless $line=~/^([0-9a-f]{64})  (.+)$/; my($want,$rel)=($1,$2); my $p="/opt/task-tools/$rel"; open my $g,'<:raw',$p or return 0; local $/; my $b=<$g>; close $g; return 0 unless sha256_hex($b) eq $want; } return 1; }
sub read_json { my($p)=@_; open my $f,'<:raw',$p or die "open $p: $!"; local $/; my $s=<$f>; close $f; return JSON::PP::decode_json($s); }
sub write_json { my($p,$v)=@_; open my $f,'>:raw',$p or die "open $p: $!"; print {$f} JSON::PP->new->canonical(1)->pretty(1)->encode($v); close $f; return $p; }
sub mutate_json { my($p,$cb)=@_; my $v=read_json($p); $cb->($v); write_json($p,$v); }
sub sign_assertion { my(%a)=@_; my @cmd=('sign-assertion','--signing-issuer',$a{signing_issuer}//'profile-ci','--claim-issuer',$a{claim_issuer}//($a{signing_issuer}//'profile-ci'),'--kid',$a{kid}//'rot-17','--subject',$a{subject}//'svc-exporter','--tenant',$a{tenant}//'acme','--audience',$a{audience}//'profile-export','--scopes',$a{scopes}//'profile:read','--actors',$a{actors}//'','--jti',$a{jti}//('jti-'.int(rand(1_000_000))),'--now',$a{now}//1900000000,'--exp',$a{exp}//1900000300,'--nbf',$a{nbf}//1899999999,'--source-epoch',$a{source_epoch}//7,'--alg',$a{alg}//'HS256'); my($rc,$o,$e)=lab(@cmd); die "sign failed: $e" if $rc; $o=~s/\s+$//; return $o; }
sub request_file { my(%a)=@_; my($fh,$p)=tempfile('exchange-XXXX',DIR=>'/tmp',SUFFIX=>'.json',UNLINK=>0); close $fh; write_json($p,{operation_id=>$a{operation_id}//'op-1',assertion=>$a{assertion},requested_scopes=>$a{requested_scopes}//['profile:read'],audience=>$a{audience}//'profile-export-api',ttl_seconds=>$a{ttl_seconds}//120}); return $p; }
sub rotation_file { my(%a)=@_; my($fh,$p)=tempfile('rotation-XXXX',DIR=>'/tmp',SUFFIX=>'.json',UNLINK=>0); close $fh; write_json($p,{operation_id=>$a{operation_id}//'rotate-42',target_key=>$a{target_key}//'broker-v2',target_generation=>$a{target_generation}//42,policy_generation=>$a{policy_generation}//42,bundle_hash=>$a{bundle_hash}//'bundle-42-a8d9',overlap_until=>$a{overlap_until}//1900000300}); return $p; }
sub verify_cap { my($token)=@_; my($rc,$o,$e)=lab('verify-capability','--token',$token); return ($rc,$rc?undef:JSON::PP::decode_json($o),$e); }
sub state_text { my($name)=@_; open my $f,'<:raw',"$ROOT/state/$name" or die $!; local $/; return <$f>; }
1;
