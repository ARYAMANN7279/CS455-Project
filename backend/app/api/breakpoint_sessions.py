"""Re-export so the api package's import line reads naturally."""
from app.api.breakpoints import router

__all__ = ["router"]
