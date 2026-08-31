"""
TEST OFFLINE - TRANSICIONES LIVE CON FDXM_QUANTITY

No conecta con IB Gateway.
No usa Gmail.
No envia ordenes reales.

Comprueba las dos secuencias completas del SignalExecutor:
    +2 -> 0 -> -2
    -2 -> 0 -> +2

Toda llamada a placeOrder() está sustituida por una simulación local.
"""

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

# La cantidad se fija ANTES de importar los módulos.
os.environ["FDXM_QUANTITY"] = "2"

from live_executor import LiveExecutor
from signal_executor import (
    SignalExecutor,
    CLOSE_LONG,
    OPEN_SHORT,
    CLOSE_SHORT,
    OPEN_LONG,
)
import signal_executor as signal_module
import live_executor as live_module


def assert_equal(actual, expected, label):

    if actual != expected:

        raise AssertionError(
            f"{label}: esperado={expected!r}, "
            f"obtenido={actual!r}"
        )


def assert_true(value, label):

    if not value:

        raise AssertionError(
            f"{label}: se esperaba True."
        )


class FakeLive:

    def __init__(self, initial_position):

        self.app = LiveExecutor()

        self.app.current_position = float(
            initial_position
        )

        self.app.position_avg_cost = 0.0
        self.app.next_order_id = 100

        self.app.connection_ready.set()
        self.app.positions_ready.set()

        self.app.is_trading_connection_ready = (
            lambda: True
        )

        self.calls = []

        self.app.placeOrder = (
            self.fake_place_order
        )

    def fake_place_order(
        self,
        order_id,
        contract,
        order
    ):

        self.calls.append(
            {
                "order_id": order_id,
                "action": order.action,
                "quantity": int(
                    order.totalQuantity
                ),
            }
        )

        old_position = (
            self.app.current_position
        )

        quantity = float(
            order.totalQuantity
        )

        if order.action == "BUY":

            new_position = (
                old_position + quantity
            )

        elif order.action == "SELL":

            new_position = (
                old_position - quantity
            )

        else:

            raise AssertionError(
                f"Accion IBKR invalida: {order.action}"
            )

        def emit_position():

            time.sleep(0.02)

            self.app.current_position = (
                new_position
            )

            self.app.position_update_event.set()

        threading.Thread(
            target=emit_position,
            daemon=True
        ).start()

        self.app.orderStatus(
            order_id,
            "Filled",
            quantity,
            0.0,
            26500.0,
            0,
            0,
            26500.0,
            0,
            "",
            0.0,
        )


def run_switch(
    title,
    initial_position,
    actions,
    expected_final
):

    print()
    print(
        "----------------------------------------"
    )
    print(title)
    print(
        "----------------------------------------"
    )

    fake = FakeLive(
        initial_position
    )

    executor = SignalExecutor(
        fake.app,
        None
    )

    # El SignalExecutor usa el mismo flujo que LIVE.
    # Activamos las banderas solo en memoria para el test.
    old_enabled = live_module.LIVE_TRADING_ENABLED
    old_validation = live_module.VALIDATION_ONLY

    live_module.LIVE_TRADING_ENABLED = True
    live_module.VALIDATION_ONLY = False

    try:

        # El estado del SignalExecutor debe calcular 2 unidades por acción.
        calculated = (
            executor._calculate_final_position(
                initial_position,
                actions
            )
        )

        assert_equal(
            calculated,
            expected_final,
            "Posición final calculada"
        )

        # Ejecutamos exactamente la señal de transición.
        signal = {
            "message_id": title,
            "email_uid": "TEST",
            "sender": "TEST",
            "subject": title,
            "date": "TEST",
            "actions": actions,
            "valid": True,
        }

        # Para probar solo la secuencia de ejecución, evitamos la
        # persistencia real del SignalState pasando un stub.
        class StateStub:

            def set_status(self, *args, **kwargs):
                pass

            def set_processing_order(self, *args, **kwargs):
                pass

            def set_operation_result(self, *args, **kwargs):
                pass

        executor.state_manager = StateStub()

        result = executor.execute(
            signal
        )

        assert_true(
            result.get("success", False),
            "Resultado de la transición"
        )

        assert_equal(
            result.get("position"),
            expected_final,
            "Posición final"
        )

        assert_equal(
            len(fake.calls),
            2,
            "Número de operaciones"
        )

        assert_equal(
            fake.calls[0]["quantity"],
            2,
            "Cantidad operación 1"
        )

        assert_equal(
            fake.calls[1]["quantity"],
            2,
            "Cantidad operación 2"
        )

        print(
            f"Operación 1: "
            f"{fake.calls[0]['action']} x"
            f"{fake.calls[0]['quantity']}"
        )

        print(
            f"Operación 2: "
            f"{fake.calls[1]['action']} x"
            f"{fake.calls[1]['quantity']}"
        )

        print(
            f"Posición final: {result.get('position')}"
        )

        print("OK")

    finally:

        live_module.LIVE_TRADING_ENABLED = (
            old_enabled
        )

        live_module.VALIDATION_ONLY = (
            old_validation
        )


def main():

    print()
    print(
        "========================================"
    )
    print(
        " TEST OFFLINE - TRANSICIONES QUANTITY=2"
    )
    print(
        "========================================"
    )

    print()
    print(
        "NO conecta con IB Gateway."
    )
    print(
        "NO envia ordenes reales."
    )
    print(
        "NO usa Gmail."
    )

    print()
    print(
        "FDXM_QUANTITY:",
        live_module.QUANTITY
    )

    assert_equal(
        live_module.QUANTITY,
        2,
        "FDXM_QUANTITY"
    )

    # +2 -> 0 -> -2
    run_switch(
        "TEST 1 | LARGO -> CORTO | +2 -> 0 -> -2",
        2,
        [
            CLOSE_LONG,
            OPEN_SHORT,
        ],
        -2
    )

    # -2 -> 0 -> +2
    run_switch(
        "TEST 2 | CORTO -> LARGO | -2 -> 0 -> +2",
        -2,
        [
            CLOSE_SHORT,
            OPEN_LONG,
        ],
        2
    )

    print()
    print(
        "========================================"
    )
    print(
        "TODAS LAS TRANSICIONES QUANTITY=2: OK"
    )
    print(
        "========================================"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
