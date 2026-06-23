//go:build ignore

package main

import (
	"os"
	"strings"
)

func main() {
	path := "/app/cmd/reconcile/main.go"
	data, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	text := string(data)
	if strings.Contains(text, "func canonicalChannel(channel string)") {
		return
	}
	text = strings.Replace(text,
		"Channel: strings.ToUpper(clean(row[4]))",
		"Channel: canonicalChannel(row[4])",
		1,
	)
	text = strings.Replace(text,
		"Channel: strings.ToUpper(clean(row[3]))",
		"Channel: canonicalChannel(row[3])",
		1,
	)
	text = strings.Replace(text,
		"func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = strings.ToUpper(clean(channel))\n\treturn channel == \"ACH\" || channel == \"CARD\" || channel == \"WIRE\"\n}",
		"func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc canonicalChannel(channel string) string {\n\tswitch strings.ToUpper(clean(channel)) {\n\tcase \"CC\":\n\t\treturn \"CARD\"\n\tcase \"WIR\":\n\t\treturn \"WIRE\"\n\tdefault:\n\t\treturn strings.ToUpper(clean(channel))\n\t}\n}\n\nfunc allowedChannel(channel string) bool {\n\tchannel = canonicalChannel(channel)\n\treturn channel == \"ACH\" || channel == \"CARD\" || channel == \"WIRE\"\n}",
		1,
	)
	if err := os.WriteFile(path, []byte(text), 0o644); err != nil {
		panic(err)
	}
}
