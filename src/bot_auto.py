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


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

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

IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 4

SIGNAL_SENDER = (
    "operativadax@gmail.com"
)

CHECK_INTERVAL = 10


# ============================================================
# ESTADO
# ============================================================

state_manager = SignalState()


# ============================================================
# CONECTAR IBKR
# ============================================================

def create_ib_executor():

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

        print(
            "ERROR: no se pudo conectar "
            "con IB Gateway."
        )

        app.disconnect()

        return None

    print(
        "Conexión IBKR establecida."
    )

    print(
        "Esperando posiciones iniciales..."
    )

    if not app.positions_ready.wait(
        timeout=10
    ):

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

    return mail


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

        return False

    except Exception as error:

        print(
            f"ERROR marcando correo como leído: "
            f"{error}"
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

        # ----------------------------------------------------
        # El resultado de trading ya está confirmado.
        # Marcamos leído para evitar duplicación.
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

    # --------------------------------------------------------
    # Ejecutar.
    # --------------------------------------------------------

    try:

        result = (
            signal_executor.execute(
                signal
            )
        )

    except Exception as error:

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

    # --------------------------------------------------------
    # Política de correo.
    #
    # Una vez que el resultado de trading está guardado,
    # NO debemos volver a ejecutar la misma señal aunque
    # el correo permanezca UNSEEN.
    #
    # SUCCESS:
    #     SEEN
    #
    # FAILED/PARTIAL:
    #     UNSEEN para revisión manual
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

    # ========================================================
    # IBKR
    # ========================================================

    ib_app = (
        create_ib_executor()
    )

    if ib_app is None:

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

        # ====================================================
        # LOOP
        # ====================================================

        while True:

            try:

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

                    return

                # ------------------------------------------------
                # Buscar correos.
                # ------------------------------------------------

                email_uids = (
                    get_unread_signal_emails(
                        mail
                    )
                )

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

    finally:

        if mail is not None:

            try:

                mail.logout()

            except Exception:

                pass

        if ib_app is not None:

            try:

                ib_app.disconnect()

            except Exception:

                pass

        print()
        print(
            "DAX BOT detenido."
        )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    run()