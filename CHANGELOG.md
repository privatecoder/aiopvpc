# Changelog

## [v4.3.4](https://github.com/privatecoder/aiopvpc/tree/v4.3.4) - 🚀 Bump dependencies (2026-01-28)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.3...v4.3.4)

- 🐛 Fix `async_timeout` dependency, incompatible with the pinned version in HA core (`async-timeout==4.0.3`)

## [v4.3.3](https://github.com/privatecoder/aiopvpc/tree/v4.3.3) - 🚀 Bump dependencies (2026-01-27)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.2...v4.3.3)

- 🚀 Bump min-version of (dev-) dependencies, especially holidays, to ensure up-to-date Holidays for Spain

## [v4.3.2](https://github.com/privatecoder/aiopvpc/tree/v4.3.2) - 🐛 Fix _no hardcoded holidays for 2026_ (2026-01-20)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.1...v4.3.2)

- 🐛 Fix crash due to missing Holidays for 2026, by replacing all hardcoded values with the [holidays library](https://pypi.org/project/holidays/) (#80)
- ✨ Changed some label- and variable-namings to better reflect their purpose
- ✨ Add debug logs
