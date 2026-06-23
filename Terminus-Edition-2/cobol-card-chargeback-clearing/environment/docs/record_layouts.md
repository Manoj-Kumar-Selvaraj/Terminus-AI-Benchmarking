Records are fixed width. Sale rows use type byte, 12-character sale id, 3-character reason, 10-digit amount, 8-character merchant id, 1-character status, and optionally an 8-character settlement date. Chargeback rows use type byte, 12-character sale id, 10-digit amount, 8-character merchant id, and optionally an 8-character chargeback date.

Legacy undated rows end immediately after the status byte on sales or after the merchant id on chargebacks. Dated rows append `YYYYMMDD` settlement or chargeback dates in the optional positions described in `/app/docs/date_gating.md`.
