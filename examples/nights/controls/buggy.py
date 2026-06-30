from models import Stay


def nights(stay: Stay) -> int:
    # bug: counts days inclusive, one too many
    return (stay.checkout - stay.checkin).days + 1
