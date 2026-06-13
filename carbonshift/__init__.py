"""CarbonShift — carbon-aware scheduling agent."""

# Load .env early so all modules see configuration via os.environ. Load the project
# .env (one level above this package) explicitly so it works regardless of cwd.
try:
    import os

    from dotenv import load_dotenv

    _project_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(_project_env)
    load_dotenv()  # also honour a .env in the current working directory
except Exception:  # python-dotenv optional at runtime
    pass

__version__ = "0.1.0"
