package reconcile

import (
	"path/filepath"
)

func loadWindows(base string) ([]Window, error) {
	rows, err := readMaps(filepath.Join(base, "config", "windows.csv"))
	if err != nil {
		return nil, err
	}
	out := make([]Window, 0, len(rows))
	for _, m := range rows {
		out = append(out, Window{ChainID: m["chain_id"], OpenTS: m["open_ts"], CloseTS: m["close_ts"], State: m["state"]})
	}
	return out, nil
}

func loadAliases(base string) (map[string]string, error) {
	rows, err := readMaps(filepath.Join(base, "config", "kind_aliases.csv"))
	if err != nil {
		return nil, err
	}
	aliases := map[string]string{}
	for _, m := range rows {
		aliases[m["alias"]] = m["canonical"]
	}
	return aliases, nil
}
