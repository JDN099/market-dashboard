import os


TRUE_VALUES = {"1", "on", "true", "yes"}


def environment_name():
    return os.getenv("APP_ENV", "development").strip().lower()


def is_production():
    return environment_name() == "production"


def env_flag(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in TRUE_VALUES


def debug_enabled():
    if is_production():
        return False

    return env_flag("FLASK_DEBUG", default=False)
