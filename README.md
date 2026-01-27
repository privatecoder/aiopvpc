[pypi-image]: https://img.shields.io/pypi/v/aiopvpc
[pypi-url]: https://pypi.org/project/aiopvpc/
[pre-commit-ci-image]: https://results.pre-commit.ci/badge/github/azogue/aiopvpc/master.svg
[pre-commit-ci-url]: https://results.pre-commit.ci/latest/github/azogue/aiopvpc/master
[build-image]: https://github.com/azogue/aiopvpc/actions/workflows/main.yml/badge.svg
[build-url]: https://github.com/azogue/aiopvpc/actions/workflows/main.yml

# aiopvpc (fork for PVPC Next)

Simple aio library to download Spanish electricity hourly prices.

Made to support the [**`PVPC Next`** HomeAssistant integration](https://github.com/privatecoder/ha-pvpc-next).

## Install

Install with `poetry install` or `pip install git+https://github.com/privatecoder/aiopvpc.git@v4.3.3` clone it to run tests or anything else.

## Usage

```python
import asyncio
import aiohttp
from datetime import datetime
from aiopvpc import PVPCData

async def main():
    async with aiohttp.ClientSession() as session:
        pvpc_handler = PVPCData(session=session, tariff="2.0TD")
        esios_data = await pvpc_handler.async_update_all(
            current_data=None, now=datetime.utcnow()
        )
        print(esios_data.sensors["PVPC"])

asyncio.run(main())
```
