import imaplib
import email

from email.header import decode_header

from logger import (
    log_info,
    log_warning,
    log_error,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

# IMPORTANTE:
# Sustituye esta dirección por tu correo REAL de control.
CONTROL_EMAIL = "riostorresgabriel97@gmail.com"

CONTROL_KEYWORD = "DAXCONTROL"


# ============================================================
# COMANDOS DE CONSULTA
# ============================================================

COMMAND_STATUS = "STATUS"
COMMAND_POSITIONS = "POSITIONS"
COMMAND_ACCOUNT = "ACCOUNT"


# ============================================================
# OPERACIONES MANUALES
# ============================================================

COMMAND_OPEN_LONG = "OPEN LONG"
COMMAND_CLOSE_LONG = "CLOSE LONG"
COMMAND_OPEN_SHORT = "OPEN SHORT"
COMMAND_CLOSE_SHORT = "CLOSE SHORT"


# ============================================================
# CONFIRMACIÓN
# ============================================================

COMMAND_CONFIRM = "CONFIRM"


# ============================================================
# COMANDOS PERMITIDOS
# ============================================================

ALLOWED_COMMANDS = {
    COMMAND_STATUS,
    COMMAND_POSITIONS,
    COMMAND_ACCOUNT,
    COMMAND_OPEN_LONG,
    COMMAND_CLOSE_LONG,
    COMMAND_OPEN_SHORT,
    COMMAND_CLOSE_SHORT,
}


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
# EXTRAER CUERPO
# ============================================================

def get_message_body(
    msg
):

    # --------------------------------------------------------
    # Mensaje multipart
    # --------------------------------------------------------

    if msg.is_multipart():

        for part in msg.walk():

            content_type = (
                part.get_content_type()
            )

            disposition = str(
                part.get(
                    "Content-Disposition",
                    ""
                )
            )

            if (
                content_type == "text/plain"
                and "attachment"
                not in disposition.lower()
            ):

                payload = (
                    part.get_payload(
                        decode=True
                    )
                )

                if payload is None:
                    continue

                return payload.decode(
                    "utf-8",
                    errors="replace"
                ).strip()

        return ""

    # --------------------------------------------------------
    # Mensaje simple
    # --------------------------------------------------------

    payload = (
        msg.get_payload(
            decode=True
        )
    )

    if payload is None:
        return ""

    return payload.decode(
        "utf-8",
        errors="replace"
    ).strip()


# ============================================================
# NORMALIZAR COMANDO
# ============================================================

def normalize_command(
    subject
):
    """
    Comandos aceptados:

        DAXCONTROL STATUS
        DAXCONTROL POSITIONS
        DAXCONTROL ACCOUNT

        DAXCONTROL OPEN LONG
        DAXCONTROL CLOSE LONG
        DAXCONTROL OPEN SHORT
        DAXCONTROL CLOSE SHORT

        DAXCONTROL CONFIRM 123456
    """

    if not subject:

        return None

    normalized = (
        subject
        .strip()
        .upper()
    )

    prefix = (
        CONTROL_KEYWORD
        + " "
    )

    if not normalized.startswith(
        prefix
    ):

        return None

    command = (
        normalized[
            len(prefix):
        ]
        .strip()
    )

    # ========================================================
    # COMANDOS NORMALES
    # ========================================================

    if command in ALLOWED_COMMANDS:

        return {
            "type": "COMMAND",
            "command": command,
            "code": None,
        }

    # ========================================================
    # CONFIRMACIÓN
    # ========================================================

    parts = command.split()

    if (
        len(parts) == 2
        and parts[0] == COMMAND_CONFIRM
        and parts[1].isdigit()
        and len(parts[1]) == 6
    ):

        return {
            "type": "CONFIRM",
            "command": COMMAND_CONFIRM,
            "code": parts[1],
        }

    return None


# ============================================================
# VALIDAR REMITENTE
# ============================================================

def is_authorized_sender(
    sender
):
    """
    Validación exacta del correo de control.
    """

    if not sender:

        return False

    sender_lower = (
        sender
        .lower()
        .strip()
    )

    authorized = (
        CONTROL_EMAIL
        .lower()
        .strip()
    )

    # --------------------------------------------------------
    # Formato:
    #
    # Nombre <correo@gmail.com>
    # --------------------------------------------------------

    if (
        "<" in sender_lower
        and ">" in sender_lower
    ):

        sender_lower = (
            sender_lower
            .split("<", 1)[1]
            .split(">", 1)[0]
            .strip()
        )

    return (
        sender_lower
        == authorized
    )


# ============================================================
# PARSEAR CORREO DE CONTROL
# ============================================================

def parse_control_email(
    msg,
    email_uid
):

    sender = decode_mime_header(
        msg.get("From")
    )

    subject = decode_mime_header(
        msg.get("Subject")
    )

    date = msg.get(
        "Date"
    )

    message_id = msg.get(
        "Message-ID"
    )

    if message_id:

        message_id = (
            message_id.strip()
        )

    else:

        message_id = (
            "control_uid:"
            f"{email_uid.decode(errors='replace')}"
        )

    email_uid_text = (
        email_uid.decode(
            errors="replace"
        )
    )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    log_info(
        f"Correo de control encontrado | "
        f"UID={email_uid_text} | "
        f"Message-ID={message_id} | "
        f"Sender={sender} | "
        f"Subject={subject}"
    )

    # ========================================================
    # AUTORIZACIÓN
    # ========================================================

    if not is_authorized_sender(
        sender
    ):

        log_warning(
            f"Comando de control rechazado | "
            f"Motivo=Remitente no autorizado | "
            f"Sender={sender}"
        )

        return {
            "valid": False,
            "reason": (
                "Remitente no autorizado."
            ),
            "command": None,
            "command_type": None,
            "code": None,
            "email_uid": email_uid_text,
            "message_id": message_id,
            "sender": sender,
            "subject": subject,
            "date": date,
        }

    # ========================================================
    # PARSEAR COMANDO
    # ========================================================

    parsed = normalize_command(
        subject
    )

    if parsed is None:

        log_warning(
            f"Comando de control rechazado | "
            f"Motivo=Comando no reconocido | "
            f"Message-ID={message_id} | "
            f"Subject={subject}"
        )

        return {
            "valid": False,
            "reason": (
                "Comando no reconocido."
            ),
            "command": None,
            "command_type": None,
            "code": None,
            "email_uid": email_uid_text,
            "message_id": message_id,
            "sender": sender,
            "subject": subject,
            "date": date,
        }

    # ========================================================
    # COMANDO VÁLIDO
    # ========================================================

    command_type = parsed[
        "type"
    ]

    command = parsed[
        "command"
    ]

    code = parsed.get(
        "code"
    )

    log_info(
        f"Comando de control válido | "
        f"Message-ID={message_id} | "
        f"Type={command_type} | "
        f"Command={command}"
        + (
            f" | Code={code}"
            if code
            else ""
        )
    )

    return {
        "valid": True,
        "reason": None,
        "command": command,
        "command_type": command_type,
        "code": code,
        "email_uid": email_uid_text,
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "date": date,
    }


# ============================================================
# BUSCAR CORREOS DE CONTROL
# ============================================================

def get_control_emails(
    mail
):
    """
    Busca correos no leídos del remitente autorizado.
    """

    if mail is None:

        raise RuntimeError(
            "La conexión Gmail es None."
        )

    try:

        status, data = mail.uid(
            "search",
            None,
            f'FROM "{CONTROL_EMAIL}" UNSEEN'
        )

    except (
        imaplib.IMAP4.abort,
        imaplib.IMAP4.error,
        OSError
    ) as error:

        log_error(
            f"Error buscando correos de control | "
            f"{type(error).__name__}: {error}"
        )

        raise

    if status != "OK":

        error = RuntimeError(
            "No se pudieron buscar "
            "los correos de control."
        )

        log_error(
            str(error)
        )

        raise error

    if (
        not data
        or not data[0]
    ):

        log_info(
            "No hay correos de control UNSEEN."
        )

        return []

    email_uids = (
        data[0].split()
    )

    log_info(
        f"Correos de control encontrados | "
        f"Cantidad={len(email_uids)}"
    )

    return email_uids


# ============================================================
# LEER CORREO DE CONTROL
# ============================================================

def read_control_email(
    mail,
    email_uid
):

    if mail is None:

        raise RuntimeError(
            "La conexión Gmail es None."
        )

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

        log_error(
            f"Error leyendo correo de control | "
            f"UID={email_uid} | "
            f"{type(error).__name__}: {error}"
        )

        raise

    if status != "OK":

        error = RuntimeError(
            f"No se pudo leer correo de control "
            f"UID={email_uid}."
        )

        log_error(
            str(error)
        )

        raise error

    for response_part in msg_data:

        if not isinstance(
            response_part,
            tuple
        ):

            continue

        msg = (
            email.message_from_bytes(
                response_part[1]
            )
        )

        return parse_control_email(
            msg,
            email_uid
        )

    return None


# ============================================================
# MARCAR CONTROL COMO LEÍDO
# ============================================================

def mark_control_as_read(
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

        if status != "OK":

            log_warning(
                f"No se pudo marcar comando como leído | "
                f"UID={email_uid}"
            )

            return False

        log_info(
            f"Comando de control marcado como leído | "
            f"UID={email_uid}"
        )

        return True

    except Exception as error:

        log_error(
            f"Error marcando control como leído | "
            f"UID={email_uid} | "
            f"{type(error).__name__}: {error}"
        )

        return False