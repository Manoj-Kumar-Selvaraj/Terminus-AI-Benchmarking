package dispatch

import "context"

func (d *Dispatcher) worker() {
	defer d.wg.Done()
	for {
		d.mu.Lock()
		job := <-d.jobs
		if d.queueDepth > 0 {
			d.queueDepth--
		}
		d.mu.Unlock()

		_ = d.deliver(context.Background(), job)
	}
}
