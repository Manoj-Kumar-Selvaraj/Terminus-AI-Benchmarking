# Time-safety contract

The process receives time through the function supplied to `limiter.New`. Tests may move this clock forwards or backwards without sleeping.

A timestamp earlier than the bucket's last accepted refill watermark must not create tokens and must not move that watermark backwards. When the clock later catches up, only forward elapsed time from the retained watermark is eligible for refill. Retry durations must remain positive and reflect the current token deficit.
