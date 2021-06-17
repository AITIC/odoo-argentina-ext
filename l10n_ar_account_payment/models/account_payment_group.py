# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"

    def get_sequence_name(self):
        self.ensure_one()
        return False

    def action_post(self):
        for rec in self:
            if not rec.document_number:
                if rec.receiptbook_id and not rec.receiptbook_id.sequence_id:
                    raise UserError(_(
                        'Error!. Please define sequence on the receiptbook'
                        ' related documents to this payment or set the '
                        'document number.'))
                if rec.receiptbook_id.sequence_id:
                    rec.document_number = (
                        rec.receiptbook_id.with_context(
                            ir_sequence_date=rec.payment_date
                        ).sequence_id.next_by_id())
            # rec.payment_ids.move_name = rec.name

            # hacemos el llamado acá y no arriba para primero hacer los checks
            # y ademas primero limpiar o copiar talonario antes de postear.
            # lo hacemos antes de mandar email asi sale correctamente numerado
            # necesitamos realmente mandar el tipo de documento? lo necesitamos para algo?
            super(AccountPaymentGroup, self.with_context(
                default_l10n_latam_document_type_id=rec.document_type_id.id)).action_post()
            if not rec.receiptbook_id:
                rec.name = any(
                    rec.payment_ids.mapped('name')) and ', '.join(
                    rec.payment_ids.mapped('name')) or False

        for rec in self:
            if rec.receiptbook_id.mail_template_id:
                rec.message_post_with_template(
                    rec.receiptbook_id.mail_template_id.id,
                )
        return True