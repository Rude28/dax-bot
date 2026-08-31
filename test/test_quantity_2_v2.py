"""
TEST OFFLINE DE FDXM_QUANTITY=2

IMPORTANTE:
- NO conecta con IB Gateway.
- NO usa Gmail.
- NO envia ninguna orden real.
- No modifica .env.
- No modifica los archivos de src.

Se ejecuta desde la raiz del proyecto con:
    python test\test_quantity_2_v2.py
"""

import os
import sys
import threading
import time
from pathlib import Path


# ============================================================
# RUTAS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Este test se ejecuta como archivo dentro de test\, por lo que
# Python no añade src\ automáticamente. Lo hacemos ANTES de
# importar los módulos del proyecto.
sys.path.insert(0, str(SRC))

# La variable debe existir ANTES de importar live_executor,
# porque QUANTITY se lee al cargar el módulo.
os.environ["FDXM_QUANTITY"] = "2"


# ============================================================
# IMPORTS NORMALES DEL PROYECTO
# ============================================================

from live_executor import (  # noqa: E402
    LiveExecutor,
)

from signal_executor import (  # noqa: E402
    SignalExecutor,
    OPEN_LONG,
    CLOSE_LONG,
    OPEN_SHORT,
    CLOSE_SHORT,
)


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

class FakeLive:

    def __init__(
        self,
        initial_position
    ):

        self.app = LiveExecutor()

        self.app.current_position = float(
            initial_position
        )

        self.app.position_avg_cost = 0.0
        self.app.next_order_id = 100

        # Simular un executor completamente preparado.
        self.app.connection_ready.set()
        self.app.positions_ready.set()

        self.app.is_trading_connection_ready = (
            lambda: True
        )

        self.calls = []

        # Nunca sale hacia IBKR.
        self.app.placeOrder = (
            self._fake_place_order
        )

    def _fake_place_order(
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
                "order_type": order.orderType,
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
                f"Acción simulada inválida: "
                f"{order.action}"
            )

        # En IBKR real el cambio de posición puede llegar
        # asíncronamente después del Filled.
        def update_position():

            time.sleep(0.02)

            self.app.current_position = (
                new_position
            )

            self.app.position_update_event.set()

        threading.Thread(
            target=update_position,
            daemon=True
        ).start()

        # Simular Filled.
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


# ============================================================
# TEST 1
# ============================================================

def test_configuration():

    assert_equal(
        LiveExecutor.__module__,
        "live_executor",
        "Import de LiveExecutor"
    )

    app = LiveExecutor()

    assert_equal(
        app.order_quantity,
        2,
        "Cantidad configurada"
    )


# ============================================================
# TEST 2-5
# ============================================================

def test_order_case(
    initial_position,
    action,
    expected_position
):

    fake = FakeLive(
        initial_position
    )

    # Activación SOLO dentro del test. No toca .env.
    module = sys.modules["live_executor"]

    old_enabled = (
        module.LIVE_TRADING_ENABLED
    )

    old_validation = (
        module.VALIDATION_ONLY
    )

    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False

    try:

        result = (
            fake.app.send_order(
                action
            )
        )

    finally:

        module.LIVE_TRADING_ENABLED = (
            old_enabled
        )

        module.VALIDATION_ONLY = (
            old_validation
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
        len(fake.calls),
        1,
        "Número de placeOrder simulados"
    )

    assert_equal(
        fake.calls[0]["quantity"],
        2,
        "Cantidad enviada"
    )


# ============================================================
# TEST 6
# ============================================================

def test_signal_calculation():

    fake = FakeLive(0)

    signal_executor = SignalExecutor(
        fake.app,
        None
    )

    cases = [
        (
            0,
            [OPEN_LONG],
            2
        ),
        (
            2,
            [CLOSE_LONG],
            0
        ),
        (
            0,
            [OPEN_SHORT],
            -2
        ),
        (
            -2,
            [CLOSE_SHORT],
            0
        ),
        (
            2,
            [CLOSE_LONG, OPEN_SHORT],
            -2
        ),
        (
            -2,
            [CLOSE_SHORT, OPEN_LONG],
            2
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
            (
                f"Calculando {initial} "
                f"con {actions}"
            )
        )


# ============================================================
# TEST 7
# ============================================================

def test_helpers():

    module = sys.modules["live_executor"]

    old_enabled = (
        module.LIVE_TRADING_ENABLED
    )

    old_validation = (
        module.VALIDATION_ONLY
    )

    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False

    try:

        # 0 -> +2
        fake = FakeLive(0)

        result = fake.app.open_long()

        assert_equal(
            result["status"],
            "Filled",
            "open_long"
        )

        assert_equal(
            fake.app.get_position(),
            2.0,
            "posición tras open_long"
        )

        # +2 -> 0
        result = (
            fake.app.close_position()
        )

        assert_equal(
            result["status"],
            "Filled",
            "close_position largo"
        )

        assert_equal(
            fake.app.get_position(),
            0.0,
            "posición tras cerrar largo"
        )

        # 0 -> -2
        fake = FakeLive(0)

        result = fake.app.open_short()

        assert_equal(
            result["status"],
            "Filled",
            "open_short"
        )

        assert_equal(
            fake.app.get_position(),
            -2.0,
            "posición tras open_short"
        )

        # -2 -> 0
        result = (
            fake.app.close_position()
        )

        assert_equal(
            result["status"],
            "Filled",
            "close_position corto"
        )

        assert_equal(
            fake.app.get_position(),
            0.0,
            "posición tras cerrar corto"
        )

    finally:

        module.LIVE_TRADING_ENABLED = (
            old_enabled
        )

        module.VALIDATION_ONLY = (
            old_validation
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

    print()
    print(
        f"ROOT: {ROOT}"
    )
    print(
        f"SRC:  {SRC}"
    )
    print(
        f"FDXM_QUANTITY: {os.environ['FDXM_QUANTITY']}"
    )

    run_test(
        "TEST 1 | Cantidad configurada = 2",
        test_configuration
    )

    run_test(
        "TEST 2 | 0 -> BUY 2 -> +2",
        lambda: test_order_case(
            0,
            "BUY",
            2
        )
    )

    run_test(
        "TEST 3 | +2 -> SELL 2 -> 0",
        lambda: test_order_case(
            2,
            "SELL",
            0
        )
    )

    run_test(
        "TEST 4 | 0 -> SELL 2 -> -2",
        lambda: test_order_case(
            0,
            "SELL",
            -2
        )
    )

    run_test(
        "TEST 5 | -2 -> BUY 2 -> 0",
        lambda: test_order_case(
            -2,
            "BUY",
            0
        )
    )

    run_test(
        "TEST 6 | SignalExecutor posiciones",
        test_signal_calculation
    )

    run_test(
        "TEST 7 | open/close helpers",
        test_helpers
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
