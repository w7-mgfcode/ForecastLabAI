# Changelog

## [0.2.0](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.8...v0.2.0) (2026-02-01)


### Features

* **registry:** implement model registry for run tracking and deployments ([#36](https://github.com/w7-mgfcode/ForecastLabAI/issues/36)) ([902f331](https://github.com/w7-mgfcode/ForecastLabAI/commit/902f331))
  - ORM models for ModelRun (JSONB columns) and DeploymentAlias with state machine validation
  - LocalFSProvider for artifact storage with SHA-256 integrity verification
  - 10 API endpoints for runs CRUD, aliases management, artifact verification, and run comparison
  - Comprehensive test suite (103 unit + 24 integration tests)


### Bug Fixes

* add date range filter to SalesDaily cleanup in ingest tests ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))
* enforce artifact_hash presence before verification in registry routes ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))
* compute SHA256 from saved file instead of source in storage ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))
* fix override_get_db to mirror production transaction semantics ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))
* update database port to 5433 in config and .env.example ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))


### Documentation

* add PHASE documentation for phases 4 (Forecasting), 5 (Backtesting), and 6 (Model Registry) ([7d2722f](https://github.com/w7-mgfcode/ForecastLabAI/commit/7d2722f))
* fix markdownlint MD040/MD060 issues in docs ([008aaac](https://github.com/w7-mgfcode/ForecastLabAI/commit/008aaac))

## [0.1.8](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.7...v0.1.8) (2026-02-01)


### Features

* **backtesting:** implement time-series backtesting module (PRP-6) ([#32](https://github.com/w7-mgfcode/ForecastLabAI/issues/32)) ([8aca4d1](https://github.com/w7-mgfcode/ForecastLabAI/commit/8aca4d13a57c0b6ebf416a384995d98c35884121))
* **backtesting:** wire config fields into implementation ([daef9ce](https://github.com/w7-mgfcode/ForecastLabAI/commit/daef9ce3d72bf90ca53f61a095576c454385c93b))
* **backtesting:** wire config fields into implementation ([80e99e8](https://github.com/w7-mgfcode/ForecastLabAI/commit/80e99e8113bc7a935a392229e72e5f416e0bda75))


### Bug Fixes

* **backtesting:** handle signed metrics in comparison summary ([215d249](https://github.com/w7-mgfcode/ForecastLabAI/commit/215d249a056727c3d95f568ce5eba7dbd52f443c))

## [0.1.7](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.6...v0.1.7) (2026-02-01)


### Features

* **forecasting:** add baseline model zoo with security validations ([3da7783](https://github.com/w7-mgfcode/ForecastLabAI/commit/3da7783748f8d9bf2fe96e194274aa88f69bdfd2))
* **forecasting:** implement baseline model zoo and unified interface ([#28](https://github.com/w7-mgfcode/ForecastLabAI/issues/28)) ([a9a055f](https://github.com/w7-mgfcode/ForecastLabAI/commit/a9a055f39cb781dbb5b6f8f9b76e7d4e833d30ce))


### Bug Fixes

* **forecasting:** add security validations and fix documentation ([1d411f9](https://github.com/w7-mgfcode/ForecastLabAI/commit/1d411f9ebd43e11b7bcba4525ba75cba7903dfbe))


### Documentation

* update DAILY-FLOW.md for Phase 4 Forecasting ([#27](https://github.com/w7-mgfcode/ForecastLabAI/issues/27)) ([e2c57ff](https://github.com/w7-mgfcode/ForecastLabAI/commit/e2c57ffb35cfa1fe0a4d0b6b9d1f56be9abdc7d9))

## [0.1.5](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.4...v0.1.5) (2026-01-26)


### Features

* **ingest:** implement idempotent batch upsert endpoint for sales_daily ([#19](https://github.com/w7-mgfcode/ForecastLabAI/issues/19)) ([0e15cb3](https://github.com/w7-mgfcode/ForecastLabAI/commit/0e15cb34587c744c41e20c554c82adf3ff27f853))


### Bug Fixes

* **docs:** address CodeRabbit review comments ([3fb1b06](https://github.com/w7-mgfcode/ForecastLabAI/commit/3fb1b06b584b7f0e39019de49d68ebc456ec02a7))


### Documentation

* add DAILY-FLOW and PHASE-FLOW documentation ([292e8c6](https://github.com/w7-mgfcode/ForecastLabAI/commit/292e8c67957488de981da27686bbd20f03040ed0))
* add Phase 2 (Ingest Layer) documentation ([#20](https://github.com/w7-mgfcode/ForecastLabAI/issues/20)) ([3249bf6](https://github.com/w7-mgfcode/ForecastLabAI/commit/3249bf61387501c38a7455479457ef6cfe778323))

## [0.1.4](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.3...v0.1.4) (2026-01-26)


### Documentation

* mark Phase 1 as completed (v0.1.3) ([#15](https://github.com/w7-mgfcode/ForecastLabAI/issues/15)) ([10601ef](https://github.com/w7-mgfcode/ForecastLabAI/commit/10601ef4f3e87ade284a4f914a422e3782e4d5d4))

## [0.1.3](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.2...v0.1.3) (2026-01-26)


### Features

* **data-platform:** implement PRP-2 schema and migrations ([#12](https://github.com/w7-mgfcode/ForecastLabAI/issues/12)) ([c392942](https://github.com/w7-mgfcode/ForecastLabAI/commit/c39294249a628fdcc2567f622a65e71dafa24d62))

## [0.1.2](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.1...v0.1.2) (2026-01-26)


### Bug Fixes

* **ci:** use uv build instead of python -m build ([#9](https://github.com/w7-mgfcode/ForecastLabAI/issues/9)) ([c2b22d3](https://github.com/w7-mgfcode/ForecastLabAI/commit/c2b22d3c760df5bbeae6bb745a25801fb8a20f4c))

## [0.1.1](https://github.com/w7-mgfcode/ForecastLabAI/compare/v0.1.0...v0.1.1) (2026-01-26)


### Features

* implement Phase 0 project foundation ([17c81cd](https://github.com/w7-mgfcode/ForecastLabAI/commit/17c81cd21bb7aa0de97d0beebe434f6a0098fa0a))
* implement Phase 1 CI/CD and repo governance ([36874ba](https://github.com/w7-mgfcode/ForecastLabAI/commit/36874ba620e49585e8373f971169c2b026dd3af9))


### Bug Fixes

* add 'testing' to allowed app_env values ([d0b152e](https://github.com/w7-mgfcode/ForecastLabAI/commit/d0b152e3a99a4ed9f00f5a481a467dbd99f9aa69))
* make config tests environment-agnostic ([65bc671](https://github.com/w7-mgfcode/ForecastLabAI/commit/65bc671b3f8532b8ca979b823e0ee8d04c752688))
* remove CRLF line endings from pyproject.toml ([#6](https://github.com/w7-mgfcode/ForecastLabAI/issues/6)) ([66007a2](https://github.com/w7-mgfcode/ForecastLabAI/commit/66007a257e4fa810982dacab3c09e109c9b0bd89))


### Documentation

* update phase-0 documentation with CI/CD infrastructure ([#4](https://github.com/w7-mgfcode/ForecastLabAI/issues/4)) ([e33aade](https://github.com/w7-mgfcode/ForecastLabAI/commit/e33aade1b5a24dad131884c9ad058a82ab94ff8f))
