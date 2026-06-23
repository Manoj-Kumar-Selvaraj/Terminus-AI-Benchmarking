package main

import (
	"encoding/csv"
	"fmt"
	"os"
	"strings"
)

func norm(v string) string { return strings.ToUpper(strings.TrimSpace(v)) }

func main() {
	if len(os.Args) < 2 { return }
	value := norm(os.Args[1])
	if len(os.Args) >= 3 {
		if f, err := os.Open(os.Args[2]); err == nil {
			defer f.Close()
			rows, _ := csv.NewReader(f).ReadAll()
			for _, row := range rows[1:] {
				if len(row) >= 2 && norm(row[0]) == value {
					fmt.Print(norm(row[1]))
					return
				}
			}
		}
	}
	fmt.Print(value)
}