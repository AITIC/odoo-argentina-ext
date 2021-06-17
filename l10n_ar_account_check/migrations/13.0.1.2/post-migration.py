# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import api
from odoo import SUPERUSER_ID

def update_last_partner(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    check_ids = env['account.check'].search([])
    for check_id in check_ids:
        if check_id.operation_ids and check_id.operation_ids.filtered(lambda x: x.partner_id
                                                                      ).partner_id != check_id.partner_id:
            check_id.write({
                'partner_id': check_id.operation_ids[0].partner_id
            })


def migrate(cr, version):
    update_last_partner(cr)

