package visiting

import "strings"

// CanonicalChannel maps legacy credit channel aliases to canonical values.
func CanonicalChannel(channel string) string {
	switch strings.ToUpper(strings.TrimSpace(channel)) {
	case "CC":
		return "CARD"
	case "WIR":
		return "WIRE"
	default:
		return strings.ToUpper(strings.TrimSpace(channel))
	}
}

// AllowedChannel reports whether a canonical channel may match a posted visit.
func AllowedChannel(channel string) bool {
	switch CanonicalChannel(channel) {
	case "ACH", "CARD", "WIRE":
		return true
	default:
		return false
	}
}
