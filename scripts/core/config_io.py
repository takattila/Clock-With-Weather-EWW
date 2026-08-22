#!/usr/bin/env python3
"""
Shared config loading with the local override layer.

The committed config.yaml holds the portable defaults; the git-ignored
config.local.yaml holds machine-specific overrides (and everything the
scripts write). load_merged() returns the deep-merged view every reader
uses, so an override may be as small as one leaf key:

    weather:
      window:
        per_monitor:
          0:
            scale: 0.85

Merge rules: mappings merge recursively, any other type (scalar, list)
is replaced by the local value. A missing or empty local file is a no-op;
an unparsable one logs a warning to stderr and is ignored (the widget
keeps running on the base config).
"""

import os
import sys

import yaml

BASE_CONFIG_FILE = "config.yaml"
LOCAL_CONFIG_FILE = "config.local.yaml"


def deep_merge(base, override):
    """Recursively merge two mappings; `override` wins on every conflict."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(merged[key], value) if key in merged else value
        return merged
    return override


def load_file(config_dir, name):
    with open(os.path.join(config_dir, name), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def local_path(config_dir):
    return os.path.join(config_dir, LOCAL_CONFIG_FILE)


def load_merged(config_dir):
    """Return config.yaml deep-merged with config.local.yaml (when present)."""
    cfg = load_file(config_dir, BASE_CONFIG_FILE)
    path = local_path(config_dir)
    if not os.path.isfile(path):
        return cfg
    try:
        return deep_merge(cfg, load_file(config_dir, LOCAL_CONFIG_FILE))
    except (OSError, yaml.YAMLError) as exc:
        print("WARN: ignoring unreadable %s (%s)" % (path, exc), file=sys.stderr)
        return cfg


def save_local(config_dir, data):
    """Write the machine-local override dict to config.local.yaml."""
    with open(local_path(config_dir), "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
