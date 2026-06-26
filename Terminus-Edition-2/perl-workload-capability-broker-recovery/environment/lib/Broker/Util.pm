package Broker::Util;
use strict; use warnings;
use Exporter 'import';
use JSON::PP (); use Digest::SHA qw(hmac_sha256 sha256_hex); use MIME::Base64 qw(encode_base64 decode_base64);
use File::Path qw(make_path); use Fcntl qw(:DEFAULT :flock);
our @EXPORT_OK = qw(app_root runtime_config state_path read_json write_json canonical_json b64u_enc b64u_dec parse_token sign_input secure_eq sha256_hex with_lock append_line slurp maybe_fail);
sub app_root { return $ENV{APP_ROOT} || '/app'; }
sub runtime_config { return app_root().'/runtime/config/'.$_[0]; }
sub state_path { return app_root().'/state/'.$_[0]; }
our $JSON=JSON::PP->new->canonical(1)->utf8(1)->allow_nonref(1);
sub canonical_json { return $JSON->encode($_[0]); }
sub read_json { my($p,$default)=@_; return $default if !-e $p; open my $f,'<:raw',$p or die "open $p: $!"; local $/; my $s=<$f>; close $f; return $default if !defined($s)||$s!~/\S/; return JSON::PP::decode_json($s); }
sub write_json { my($p,$v)=@_; my($d)=$p=~m{^(.*)/[^/]+$}; make_path($d) if $d && !-d $d; my $tmp="$p.tmp.$$"; open my $f,'>:raw',$tmp or die "open $tmp: $!"; print {$f} canonical_json($v),"\n"; close $f or die "close $tmp: $!"; rename $tmp,$p or die "rename $tmp -> $p: $!"; }
sub slurp { my($p)=@_; open my $f,'<:raw',$p or die "open $p: $!"; local $/; my $s=<$f>; close $f; return $s; }
sub append_line { my($p,$line)=@_; open my $f,'>>:raw',$p or die "open $p: $!"; print {$f} $line,"\n"; close $f or die "close $p: $!"; }
sub b64u_enc { my $s=encode_base64($_[0],''); $s=~tr{+/}{-_}; $s=~s/=+$//; return $s; }
sub b64u_dec { my $s=$_[0]; $s=~tr{-_}{+/}; $s.='=' x ((4-length($s)%4)%4); return decode_base64($s); }
sub parse_token { my($t)=@_; my @p=split /\./,$t,-1; die 'malformed compact token' unless @p==3 && $p[0] ne '' && $p[1] ne '' && $p[2] ne ''; my $h=eval{JSON::PP::decode_json(b64u_dec($p[0]))}; die 'malformed protected header' if $@ || ref($h) ne 'HASH'; my $c=eval{JSON::PP::decode_json(b64u_dec($p[1]))}; die 'malformed token claims' if $@ || ref($c) ne 'HASH'; return ($h,$c,"$p[0].$p[1]",b64u_dec($p[2])); }
sub sign_input { my($input,$secret)=@_; return b64u_enc(hmac_sha256($input,$secret)); }
sub secure_eq { my($a,$b)=@_; return 0 unless defined($a)&&defined($b)&&length($a)==length($b); my $x=0; for(my $i=0;$i<length($a);$i++){ $x |= ord(substr($a,$i,1)) ^ ord(substr($b,$i,1)); } return $x==0; }
sub with_lock { my($code)=@_; my $p=state_path('controller.lock'); sysopen(my $f,$p,O_RDWR|O_CREAT,0600) or die "lock open: $!"; flock($f,LOCK_EX) or die "lock: $!"; my(@r,$ok,$err); $ok=eval{ @r=$code->(); 1 }; $err=$@; flock($f,LOCK_UN); close $f; die $err unless $ok; return wantarray?@r:$r[0]; }
sub maybe_fail { my($point)=@_; my $p=state_path('failure.json'); my $f=read_json($p,{point=>undef}); return unless defined($f->{point}) && $f->{point} eq $point; $f->{point}=undef; write_json($p,$f); die "INJECTED:$point"; }
1;
