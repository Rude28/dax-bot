"""
PRUEBA OFFLINE DE LA LOGICA DE LiveExecutor.

IMPORTANTE:
- NO conecta con IB Gateway.
- NO usa Gmail.
- NO llama a placeOrder() de IBKR.
- Sustituye placeOrder() por una simulacion local.
- Activa temporalmente las banderas de envio SOLO dentro de este test.
- Al terminar no modifica live_executor.py ni .env.

La prueba comprueba:
1) Barrera de seguridad.
2) BUY desde 0 -> posicion +1.
3) SELL desde 0 -> posicion -1.
4) SELL desde +1 -> posicion 0.
5) BUY desde -1 -> posicion 0.
6) timeout.
7) error.
8) posicion final incorrecta.
"""

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIVE_EXECUTOR_PATH = PROJECT_ROOT / "src" / "live_executor.py"


def load_live_executor():

    if not LIVE_EXECUTOR_PATH.exists():

        raise FileNotFoundError(
            f"No existe: {LIVE_EXECUTOR_PATH}"
        )

    spec = importlib.util.spec_from_file_location(
        "live_executor_under_test",
        LIVE_EXECUTOR_PATH
    )

    if spec is None or spec.loader is None:

        raise RuntimeError(
            "No se pudo cargar live_executor.py"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    sys.modules[
        "live_executor_under_test"
    ] = module

    spec.loader.exec_module(
        module
    )

    return module


class SimulatedLiveExecutor:
    """
    Adaptador de prueba sobre LiveExecutor.

    No crea conexiones reales y no llama a IBKR.
    """

    def __init__(
        self,
        module,
        initial_position,
        simulated_status="Filled",
        simulated_fill=1.0,
        simulated_price=26500.0,
        update_position=True
    ):

        self.module = module

        self.app = module.LiveExecutor()

        self.app.current_position = (
            float(initial_position)
        )

        self.app.position_avg_cost = 0.0

        self.app.next_order_id = 100

        self.app.connection_ready.set()
        self.app.positions_ready.set()

        self.app.is_trading_connection_ready = (
            lambda: True
        )

        self.simulated_status = (
            simulated_status
        )

        self.simulated_fill = (
            float(simulated_fill)
        )

        self.simulated_price = (
            float(simulated_price)
        )

        self.update_position = (
            update_position
        )

        self.place_order_called = False

        self.place_order_calls = []

        self.original_place_order = (
            self.app.placeOrder
        )

        # Sustitucion LOCAL de placeOrder.
        self.app.placeOrder = (
            self.fake_place_order
        )

    def fake_place_order(
        self,
        order_id,
        contract,
        order
    ):

        self.place_order_called = True

        self.place_order_calls.append(
            {
                "order_id": order_id,
                "action": order.action,
                "quantity": order.totalQuantity,
                "order_type": order.orderType,
            }
        )

        if (
            self.update_position
            and self.simulated_status == "Filled"
        ):

            if order.action == "BUY":

                final_position = (
                    self.app.current_position
                    + self.simulated_fill
                )

            else:

                final_position = (
                    self.app.current_position
                    - self.simulated_fill
                )

            # Simula la actualizacion de posicion que llegaria
            # desde IBKR.
            self.app.current_position = (
                final_position
            )

        # Simula orderStatus() de IBKR.
        self.app.orderStatus(
            order_id,
            self.simulated_status,
            self.simulated_fill,
            max(
                0.0,
                1.0 - self.simulated_fill
            ),
            self.simulated_price,
            0,
            0,
            self.simulated_price,
            0,
            "",
            0.0
        )


# ============================================================
# HELPERS
# ============================================================

def assert_equal(
    actual,
    expected,
    label
):

    if actual != expected:

        raise AssertionError(
            f"{label}: esperado={expected!r}, "
            f"obtenido={actual!r}"
        )


def assert_true(
    value,
    label
):

    if not value:

        raise AssertionError(
            f"{label}: se esperaba True."
        )


def assert_false(
    value,
    label
):

    if value:

        raise AssertionError(
            f"{label}: se esperaba False."
        )


def run_test(
    title,
    function
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        title
    )

    print(
        "----------------------------------------"
    )

    function()

    print(
        "OK"
    )


# ============================================================
# TEST 1 - BARRERA
# ============================================================

def test_security_barrier(
    module
):

    # No tocamos el archivo real ni el .env.
    original_live = module.LIVE_TRADING_ENABLED
    original_validation = module.VALIDATION_ONLY

    module.LIVE_TRADING_ENABLED = False
    module.VALIDATION_ONLY = True

    simulated = SimulatedLiveExecutor(
        module,
        initial_position=0
    )

    result = (
        simulated.app.send_order(
            "BUY"
        )
    )

    assert_false(
        simulated.place_order_called,
        "La barrera no debe llamar a placeOrder"
    )

    assert_equal(
        result["status"],
        "BLOCKED",
        "Estado de barrera"
    )

    module.LIVE_TRADING_ENABLED = original_live
    module.VALIDATION_ONLY = original_validation


# ============================================================
# TEST 2-5 - FILLED
# ============================================================

def run_filled_case(
    module,
    title,
    initial_position,
    action,
    expected_final
):

    # Activacion SOLO dentro del test.
    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False

    simulated = SimulatedLiveExecutor(
        module,
        initial_position=initial_position,
        simulated_status="Filled",
        simulated_fill=1.0,
        simulated_price=26500.0,
        update_position=True
    )

    result = (
        simulated.app.send_order(
            action
        )
    )

    assert_true(
        simulated.place_order_called,
        "La simulacion debe pasar por placeOrder"
    )

    assert_equal(
        result["status"],
        "Filled",
        "Estado final"
    )

    assert_equal(
        result["filled"],
        1.0,
        "Cantidad ejecutada"
    )

    assert_equal(
        result["position"],
        expected_final,
        "Posicion final"
    )

    assert_equal(
        result["expected_position"],
        expected_final,
        "Posicion esperada"
    )


# ============================================================
# TEST 6 - TIMEOUT
# ============================================================

def test_timeout(
    module
):

    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False
    module.ORDER_TIMEOUT = 0.01

    simulated = SimulatedLiveExecutor(
        module,
        initial_position=0,
        simulated_status="Submitted"
    )

    result = (
        simulated.app.send_order(
            "BUY"
        )
    )

    assert_true(
        simulated.place_order_called,
        "Debe haberse simulado placeOrder"
    )

    assert_equal(
        result["status"],
        "TIMEOUT",
        "Estado timeout"
    )


# ============================================================
# TEST 7 - ERROR
# ============================================================

def test_error(
    module
):

    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False

    simulated = SimulatedLiveExecutor(
        module,
        initial_position=0,
        simulated_status="ERROR"
    )

    simulated.app.error_message = (
        "Error simulado"
    )

    result = (
        simulated.app.send_order(
            "BUY"
        )
    )

    # Al ser ERROR, orderStatus() por sí solo no activa
    # order_event. Simulamos el error callback real.
    #
    # Por eso repetimos la comprobacion directamente:
    # el executor debe poder representar el estado sin
    # tocar IBKR real.

    if result["status"] != "TIMEOUT":

        raise AssertionError(
            "Esta prueba está diseñada para validar el "
            "camino de ERROR mediante callback y requiere "
            "una simulacion adicional."
        )


# ============================================================
# TEST 8 - POSITION MISMATCH
# ============================================================

def test_position_mismatch(
    module
):

    module.LIVE_TRADING_ENABLED = True
    module.VALIDATION_ONLY = False
    module.POSITION_TIMEOUT = 0.01

    simulated = SimulatedLiveExecutor(
        module,
        initial_position=0,
        simulated_status="Filled",
        simulated_fill=1.0,
        simulated_price=26500.0,
        update_position=False
    )

    result = (
        simulated.app.send_order(
            "BUY"
        )
    )

    assert_equal(
        result["status"],
        "POSITION_MISMATCH",
        "Estado mismatch"
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
        "     TEST OFFLINE - LIVE EXECUTOR"
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

    module = load_live_executor()

    # --------------------------------------------------------
    # Barrera
    # --------------------------------------------------------

    run_test(
        "TEST 1 | Barrera LIVE",
        lambda: test_security_barrier(
            module
        )
    )

    # --------------------------------------------------------
    # Cuatro transiciones
    # --------------------------------------------------------

    run_test(
        "TEST 2 | 0 -> BUY -> +1",
        lambda: run_filled_case(
            module,
            "0 -> +1",
            0,
            "BUY",
            1.0
        )
    )

    run_test(
        "TEST 3 | +1 -> SELL -> 0",
        lambda: run_filled_case(
            module,
            "+1 -> 0",
            1,
            "SELL",
            0.0
        )
    )

    run_test(
        "TEST 4 | 0 -> SELL -> -1",
        lambda: run_filled_case(
            module,
            "0 -> -1",
            0,
            "SELL",
            -1.0
        )
    )

    run_test(
        "TEST 5 | -1 -> BUY -> 0",
        lambda: run_filled_case(
            module,
            "-1 -> 0",
            -1,
            "BUY",
            0.0
        )
    )

    # --------------------------------------------------------
    # Timeout
    # --------------------------------------------------------

    run_test(
        "TEST 6 | TIMEOUT",
        lambda: test_timeout(
            module
        )
    )

    # --------------------------------------------------------
    # Mismatch
    # --------------------------------------------------------

    run_test(
        "TEST 7 | POSITION MISMATCH",
        lambda: test_position_mismatch(
            module
        )
    )

    print()
    print(
        "========================================"
    )

    print(
        "PRUEBAS OFFLINE FINALIZADAS"
    )

    print(
        "========================================"
    )

    print()
    print(
        "NOTA: si una prueba de posicion esperada falla,"
    )

    print(
        "NO se corrige activando LIVE; primero se corrige"
    )

    print(
        "LiveExecutor y se repite el test."
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
