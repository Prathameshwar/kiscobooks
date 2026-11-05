"""Order-independent business role selection; reference validity lives in the DB."""


def normalize_business_roles(codes: list[str]) -> list[str]:
    if len(codes) != len(set(codes)):
        raise ValueError("business_roles must not contain duplicates")
    return sorted(codes)
