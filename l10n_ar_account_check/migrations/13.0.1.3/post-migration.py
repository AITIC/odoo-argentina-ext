# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api
from odoo import SUPERUSER_ID

def update_debit_operation(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    check_ids = env['account.check'].search([('state', '=', 'debited'), ('type', '=', 'issue_check')])
    for check_id in check_ids:
        operation = check_id._get_operation(check_id.state)
        if operation and operation.origin and operation.origin._name == 'account.move':
            operation_first = check_id._get_operation('handed', False) or check_id._get_operation('selled', False)
            if operation_first:
                operation.origin.button_draft()
                operation.origin.write({
                    'partner_id': operation_first.partner_id.id
                })
                operation.origin.line_ids.write({
                    'partner_id': operation_first.partner_id.id
                })
                operation.origin.action_post()
                operation.write({
                    'partner_id': operation_first.partner_id.id
                })

def migrate(cr, version):
    update_debit_operation(cr)

