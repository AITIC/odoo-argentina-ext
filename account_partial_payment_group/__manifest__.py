# Copyright 2020 AITIC S.A.S
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Partial Account Payment with Multiple methods",
    "summary": "It allows to partially pay several debts allowing to define an amount to be paid at the user's discretion.",
    "version": "13.0.1.0.0",
    "development_status": "Beta",
    "category": "Accounting",
    "website": "https://www.aitic.com.ar/",
    "author": "AITIC S.A.S.",
    "license": "AGPL-3",
    "application": False,
    'installable': True,
    "depends": ["account_payment_group", "account_accountant"],
    "data": [
        'security/ir.model.access.csv',
        'views/account_move_line_view.xml',
        'views/account_payment_group_view.xml',
        'views/account_payment_view.xml',
        'data/account_accountant_data.xml',
    ],
}
