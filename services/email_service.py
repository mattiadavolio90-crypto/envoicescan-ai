"""Invio email via Brevo e template HTML condiviso.

Qui vive l'unico punto da cui il worker spedisce: onboarding, reinvio
attivazione e reset admin (`services/routers/admin.py`) e l'email settimanale
dell'assistente (`services/email_settimanale_service.py`). Stava in admin.py;
spostato il 24/09/2026 perche' un secondo router non importi un router.

Il reset self-service (`services/auth_service.invia_codice_reset`) ha ancora la
sua copia: stesso mittente per costruzione (`BREVO_SENDER_EMAIL_DEFAULT`),
presidiato da tests/test_brevo_mittente_default.py.
"""
from __future__ import annotations

import os
from typing import Dict, Optional

from config.constants import (
    APP_URL,
    BREVO_SENDER_EMAIL_DEFAULT,
    BREVO_SENDER_NAME_DEFAULT,
)
from config.logger_setup import get_logger

logger = get_logger("email_service")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def brevo_send(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    *,
    contesto: str = "email",
    text_body: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> bool:
    """Invia un'email via Brevo. Ritorna True solo su status 201.

    Mittente: BREVO_SENDER_EMAIL, che DEVE essere un sender verificato in Brevo
    (default agent@oneflux.it): un mittente non verificato fa fallire l'invio in
    silenzio. `headers` finisce nelle intestazioni del messaggio (es.
    List-Unsubscribe); `text_body` e' la versione solo testo.
    """
    import requests as _requests

    brevo_key = os.getenv("BREVO_API_KEY", "")
    if not brevo_key:
        logger.warning("Email %s non inviata: BREVO_API_KEY mancante", contesto)
        return False
    sender_email = os.getenv("BREVO_SENDER_EMAIL", BREVO_SENDER_EMAIL_DEFAULT)
    sender_name = os.getenv("BREVO_SENDER_NAME", BREVO_SENDER_NAME_DEFAULT)
    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": to_email, "name": to_name}],
        "replyTo": {"email": "md@oneflux.it", "name": "Mattia - ONEFLUX"},
        "subject": subject,
        "htmlContent": html_body,
    }
    if text_body:
        payload["textContent"] = text_body
    if headers:
        payload["headers"] = dict(headers)
    try:
        r = _requests.post(
            BREVO_URL,
            json=payload,
            headers={"api-key": brevo_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if r.status_code != 201:
            logger.warning("Brevo %s KO: status=%s (sender=%s)", contesto, r.status_code, sender_email)
        return r.status_code == 201
    except Exception as exc:
        logger.warning("Errore invio email %s: %s", contesto, exc)
        return False


def email_template(
    *,
    titolo: str,
    corpo_html: str,
    cta_label: str,
    cta_link: str,
    nota: str = "",
    piede_html: str = "",
) -> str:
    """Template HTML condiviso (onboarding, reset, email settimanale).

    Tabella con attributi bgcolor/width invece di solo CSS: i client aziendali
    (Outlook desktop su motore Word) ignorano gran parte del CSS moderno.
    `piede_html` va sotto la firma (es. il link per disiscriversi).
    """
    nota_html = f'<tr><td align="center" style="padding:20px 40px 4px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:20px;color:#f59e0b;text-align:center;">{nota}</td></tr>' if nota else ""
    piede = (
        f'<p style="margin:12px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#64748b;">{piede_html}</p>'
        if piede_html else ""
    )
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0a0e14;padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background-color:#12161f;border:1px solid #232936;border-radius:12px;">
        <tr>
          <td style="padding:32px 40px 8px;font-family:Arial,Helvetica,sans-serif;">
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding-right:10px;vertical-align:middle;">
                  <img src="{APP_URL}/icons/icon-192.png" width="28" height="28" alt="ONEFLUX" style="display:block;border-radius:50%;">
                </td>
                <td style="vertical-align:middle;">
                  <span style="font-size:20px;font-weight:bold;color:#38bdf8;">ONEFLUX</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 40px 0;font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:bold;color:#f1f5f9;">
            {titolo}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 40px 0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:24px;color:#cbd5e1;">
            {corpo_html}
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:28px 40px 8px;">
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center" bgcolor="#0ea5e9" style="border-radius:8px;">
                  <a href="{cta_link}" style="display:inline-block;padding:14px 32px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;">
                    {cta_label}
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        {nota_html}
        <tr>
          <td style="padding:24px 40px 32px;">
            <hr style="border:none;border-top:1px solid #232936;margin:0 0 16px;">
            <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#64748b;">
              ONEFLUX Team — <a href="mailto:agent@oneflux.it" style="color:#64748b;">agent@oneflux.it</a>
            </p>{piede}
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""
