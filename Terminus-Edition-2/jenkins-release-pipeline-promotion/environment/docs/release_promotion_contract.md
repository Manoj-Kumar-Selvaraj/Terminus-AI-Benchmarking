# Release promotion contract
Production promotion must deploy the exact artifact digest produced by the Build stage after integration and quality gates pass for that digest. Rollback must redeploy the last successful production artifact digest and must not rebuild from HEAD.
