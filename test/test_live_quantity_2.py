"""
TEST OFFLINE DE CANTIDAD CONFIGURABLE PARA LIVE.

No conecta con IB Gateway.
No usa Gmail.
No envia ordenes reales.

Objetivo:
- Verificar FDXM_QUANTITY=2.
- Verificar que LiveExecutor usa 2 contratos.
- Verificar que SignalExecutor calcula correctamente las posiciones.
- Verificar las cuatro acciones y las dos transiciones.
"""

import importlib.util
import os
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def load_module(name, filename):

    path = SRC / filename

    spec = importlib.util.spec_from_file_location(
        name,
        path
    )

    if spec is None or spec.loader is None:

        raise RuntimeError(
            f"No se pudo cargar {path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    sys.modules[name] = module

    spec.loader.exec_module(
        module
    )

    return module


# ============================================================
# ASSERTS
# ============================================================

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


def run_test(title, fn):

    print()
    print(
        "----------------------------------------"
    )

    print(title)

    print(
        "----------------------------------------"
    )

    fn()

    print("OK")


# ============================================================
# EXECUTOR SIMULADO
# ============================================================

class SimulatedExecutor:

    def __init__(
        self,
        live_module,
        initial_position=0
    ):

        self.live_module = live_module

        self.app = (
            live_module.LiveExecutor()
        )

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

        self.app.placeOrder = (
            self.fake_place_order
        )

        self.place_order_calls = []

        self.app_order_quantity = (
            self.app.order_quantity
        )

    def fake_place_order(
        self,
        order_id,
        contract,
        order
    ):

        self.place_order_calls.append(
            {
                "order_id": order_id,
                "action": order.action,
                "quantity": order.totalQuantity,
                "order_type": order.orderType
            }
        )

        old_position = (
            self.app.current_position
        )

        if order.action == "BUY":

            new_position = (
                old_position
                + float(order.totalQuantity)
            )

        else:

            new_position = (
                old_position
                - float(order.totalQuantity)
            )

        def update_position():

            time.sleep(0.01)

            self.app.current_position = (
                new_position
            )

            self.app.position_update_event.set()

        threading.Thread(
            target=update_position,
            daemon=True
        ).start()

        self.app.orderStatus(
            order_id,
            "Filled",
            float(order.totalQuantity),
            0.0,
            26500.0,
            0,
            0,
            26500.0,
            0,
            "",
            0.0
        )


# ============================================================
# TEST 1
# ============================================================

def test_quantity_configuration(live):

    assert_equal(
        live.QUANTITY,
        2,
        "QUANTITY de LiveExecutor"
    )

    app = live.LiveExecutor()

    assert_equal(
        app.order_quantity,
        2,
        "order_quantity de LiveExecutor"
    )


# ============================================================
# TEST 2-5
# ============================================================

def run_order_case(
    live,
    title,
    initial_position,
    action,
    expected_position
):

    simulated = (
        SimulatedExecutor(
            live,
            initial_position
        )
    )

    result = (
        simulated.app.send_order(
            action
        )
    )

    assert_equal(
        result["status"],
        "Filled",
        "Estado"
    )

    assert_equal(
        result["filled"],
        2.0,
        "Cantidad ejecutada"
    )

    assert_equal(
        result["position"],
        expected_position,
        "Posición final"
    )

    assert_equal(
        result["expected_position"],
        expected_position,
        "Posición esperada"
    )

    assert_equal(
        simulated.place_order_calls[0]["quantity"],
        2,
        "Cantidad enviada a placeOrder"
    )


# ============================================================
# TEST 6
# ============================================================

def test_signal_executor_calculation(
    signal_module,
    simulated_executor
):

    signal_executor = (
        signal_module.SignalExecutor(
            simulated_executor.app,
            None
        )
    )

    cases = [
        (
            0.0,
            ["ABRIR_LARGO"],
            2.0
        ),
        (
            2.0,
            ["CERRAR_LARGO"],
            0.0
        ),
        (
            0.0,
            ["ABRIR_CORTO"],
            -2.0
        ),
        (
            -2.0,
            ["CERRAR_CORTO"],
            0.0
        ),
        (
            2.0,
            [
                "CERRAR_LARGO",
                "ABRIR_CORTO"
            ],
            -2.0
        ),
        (
            -2.0,
            [
                "CERRAR_CORTO",
                "ABRIR_LARGO"
            ],
            2.0
        ),
    ]

    for initial, actions, expected in cases:

        result = (
            signal_executor
            ._calculate_final_position(
                initial,
                actions
            )
        )

        assert_equal(
            result,
            expected,
            f"{initial} + {actions}"
        )


# ============================================================
# TEST 7
# ============================================================

def test_open_close_helpers(
    live
):

    # 0 -> +2
    sim = SimulatedExecutor(
        live,
        0
    )

    result = (
        sim.app.open_long()
    )

    assert_equal(
        result["status"],
        "Filled",
        "open_long"
    )

    assert_equal(
        sim.app.get_position(),
        2.0,
        "posición después de open_long"
    )

    # +2 -> 0
    result = (
        sim.app.close_position()
    )

    assert_equal(
        result["status"],
        "Filled",
        "close_position largo"
    )

    assert_equal(
        sim.app.get_position(),
        0.0,
        "posición después de cerrar largo"
    )

    # 0 -> -2
    sim = SimulatedExecutor(
        live,
        0
    )

    result = (
        sim.app.open_short()
    )

    assert_equal(
        result["status"],
        "Filled",
        "open_short"
    )

    assert_equal(
        sim.app.get_position(),
        -2.0,
        "posición después de open_short"
    )

    # -2 -> 0
    result = (
        sim.app.close_position()
    )

    assert_equal(
        result["status"],
        "Filled",
        "close_position corto"
    )

    assert_equal(
        sim.app.get_position(),
        0.0,
        "posición después de cerrar corto"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "========================================"
    )

    print(
        " TEST OFFLINE - FDXM QUANTITY = 2"
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

    # --------------------------------------------------------
    # Cargar módulos después de establecer la variable.
    # --------------------------------------------------------

    os.environ["FDXM_QUANTITY"] = "2"

    live = load_module(
        "live_executor_quantity_test",
        "live_executor.py"
    )

    signal_module = load_module(
        "signal_executor_quantity_test",
        "signal_executor.py"
    )

    run_test(
        "TEST 1 | Cantidad configurada = 2",
        lambda: test_quantity_configuration(
            live
        )
    )

    run_test(
        "TEST 2 | 0 -> BUY 2 -> +2",
        lambda: run_order_case(
            live,
            "0 -> +2",
            0,
            "BUY",
            2.0
        )
    )

    run_test(
        "TEST 3 | +2 -> SELL 2 -> 0",
        lambda: run_order_case(
            live,
            "+2 -> 0",
            2,
            "SELL",
            0.0
        )
    )

    run_test(
        "TEST 4 | 0 -> SELL 2 -> -2",
        lambda: run_order_case(
            live,
            "0 -> -2",
            0,
            "SELL",
            -2.0
        )
    )

    run_test(
        "TEST 5 | -2 -> BUY 2 -> 0",
        lambda: run_order_case(
            live,
            "-2 -> 0",
            -2,
            "BUY",
            0.0
        )
    )

    simulated = SimulatedExecutor(
        live,
        0
    )

    run_test(
        "TEST 6 | SignalExecutor posiciones esperadas",
        lambda: test_signal_executor_calculation(
            signal_module,
            simulated
        )
    )

    run_test(
        "TEST 7 | open/close helpers con 2 contratos",
        lambda: test_open_close_helpers(
            live
        )
    )

    print()
    print(
        "========================================"
    )

    print(
        "TODAS LAS PRUEBAS QUANTITY=2: OK"
    )

    print(
        "========================================"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
