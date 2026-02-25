"""BreakTheVibe entrypoint."""

import uvicorn


def cli() -> None:
    """CLI entrypoint."""
    uvicorn.run("breakthevibe.web.app:create_app", factory=True, reload=True)


if __name__ == "__main__":
    cli()
