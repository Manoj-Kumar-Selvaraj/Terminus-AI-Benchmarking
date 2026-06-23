package main

import (
	"log"
	"net/http"

	"tenant-route-service/internal/proxy"
	"tenant-route-service/internal/routes"
	"tenant-route-service/internal/server"
)

func main() {
	store := routes.NewStore([]routes.Route{
		{Tenant: "tenant-a", Upstream: "http://127.0.0.1:19090/a", Revision: 1},
	})
	svc := server.New(store, proxy.NewClient(http.DefaultClient))
	log.Fatal(http.ListenAndServe(":8080", svc.Handler()))
}
