package Broker::App;
use strict; use warnings;
use Broker::Assertion; use Broker::Policy; use Broker::Replay; use Broker::Rotation;
use Broker::Util qw(state_path read_json);
sub verify_assertion { return Broker::Assertion::verify(@_); }
sub authorize { return Broker::Policy::authorize(@_); }
sub exchange { return Broker::Replay::exchange(@_); }
sub recover { return {exchange=>Broker::Replay::recover(),rotation=>Broker::Rotation::recover()}; }
sub rotate { return Broker::Rotation::rotate(@_); }
sub rollback_rotation { return Broker::Rotation::rollback(@_); }
sub inspect { my($what)=@_; my %m=(replay=>'replay.json',rotation=>'rotation.json',keys=>'broker-keys.json',nodes=>'nodes.json',cache=>'policy-cache.json'); die 'unknown inspection target' unless $m{$what}; return read_json(state_path($m{$what}),{}); }
1;
