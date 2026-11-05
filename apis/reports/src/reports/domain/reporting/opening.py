"""Opening-effect classification shared by reference and native financial inputs."""


def opening_effect(kind: str, has_original: bool, original_kind: str | None) -> bool:
    if kind == "OPENING":
        return True
    if kind != "REVERSAL" or not has_original:
        return False
    if original_kind is None:
        raise ValueError("reversal's original journal is missing from retained history")
    return original_kind == "OPENING"
