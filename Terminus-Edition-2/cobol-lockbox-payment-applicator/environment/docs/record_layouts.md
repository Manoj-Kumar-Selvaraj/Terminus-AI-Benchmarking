# Record Layouts

Invoice records:

```text
1      record type, "I"
2-13   invoice id, 12 chars
14-21  customer id, 8 chars
22-31  amount cents, 10 digits
32     invoice status, O=open, P=paid, V=void
33-40  cutoff date, YYYYMMDD
41-43  expected payment channel
44     invoice hold flag, N=not held, H=held
```

Payment records:

```text
1      record type, "P"
2-13   invoice id, 12 chars
14-21  customer id, 8 chars
22-31  amount cents, 10 digits
32-39  payment date, YYYYMMDD
40-42  payment channel
43     payment disposition, P=postable, R=returned
```
