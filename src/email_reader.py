import imaplib
import email
import os

from email.header import decode_header

from dotenv import load_dotenv

from signal_parser import parse_signal
from signal_state import (
    SignalState,
    NEW,
    REJECTED,
    SUCCESS,
    FAILED,
    PARTIAL,
    PROCESSING,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

# ------------------------------------------------------------
# GMAIL
# ------------------------------------------------------------

GMAIL_USER = os.getenv(
    "GMAIL_USER"
)

GMAIL_APP_PASSWORD = os.getenv(
    "GMAIL_APP_PASSWORD"
)

# ------------------------------------------------------------
# IMAP
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# PROVEEDOR DE SEÑALES
# ------------------------------------------------------------

SIGNAL_SENDER = (
    "operativadax@gmail.com"
)


# ============================================================
# GESTOR DE ESTADOS
# ============================================================

state_manager = SignalState()


# ============================================================
# DECODIFICAR CABECERAS
# ============================================================

def decode_mime_header(
    value
):

    if not value:
        return ""

    decoded = decode_header(
        value
    )

    result = ""

    for part, encoding in decoded:

        if isinstance(
            part,
            bytes
        ):

            result += part.decode(
                encoding or "utf-8",
                errors="replace"
            )

        else:

            result += part

    return result


# ============================================================
# COMPROBAR ESTADO
# ============================================================

def get_existing_signal_status(
    message_id
):
    """
    Devuelve el estado actual de una señal.

    None
        → señal no registrada

    NEW
        → pendiente de ejecución

    PROCESSING
        → en proceso

    SUCCESS
        → ejecutada correctamente

    FAILED
        → ejecución fallida

    PARTIAL
        → ejecución parcial

    REJECTED
        → señal rechazada/no reconocida
    """

    return state_manager.get_status(
        message_id
    )


# ============================================================
# CREAR SEÑAL BASE
# ============================================================

def build_signal(
    email_uid_text,
    message_id,
    sender,
    subject,
    date,
    actions,
    valid,
    status,
    error=None
):
    """
    Construye una señal estructurada común para señales
    válidas y rechazadas.
    """

    return {
        "valid": valid,

        "status": status,

        "email_uid": email_uid_text,

        "message_id": message_id,

        "sender": sender,

        "subject": subject,

        "date": date,

        "actions": actions,

        "error": error
    }


# ============================================================
# PROCESAR CORREO
# ============================================================

def process_email(
    mail,
    email_uid
):
    """
    Lee un correo mediante UID y lo transforma en una señal.

    IMPORTANTE:

    - No ejecuta IBKR.
    - No marca el correo como leído.
    - Registra el estado local de la señal.
    """

    # --------------------------------------------------------
    # Obtener mensaje mediante UID.
    # --------------------------------------------------------

    status, msg_data = mail.uid(
        "fetch",
        email_uid,
        "(RFC822)"
    )

    if status != "OK":

        print()
        print(
            "ERROR: no se pudo leer "
            "el correo."
        )

        return None

    # --------------------------------------------------------
    # Extraer mensaje MIME.
    # --------------------------------------------------------

    for response_part in msg_data:

        if not isinstance(
            response_part,
            tuple
        ):

            continue

        msg = email.message_from_bytes(
            response_part[1]
        )

        # ----------------------------------------------------
        # DATOS DEL CORREO
        # ----------------------------------------------------

        sender = decode_mime_header(
            msg.get("From")
        )

        subject = decode_mime_header(
            msg.get("Subject")
        )

        date = msg.get(
            "Date"
        )

        # ----------------------------------------------------
        # MESSAGE-ID
        # ----------------------------------------------------

        message_id = msg.get(
            "Message-ID"
        )

        if message_id:

            message_id = (
                message_id.strip()
            )

        else:

            # Fallback.
            message_id = (
                "imap_uid:"
                f"{email_uid.decode(errors='replace')}"
            )

        # ----------------------------------------------------
        # UID
        # ----------------------------------------------------

        email_uid_text = (
            email_uid.decode(
                errors="replace"
            )
        )

        # ----------------------------------------------------
        # INFORMACIÓN
        # ----------------------------------------------------

        print()
        print(
            "----------------------------------------"
        )

        print(
            f"UID:        {email_uid_text}"
        )

        print(
            f"Message-ID: {message_id}"
        )

        print(
            f"Remitente:  {sender}"
        )

        print(
            f"Asunto:     {subject}"
        )

        print(
            f"Fecha:       {date}"
        )

        print(
            "----------------------------------------"
        )

        # ====================================================
        # COMPROBAR ESTADO PREVIO
        # ====================================================

        existing_status = (
            get_existing_signal_status(
                message_id
            )
        )

        if existing_status is not None:

            print()
            print(
                ">>> SEÑAL YA REGISTRADA <<<"
            )

            print(
                f"Estado: "
                f"{existing_status}"
            )

            print(
                "No se volverá a ejecutar."
            )

            # ------------------------------------------------
            # Devolvemos igualmente los metadatos si la señal
            # estaba REJECTED.
            #
            # Esto permite que bot_auto.py pueda decidir
            # posteriormente si debe notificar/marcar el correo.
            # ------------------------------------------------

            if existing_status == REJECTED:

                return build_signal(
                    email_uid_text,
                    message_id,
                    sender,
                    subject,
                    date,
                    [],
                    False,
                    REJECTED,
                    "Señal no reconocida."
                )

            return None

        # ====================================================
        # PARSER
        # ====================================================

        actions = parse_signal(
            subject
        )

        # ====================================================
        # SEÑAL NO RECONOCIDA
        # ====================================================

        if actions is None:

            print()
            print(
                ">>> SEÑAL NO RECONOCIDA <<<"
            )

            rejection_reason = (
                "El asunto no contiene "
                "una combinación de acciones "
                "válida."
            )

            # ------------------------------------------------
            # Registrar REJECTED.
            # ------------------------------------------------

            state_manager.set_status(
                message_id,
                REJECTED,

                email_uid=(
                    email_uid_text
                ),

                sender=sender,

                subject=subject,

                date=date,

                actions=[],

                error=rejection_reason
            )

            print(
                "Estado guardado: REJECTED"
            )

            # ------------------------------------------------
            # Devolver la señal rechazada.
            #
            # bot_auto.py será responsable de:
            #
            #   REJECTED
            #      ↓
            #   notifier
            #      ↓
            #   marcar leído
            #
            # Aquí NO se marca el correo.
            # ------------------------------------------------

            return build_signal(
                email_uid_text,
                message_id,
                sender,
                subject,
                date,
                [],
                False,
                REJECTED,
                rejection_reason
            )

        # ====================================================
        # CREAR SEÑAL VÁLIDA
        # ====================================================

        signal = build_signal(
            email_uid_text,
            message_id,
            sender,
            subject,
            date,
            actions,
            True,
            NEW,
            None
        )

        # ====================================================
        # REGISTRAR COMO NEW
        # ====================================================
        #
        # NO utilizamos PROCESSING aquí.
        #
        # bot_auto.py cambia:
        #
        # NEW → PROCESSING
        #
        # justo antes de ejecutar.
        # ====================================================

        state_manager.set_status(
            message_id,
            NEW,

            email_uid=(
                email_uid_text
            ),

            sender=sender,

            subject=subject,

            date=date,

            actions=actions,

            valid=True,

            error=None
        )

        # ====================================================
        # MOSTRAR SEÑAL
        # ====================================================

        print()
        print(
            ">>> SEÑAL NUEVA <<<"
        )

        print(
            f"Message-ID: "
            f"{message_id}"
        )

        print(
            f"UID:        "
            f"{email_uid_text}"
        )

        print(
            f"Acciones:   "
            f"{actions}"
        )

        print(
            "Estado:     NEW"
        )

        for action in actions:

            print(
                f"  → {action}"
            )

        print(
            "----------------------------------------"
        )

        return signal

    return None


# ============================================================
# BUSCAR CORREOS NO LEÍDOS
# ============================================================

def get_unread_signal_emails(
    mail
):
    """
    Busca exclusivamente:

        FROM operativadax@gmail.com
        UNSEEN

    y devuelve UIDs IMAP.
    """

    status, data = mail.uid(
        "search",
        None,
        f'FROM "{SIGNAL_SENDER}" UNSEEN'
    )

    if status != "OK":

        print()
        print(
            "ERROR: no se pudieron buscar "
            "los correos."
        )

        return []

    return data[0].split()


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "       DAX BOT - EMAIL READER"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # CONFIGURACIÓN
    # --------------------------------------------------------

    if not GMAIL_USER:

        print(
            "ERROR: falta GMAIL_USER"
        )

        return

    if not GMAIL_APP_PASSWORD:

        print(
            "ERROR: falta GMAIL_APP_PASSWORD"
        )

        return

    print(
        f"Usuario:       {GMAIL_USER}"
    )

    print(
        f"Servidor IMAP: {IMAP_SERVER}"
    )

    print(
        f"Puerto IMAP:   {IMAP_PORT}"
    )

    print(
        f"Remitente:     {SIGNAL_SENDER}"
    )

    print()

    mail = None

    try:

        # ----------------------------------------------------
        # CONEXIÓN
        # ----------------------------------------------------

        print(
            "Conectando con Gmail IMAP..."
        )

        mail = imaplib.IMAP4_SSL(
            IMAP_SERVER,
            IMAP_PORT
        )

        print(
            "Conexión IMAP establecida."
        )

        # ----------------------------------------------------
        # AUTENTICACIÓN
        # ----------------------------------------------------

        mail.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        print(
            "Autenticación con Gmail correcta."
        )

        # ----------------------------------------------------
        # INBOX
        # ----------------------------------------------------

        status, _ = mail.select(
            "INBOX"
        )

        if status != "OK":

            print(
                "ERROR: no se pudo abrir "
                "INBOX."
            )

            return

        print(
            "INBOX seleccionada."
        )

        # ----------------------------------------------------
        # BUSCAR CORREOS
        # ----------------------------------------------------

        print()

        print(
            f"Buscando correos NO LEÍDOS "
            f"de {SIGNAL_SENDER}..."
        )

        email_uids = (
            get_unread_signal_emails(
                mail
            )
        )

        if not email_uids:

            print()

            print(
                "No hay señales nuevas."
            )

            return

        # ----------------------------------------------------
        # RESUMEN
        # ----------------------------------------------------

        print()

        print(
            f"Correos no leídos encontrados: "
            f"{len(email_uids)}"
        )

        print()

        print(
            "========================================"
        )

        print(
            "PROCESANDO SEÑALES"
        )

        print(
            "========================================"
        )

        valid_signals = []

        rejected_signals = []

        # ----------------------------------------------------
        # Procesar en orden.
        # ----------------------------------------------------

        for email_uid in email_uids:

            print()

            print(
                "========================================"
            )

            print(
                f"Procesando UID: "
                f"{email_uid.decode(errors='replace')}"
            )

            print(
                "========================================"
            )

            signal = process_email(
                mail,
                email_uid
            )

            if signal is None:

                continue

            # ------------------------------------------------
            # Señal válida.
            # ------------------------------------------------

            if signal.get(
                "valid",
                False
            ):

                valid_signals.append(
                    signal
                )

            # ------------------------------------------------
            # Señal rechazada.
            # ------------------------------------------------

            elif signal.get(
                "status"
            ) == REJECTED:

                rejected_signals.append(
                    signal
                )

        # ====================================================
        # RESUMEN
        # ====================================================

        print()

        print(
            "========================================"
        )

        print(
            "RESUMEN"
        )

        print(
            "========================================"
        )

        print(
            f"Señales válidas:   "
            f"{len(valid_signals)}"
        )

        print(
            f"Señales rechazadas:"
            f" {len(rejected_signals)}"
        )

        # ----------------------------------------------------
        # VÁLIDAS
        # ----------------------------------------------------

        for index, signal in enumerate(
            valid_signals,
            start=1
        ):

            print()

            print(
                f"SEÑAL VÁLIDA {index}"
            )

            print(
                f"Message-ID: "
                f"{signal['message_id']}"
            )

            print(
                f"UID:        "
                f"{signal['email_uid']}"
            )

            print(
                f"Asunto:     "
                f"{signal['subject']}"
            )

            print(
                f"Acciones:   "
                f"{signal['actions']}"
            )

            print(
                "Estado:     NEW"
            )

        # ----------------------------------------------------
        # RECHAZADAS
        # ----------------------------------------------------

        for index, signal in enumerate(
            rejected_signals,
            start=1
        ):

            print()

            print(
                f"SEÑAL RECHAZADA {index}"
            )

            print(
                f"Message-ID: "
                f"{signal['message_id']}"
            )

            print(
                f"UID:        "
                f"{signal['email_uid']}"
            )

            print(
                f"Asunto:     "
                f"{signal['subject']}"
            )

            print(
                f"Motivo:     "
                f"{signal.get('error', 'N/A')}"
            )

            print(
                "Estado:     REJECTED"
            )

        print()

        print(
            "Los correos siguen SIN LEER."
        )

        print(
            "No se ha ejecutado ninguna orden."
        )

        print(
            "========================================"
        )

    except Exception as error:

        print()

        print(
            "========================================"
        )

        print(
            "ERROR AL LEER GMAIL"
        )

        print(
            "========================================"
        )

        print(
            f"Tipo:    "
            f"{type(error).__name__}"
        )

        print(
            f"Mensaje: "
            f"{error}"
        )

    finally:

        if mail is not None:

            try:

                mail.logout()

                print(
                    "Conexión cerrada correctamente."
                )

            except Exception:

                pass


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()