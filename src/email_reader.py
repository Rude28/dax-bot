import imaplib
import email

from email.header import decode_header

from signal_parser import parse_signal

from signal_state import (
    SignalState,
    NEW,
    REJECTED,
)

from logger import (
    log_info,
    log_warning,
    log_error,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

SIGNAL_SENDER = (
    "operativadax@gmail.com"
)


# ============================================================
# ESTADO
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
# COMPROBAR ESTADO EXISTENTE
# ============================================================

def get_existing_signal_status(
    message_id
):

    return state_manager.get_status(
        message_id
    )


# ============================================================
# CONSTRUIR SEÑAL
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
# COMPROBAR CONEXIÓN IMAP
# ============================================================

def check_mail_connection(
    mail
):
    """
    Comprueba que la conexión IMAP sigue viva.

    Devuelve True si responde correctamente.

    Lanza la excepción original si Gmail/IMAP
    no responde correctamente.
    """

    if mail is None:

        raise RuntimeError(
            "La conexión Gmail es None."
        )

    try:

        status, _ = mail.noop()

        if status != "OK":

            raise ConnectionError(
                f"Gmail NOOP devolvió estado: "
                f"{status}"
            )

        return True

    except (
        imaplib.IMAP4.abort,
        imaplib.IMAP4.error,
        OSError,
        ConnectionError
    ) as error:

        log_warning(
            f"Conexión Gmail no disponible | "
            f"{type(error).__name__}: {error}"
        )

        raise


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

    Las excepciones IMAP se propagan para que bot_auto.py
    pueda iniciar la reconexión automática.
    """

    # --------------------------------------------------------
    # Verificar conexión antes de leer.
    # --------------------------------------------------------

    check_mail_connection(
        mail
    )

    # --------------------------------------------------------
    # Obtener mensaje mediante UID.
    # --------------------------------------------------------

    try:

        status, msg_data = mail.uid(
            "fetch",
            email_uid,
            "(RFC822)"
        )

    except (
        imaplib.IMAP4.abort,
        imaplib.IMAP4.error,
        OSError
    ) as error:

        log_warning(
            f"Error IMAP durante FETCH | "
            f"UID={email_uid} | "
            f"{type(error).__name__}: {error}"
        )

        raise

    if status != "OK":

        error = RuntimeError(
            f"No se pudo leer el correo UID={email_uid}. "
            f"Estado IMAP={status}"
        )

        log_error(
            str(error)
        )

        raise error

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

            message_id = (
                "imap_uid:"
                f"{email_uid.decode(errors='replace')}"
            )

            log_warning(
                f"Correo sin Message-ID | "
                f"UID={email_uid}"
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

        log_info(
            f"Correo recibido | "
            f"UID={email_uid_text} | "
            f"Message-ID={message_id} | "
            f"Sender={sender} | "
            f"Subject={subject}"
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

            log_warning(
                f"Señal ya registrada | "
                f"Message-ID={message_id} | "
                f"UID={email_uid_text} | "
                f"Status={existing_status}"
            )

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

        log_info(
            f"Resultado parser | "
            f"Message-ID={message_id} | "
            f"Actions={actions}"
        )

        # ====================================================
        # REJECTED
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

            log_warning(
                f"Señal REJECTED | "
                f"Message-ID={message_id} | "
                f"UID={email_uid_text} | "
                f"Subject={subject} | "
                f"Reason={rejection_reason}"
            )

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
        # SEÑAL VÁLIDA
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

        log_info(
            f"Señal NEW registrada | "
            f"Message-ID={message_id} | "
            f"UID={email_uid_text} | "
            f"Actions={actions}"
        )

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

    Devuelve UIDs IMAP.

    Si la conexión se ha perdido, la excepción se propaga
    para que bot_auto.py pueda reconectar.
    """

    # --------------------------------------------------------
    # Comprobar conexión
    # --------------------------------------------------------

    check_mail_connection(
        mail
    )

    # --------------------------------------------------------
    # Buscar
    # --------------------------------------------------------

    try:

        status, data = mail.uid(
            "search",
            None,
            f'FROM "{SIGNAL_SENDER}" UNSEEN'
        )

    except (
        imaplib.IMAP4.abort,
        imaplib.IMAP4.error,
        OSError
    ) as error:

        log_warning(
            f"Error IMAP durante SEARCH | "
            f"{type(error).__name__}: {error}"
        )

        raise

    if status != "OK":

        error = RuntimeError(
            "No se pudieron buscar correos "
            f"UNSEEN. Estado IMAP={status}"
        )

        log_error(
            str(error)
        )

        raise error

    if not data or not data[0]:

        log_info(
            f"No hay correos UNSEEN | "
            f"Sender={SIGNAL_SENDER}"
        )

        return []

    email_uids = (
        data[0].split()
    )

    if email_uids:

        log_info(
            f"Correos UNSEEN encontrados | "
            f"Cantidad={len(email_uids)} | "
            f"Sender={SIGNAL_SENDER}"
        )

    return email_uids