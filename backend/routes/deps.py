from utils import config


def get_user_id() -> str:
    """Single-user for now. Replace with authentication (e.g. a JWT subject) to get per-user separation:
    every repository and vector-store call is already scoped by this value."""
    return config.get_default_user_id()
