package routes

type Route struct {
	Tenant   string
	Upstream string
	Revision int
}

type Snapshot struct {
	Revision int
	Routes   []Route
}
