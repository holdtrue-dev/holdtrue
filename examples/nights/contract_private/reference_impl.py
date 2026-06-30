from models import Stay


def nights(stay: Stay) -> int:
    return (stay.checkout - stay.checkin).days
