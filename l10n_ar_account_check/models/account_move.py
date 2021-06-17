##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    used_check_ids = fields.Many2many(
        'account.check',
        string='Used Check',
        copy=False
    )

    lot_operation = fields.Char(
        string="Lot Operation",
        copy=False
    )

    def _get_l10n_latam_documents_domain(self):
        self.ensure_one()
        domain = super()._get_l10n_latam_documents_domain()
        if self.journal_id.company_id.country_id == self.env.ref('base.ar'):
            if self.rejected_check_id and self.type in ['out_invoice', 'in_invoice']:
                for i in range(len(domain)):
                    if domain[i][0] == 'internal_type':
                        aux = list(domain[i])
                        aux[1] = '='
                        aux[2] = 'debit_note'
                        domain[i] = tuple(aux)
        return domain

    def post(self):
        """
        Si al validar la factura, la misma tiene un cheque de rechazo asociado
        intentamos concilarlo
        """
        res = super().post()
        for rec in self.filtered(lambda x: x.used_check_ids):
            if rec.used_check_ids:
                rec.used_check_ids._add_operation('used', rec, rec.partner_id, rec.date, rec.lot_operation)
        return res
