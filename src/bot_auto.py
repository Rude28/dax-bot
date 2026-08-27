import imaplib
import os
import smtplib
import threading
import time

from email.mime.text import MIMEText

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

from control_email import (
    get_control_emails,
    read_control_email,
    mark_control_as_read,
)

from control_executor import (
    ControlExecutor,
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
# CORREO DE CONTROL
# ============================================================

CONTROL_RESPONSE_TO = os.getenv(
    "CONTROL_EMAIL"
)

SMTP_SERVER = os.getenv(
    "SMTP_SERVER",
    "smtp.gmail.com"
)

SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "465"
    )
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
    """Crea y valida una conexión IMAP nueva."""

    print()
    print("========================================")
    print("CONECTANDO CON GMAIL")
    print("========================================")

    if not GMAIL_USER:
        raise RuntimeError("Falta GMAIL_USER.")

    if not GMAIL_APP_PASSWORD:
        raise RuntimeError("Falta GMAIL_APP_PASSWORD.")

    mail = None

    try:
        mail = imaplib.IMAP4_SSL(
            IMAP_SERVER,
            IMAP_PORT,
            timeout=GMAIL_RECONNECT_TIMEOUT
        )

        mail.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        status, _ = mail.select("INBOX")

        if status != "OK":
            raise RuntimeError(
                "No se pudo abrir INBOX."
            )

        noop_status, _ = mail.noop()

        if noop_status != "OK":
            raise RuntimeError(
                "Gmail respondió incorrectamente al NOOP."
            )

        bot_state.set_gmail_connected(True)
        log_info("Conexión Gmail establecida y validada.")

        print("Gmail preparado correctamente.")

        return mail

    except Exception:
        bot_state.set_gmail_connected(False)

        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass

        raise


# ============================================================
# UTILIDADES DE CONEXIÓN
# ============================================================

def _ibkr_connected(ib_app):
    """Comprueba la conexión real de ibapi sin asumir APIs de otro cliente."""

    if ib_app is None:
        return False

    try:
        if hasattr(ib_app, "isConnected"):
            return bool(ib_app.isConnected())

        if hasattr(ib_app, "is_trading_connection_ready"):
            return bool(
                ib_app.is_trading_connection_ready()
            )

    except Exception as error:
        log_warning(
            f"Error comprobando conexión IBKR | "
            f"{type(error).__name__}: {error}"
        )

    return False


def _set_ready_if_safe(ib_app):
    """READY solo si IBKR y Gmail están conectados y no hay PROCESSING."""

    state = bot_state.snapshot()

    if not state.get("gmail_connected", False):
        return False

    if not _ibkr_connected(ib_app):
        return False

    processing = state_manager.get_processing_signals()

    if processing:
        return False

    bot_state.set_position(
        ib_app.get_position()
    )

    bot_state.set_status(READY)
    return True


# ============================================================
# RECONEXIÓN GMAIL
# ============================================================

def reconnect_gmail(mail, ib_app):
    """
    Recupera IMAP de Gmail sin dar por buena la conexión hasta
    autenticar, abrir INBOX y responder a NOOP.

    IMPORTANTE:
    Gmail e IBKR se validan de forma independiente. Gmail no se
    considera reconectado si IMAP no responde; y READY solo se
    recupera cuando ambas conexiones están disponibles.
    """

    attempt = 0

    while True:
        attempt += 1

        bot_state.set_status(RECONNECTING_GMAIL)
        bot_state.set_gmail_connected(False)

        print()
        print("========================================")
        print("RECONEXIÓN GMAIL")
        print(f"Intento: {attempt}")
        print("========================================")

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

            status, _ = new_mail.select("INBOX")

            if status != "OK":
                raise RuntimeError(
                    "No se pudo abrir INBOX tras reconectar Gmail."
                )

            noop_status, _ = new_mail.noop()

            if noop_status != "OK":
                raise RuntimeError(
                    "Gmail respondió incorrectamente al NOOP tras reconectar."
                )

            bot_state.set_gmail_connected(True)

            log_info(
                f"Gmail reconectado a nivel IMAP | Intento={attempt}"
            )

            # Si IBKR está desconectado, Gmail sigue siendo válido,
            # pero no declaramos READY ni procesamos operaciones.
            if not _ibkr_connected(ib_app):
                log_warning(
                    "Gmail reconectado pero IBKR sigue desconectado. "
                    "Gmail queda disponible; el bot espera a IBKR."
                )

                bot_state.set_status(
                    RECONNECTING_IBKR
                )

                return new_mail

            # Si había PROCESSING, reconciliamos antes de READY.
            processing = state_manager.get_processing_signals()

            if processing:
                print("PROCESSING DETECTADO TRAS RECONEXIÓN DE GMAIL.")
                log_warning(
                    f"PROCESSING tras reconexión Gmail | "
                    f"Cantidad={len(processing)}"
                )

                if not reconcile_processing_signals(
                    ib_app,
                    new_mail
                ):
                    bot_state.set_status(SAFETY_LOCK)
                    log_error(
                        "No se pudo reconciliar PROCESSING tras reconexión Gmail."
                    )
                    try:
                        new_mail.logout()
                    except Exception:
                        pass
                    bot_state.set_gmail_connected(False)
                    return None

            if not _set_ready_if_safe(ib_app):
                log_warning(
                    "Gmail reconectado pero el bot no puede pasar a READY."
                )
                return new_mail

            print("GMAIL RECONECTADO CORRECTAMENTE.")
            log_info(
                f"Gmail reconectado y validado | "
                f"Position={ib_app.get_position()}"
            )

            return new_mail

        except Exception as error:
            bot_state.set_gmail_connected(False)
            bot_state.set_error(error)

            log_warning(
                f"Error reconectando Gmail | Intento={attempt} | "
                f"{type(error).__name__}: {error}"
            )

            time.sleep(GMAIL_RECONNECT_INTERVAL)


# ============================================================
# COMPROBAR CONEXIÓN GMAIL
# ============================================================

def ensure_gmail_connection(mail, ib_app):
    """Comprueba IMAP de forma activa y devuelve una conexión válida."""

    if mail is None:
        log_warning("No existe conexión Gmail; iniciando reconexión.")
        return reconnect_gmail(None, ib_app)

    try:
        status, _ = mail.noop()

        if status != "OK":
            raise RuntimeError(
                "IMAP NOOP devolvió un estado no OK."
            )

        # La conexión IMAP está viva. Solo reflejamos su estado.
        if not bot_state.snapshot().get("gmail_connected", False):
            bot_state.set_gmail_connected(True)

        return mail

    except Exception as error:
        bot_state.set_gmail_connected(False)
        bot_state.set_error(error)

        log_warning(
            f"Gmail desconectado detectado | "
            f"{type(error).__name__}: {error}"
        )

        print()
        print("GMAIL DESCONECTADO.")
        print("No se procesarán correos hasta reconectar.")

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

            if bot_state.snapshot().get("gmail_connected", False):
                bot_state.set_status(READY)
                log_info(
                    "IBKR reconectado y validado. Estado READY."
                )
            else:
                bot_state.set_status(RECONNECTING_GMAIL)
                log_info(
                    "IBKR reconectado; esperando reconexión Gmail antes de READY."
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
# ENVIAR RESPUESTA DE CONTROL
# ============================================================

def send_control_response(
    result
):

    recipient = CONTROL_RESPONSE_TO

    if not recipient:

        log_error(
            "CONTROL_EMAIL no está configurado; "
            "no se puede enviar respuesta de control."
        )

        return False

    subject = result.get(
        "subject",
        "DAX BOT - Control"
    )

    body = result.get(
        "body",
        ""
    )

    message = MIMEText(
        body,
        "plain",
        "utf-8"
    )

    message["From"] = GMAIL_USER
    message["To"] = recipient
    message["Subject"] = subject

    try:

        with smtplib.SMTP_SSL(
            SMTP_SERVER,
            SMTP_PORT
        ) as smtp:

            smtp.login(
                GMAIL_USER,
                GMAIL_APP_PASSWORD
            )

            smtp.sendmail(
                GMAIL_USER,
                recipient,
                message.as_string()
            )

        log_info(
            f"Respuesta de control enviada | "
            f"Subject={subject}"
        )

        print(
            f"Respuesta de control enviada: {subject}"
        )

        return True

    except Exception as error:

        log_error(
            f"Error enviando respuesta de control | "
            f"{type(error).__name__}: {error}"
        )

        return False


# ============================================================
# MAPA DE OPERACIONES MANUALES
# ============================================================

MANUAL_ACTIONS = {
    "OPEN LONG": "ABRIR_LARGO",
    "CLOSE LONG": "CERRAR_LARGO",
    "OPEN SHORT": "ABRIR_CORTO",
    "CLOSE SHORT": "CERRAR_CORTO",
}


def build_manual_control_response(result, command):
    """Construye la respuesta específica de una orden manual."""

    if not result:
        return {
            "subject": "DAX BOT - Operación manual",
            "body": (
                f"Operación: {command}\n\n"
                "No se recibió un resultado de ejecución."
            ),
        }

    success = result.get("success", False)
    status = result.get("status", "UNKNOWN")
    position = result.get("position", "N/A")
    price = result.get("price", "N/A")
    order_id = result.get("order_id", "N/A")
    filled = result.get("filled", 0.0)
    error = result.get("error")

    if success:
        subject = "DAX BOT - Operación manual realizada"
        headline = "OPERACIÓN MANUAL REALIZADA"
    elif status == "PARTIAL":
        subject = "DAX BOT - Operación manual parcial"
        headline = "OPERACIÓN MANUAL PARCIAL"
    else:
        subject = "DAX BOT - Operación manual fallida"
        headline = "OPERACIÓN MANUAL NO REALIZADA"

    lines = [
        headline,
        "================================",
        "",
        f"Operación: {command}",
        f"Estado: {status}",
        f"Order ID: {order_id}",
        f"Ejecutado: {filled}",
        f"Precio: {price}",
        f"Posición final: {position}",
    ]

    if error:
        lines.extend(["", f"Error: {error}"])

    return {
        "subject": subject,
        "body": "\n".join(lines),
    }


def process_control_messages(
    mail,
    control_executor,
    signal_executor
):
    """Procesa consultas y órdenes manuales directas."""

    control_uids = get_control_emails(
        mail
    )

    if not control_uids:
        return True

    for email_uid in control_uids:

        control = read_control_email(
            mail,
            email_uid
        )

        if control is None:
            continue

        if not control.get("valid", False):
            send_control_response({
                "subject": "DAX BOT - Control rechazado",
                "body": (
                    "COMANDO DE CONTROL RECHAZADO\n\n"
                    f"Motivo: {control.get('reason', 'Desconocido')}\n\n"
                    "No se ha realizado ninguna operación."
                )
            })
            mark_control_as_read(mail, email_uid)
            continue

        command_type = control.get("command_type")
        command = control.get("command")

        # ----------------------------------------------------
        # Consultas
        # ----------------------------------------------------
        if command_type == "COMMAND" and command in (
            "STATUS",
            "POSITIONS",
            "ACCOUNT",
        ):

            result = control_executor.execute(
                command
            )

            send_control_response(result)
            mark_control_as_read(mail, email_uid)
            continue

        # ----------------------------------------------------
        # Orden manual DIRECTA
        # ----------------------------------------------------
        if command_type == "COMMAND" and command in MANUAL_ACTIONS:

            validation = control_executor.execute_manual_command(
                control
            )

            if not validation.get("success", False):
                send_control_response({
                    "subject": "DAX BOT - Operación manual bloqueada",
                    "body": validation.get(
                        "body",
                        "No se ha enviado ninguna orden."
                    ),
                })
                mark_control_as_read(mail, email_uid)
                continue

            manual_signal = validation.get("signal")

            if not manual_signal:
                log_error(
                    f"ControlExecutor no devolvió señal manual | "
                    f"Command={command}"
                )
                send_control_response({
                    "subject": "DAX BOT - Error operación manual",
                    "body": "No se ha generado la señal manual.\n\nNo se ha enviado ninguna orden.",
                })
                mark_control_as_read(mail, email_uid)
                continue

            manual_message_id = manual_signal[
                "message_id"
            ]

            # ------------------------------------------------
            # Registrar NEW antes de pasar al flujo normal.
            # Esto soluciona el problema que vimos con Status=None.
            # ------------------------------------------------
            state_manager.set_status(
                manual_message_id,
                NEW,
                email_uid=manual_signal.get("email_uid"),
                sender=manual_signal.get("sender"),
                subject=manual_signal.get("subject"),
                date=manual_signal.get("date"),
                actions=manual_signal.get("actions", []),
                valid=True,
                manual=True,
                manual_command=command,
                position_initial=validation.get("position"),
                expected_final_position=(
                    validation.get("expected_position")
                ),
                operations=[]
            )

            log_info(
                f"Orden manual registrada como NEW | "
                f"Message-ID={manual_message_id} | "
                f"Command={command} | "
                f"Actions={manual_signal.get('actions')}"
            )

            try:
                result = process_valid_signal(
                    mail,
                    manual_signal,
                    signal_executor
                )

            except Exception as error:
                log_error(
                    f"Error ejecutando operación manual | "
                    f"Message-ID={manual_message_id} | "
                    f"{type(error).__name__}: {error}"
                )

                result = {
                    "success": False,
                    "status": "ERROR",
                    "position": signal_executor.ib_app.get_position(),
                    "price": 0.0,
                    "filled": 0.0,
                    "order_id": None,
                    "error": str(error),
                }

            response = build_manual_control_response(
                result,
                command
            )

            send_control_response(response)

            # Este correo ya se ha consumido como orden manual.
            # El estado persistente evita reejecuciones.
            mark_control_as_read(mail, email_uid)

            continue

        # CONFIRM ya no forma parte del sistema.
        # control_email.py aún puede reconocerlo, pero lo rechazamos
        # explícitamente para evitar un segundo paso accidental.
        if command_type == "CONFIRM":
            send_control_response({
                "subject": "DAX BOT - Confirmación no necesaria",
                "body": (
                    "Las órdenes manuales ya no utilizan confirmación por código.\n\n"
                    "Envía directamente uno de estos comandos:\n"
                    "DAXCONTROL OPEN LONG\n"
                    "DAXCONTROL CLOSE LONG\n"
                    "DAXCONTROL OPEN SHORT\n"
                    "DAXCONTROL CLOSE SHORT"
                ),
            })
            mark_control_as_read(mail, email_uid)
            continue

    return True


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

        return None

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

    return result


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

        control_executor = ControlExecutor(
            ib_app
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

        # Primer heartbeat antes de entrar al ciclo.
        try:
            bot_state.heartbeat()
            log_info("Heartbeat inicial creado.")
        except Exception as error:
            log_warning(
                f"Error creando heartbeat inicial | "
                f"{type(error).__name__}: {error}"
            )

        log_info(
            "DAX BOT preparado y listo para recibir señales."
        )

        # ====================================================
        # LOOP
        # ====================================================

        while True:

            # ------------------------------------------------
            # HEARTBEAT
            # ------------------------------------------------
            # Se actualiza al inicio de cada ciclo. Si el proceso
            # queda bloqueado, el timestamp dejará de avanzar.
            try:
                bot_state.heartbeat()
                log_info(
                    "Heartbeat actualizado | "
                    f"CycleStatus={bot_state.snapshot().get('status')}"
                )
            except Exception as error:
                # Un fallo al escribir el heartbeat no debe crear
                # una parada del bot ni afectar al trading.
                log_warning(
                    f"Error actualizando heartbeat | "
                    f"{type(error).__name__}: {error}"
                )

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
                # PROCESAR CORREOS DE CONTROL
                # ------------------------------------------------

                try:

                    if not process_control_messages(
                        mail,
                        control_executor,
                        signal_executor
                    ):

                        bot_state.set_status(
                            SAFETY_LOCK
                        )

                        return

                except Exception as error:

                    log_warning(
                        f"Error procesando control por correo | "
                        f"{type(error).__name__}: {error}"
                    )

                    # El fallo de un correo de control no debe bloquear
                    # automáticamente las señales normales. Si además
                    # se ha perdido Gmail, ensure_gmail_connection lo
                    # detectará en el siguiente ciclo.

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