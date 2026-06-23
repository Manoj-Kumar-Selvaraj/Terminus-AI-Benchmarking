import subprocess
from pathlib import Path

APP = Path("/app")
TEST_FILE = APP / "internal" / "tlsmaterial" / "rotation_recovery_test.go"
GO_TEST = r'''package tlsmaterial_test

import (
    "context"
    "crypto/tls"
    "crypto/x509"
    "io"
    "net/http"
    "net/http/httptest"
    "os"
    "path/filepath"
    "testing"
    "time"

    "edge-gateway-tls-recovery/internal/tlsmaterial"
    "edge-gateway-tls-recovery/internal/upstream"
)

const certRoot = "/app/certs"

func fixture(parts ...string) string {
    all := append([]string{certRoot}, parts...)
    return filepath.Join(all...)
}

func mustRead(t *testing.T, path string) []byte {
    t.Helper()
    data, err := os.ReadFile(path)
    if err != nil {
        t.Fatalf("read %s: %v", path, err)
    }
    return data
}

func copyFile(t *testing.T, src, dst string) {
    t.Helper()
    if err := os.WriteFile(dst, mustRead(t, src), 0600); err != nil {
        t.Fatalf("copy %s to %s: %v", src, dst, err)
    }
}

func writeBundle(t *testing.T, path string, certs ...string) {
    t.Helper()
    var bundle []byte
    for _, cert := range certs {
        bundle = append(bundle, mustRead(t, cert)...)
    }
    if err := os.WriteFile(path, bundle, 0600); err != nil {
        t.Fatalf("write trust bundle: %v", err)
    }
}

func startTLSServer(t *testing.T, certPath, keyPath, clientCAPath, expectedClientCN string) *httptest.Server {
    t.Helper()
    pair, err := tls.LoadX509KeyPair(certPath, keyPath)
    if err != nil {
        t.Fatalf("load server pair: %v", err)
    }
    handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Connection", "close")
        if expectedClientCN != "" {
            if r.TLS == nil || len(r.TLS.PeerCertificates) == 0 {
                http.Error(w, "client certificate missing", http.StatusUnauthorized)
                return
            }
            if got := r.TLS.PeerCertificates[0].Subject.CommonName; got != expectedClientCN {
                http.Error(w, "unexpected client identity: "+got, http.StatusForbidden)
                return
            }
        }
        _, _ = io.WriteString(w, "ledger-ready")
    })
    srv := httptest.NewUnstartedServer(handler)
    srv.TLS = &tls.Config{
        Certificates: []tls.Certificate{pair},
        MinVersion: tls.VersionTLS12,
    }
    if clientCAPath != "" {
        pool := x509.NewCertPool()
        if ok := pool.AppendCertsFromPEM(mustRead(t, clientCAPath)); !ok {
            t.Fatalf("client CA fixture had no certificate")
        }
        srv.TLS.ClientAuth = tls.RequireAndVerifyClientCert
        srv.TLS.ClientCAs = pool
    }
    srv.StartTLS()
    t.Cleanup(srv.Close)
    return srv
}

func newManager(t *testing.T, rootFile, serverName, certFile, keyFile string) *tlsmaterial.Manager {
    t.Helper()
    manager, err := tlsmaterial.NewManager(tlsmaterial.Config{
        RootCAFile: rootFile,
        ServerName: serverName,
        ClientCertFile: certFile,
        ClientKeyFile: keyFile,
    })
    if err != nil {
        t.Fatalf("NewManager: %v", err)
    }
    cfg := manager.ClientTLSConfig()
    if cfg.InsecureSkipVerify {
        t.Fatalf("certificate verification must remain enabled")
    }
    if cfg.MinVersion < tls.VersionTLS12 {
        t.Fatalf("minimum TLS version = %d, want TLS 1.2 or newer", cfg.MinVersion)
    }
    return manager
}

func fetch(t *testing.T, client *upstream.Client, target string) {
    t.Helper()
    ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
    defer cancel()
    body, err := client.Get(ctx, target)
    if err != nil {
        t.Fatalf("verified request failed: %v", err)
    }
    if string(body) != "ledger-ready" {
        t.Fatalf("response = %q, want ledger-ready", string(body))
    }
}

func TestConfiguredPrivateTrustAuthenticatesReplacementIssuer(t *testing.T) {
    tempRoot := filepath.Join(t.TempDir(), "deployment-root.pem")
    copyFile(t, fixture("trust", "current-issuer.pem"), tempRoot)
    manager := newManager(t, tempRoot, "", "", "")
    server := startTLSServer(t,
        fixture("server", "replacement-ip.pem"),
        fixture("server", "replacement-ip.key"),
        "", "")
    fetch(t, upstream.NewClient(manager), server.URL)
}

func TestConfiguredPrivateTrustAuthenticatesReplacementIssuerFromMultiCertBundle(t *testing.T) {
    tempRoot := filepath.Join(t.TempDir(), "deployment-root.pem")
    // The replacement CA appears second in the PEM bundle, so trust loading must
    // process all certificate blocks (not only the first PEM block).
    writeBundle(t, tempRoot,
        fixture("trust", "current-issuer.pem"),
        fixture("ca", "replacement-issuer.pem"),
    )
    manager := newManager(t, tempRoot, "", "", "")
    server := startTLSServer(t,
        fixture("server", "replacement-ip.pem"),
        fixture("server", "replacement-ip.key"),
        "", "")
    fetch(t, upstream.NewClient(manager), server.URL)
}
'''

def test_tls_rotation_milestone_1():
    """Verify private trust anchors and multi-cert PEM bundles authenticate rotated issuers."""
    TEST_FILE.write_text(GO_TEST)
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "-race", "./internal/tlsmaterial", "-count=1"],
        cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240,
    )
    assert result.returncode == 0, result.stdout
