"""Lets the sender run as `python -m delivery_ops_hub ...` without installing it."""

from .cli import main

raise SystemExit(main())
