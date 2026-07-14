# Contributing

Open an issue before large behavioral changes. Preserve the interaction
contract, add a failing conformance test first, and keep provider-specific code
outside the core server and browser protocol.

Run `pytest`, `ruff check .`, the browser matrix, and the monitor replay suite
before requesting review. Do not use private project artifacts as fixtures.

