import os

# settings.py の ANTHROPIC_API_KEY 必須チェックを回避
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-ci")
