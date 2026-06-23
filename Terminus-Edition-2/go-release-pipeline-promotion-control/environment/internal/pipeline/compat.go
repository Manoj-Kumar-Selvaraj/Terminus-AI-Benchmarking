package pipeline

func PublicStageNames() []string {
	return append([]string{}, stageOrder...)
}
