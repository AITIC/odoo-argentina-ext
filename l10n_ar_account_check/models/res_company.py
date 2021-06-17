##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'
    sale_check_account_id = fields.Many2one(
        'account.account',
        'Account for the Sale of Check',
        help='Account where the balance of the debt contracted with the buyer of the check is recorded.',
    )

    def _get_check_account(self, check_type):
        if check_type == 'selled':
            account = self.sale_check_account_id
            return account
        return super(ResCompany, self)._get_check_account(check_type)
