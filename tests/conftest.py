import os

# settings.py の GOOGLE_API_KEY 必須チェックを回避
os.environ.setdefault("GOOGLE_API_KEY", "test-key-for-ci")
