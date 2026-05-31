import os
import tempfile
import uuid

# Set env BEFORE any app import (tests import app.main at module level).
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test-{uuid.uuid4().hex}.db")
os.environ.setdefault("JWT_SECRET", "test_secret_test_secret_test_secret_xxxx")
os.environ.setdefault("WA_BRIDGE_SECRET", "test_wa_secret_test_wa_secret_xxxx")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")
os.environ.setdefault("RATE_LIMIT_LOGIN", "1000/minute")
os.environ.setdefault("RATE_LIMIT_SIGNUP", "1000/hour")
