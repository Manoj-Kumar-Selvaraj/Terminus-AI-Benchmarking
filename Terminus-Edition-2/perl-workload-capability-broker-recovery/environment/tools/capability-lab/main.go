package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type M map[string]any

func root() string {
	if v := os.Getenv("APP_ROOT"); v != "" {
		return v
	}
	return "/app"
}
func must(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
func read(path string, v any) { b, e := os.ReadFile(path); must(e); must(json.Unmarshal(b, v)) }
func write(path string, v any) {
	b, e := json.MarshalIndent(v, "", "  ")
	must(e)
	must(os.MkdirAll(filepath.Dir(path), 0755))
	must(os.WriteFile(path, append(b, '\n'), 0644))
}
func copyFile(a, b string) {
	in, e := os.Open(a)
	must(e)
	defer in.Close()
	must(os.MkdirAll(filepath.Dir(b), 0755))
	out, e := os.Create(b)
	must(e)
	_, e = io.Copy(out, in)
	must(e)
	must(out.Close())
}
func copyTree(src, dst string) {
	ents, e := os.ReadDir(src)
	must(e)
	for _, x := range ents {
		a := filepath.Join(src, x.Name())
		b := filepath.Join(dst, x.Name())
		if x.IsDir() {
			copyTree(a, b)
		} else {
			copyFile(a, b)
		}
	}
}
func b64(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }
func canon(v any) []byte  { b, _ := json.Marshal(v); return b }
func sign(input, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(input))
	return b64(h.Sum(nil))
}
func arg(name string) string {
	for i := 2; i < len(os.Args)-1; i += 2 {
		if os.Args[i] == "--"+name {
			return os.Args[i+1]
		}
	}
	return ""
}
func boolArg(name string) bool { return arg(name) == "true" }
func findSecret(signingIssuer, kid string) (string, error) {
	var cfg struct {
		Issuers []struct {
			Issuer string                         `json:"issuer"`
			Keys   []struct{ Kid, Secret string } `json:"keys"`
		} `json:"issuers"`
	}
	read("/opt/task-tools/baseline/config/issuers.json", &cfg)
	for _, is := range cfg.Issuers {
		if is.Issuer == signingIssuer {
			for _, k := range is.Keys {
				if k.Kid == kid {
					return k.Secret, nil
				}
			}
		}
	}
	return "", errors.New("key not found")
}
func signAssertion() {
	si := arg("signing-issuer")
	ci := arg("claim-issuer")
	if ci == "" {
		ci = si
	}
	kid := arg("kid")
	if kid == "" {
		kid = "rot-17"
	}
	sec, e := findSecret(si, kid)
	must(e)
	now, _ := strconv.ParseInt(arg("now"), 10, 64)
	if now == 0 {
		now = 1900000000
	}
	exp, _ := strconv.ParseInt(arg("exp"), 10, 64)
	if exp == 0 {
		exp = now + 300
	}
	nbf, _ := strconv.ParseInt(arg("nbf"), 10, 64)
	if nbf == 0 {
		nbf = now - 1
	}
	epoch, _ := strconv.Atoi(arg("source-epoch"))
	if epoch == 0 {
		epoch = 7
	}
	aud := strings.Split(arg("audience"), ",")
	if arg("audience") == "" {
		aud = []string{"profile-export"}
	}
	sc := strings.Split(arg("scopes"), ",")
	if arg("scopes") == "" {
		sc = []string{"profile:read"}
	}
	act := []string{}
	if arg("actors") != "" {
		act = strings.Split(arg("actors"), ",")
	}
	h := M{"alg": func() string {
		if arg("alg") != "" {
			return arg("alg")
		}
		return "HS256"
	}(), "typ": "SWA1", "kid": kid}
	p := M{"iss": ci, "sub": arg("subject"), "tenant": arg("tenant"), "aud": aud, "scope": sc, "jti": arg("jti"), "iat": now, "nbf": nbf, "exp": exp, "source_epoch": epoch, "act": act}
	if p["sub"] == "" {
		p["sub"] = "svc-exporter"
	}
	if p["tenant"] == "" {
		p["tenant"] = "acme"
	}
	if p["jti"] == "" {
		p["jti"] = "jti-default"
	}
	input := b64(canon(h)) + "." + b64(canon(p))
	fmt.Println(input + "." + sign(input, sec))
}
func verifyCapability() {
	tok := arg("token")
	ps := strings.Split(tok, ".")
	if len(ps) != 3 {
		must(errors.New("malformed capability"))
	}
	hb, e := base64.RawURLEncoding.DecodeString(ps[0])
	must(e)
	pb, e := base64.RawURLEncoding.DecodeString(ps[1])
	must(e)
	var h M
	var p M
	must(json.Unmarshal(hb, &h))
	must(json.Unmarshal(pb, &p))
	var ks struct {
		ActiveSigner string                                     `json:"active_signer"`
		Keys         map[string]struct{ Secret, Status string } `json:"keys"`
	}
	read(filepath.Join(root(), "state/broker-keys.json"), &ks)
	kid, _ := h["kid"].(string)
	k, ok := ks.Keys[kid]
	if !ok {
		must(errors.New("unknown capability key"))
	}
	mac := sign(ps[0]+"."+ps[1], k.Secret)
	if !hmac.Equal([]byte(mac), []byte(ps[2])) {
		must(errors.New("bad capability signature"))
	}
	out := M{"header": h, "claims": p, "key_status": k.Status}
	b, _ := json.Marshal(out)
	fmt.Println(string(b))
}
func reset() {
	os.RemoveAll(filepath.Join(root(), "state"))
	os.RemoveAll(filepath.Join(root(), "runtime"))
	copyTree("/opt/task-tools/baseline/state", filepath.Join(root(), "state"))
	copyTree("/opt/task-tools/baseline/config", filepath.Join(root(), "runtime/config"))
	fmt.Println(`{"status":"reset"}`)
}
func inject() {
	var v M
	read(filepath.Join(root(), "state/failure.json"), &v)
	v["point"] = arg("point")
	write(filepath.Join(root(), "state/failure.json"), v)
	fmt.Println(`{"status":"armed"}`)
}
func ack() {
	var v struct {
		Nodes map[string]M `json:"nodes"`
	}
	read(filepath.Join(root(), "state/nodes.json"), &v)
	if v.Nodes == nil {
		v.Nodes = map[string]M{}
	}
	g, _ := strconv.Atoi(arg("generation"))
	v.Nodes[arg("node")] = M{"generation": g, "bundle_hash": arg("bundle-hash")}
	write(filepath.Join(root(), "state/nodes.json"), v)
	fmt.Println(`{"status":"acked"}`)
}
func revoke() {
	var v M
	read(filepath.Join(root(), "state/broker-keys.json"), &v)
	keys := v["keys"].(map[string]any)
	k := keys[arg("key")].(map[string]any)
	k["status"] = "revoked"
	keys[arg("key")] = k
	v["keys"] = keys
	write(filepath.Join(root(), "state/broker-keys.json"), v)
	fmt.Println(`{"status":"revoked"}`)
}
func inspect() {
	b, e := os.ReadFile(filepath.Join(root(), arg("path")))
	must(e)
	fmt.Print(string(b))
}
func main() {
	if len(os.Args) < 2 {
		must(errors.New("command required"))
	}
	switch os.Args[1] {
	case "reset":
		reset()
	case "sign-assertion":
		signAssertion()
	case "verify-capability":
		verifyCapability()
	case "inject-failure":
		inject()
	case "ack-node":
		ack()
	case "revoke-key":
		revoke()
	case "inspect":
		inspect()
	case "sort-json":
		var v any
		read(arg("file"), &v)
		if m, ok := v.(map[string]any); ok {
			keys := make([]string, 0, len(m))
			for k := range m {
				keys = append(keys, k)
			}
			sort.Strings(keys)
		}
		b, _ := json.Marshal(v)
		fmt.Println(string(b))
	default:
		must(errors.New("unknown command"))
	}
}
