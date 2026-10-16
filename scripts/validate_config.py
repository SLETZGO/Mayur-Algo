"""Validate the current safe-default configuration without connecting to a broker."""

from nifty_algo.config import config_from_environment


if __name__ == "__main__":
    config = config_from_environment()
    print(f"Valid configuration: {config.execution_mode.value}")
