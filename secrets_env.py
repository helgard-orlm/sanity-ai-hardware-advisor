"""Tokens are read from ~/.config/sanity_live/env (KEY=value per line, chmod 600). Never commit them."""
import os
def tok(name):
    if os.environ.get(name): return os.environ[name]
    for line in open(os.path.expanduser("~/.config/sanity_live/env")):
        k, _, v = line.strip().partition("=")
        if k == name:
            return v
    raise KeyError(name)
