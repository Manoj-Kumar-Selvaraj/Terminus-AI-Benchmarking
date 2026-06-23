package config

import (
	"encoding/json"
	"errors"
	"os"
)

type Gateway struct {
	ListenAddress  string `json:"listen_address"`
	UpstreamURL    string `json:"upstream_url"`
	ServerName     string `json:"server_name"`
	RootCAFile     string `json:"root_ca_file"`
	ClientCertFile string `json:"client_cert_file"`
	ClientKeyFile  string `json:"client_key_file"`
}

func Load(path string) (Gateway, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return Gateway{}, err
	}
	var cfg Gateway
	if err := json.Unmarshal(data, &cfg); err != nil {
		return Gateway{}, err
	}
	if cfg.ListenAddress == "" || cfg.UpstreamURL == "" || cfg.RootCAFile == "" {
		return Gateway{}, errors.New("listen_address, upstream_url, and root_ca_file are required")
	}
	return cfg, nil
}
