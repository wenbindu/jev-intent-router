import uvicorn

from .config import load_config


def main() -> None:
    config = load_config()
    uvicorn.run("intent_router.main:app", host=config.hostname, port=config.port)


if __name__ == "__main__":
    main()
