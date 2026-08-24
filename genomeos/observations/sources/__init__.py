"""Observation source adapters (design §6, P1).

Registry-joined adapters expose `load(path, populations, aliases, ingest_version)`; adapters
whose source carries its own coordinates (e.g. survey data) expose `load(path, ingest_version)`.
"""
