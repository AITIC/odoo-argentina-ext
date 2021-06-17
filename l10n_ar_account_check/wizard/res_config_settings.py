from odoo import fields, models
# from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sale_check_account_id = fields.Many2one(
        related='company_id.sale_check_account_id',
        readonly=False,
    )
