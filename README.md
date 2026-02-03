# aiopvpc (fork for PVPC Next)

Simple aio library to download Spanish electricity hourly prices.

Made to support the [**`PVPC Next`** HomeAssistant integration](https://github.com/privatecoder/ha-pvpc-next).

---

## Install

Install with `poetry install` or `pip install git+https://github.com/privatecoder/aiopvpc.git@v5.0.0` clone it to run tests or anything else.

---

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

### Tariff period CLI

The package also exposes a small CLI to inspect tariff periods and holiday source:

```bash
# default source is csv
poetry run aiopvpc-tariff
poetry run aiopvpc-tariff --source csv
poetry run aiopvpc-tariff --source python-holidays
```

---

## License

MIT License. See the [LICENSE](LICENSE) file.
