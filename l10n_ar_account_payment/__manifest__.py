# Copyright 2020 AITIC S.A.S
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Payment improvements for Argentina",
    "summary": "Payment improvements for Argentina",
    "version": "14.0.1.0.0",
    "development_status": "Beta",
    "category": "Localization/Argentina",
    "website": "https://www.aitic.com.ar/",
    "author": "AITIC S.A.S.",
    "license": "AGPL-3",
    "depends": ["account_partial_payment_group",'l10n_ar_account_check', 'account_debit_note', 'account_payment_group_document'],
    "data": [
        'views/account_payment_group_view.xml',
    ],
    "application": False,
    "installable": True,
    'auto_install': True,
}
