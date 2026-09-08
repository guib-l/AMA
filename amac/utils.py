#!/usr/bin/env python3
import os
import subprocess
from functools import wraps
from pathlib import Path


def assert_flags(myset):
    def decorateur(func):

        @wraps(func)
        def wrapper(self, *args, **kwargs):

            _flags = getattr(self, "flags")

            if isinstance(myset, list):
                for ms in myset:
                    if ms not in _flags:
                        return
            else:
                if myset not in _flags:
                    return

            return func(self, *args, **kwargs)

        return wrapper

    return decorateur


def exclude_flags(myset):
    def decorateur(func):

        @wraps(func)
        def wrapper(self, *args, **kwargs):

            _flags = getattr(self, "flags")

            if isinstance(myset, list):
                for ms in myset:
                    if ms in _flags:
                        return
            else:
                if myset in _flags:
                    return

            return func(self, *args, **kwargs)

        return wrapper

    return decorateur



