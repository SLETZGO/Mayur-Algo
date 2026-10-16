"""Minimal configuration validation entry point; does not start a trader."""

from nifty_algo.config import config_from_environment


def main() -> None:
    config = config_from_environment()
    print(f"Configuration valid. Execution mode: {config.execution_mode.value}")
    print("No broker connection or order execution is implemented.")


if __name__ == "__main__":
    main()
