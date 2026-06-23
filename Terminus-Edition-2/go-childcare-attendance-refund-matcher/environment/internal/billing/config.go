package billing

func allowedRoom(room string) bool {
    return room == "INFANT" || room == "TODDLER" || room == "PREK"
}
