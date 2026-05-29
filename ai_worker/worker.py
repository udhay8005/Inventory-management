"""Optional out-of-process forecast worker.

For most installs the in-process Odoo cron in `wms_ai_forecast` is enough.
Use this worker only when:
  - The Odoo container is memory-constrained and can't load statsmodels.
  - You want forecasts to be retrained on a beefier separate machine.

It periodically calls the `wms.forecast.engine` server method via XML-RPC and
asks Odoo to retrain. The heavy math still happens on whichever side has the
library installed — so the worker is just an orchestrator unless you import the
algorithm here too.
"""

from __future__ import annotations

import os
import time
import xmlrpc.client

URL = os.environ["ODOO_URL"]
DB = os.environ["ODOO_DB"]
USER = os.environ["ODOO_USER"]
PASSWORD = os.environ["ODOO_PASSWORD"]
INTERVAL = int(os.environ.get("FORECAST_INTERVAL_HOURS", "6")) * 3600


def connect() -> tuple[int, xmlrpc.client.ServerProxy]:
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    # XML-RPC `authenticate` is typed as the broad _Marshallable union, but
    # on Odoo it returns an int (user id) or False on bad creds. The `if not
    # uid` above rules out False/None, so the cast here is safe at runtime
    # and makes the declared return type honest for type-checkers.
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        raise RuntimeError("auth failed")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")
    return int(uid), models  # type: ignore[arg-type]


def trigger_forecast(uid: int, models: xmlrpc.client.ServerProxy) -> None:
    models.execute_kw(
        DB,
        uid,
        PASSWORD,
        "wms.forecast.engine",
        "run_all_forecasts",
        [],
    )


def main() -> None:
    print(f"[ai_worker] starting, interval={INTERVAL}s url={URL}")
    while True:
        try:
            uid, models = connect()
            trigger_forecast(uid, models)
            print("[ai_worker] forecast cycle ok")
        except Exception as exc:  # noqa: BLE001
            print(f"[ai_worker] error: {exc}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
