# Changelog

Todos los cambios relevantes de `atril` se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [0.1.2] - 2026-11-03

### Changed

- Requiere `acodo>=0.5.1`, cuyos `has_only_keys` y `has_required_keys` son genéricos en el
  tipo de llave; se elimina el `cast` que hacía falta en `Table.close()`.

## [0.1.1] - 2026-11-03

### Changed

- Requiere `acodo>=0.5`: la validación de rutas relativas de `temario.toml` usa
  `valid_relative_path` y la detección de claves desconocidas usa `has_only_keys`, en lugar
  de implementaciones propias.
- `[backup] repos_git` exige rutas absolutas (`D:\…` o `/…`), validadas con `valid_path`, que
  ya reconoce las de Windows. Los repos que se empaquetan viven fuera de la estación, así que
  resolverlos contra ella no tenía sentido.

### Fixed

- Las rutas relativas que empiezan por `~` (que `to_path` expandiría) ya no se aceptan en
  `carpeta`, `prompt` ni `evaluacion`.

## [0.1.0] - 2026-11-03

### Added

- Esqueleto del proyecto a partir de `acodo-template` 0.3.0 (uv, Ruff, ty, pytest, CI en
  Linux y Windows).
- Esquemas cerrados de `atril.toml` (estación) y `temario.toml` (temarios), con validación
  estricta: tipos, claves desconocidas, reglas por tipo de fuente, pertenencia de cada fuente
  a una sola KB e id de KB únicos en la estación. Documentados en `docs/esquemas.md`.
- CLI `atril` (Typer) con `--estacion` / `ATRIL_ESTACION`, `--version` y `atril validar`.
