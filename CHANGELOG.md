# Changelog

## [v4.3.5](https://github.com/privatecoder/aiopvpc/tree/v4.3.5) - 🚀 Replace holidays with spanish-pvpc-holidays (2026-02-04)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.4...v4.3.5)

- ✨ **Replace [holidays library](https://pypi.org/project/holidays/) with [spanish-pvpc-holidays](https://github.com/privatecoder/spanish-pvpc-holidays)** as for PVPC pricing in 2.0 TD tariffs, there are some additional rules for holidays that count as such.
- ✨ Add some CLI tests

## [v4.3.4](https://github.com/privatecoder/aiopvpc/tree/v4.3.4) - 🚀 Bump dependencies (2026-01-28)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.3...v4.3.4)

- 🐛 Fix `async_timeout` dependency (also loosened `aiohttp`), incompatible with the pinned version in HA core (`async-timeout==4.0.3`)
- 🐛 Loosened `aiohttp` dependency for compatibility with older HA versions

## [v4.3.3](https://github.com/privatecoder/aiopvpc/tree/v4.3.3) - 🚀 Bump dependencies (2026-01-27)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.2...v4.3.3)

- 🚀 Bump min-version of (dev-) dependencies, especially holidays, to ensure up-to-date Holidays for Spain

## [v4.3.2](https://github.com/privatecoder/aiopvpc/tree/v4.3.2) - 🐛 Fix _no hardcoded holidays for 2026_ (2026-01-20)

[Full Changelog](https://github.com/privatecoder/aiopvpc/compare/v4.3.1...v4.3.2)

- 🐛 Fix crash due to missing Holidays for 2026, by replacing all hardcoded values with the [holidays library](https://pypi.org/project/holidays/) (#80)
- ✨ Changed some label- and variable-namings to better reflect their purpose
- ✨ Add debug logs
