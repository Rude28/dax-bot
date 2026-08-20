import imaplib
import email

from email.header import decode_header

from dotenv import load_dotenv
import os

from email_reader import process_email
from paper_executor import PaperExecutor
from signal_executor import SignalExecutor
from notifier import send_notification


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

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

SIGNAL_SENDER = "operativadax@gmail.com"


# ============================================================
# DECODIFICAR CABECERAS
# ============================================================

def decode_mime_header(value):

    if not value:
        return ""

    decoded = decode_header(value)

    result = ""

    for part, encoding in decoded:

        if isinstance(part, bytes):

            result += part.decode(
                encoding or "utf-8",
                errors="replace"
            )

        else:

            result += part

    return result


# ============================================================
# MARCAR CORREO COMO LEÍDO
# ============================================================

def mark_as_read(
    mail,
    email_id
):

    try:

        status, _ = mail.store(
            email_id,
            "+FLAGS",
            "\\Seen"
        )

        if status == "OK":

            print(
                "Correo marcado como LEÍDO."
            )

            return True

        print(
            "ERROR: no se pudo marcar "
            "el correo como leído."
        )

        return False

    except Exception as error:

        print(
            "ERROR AL MARCAR CORREO "
            "COMO LEÍDO:"
        )

        print(error)

        return False


# ============================================================
# CONECTAR CON IBKR
# ============================================================

def create_ib_executor():

    print()
    print(
        "========================================"
    )

    print(
        "CONECTANDO CON IB GATEWAY"
    )

    print(
        "========================================"
    )

    app = PaperExecutor()

    app.connect(
        "127.0.0.1",
        4002,
        4
    )

    # Hilo de la API
    # --------------------------------------------------------

    import threading

    api_thread = threading.Thread(
        target=app.run,
        daemon=True
    )

    api_thread.start()

    # --------------------------------------------------------
    # Esperar conexión
    # --------------------------------------------------------

    if not app.connection_ready.wait(
        timeout=10
    ):

        print(
            "ERROR: no se pudo conectar "
            "con IB Gateway."
        )

        app.disconnect()

        return None

    # --------------------------------------------------------
    # Esperar posiciones
    # --------------------------------------------------------

    print(
        "Esperando posiciones iniciales..."
    )

    if not app.positions_ready.wait(
        timeout=10
    ):

        print(
            "ERROR: no se recibieron "
            "las posiciones iniciales."
        )

        app.disconnect()

        return None

    print()
    print(
        "IBKR preparado correctamente."
    )

    print(
        f"Posición inicial FDXM: "
        f"{app.get_position()}"
    )

    return app


# ============================================================
# CONEXIÓN IMAP
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
# OBTENER CORREOS NO LEÍDOS
# ============================================================

def get_unread_signal_emails(
    mail
):

    status, data = mail.search(
        None,
        f'FROM "{SIGNAL_SENDER}" UNSEEN'
    )

    if status != "OK":

        raise RuntimeError(
            "No se pudieron buscar "
            "los correos no leídos."
        )

    email_ids = data[0].split()

    return email_ids


# ============================================================
# PROCESAR SEÑAL
# ============================================================

def process_signal(
    mail,
    email_id,
    signal_executor
):

    print()
    print(
        "########################################"
    )

    print(
        "PROCESANDO NUEVA SEÑAL"
    )

    print(
        "########################################"
    )

    print(
        f"Email ID: "
        f"{email_id.decode(errors='replace')}"
    )

    # --------------------------------------------------------
    # Leer + parsear correo
    # --------------------------------------------------------

    signal = process_email(
        mail,
        email_id
    )

    # --------------------------------------------------------
    # No es una señal reconocida
    # --------------------------------------------------------

    if signal is None:

        print()
        print(
            "Señal no reconocida."
        )

        # ----------------------------------------------------
        # IMPORTANTE:
        #
        # La señal desconocida todavía NO se marca como leída.
        #
        # Esto lo dejaremos para una política posterior,
        # cuando tengamos también el sistema de notificaciones
        # completamente integrado.
        # ----------------------------------------------------

        return False

    print()
    print(
        "SEÑAL ESTRUCTURADA:"
    )

    print(
        signal
    )

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    print()
    print(
        "Enviando señal al ejecutor..."
    )

    result = signal_executor.execute(
        signal
    )

    # --------------------------------------------------------
    # Mostrar resultado
    # --------------------------------------------------------

    print()
    print(
        "RESULTADO DE EJECUCIÓN:"
    )

    print(
        result
    )

    # --------------------------------------------------------
    # NOTIFICACIÓN
    # --------------------------------------------------------

    print()
    print(
        "Enviando notificación..."
    )

    notification_sent = send_notification(
        result
    )

    if notification_sent:

        print(
            "Notificación enviada correctamente."
        )

    else:

        print(
            "ATENCIÓN: no se pudo enviar "
            "la notificación."
        )

    # --------------------------------------------------------
    # MARCAR COMO LEÍDO
    # --------------------------------------------------------
    #
    # MUY IMPORTANTE:
    #
    # El correo se marca como leído DESPUÉS de haber
    # intentado procesar la señal y obtener un resultado.
    #
    # Esto evita que una señal desaparezca antes de ser
    # procesada.
    #
    # En esta versión, incluso si falla el envío de la
    # notificación, la operación ya fue procesada y por tanto
    # NO debemos dejar el correo pendiente para evitar que
    # una reinicialización vuelva a ejecutar la misma orden.
    # --------------------------------------------------------

    mark_as_read(
        mail,
        email_id
    )

    return result.get(
        "success",
        False
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
        "           DAX BOT"
    )

    print(
        "       PAPER TRADING MODE"
    )

    print(
        "========================================"
    )

    # ========================================================
    # 1. CONECTAR IBKR
    # ========================================================

    ib_app = create_ib_executor()

    if ib_app is None:

        print(
            "El bot no puede continuar."
        )

        return

    # ========================================================
    # 2. CREAR EJECUTOR DE SEÑALES
    # ========================================================

    signal_executor = SignalExecutor(
        ib_app
    )

    print()
    print(
        "SignalExecutor preparado."
    )

    # ========================================================
    # 3. CONECTAR GMAIL
    # ========================================================

    mail = None

    try:

        mail = create_mail_connection()

        # ====================================================
        # 4. BUSCAR SEÑALES NO LEÍDAS
        # ====================================================

        email_ids = get_unread_signal_emails(
            mail
        )

        print()
        print(
            "========================================"
        )

        print(
            f"Señales pendientes: "
            f"{len(email_ids)}"
        )

        print(
            "========================================"
        )

        if not email_ids:

            print()
            print(
                "No hay señales nuevas."
            )

            return

        # ====================================================
        # 5. PROCESAR EN ORDEN CRONOLÓGICO
        # ====================================================

        for email_id in email_ids:

            process_signal(
                mail,
                email_id,
                signal_executor
            )

        print()
        print(
            "========================================"
        )

        print(
            "PROCESAMIENTO FINALIZADO"
        )

        print(
            "========================================"
        )

    except Exception as error:

        print()
        print(
            "########################################"
        )

        print(
            "ERROR GENERAL DEL BOT"
        )

        print(
            "########################################"
        )

        print(
            f"Tipo: "
            f"{type(error).__name__}"
        )

        print(
            f"Mensaje: "
            f"{error}"
        )

    finally:

        # ----------------------------------------------------
        # CERRAR GMAIL
        # ----------------------------------------------------

        if mail is not None:

            try:

                mail.logout()

            except Exception:

                pass

        # ----------------------------------------------------
        # CERRAR IBKR
        # ----------------------------------------------------

        if ib_app is not None:

            try:

                ib_app.disconnect()

            except Exception:

                pass

        print()
        print(
            "DAX BOT finalizado."
        )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()