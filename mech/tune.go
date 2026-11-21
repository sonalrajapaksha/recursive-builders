package mech

import (
	_ "embed"
	"encoding/json"
	"reflect"
)

// tune.json holds numeric/bool overrides for the squad (practice) profile,
// applied by name via reflection. Data-only experiments edit this file.
//
//go:embed tune.json
var tuneRaw []byte

func applyTune(p Params) Params {
	var m map[string]float64
	if json.Unmarshal(tuneRaw, &m) != nil {
		return p
	}
	v := reflect.ValueOf(&p).Elem()
	for k, x := range m {
		f := v.FieldByName(k)
		if !f.IsValid() || !f.CanSet() {
			continue
		}
		switch f.Kind() {
		case reflect.Float64:
			f.SetFloat(x)
		case reflect.Bool:
			f.SetBool(x != 0)
		}
	}
	return p
}
