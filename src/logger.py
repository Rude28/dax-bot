import logging
import os


# ============================================================
# CONFIGURACIÓN
# ============================================================

LOG_DIR = "logs"

LOG_FILE = os.path.join(
    LOG_DIR,
    "dax_bot.log"
)


# ============================================================
# CREAR DIRECTORIO
# ============================================================

os.makedirs(
    LOG_DIR,
    exist_ok=True
)


# ============================================================
# LOGGER
# ============================================================

logger = logging.getLogger(
    "dax_bot"
)

logger.setLevel(
    logging.INFO
)


# ============================================================
# EVITAR HANDLERS DUPLICADOS
# ============================================================

if not logger.handlers:

    # --------------------------------------------------------
    # Formato
    # --------------------------------------------------------

    formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # Archivo
    # --------------------------------------------------------

    file_handler = (
        logging.FileHandler(
            LOG_FILE,
            encoding="utf-8"
        )
    )

    file_handler.setLevel(
        logging.INFO
    )

    file_handler.setFormatter(
        formatter
    )

    # --------------------------------------------------------
    # Consola
    # --------------------------------------------------------

    console_handler = (
        logging.StreamHandler()
    )

    console_handler.setLevel(
        logging.INFO
    )

    console_handler.setFormatter(
        formatter
    )

    # --------------------------------------------------------
    # Añadir handlers
    # --------------------------------------------------------

    logger.addHandler(
        file_handler
    )

    logger.addHandler(
        console_handler
    )


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def log_info(message):
    logger.info(message)


def log_warning(message):
    logger.warning(message)


def log_error(message):
    logger.error(message)


def log_debug(message):
    logger.debug(message)