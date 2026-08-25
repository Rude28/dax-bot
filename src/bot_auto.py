import imaplib
import os
import threading
import time

from dotenv import load_dotenv

from email_reader import (
    get_unread_signal_emails,
    process_email,
)

from paper_executor import PaperExecutor

from signal_executor import SignalExecutor

from signal_state import (
    SignalState,
    NEW,
    PROCESSING,
    SUCCESS,
    FAILED,
    PARTIAL,
    REJECTED,
    SignalStateError,
)

from notifier import send_notification

from logger import (
    log_info,
    log_warning,
    log_error,
)

from bot_state import (
    bot_state,
    STARTING,
    CONNECTED,
    READY,
    PROCESSING_SIGNAL,
    RECONNECTING_IBKR,
    RECONNECTING_GMAIL,
    SAFETY_LOCK,
    STOPPING,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()


# ============================================================
# GMAIL
# ============================================================

GMAIL_USER = os.getenv(
    "GMAIL_USER"
)

GMAIL_APP_PASSWORD = os.getenv(
    "GMAIL_APP_PASSWORD"
)

IMAP_SERVER = os.getenv(
    "IMAP_SERVER",
    "imap.gmail.com"
)

IMAP_PORT = int(
    os.getenv(
        "IMAP_PORT",
        "993"
    )
)


# ============================================================
# IBKR
# ============================================================

IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 4


# ============================================================
# PROVEEDOR DE SEÑALES
# ============================================================

SIGNAL_SENDER = (
    "operativadax@gmail.com"
)


# ============================================================
# INTERVALO DE COMPROBACIÓN
# ============================================================

CHECK_INTERVAL = 10
IBKR_RECONNECT_INTERVAL = 5
IBKR_RECONNECT_TIMEOUT = 10
GMAIL_RECONNECT_INTERVAL = 5
GMAIL_RECONNECT_TIMEOUT = 10


# ============================================================
# ESTADO
# ============================================================

state_manager = SignalState()

bot_state.mark_started()
bot_state.set_status(STARTING)


# ============================================================
# CONECTAR IBKR
# ============================================================

def create_ib_executor():

    bot_state.set_status(STARTING)
    bot_state.set_ibkr_connected(False)

    print()
    print(
        "========================================"
    )

    print(
        "CONECTANDO CON IB GATEWAY PAPER"
    )

    print(
        "========================================"
    )

    app = PaperExecutor()

    app.connect(
        IB_HOST,
        IB_PORT,
        IB_CLIENT_ID
    )

    api_thread = threading.Thread(
        target=app.run,
        daemon=True
    )

    api_thread.start()

    if not app.connection_ready.wait(
        timeout=10
    ):

        log_error(
            "No se pudo conectar con IB Gateway."
        )

        print()
        print(
            "ERROR: no se pudo conectar "
            "con IB Gateway."
        )

        app.disconnect()

        return None

    print(
        "Conexión IBKR establecida."
    )

    log_info(
        "Conexión con IBKR establecida."
    )

    bot_state.set_ibkr_connected(True)
    bot_state.set_status(CONNECTED)

    print(
        "Esperando posiciones iniciales..."
    )

    if not app.positions_ready.wait(
        timeout=10
    ):

        log_error(
            "No se recibieron las posiciones iniciales de IBKR."
        )

        print()
        print(
            "ERROR: no se recibieron "
            "las posiciones."
        )

        app.disconnect()

        return None

    print()
    print(
        "IBKR preparado correctamente."
    )

    print(
        f"Posición FDXM: "
        f"{app.get_position()}"
    )

    log_info(
        f"Posición inicial FDXM: "
        f"{app.get_position()}"
    )

    bot_state.set_position(app.get_position())

    return app


# ============================================================
# GMAIL
# ============================================================

def create_mail_connection():

    print()
    print(
        "========================================"
    )

    print(
        "CONECTANDO CON GMAIL"
    )

    print(
        "========================================"
    )

    mail = imaplib.IMAP4_SSL(
        IMAP_SERVER,
        IMAP_PORT
    )

    mail.login(
        GMAIL_USER,
        GMAIL_APP_PASSWORD
    )

    status, _ = mail.select(
        "INBOX"
    )

    if status != "OK":

        raise RuntimeError(
            "No se pudo abrir INBOX."
        )

    print(
        "Gmail preparado correctamente."
    )

    log_info(
        "Conexión Gmail establecida."
    )

    bot_state.set_gmail_connected(True)

    return mail


# ============================================================
# RECONEXIÓN GMAIL
# ============================================================

def reconnect_gmail(
    mail,
    ib_app
):
    """
    Recupera la conexión IMAP de Gmail de forma segura.

    Durante la reconexión no se procesan señales.
    Se crea una conexión nueva, se autentica y se selecciona INBOX
    antes de volver al estado READY.
    """

    attempt = 0

    while True:

        attempt += 1

        bot_state.set_status(
            RECONNECTING_GMAIL
        )

        bot_state.set_gmail_connected(
            False
        )

        print()
        print(
            "========================================"
        )
        print(
            "RECONEXIÓN GMAIL"
        )
        print(
            f"Intento: {attempt}"
        )
        print(
            "========================================"
        )

        log_warning(
            f"Intentando reconectar Gmail | Intento={attempt}"
        )

        try:

            if mail is not None:

                try:
                    mail.logout()
                except Exception:
                    pass

            new_mail = imaplib.IMAP4_SSL(
                IMAP_SERVER,
                IMAP_PORT,
                timeout=GMAIL_RECONNECT_TIMEOUT
            )

            new_mail.login(
                GMAIL_USER,
                GMAIL_APP_PASSWORD
            )

            status, _ = new_mail.select(
                "INBOX"
            )

            if status != "OK":
                raise RuntimeError(
                    "No se pudo abrir INBOX tras reconectar Gmail."
                )

            # Verificación explícita de que IMAP responde.
            noop_status, _ = new_mail.noop()

            if noop_status != "OK":
                raise RuntimeError(
                    "Gmail respondió incorrectamente al NOOP."
                )

            bot_state.set_gmail_connected(True)

            # Antes de READY comprobamos que IBKR sigue conectado.
            if not ib_app.is_trading_connection_ready():

                log_warning(
                    "Gmail reconectado pero IBKR no está conectado. Se mantiene estado de reconexión."
                )

                try:
                    new_mail.logout()
                except Exception:
                    pass

                bot_state.set_gmail_connected(False)
                time.sleep(GMAIL_RECONNECT_INTERVAL)
                continue

            # Si existe PROCESSING, no reanudamos directamente la lectura
            # de nuevas señales. Primero reconciliamos.
            processing = state_manager.get_processing_signals()

            if processing:

                print()
                print(
                    "PROCESSING DETECTADO TRAS RECONEXIÓN DE GMAIL."
                )

                log_warning(
                    f"PROCESSING tras reconexión Gmail | Cantidad={len(processing)}"
                )

                if not reconcile_processing_signals(
                    ib_app,
                    new_mail
                ):

                    bot_state.set_status(
                        SAFETY_LOCK
                    )

                    log_error(
                        "No se pudo reconciliar PROCESSING tras reconexión Gmail."
                    )

                    return None

            bot_state.set_position(
                ib_app.get_position()
            )

            bot_state.set_status(
                READY
            )

            log_info(
                f"Gmail reconectado y validado | Position={ib_app.get_position()}"
            )

            print()
            print(
                "GMAIL RECONECTADO CORRECTAMENTE."
            )

            return new_mail

        except Exception as error:

            bot_state.set_error(
                error
            )

            log_warning(
                f"Error reconectando Gmail | Intento={attempt} | "
                f"{type(error).__name__}: {error}"
            )

            time.sleep(
                GMAIL_RECONNECT_INTERVAL
            )


# ============================================================
# COMPROBAR CONEXIÓN GMAIL
# ============================================================

def ensure_gmail_connection(
    mail,
    ib_app
):
    """Comprueba IMAP y reconecta si la conexión no responde."""

    try:

        status, _ = mail.noop()

        if status != "OK":
            raise RuntimeError(
                "IMAP NOOP devolvió un estado no OK."
            )

        if not ib_app.is_trading_connection_ready():
            return mail

        return mail

    except Exception as error:

        bot_state.set_gmail_connected(False)
        bot_state.set_error(error)
        log_warning(
            f"Gmail desconectado detectado | "
            f"{type(error).__name__}: {error}"
        )

        print()
        print(
            "GMAIL DESCONECTADO."
        )
        print(
            "No se procesarán señales hasta reconectar."
        )

        return reconnect_gmail(
            mail,
            ib_app
        )


# ============================================================
# RECONEXIÓN IBKR
# ============================================================

def reconnect_ibkr(
    app,
    mail
):
    """
    Intenta recuperar la conexión IBKR de forma segura.

    No permite nuevas órdenes durante la reconexión.
    Después de reconectar:
        1. obtiene un nuevo Order ID;
        2. solicita posiciones reales;
        3. comprueba PROCESSING;
        4. reconcilia si es necesario;
        5. solo entonces vuelve a READY.
    """

    attempt = 0

    while True:

        attempt += 1

        bot_state.set_status(
            RECONNECTING_IBKR
        )

        bot_state.set_ibkr_connected(
            False
        )

        print()
        print(
            "========================================"
        )
        print(
            "RECONEXIÓN IBKR"
        )
        print(
            f"Intento: {attempt}"
        )
        print(
            "========================================"
        )

        log_warning(
            f"Intentando reconectar IBKR | Intento={attempt}"
        )

        try:

            try:
                app.disconnect()
            except Exception:
                pass

            app.connection_ready.clear()
            app.positions_ready.clear()
            app.connection_lost.clear()

            app.connect(
                IB_HOST,
                IB_PORT,
                IB_CLIENT_ID
            )

            api_thread = threading.Thread(
                target=app.run,
                daemon=True
            )

            app.api_thread = api_thread
            api_thread.start()

            connected = app.connection_ready.wait(
                timeout=IBKR_RECONNECT_TIMEOUT
            )

            if not connected:

                log_warning(
                    f"Reconexión IBKR sin conexión | Intento={attempt}"
                )

                time.sleep(
                    IBKR_RECONNECT_INTERVAL
                )

                continue

            bot_state.set_ibkr_connected(
                True
            )

            if not app.positions_ready.wait(
                timeout=IBKR_RECONNECT_TIMEOUT
            ):

                log_warning(
                    f"Reconexión IBKR sin posiciones iniciales | Intento={attempt}"
                )

                try:
                    app.disconnect()
                except Exception:
                    pass

                time.sleep(
                    IBKR_RECONNECT_INTERVAL
                )

                continue

            current_position = (
                app.get_position()
            )

            bot_state.set_position(
                current_position
            )

            print()
            print(
                "IBKR RECONECTADO CORRECTAMENTE."
            )
            print(
                f"Posición FDXM: {current_position}"
            )

            log_info(
                f"IBKR reconectado | "
                f"Position={current_position} | "
                f"NextOrderID={app.next_order_id}"
            )

            # ------------------------------------------------
            # Reconciliar cualquier PROCESSING antes de volver
            # a permitir operaciones.
            # ------------------------------------------------

            processing = (
                state_manager
                .get_processing_signals()
            )

            if processing:

                print()
                print(
                    "PROCESSING DETECTADO TRAS RECONEXIÓN."
                )

                log_warning(
                    f"PROCESSING tras reconexión | "
                    f"Cantidad={len(processing)}"
                )

                if not reconcile_processing_signals(
                    app,
                    mail
                ):

                    bot_state.set_status(
                        SAFETY_LOCK
                    )

                    log_error(
                        "No se pudo reconciliar PROCESSING tras reconexión."
                    )

                    return False

            bot_state.set_status(
                READY
            )

            log_info(
                "IBKR reconectado y validado. Estado READY."
            )

            return True

        except Exception as error:

            bot_state.set_error(
                error
            )

            log_error(
                f"Error durante reconexión IBKR | "
                f"Intento={attempt} | "
                f"{type(error).__name__}: {error}"
            )

            time.sleep(
                IBKR_RECONNECT_INTERVAL
            )


# ============================================================
# MARCAR LEÍDO
# ============================================================

def mark_as_read(
    mail,
    email_uid
):

    try:

        status, _ = mail.uid(
            "store",
            email_uid,
            "+FLAGS",
            "\\Seen"
        )

        if status == "OK":

            print(
                "Correo marcado como LEÍDO."
            )

            return True

        print(
            "No se pudo marcar el correo "
            "como leído."
        )

        log_warning(
            f"No se pudo marcar correo como leído | "
            f"UID={email_uid}"
        )

        return False

    except Exception as error:

        print(
            f"ERROR marcando correo como leído: "
            f"{error}"
        )

        log_error(
            f"Error marcando correo como leído | "
            f"UID={email_uid} | "
            f"{type(error).__name__}: {error}"
        )

        return False


# ============================================================
# CONSTRUIR RESULTADO DE RECUPERACIÓN
# ============================================================

def build_recovered_result(
    message_id,
    state
):

    operations = []

    for operation in state.get(
        "operations",
        []
    ):

        stored_result = operation.get(
            "result"
        )

        if stored_result:

            operations.append(
                stored_result
            )

        else:

            operations.append(
                {
                    "success": False,
                    "signal_action":
                        operation.get(
                            "signal_action"
                        ),
                    "action":
                        operation.get(
                            "action"
                        ),
                    "status":
                        operation.get(
                            "status",
                            "UNKNOWN"
                        ),
                    "filled": 0.0,
                    "price": 0.0,
                    "position":
                        None,
                    "order_id":
                        operation.get(
                            "order_id"
                        ),
                    "error":
                        "Resultado recuperado "
                        "incompleto."
                }
            )

    filled = sum(
        operation.get(
            "filled",
            0.0
        )
        for operation in operations
    )

    price = 0.0

    for operation in reversed(
        operations
    ):

        if operation.get(
            "price"
        ) not in (
            None,
            0,
            0.0
        ):

            price = operation[
                "price"
            ]

            break

    return {

        "success": True,

        "type": (
            "sequence"
            if len(
                state.get(
                    "actions",
                    []
                )
            ) > 1
            else "single"
        ),

        "message_id":
            message_id,

        "email_uid":
            state.get(
                "email_uid"
            ),

        "sender":
            state.get(
                "sender"
            ),

        "date":
            state.get(
                "date"
            ),

        "subject":
            state.get(
                "subject"
            ),

        "actions":
            state.get(
                "actions",
                []
            ),

        "status":
            "FILLED",

        "filled":
            filled,

        "price":
            price,

        "position":
            state.get(
                "position_final"
            ),

        "expected_position":
            state.get(
                "expected_final_position"
            ),

        "error":
            None,

        "operations":
            operations
    }


# ============================================================
# RECONCILIAR PROCESSING
# ============================================================

def reconcile_processing_signals(
    ib_app,
    mail
):
    """
    Revisa las señales que quedaron en PROCESSING.

    Política:

    - orden COMPLETED/Filled y última operación:
        podemos reconstruirla.
    - orden OPEN:
        bloquear.
    - UNKNOWN:
        bloquear.
    - operación intermedia completada:
        bloquear; no reanudamos automáticamente.
    """

    processing_signals = (
        state_manager
        .get_processing_signals()
    )

    if not processing_signals:

        print(
            "No hay señales PROCESSING pendientes."
        )

        log_info(
            "No hay señales PROCESSING pendientes."
        )

        return True

    print()
    print(
        "########################################"
    )

    print(
        "RECUPERACIÓN DE SEÑALES PROCESSING"
    )

    print(
        "########################################"
    )

    log_warning(
        f"Se detectaron {len(processing_signals)} "
        f"señales PROCESSING."
    )

    for message_id, state in (
        processing_signals.items()
    ):

        print()
        print(
            "----------------------------------------"
        )

        print(
            f"Message-ID: {message_id}"
        )

        print(
            f"Asunto: "
            f"{state.get('subject')}"
        )

        print(
            f"Acciones: "
            f"{state.get('actions')}"
        )

        log_info(
            f"Reconciliando PROCESSING | "
            f"Message-ID={message_id} | "
            f"Actions={state.get('actions')}"
        )

        operations = state.get(
            "operations",
            []
        )

        if not operations:

            print(
                "No existe Order ID guardado."
            )

            print(
                "NO es seguro continuar."
            )

            log_error(
                f"PROCESSING sin operaciones guardadas | "
                f"Message-ID={message_id}"
            )

            return False

        # ----------------------------------------------------
        # Buscar operación pendiente.
        # ----------------------------------------------------

        pending_operations = [
            operation
            for operation in operations
            if operation.get(
                "status"
            ) == "PENDING"
        ]

        # ----------------------------------------------------
        # Si no hay pendientes pero quedan acciones, no
        # reanudamos automáticamente.
        # ----------------------------------------------------

        if not pending_operations:

            if len(
                operations
            ) < len(
                state.get(
                    "actions",
                    []
                )
            ):

                print(
                    "La señal quedó a medias entre "
                    "dos operaciones."
                )

                print(
                    "NO se reanudará automáticamente."
                )

                log_error(
                    f"PROCESSING incompleto entre operaciones | "
                    f"Message-ID={message_id}"
                )

                return False

            continue

        # ----------------------------------------------------
        # Debe haber exactamente una orden pendiente.
        # ----------------------------------------------------

        if len(
            pending_operations
        ) != 1:

            print(
                "Existe más de una operación "
                "pendiente."
            )

            print(
                "NO es seguro reconciliar."
            )

            log_error(
                f"Más de una operación pendiente | "
                f"Message-ID={message_id}"
            )

            return False

        pending = (
            pending_operations[0]
        )

        order_id = pending.get(
            "order_id"
        )

        if order_id is None:

            print(
                "PROCESSING sin Order ID."
            )

            print(
                "NO es seguro continuar."
            )

            log_error(
                f"PROCESSING sin Order ID | "
                f"Message-ID={message_id}"
            )

            return False

        # ----------------------------------------------------
        # Consultar IBKR.
        # ----------------------------------------------------

        reconciliation = (
            ib_app.reconcile_order(
                order_id
            )
        )

        source = reconciliation.get(
            "source"
        )

        status = reconciliation.get(
            "status"
        )

        # ----------------------------------------------------
        # Orden abierta.
        # ----------------------------------------------------

        if source == "OPEN":

            print()
            print(
                "ORDEN TODAVÍA ABIERTA."
            )

            print(
                f"Order ID: {order_id}"
            )

            print(
                "BOT BLOQUEADO."
            )

            log_error(
                f"Orden PROCESSING todavía abierta | "
                f"Message-ID={message_id} | "
                f"OrderID={order_id}"
            )

            return False

        # ----------------------------------------------------
        # Orden desconocida.
        # ----------------------------------------------------

        if not reconciliation.get(
            "found",
            False
        ):

            print()
            print(
                "ORDEN NO ENCONTRADA."
            )

            print(
                f"Order ID: {order_id}"
            )

            print(
                "NO podemos asumir que no se ejecutó."
            )

            print(
                "BOT BLOQUEADO."
            )

            log_error(
                f"Orden UNKNOWN durante recuperación | "
                f"Message-ID={message_id} | "
                f"OrderID={order_id}"
            )

            return False

        # ----------------------------------------------------
        # Orden encontrada pero no Filled.
        # ----------------------------------------------------

        if status != "Filled":

            print()
            print(
                f"Orden recuperada con estado: "
                f"{status}"
            )

            print(
                "NO se resolverá automáticamente."
            )

            log_warning(
                f"Orden recuperada no Filled | "
                f"Message-ID={message_id} | "
                f"OrderID={order_id} | "
                f"Status={status}"
            )

            return False

        # ----------------------------------------------------
        # Comprobar cantidad.
        # ----------------------------------------------------

        if reconciliation.get(
            "filled",
            0.0
        ) != 1.0:

            print()
            print(
                "La orden no tiene una ejecución "
                "completa."
            )

            log_error(
                f"Cantidad recuperada incompleta | "
                f"Message-ID={message_id} | "
                f"OrderID={order_id} | "
                f"Filled={reconciliation.get('filled', 0.0)}"
            )

            return False

        # ----------------------------------------------------
        # Actualizar operación.
        # ----------------------------------------------------

        recovered_result = {
            "success": True,
            "signal_action":
                pending.get(
                    "signal_action"
                ),
            "action":
                pending.get(
                    "action"
                ),
            "status": "Filled",
            "filled":
                reconciliation.get(
                    "filled",
                    0.0
                ),
            "price":
                reconciliation.get(
                    "price",
                    0.0
                ),
            "position":
                ib_app.get_position(),
            "expected_position":
                pending.get(
                    "expected_position"
                ),
            "order_id":
                order_id,
            "error":
                None
        }

        operation_index = pending.get(
            "operation_index"
        )

        state_manager.set_operation_result(
            message_id,
            operation_index,
            recovered_result
        )

        log_info(
            f"Operación recuperada | "
            f"Message-ID={message_id} | "
            f"OrderID={order_id} | "
            f"Price={recovered_result.get('price')}"
        )

        refreshed_state = (
            state_manager.get(
                message_id
            )
        )

        # ----------------------------------------------------
        # Solo podemos cerrar automáticamente la recuperación
        # si esa era la última operación.
        # ----------------------------------------------------

        refreshed_operations = (
            refreshed_state.get(
                "operations",
                []
            )
        )

        required_actions = (
            refreshed_state.get(
                "actions",
                []
            )
        )

        if len(
            refreshed_operations
        ) != len(
            required_actions
        ):

            print()
            print(
                "La orden se ha confirmado como Filled,"
            )

            print(
                "pero todavía quedan acciones de la señal."
            )

            print(
                "NO se reanudará automáticamente."
            )

            log_warning(
                f"Recuperación incompleta de secuencia | "
                f"Message-ID={message_id}"
            )

            return False

        expected_final_position = (
            refreshed_state.get(
                "expected_final_position"
            )
        )

        actual_position = (
            ib_app.get_position()
        )

        if (
            expected_final_position
            is None
        ):

            print(
                "No existe posición final esperada."
            )

            log_error(
                f"Sin posición final esperada | "
                f"Message-ID={message_id}"
            )

            return False

        if actual_position != (
            expected_final_position
        ):

            print()
            print(
                "POSITION MISMATCH EN RECUPERACIÓN."
            )

            print(
                f"Esperada: "
                f"{expected_final_position}"
            )

            print(
                f"Real: "
                f"{actual_position}"
            )

            log_error(
                f"POSITION_MISMATCH durante recuperación | "
                f"Message-ID={message_id} | "
                f"Expected={expected_final_position} | "
                f"Actual={actual_position}"
            )

            return False

        # ----------------------------------------------------
        # Recuperación completa.
        # ----------------------------------------------------

        final_result = (
            build_recovered_result(
                message_id,
                refreshed_state
            )
        )

        state_manager.set_status(
            message_id,
            SUCCESS,

            result=final_result,

            position_final=(
                actual_position
            )
        )

        print()
        print(
            "SIGNAL RECUPERADA CORRECTAMENTE."
        )

        print(
            "Estado: SUCCESS"
        )

        log_info(
            f"Señal recuperada correctamente | "
            f"Message-ID={message_id} | "
            f"Estado=SUCCESS | "
            f"Posición={actual_position}"
        )

        # ----------------------------------------------------
        # Notificación.
        # ----------------------------------------------------

        notification_sent = (
            send_notification(
                final_result
            )
        )

        if not notification_sent:

            print(
                "ATENCIÓN: no se pudo enviar "
                "la notificación de recuperación."
            )

            log_warning(
                f"Falló notificación de recuperación | "
                f"Message-ID={message_id}"
            )

        # ----------------------------------------------------
        # Marcar leído.
        # ----------------------------------------------------

        mark_as_read(
            mail,
            refreshed_state[
                "email_uid"
            ]
        )

    print()
    print(
        "Reconciliación PROCESSING completada."
    )

    log_info(
        "Reconciliación PROCESSING completada."
    )

    return True


# ============================================================
# SEÑAL RECHAZADA
# ============================================================

def process_rejected_signal(
    mail,
    signal
):

    result = {

        "success": False,

        "type": "rejected",

        "message_id":
            signal.get(
                "message_id"
            ),

        "email_uid":
            signal.get(
                "email_uid"
            ),

        "sender":
            signal.get(
                "sender"
            ),

        "date":
            signal.get(
                "date"
            ),

        "subject":
            signal.get(
                "subject"
            ),

        "actions":
            [],

        "status":
            "REJECTED",

        "filled":
            0.0,

        "price":
            0.0,

        "position":
            None,

        "error":
            signal.get(
                "error"
            ),

        "operations":
            []
    }

    print()
    print(
        "SEÑAL RECHAZADA."
    )

    log_warning(
        f"Señal REJECTED | "
        f"Message-ID={signal.get('message_id')} | "
        f"Subject={signal.get('subject')}"
    )

    notification_sent = (
        send_notification(
            result
        )
    )

    if not notification_sent:

        print(
            "No se pudo enviar la "
            "notificación de rechazo."
        )

        log_warning(
            f"No se pudo notificar REJECTED | "
            f"Message-ID={signal.get('message_id')}"
        )

    mark_as_read(
        mail,
        signal[
            "email_uid"
        ]
    )


# ============================================================
# SEÑAL VÁLIDA
# ============================================================

def process_valid_signal(
    mail,
    signal,
    signal_executor
):

    message_id = signal[
        "message_id"
    ]

    current_status = (
        state_manager.get_status(
            message_id
        )
    )

    if current_status != NEW:

        print(
            f"Estado actual {current_status}; "
            "no se ejecutará."
        )

        log_warning(
            f"Señal no ejecutada por estado | "
            f"Message-ID={message_id} | "
            f"Status={current_status}"
        )

        return

    # --------------------------------------------------------
    # PROCESSING
    # --------------------------------------------------------

    initial_position = (
        signal_executor
        .ib_app
        .get_position()
    )

    expected_final_position = (
        signal_executor
        ._calculate_final_position(
            initial_position,
            signal[
                "actions"
            ]
        )
    )

    state_manager.set_status(
        message_id,
        PROCESSING,

        email_uid=signal[
            "email_uid"
        ],

        sender=signal[
            "sender"
        ],

        subject=signal[
            "subject"
        ],

        date=signal[
            "date"
        ],

        actions=signal[
            "actions"
        ],

        valid=True,

        position_initial=(
            initial_position
        ),

        expected_final_position=(
            expected_final_position
        ),

        operations=[]
    )

    print()
    print(
        "Estado cambiado a PROCESSING."
    )

    log_info(
        f"Estado PROCESSING | "
        f"Message-ID={message_id} | "
        f"InitialPosition={initial_position} | "
        f"ExpectedFinal={expected_final_position}"
    )

    # --------------------------------------------------------
    # Ejecutar.
    # --------------------------------------------------------

    try:

        result = (
            signal_executor.execute(
                signal
            )
        )

        log_info(
            f"Resultado señal | "
            f"Message-ID={signal.get('message_id')} | "
            f"Resultado={result}"
        )

    except Exception as error:

        log_error(
            f"Error durante ejecución de señal | "
            f"Message-ID={message_id} | "
            f"{type(error).__name__}: {error}"
        )

        result = {
            "success": False,
            "type": "error",
            "message_id":
                signal.get(
                    "message_id"
                ),
            "email_uid":
                signal.get(
                    "email_uid"
                ),
            "sender":
                signal.get(
                    "sender"
                ),
            "date":
                signal.get(
                    "date"
                ),
            "subject":
                signal.get(
                    "subject"
                ),
            "actions":
                signal.get(
                    "actions",
                    []
                ),
            "status":
                "ERROR",
            "filled":
                0.0,
            "price":
                0.0,
            "position":
                signal_executor
                .ib_app
                .get_position(),
            "error":
                str(error),
            "operations":
                []
        }

    print()
    print(
        "RESULTADO:"
    )

    print(
        result
    )

    success = result.get(
        "success",
        False
    )

    operations = result.get(
        "operations",
        []
    )

    # --------------------------------------------------------
    # Estado final.
    # --------------------------------------------------------

    if success:

        final_status = SUCCESS

    elif any(
        operation.get(
            "status"
        ) == "Filled"
        for operation in operations
    ):

        final_status = PARTIAL

    else:

        final_status = FAILED

    # --------------------------------------------------------
    # Guardar.
    # --------------------------------------------------------

    state_manager.set_status(
        message_id,
        final_status,

        email_uid=signal[
            "email_uid"
        ],

        sender=signal[
            "sender"
        ],

        subject=signal[
            "subject"
        ],

        date=signal[
            "date"
        ],

        actions=signal[
            "actions"
        ],

        valid=True,

        result=result,

        position_final=result.get(
            "position"
        ),

        error=result.get(
            "error"
        )
    )

    print()
    print(
        f"Estado guardado: "
        f"{final_status}"
    )

    log_info(
        f"Estado final señal | "
        f"Message-ID={message_id} | "
        f"Estado={final_status} | "
        f"Posición={result.get('position')}"
    )

    # --------------------------------------------------------
    # Notificación.
    # --------------------------------------------------------

    notification_sent = (
        send_notification(
            result
        )
    )

    if not notification_sent:

        print(
            "ATENCIÓN: fallo al enviar "
            "la notificación."
        )

        log_warning(
            f"Fallo notificación | "
            f"Message-ID={message_id}"
        )

    # --------------------------------------------------------
    # Política de correo.
    # --------------------------------------------------------

    if final_status == SUCCESS:

        mark_as_read(
            mail,
            signal[
                "email_uid"
            ]
        )

    else:

        print()
        print(
            "La señal no terminó correctamente."
        )

        print(
            "El correo permanece SIN LEER."
        )

        log_warning(
            f"Correo permanece UNSEEN | "
            f"Message-ID={message_id} | "
            f"Estado={final_status}"
        )


# ============================================================
# PROCESAR CORREO
# ============================================================

def process_signal(
    mail,
    email_uid,
    signal_executor
):

    print()
    print(
        "########################################"
    )

    print(
        "        PROCESANDO CORREO"
    )

    print(
        "########################################"
    )

    signal = process_email(
        mail,
        email_uid
    )

    if signal is not None:

        log_info(
            f"Correo procesado | "
            f"Message-ID={signal.get('message_id')} | "
            f"UID={signal.get('email_uid')} | "
            f"Acciones={signal.get('actions')} | "
            f"Estado={signal.get('status')}"
        )

    if signal is None:

        return

    # --------------------------------------------------------
    # REJECTED
    # --------------------------------------------------------

    if not signal.get(
        "valid",
        False
    ):

        if signal.get(
            "status"
        ) == REJECTED:

            process_rejected_signal(
                mail,
                signal
            )

        return

    # --------------------------------------------------------
    # VALID
    # --------------------------------------------------------

    process_valid_signal(
        mail,
        signal,
        signal_executor
    )


# ============================================================
# RUN
# ============================================================

def run():

    bot_state.mark_started()
    bot_state.set_status(STARTING)

    print()
    print(
        "========================================"
    )

    print(
        "           DAX BOT"
    )

    print(
        "        PAPER TRADING"
    )

    print(
        "========================================"
    )

    log_info(
        "DAX BOT iniciado en modo PAPER."
    )

    # ========================================================
    # IBKR
    # ========================================================

    ib_app = (
        create_ib_executor()
    )

    if ib_app is None:

        log_error(
            "El bot no pudo iniciar porque IBKR no está disponible."
        )

        return

    mail = None

    try:

        # ====================================================
        # GMAIL
        # ====================================================

        mail = (
            create_mail_connection()
        )

        # ====================================================
        # RECONCILIAR PROCESSING
        # ====================================================

        if not reconcile_processing_signals(
            ib_app,
            mail
        ):

            print()
            print(
                "BOT BLOQUEADO POR SEGURIDAD."
            )

            log_error(
                "Bot bloqueado durante reconciliación PROCESSING."
            )

            return

        # ====================================================
        # SIGNAL EXECUTOR
        # ====================================================

        signal_executor = (
            SignalExecutor(
                ib_app,
                state_manager
            )
        )

        print()
        print(
            "========================================"
        )

        print(
            "DAX BOT PREPARADO"
        )

        print(
            "========================================"
        )

        print(
            f"Comprobación cada "
            f"{CHECK_INTERVAL} segundos."
        )

        print()
        print(
            "Protecciones activas:"
        )

        print(
            "  ✓ Duplicados"
        )

        print(
            "  ✓ JSON corrupto"
        )

        print(
            "  ✓ PROCESSING"
        )

        print(
            "  ✓ Order ID persistente"
        )

        print(
            "  ✓ Reconciliación IBKR"
        )

        print(
            "  ✓ Verificación de posición"
        )

        print(
            "  ✓ Procesamiento secuencial"
        )

        bot_state.set_position(ib_app.get_position())
        bot_state.set_status(READY)

        log_info(
            "DAX BOT preparado y listo para recibir señales."
        )

        # ====================================================
        # LOOP
        # ====================================================

        while True:

            try:

                # ------------------------------------------------
                # Reconexión IBKR
                # ------------------------------------------------

                if not ib_app.is_trading_connection_ready():

                    log_warning(
                        "IBKR no está disponible durante el ciclo."
                    )

                    if not reconnect_ibkr(
                        ib_app,
                        mail
                    ):

                        bot_state.set_status(
                            SAFETY_LOCK
                        )

                        return

                # ------------------------------------------------
                # No operar si aparece PROCESSING.
                # ------------------------------------------------

                processing = (
                    state_manager
                    .get_processing_signals()
                )

                if processing:

                    print()
                    print(
                        "SEÑAL PROCESSING DETECTADA."
                    )

                    print(
                        "El bot se detendrá."
                    )

                    log_error(
                        f"Señal PROCESSING detectada durante el ciclo | "
                        f"Cantidad={len(processing)}"
                    )

                    return

                bot_state.set_position(
                    ib_app.get_position()
                )

                # ------------------------------------------------
                # Comprobar Gmail antes de buscar correos.
                # ------------------------------------------------

                mail = ensure_gmail_connection(
                    mail,
                    ib_app
                )

                if mail is None:

                    print()
                    print(
                        "BOT BLOQUEADO POR SEGURIDAD."
                    )

                    bot_state.set_status(
                        SAFETY_LOCK
                    )

                    return

                # ------------------------------------------------
                # Buscar correos.
                # ------------------------------------------------

                try:

                    email_uids = (
                        get_unread_signal_emails(
                            mail
                        )
                    )

                except Exception as error:

                    log_warning(
                        f"Error leyendo Gmail durante ciclo | "
                        f"{type(error).__name__}: {error}"
                    )

                    mail = reconnect_gmail(
                        mail,
                        ib_app
                    )

                    if mail is None:

                        bot_state.set_status(
                            SAFETY_LOCK
                        )

                        return

                    continue

                if not email_uids:

                    print(
                        "No hay señales nuevas."
                    )

                else:

                    print()
                    print(
                        f"Señales UNSEEN: "
                        f"{len(email_uids)}"
                    )

                    log_info(
                        f"Señales UNSEEN encontradas | "
                        f"Cantidad={len(email_uids)}"
                    )

                    for email_uid in (
                        email_uids
                    ):

                        process_signal(
                            mail,
                            email_uid,
                            signal_executor
                        )

                        # ----------------------------------------
                        # Comprobar inmediatamente después.
                        # ----------------------------------------

                        processing = (
                            state_manager
                            .get_processing_signals()
                        )

                        if processing:

                            print()
                            print(
                                "########################################"
                            )

                            print(
                                "BOT BLOQUEADO"
                            )

                            print(
                                "Existe una señal PROCESSING."
                            )

                            print(
                                "########################################"
                            )

                            log_error(
                                f"Bot bloqueado | "
                                f"Existe PROCESSING después de procesar correo | "
                                f"Cantidad={len(processing)}"
                            )

                            return

            except SignalStateError as error:

                print()
                print(
                    "########################################"
                )

                print(
                    "ERROR CRÍTICO DE ESTADO"
                )

                print(
                    "########################################"
                )

                print(
                    str(error)
                )

                print(
                    "EL BOT SE DETIENE."
                )

                log_error(
                    f"ERROR CRÍTICO DE ESTADO | {error}"
                )

                return

            except Exception as error:

                print()
                print(
                    "ERROR EN EL CICLO:"
                )

                print(
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                log_error(
                    f"Error en ciclo automático | "
                    f"{type(error).__name__}: {error}"
                )

                bot_state.set_error(error)
                bot_state.set_status(
                    SAFETY_LOCK,
                    error=error
                )

                return

            print()
            print(
                f"Esperando "
                f"{CHECK_INTERVAL} segundos..."
            )

            time.sleep(
                CHECK_INTERVAL
            )

    except KeyboardInterrupt:

        print()
        print(
            "Interrupción manual recibida."
        )

        log_warning(
            "DAX BOT interrumpido manualmente."
        )

    finally:

        if mail is not None:

            try:

                mail.logout()

            except Exception as error:

                log_warning(
                    f"Error cerrando conexión Gmail | "
                    f"{error}"
                )

        if ib_app is not None:

            try:

                ib_app.disconnect()

            except Exception as error:

                log_warning(
                    f"Error cerrando conexión IBKR | "
                    f"{error}"
                )

        bot_state.set_status(
            STOPPING
        )

        print()
        print(
            "DAX BOT detenido."
        )

        log_info(
            "DAX BOT detenido."
        )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    run()