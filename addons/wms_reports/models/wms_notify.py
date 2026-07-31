"""Shared "tell the WMS managers" helper (maturity C).

One place that decides HOW an alert reaches managers, so every alert
(low-stock, expiry, backup/restore failure, health) behaves the same:

  * In-app ALWAYS via ``message_notify`` -> Discuss Inbox + systray. A plain
    ``partner.message_post`` does NOT reach a user's inbox (a user doesn't
    follow their own contact) - that silent gap is exactly why this helper
    exists and why the older alerts were being missed.
  * Email when the System Parameter ``wms_reports.alert_email`` = 1
    (best-effort; a missing outgoing mail server never breaks the caller).

Best-effort throughout: a notification must never break the cron / action that
raised it.
"""

import logging

_logger = logging.getLogger(__name__)
_TRUE = ("1", "true", "True", "yes", "on")


def notify_wms_managers(env, body, subject):
    """Deliver ``body`` to every WMS manager in-app, and by email when enabled.

    :param env: an Odoo environment.
    :param body: Markup/HTML body.
    :param subject: short subject line.
    """
    managers = env.ref("wms_location.group_wms_manager", raise_if_not_found=False)
    if not managers or not managers.all_user_ids:
        return
    partners = managers.all_user_ids.partner_id
    try:
        env["mail.thread"].message_notify(partner_ids=partners.ids, body=body, subject=subject)
    except Exception:  # noqa: BLE001 - a notice must never break the caller
        _logger.exception("wms notify: in-app delivery failed (%s)", subject)

    email_on = env["ir.config_parameter"].sudo().get_param("wms_reports.alert_email", "0") in _TRUE
    if not email_on:
        return
    for user in managers.all_user_ids.filtered("email"):
        try:
            env["mail.mail"].sudo().create(
                {
                    "subject": subject,
                    "body_html": body,
                    "email_to": user.email,
                    "auto_delete": True,
                }
            ).send()
        except Exception:  # noqa: BLE001 - email is best-effort
            _logger.exception("wms notify: email failed for %s", user.login)
