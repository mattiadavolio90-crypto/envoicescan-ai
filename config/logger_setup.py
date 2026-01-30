"""
Modulo centralizzato per configurazione logger.

Fornisce get_logger() per ottenere logger configurati uniformemente
in tutti i moduli del progetto FCI.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """
    Crea e restituisce un logger con nome standardizzato.
    
    Args:
        name: Nome modulo (es: 'auth', 'ai', 'db', 'invoice')
    
    Returns:
        logging.Logger: Logger configurato con nome 'fci_app.{name}'
    
    Example:
        >>> from config.logger_setup import get_logger
        >>> logger = get_logger('auth')
        >>> logger.info("Login effettuato")
    """
    logger_name = f'fci_app.{name}'
    return logging.getLogger(logger_name)


# Alias per compatibilità
setup_logger = get_logger
