package cutover

import (
	"errors"
	"os"

	"jenkins-lambda-cutover/internal/model"
	"jenkins-lambda-cutover/internal/simclient"
	"jenkins-lambda-cutover/internal/store"
)

type response struct {
	OK         bool   `json:"ok"`
	Generation int    `json:"generation"`
	Writer     string `json:"writer"`
	Epoch      int64  `json:"epoch"`
	Message    string `json:"message"`
}

func Ensure(generation int) (model.CutoverState, error) {
	c, err := store.LoadCutover()
	if err == nil {
		return c, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return c, err
	}
	var r response
	if err := simclient.Call("control", map[string]any{"generation": generation, "writer": "lambda", "epoch": 1}, &r); err != nil {
		return c, err
	}
	if !r.OK {
		return c, errors.New(r.Message)
	}
	c = model.CutoverState{ActiveGeneration: generation, Writer: "lambda", Epoch: r.Epoch}
	return c, store.SaveCutover(c)
}
func Load() (model.CutoverState, error) { return store.LoadCutover() }
func Shift(generation int, writer string) (model.CutoverState, error) {
	current, err := store.LoadCutover()
	if err != nil {
		return current, err
	}
	// The local pointer moves first and the overlap window hands writes back to Jenkins.
	next := model.CutoverState{ActiveGeneration: generation, PreviousGeneration: current.ActiveGeneration, Writer: "jenkins", Epoch: current.Epoch + 1}
	if err := store.SaveCutover(next); err != nil {
		return next, err
	}
	var r response
	if err := simclient.Call("control", map[string]any{"generation": generation, "writer": "jenkins", "epoch": next.Epoch}, &r); err != nil {
		return next, err
	}
	if !r.OK {
		return next, errors.New(r.Message)
	}
	return next, nil
}
