package clock

import (
    "context"
    "time"
    rt "vault-dynamic-database-lease-recovery/internal/runtime"
)

type Clock struct { Runtime *rt.Client }
type status struct { Clock string `json:"clock"` }
func (c Clock) Now(ctx context.Context) (time.Time,error) {
    var out status;if err:=c.Runtime.Run(ctx,&out,"status");err!=nil{return time.Time{},err}
    return time.Parse(time.RFC3339,out.Clock)
}
