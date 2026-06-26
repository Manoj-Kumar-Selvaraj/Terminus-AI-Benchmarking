package Broker::Store;
use strict; use warnings; use Exporter 'import';
our @EXPORT_OK = qw(journal_append journal_read audit);
use Broker::Util qw(canonical_json sha256_hex append_line read_json write_json state_path);
use JSON::PP ();
sub journal_append { my($name,$event)=@_; my %e=%$event; delete $e{checksum}; $e{checksum}=sha256_hex(canonical_json(\%e)); append_line(state_path($name),canonical_json(\%e)); return \%e; }
sub journal_read { my($name,$allow_torn)=@_; my $p=state_path($name); return [] if !-e $p; open my $f,'<:raw',$p or die "open $p: $!"; my @raw=<$f>; close $f; my @out; for(my $i=0;$i<@raw;$i++){ my $line=$raw[$i]; $line=~s/[\r\n]+$//; next if $line eq ''; my $e=eval{JSON::PP::decode_json($line)}; if($@ || ref($e) ne 'HASH'){ next if $allow_torn && $i==$#raw; die "corrupt journal line ".($i+1); } my $got=delete $e->{checksum}; my $want=sha256_hex(canonical_json($e)); die "journal checksum mismatch line ".($i+1) unless defined($got)&&$got eq $want; $e->{checksum}=$got; push @out,$e; } return \@out; }
sub audit { my($event)=@_; journal_append('audit.jsonl',$event); }
1;
