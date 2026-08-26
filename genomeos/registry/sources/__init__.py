"""Registry source adapters (design §6, P0).

Every module here exposes `load(path, registry_version) -> (populations, aliases)` conforming to
`registry.schema`. An adapter that can refuse rows returns them followed by a report counting
each refusal reason, so a refusal is stated rather than silent (§12) — the same shape as
`observations.sources.map_surveys.load`. `hgdp` refuses nothing and returns the pair alone.
"""
