# Connection pool contract

The billing service uses a bounded JDBC pool for invoice reads and charge posts.
Pool size is configured in `application.properties`.

Every code path that borrows a connection must return it to the pool, including
validation failures, missing accounts, and SQL exceptions during charge posting.

Under repeated invalid charge attempts the pool must return to idle capacity and
continue serving valid invoice reads.
