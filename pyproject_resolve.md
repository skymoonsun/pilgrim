[[tool.mypy.overrides]]
# Third-party scrapling ships py.typed but is not strict-clean; tests
# import it to pin the fetcher API surface, so keep its internals out.
module = ["scrapling.*", "curl_cffi.*"]
ignore_errors = true

[[tool.mypy.overrides]]
# Legacy code (pre-test-core) still has hundreds of pre-existing strict
# violations; it stays type-annotated but error-tolerant until the
# cleanup lands. Everything else — tests in particular — is strict.
module = ["app.*", "migrations.*", "seeds.*"]
ignore_errors = true
