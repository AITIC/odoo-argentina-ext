##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, _, api
from odoo.exceptions import UserError, ValidationError
import logging
# import odoo.addons.decimal_precision as dp
_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    check_issue_id = fields.Many2one(
        'account.check',
        string='Check',
    )
    not_endorsable = fields.Boolean(string='Not Endorsable')

    @api.onchange('check_number')
    def change_check_number(self):
        check_obj = self.env['account.check']
        for rec in self:
            if rec.payment_method_code in ['issue_check']:
                sequence = rec.checkbook_id.sequence_id
                if rec.check_number != sequence.number_next_actual:
                    check_obj._get_number(rec.checkbook_id, rec.check_number)
            if not rec.check_number:
                check_name = False
            else:
                check_name = check_obj._get_name_from_number(rec.check_number)
            rec.check_name = check_name

    def do_checks_operations(self, cancel=False):
        """
        Check attached .ods file on this module to understand checks workflows
        This method is called from:
        * cancellation of payment to execute delete the right operation and
            unlink check if needed
        * from _get_liquidity_move_line_vals to add check operation and, if
            needded, change payment vals and/or create check and
        TODO si queremos todos los del operation podriamos moverlos afuera y
        simplificarlo ya que es el mismo en casi todos
        Tambien podemos simplficiar las distintas opciones y como se recorren
        los if
        """
        self.ensure_one()
        vals = {}
        lot_operation = self._context.get('lot_operation', False)
        rec = self
        if not rec.check_type:
            # continue
            return vals
        if cancel:
            rec.check_ids._update_check_cancel(rec)
            return None
        if (
                rec.payment_method_code == 'received_third_check' and
                rec.payment_type == 'inbound'
                # el chequeo de partner type no seria necesario
                # un proveedor nos podria devolver plata con un cheque
                # and rec.partner_type == 'customer'
        ):
            operation = 'holding'
            # if cancel:
            #     _logger.info('Cancel Receive Check')
            #     rec.check_ids._del_operation(self)
            #     rec.check_ids.unlink()
            #     return None

            _logger.info('Receive Check')
            check = self.create_check(
                'third_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['account_id'] = check.get_third_check_account().id
            vals['name'] = _('Receive check %s') % check.name
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'transfer'):

            # TODO we should make this method selectable for transfers
            inbound_method = (
                rec.destination_journal_id.inbound_payment_method_ids)
            if len(inbound_method) == 1 and (
                    inbound_method.code == 'received_third_check'):

                _logger.info('Transfer Check')
                # get the account before changing the journal on the check
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                rec.check_ids._add_operation(
                    'transfered', rec, False, date=rec.payment_date, lot_operation=lot_operation)
                rec.check_ids._add_operation(
                    'holding', rec, False, date=rec.payment_date, lot_operation=lot_operation)
                rec.check_ids.write({
                    'journal_id': rec.destination_journal_id.id})
                vals['name'] = _('Transfer checks %s') % ', '.join(
                    rec.check_ids.mapped('name'))
            elif rec.destination_journal_id.type == 'cash':

                _logger.info('Change Check')
                rec.check_ids._add_operation(
                    'changed', rec, False, date=rec.payment_date, lot_operation=lot_operation)
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                vals['name'] = _('Change check %s') % ', '.join(
                    rec.check_ids.mapped('name'))
            else:

                _logger.info('Deposit Check')
                rec.check_ids._add_operation(
                    'deposited', rec, False, date=rec.payment_date, lot_operation=lot_operation)
                rec.check_ids.write({
                    'deposited_journal_id': rec.destination_journal_id.id,
                    'deposited_bank_id': rec.destination_journal_id.bank_id.id,
                    'deposited_date': rec.payment_date,
                })
                vals['account_id'] = rec.check_ids.get_third_check_account().id
                vals['name'] = _('Deposit checks %s') % ', '.join(
                    rec.check_ids.mapped('name'))
        elif (
                rec.payment_method_code == 'delivered_third_check' and
                rec.payment_type == 'outbound'
        ):

            _logger.info('Deliver Check')
            if len(rec.check_ids) == 1 and rec.check_ids.payment_date:
                vals['date_maturity'] = rec.check_ids.payment_date
            rec.check_ids._add_operation(
                'delivered', rec, rec.partner_id, date=rec.payment_date, lot_operation=lot_operation)
            vals['account_id'] = rec.check_ids.get_third_check_account().id
            vals['name'] = _('Deliver checks %s') % ', '.join(
                rec.check_ids.mapped('name'))
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'outbound'
        ):

            _logger.info('Hand/debit Check')
            vals['account_id'] = self.company_id._get_check_account(
                'deferred').id
            operation = 'handed'
            check = self.create_check(
                'issue_check', operation, self.check_bank_id)
            vals['date_maturity'] = self.check_payment_date
            vals['name'] = _('Hand check %s') % check.name
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'cash'):

            _logger.info('Withdraw Check')
            if rec.check_ids:
                rec.check_ids._add_operation(
                    'withdrawed', rec, rec.partner_id, date=rec.payment_date, lot_operation=lot_operation)
            else:
                self.create_check('issue_check', 'withdrawed', self.check_bank_id)
            vals['name'] = _('Withdraw with checks %s') % ', '.join(
                rec.check_ids.mapped('name'))
            vals['date_maturity'] = self.check_payment_date
        elif (
                rec.payment_method_code == 'issue_check' and
                rec.payment_type == 'transfer' and
                rec.destination_journal_id.type == 'bank'):

            _logger.info('Deposit Issue Check')
            if rec.check_ids:
                rec.check_ids._add_operation(
                    'deposited', rec, rec.partner_id, date=rec.payment_date, lot_operation=lot_operation)
            else:
                self.create_check('issue_check', 'deposited', self.check_bank_id)
            rec.check_ids.write({
                'deposited_journal_id': rec.destination_journal_id.id,
                'deposited_bank_id': rec.destination_journal_id.bank_id.id,
                'deposited_date': rec.payment_date,
            })
            vals['name'] = _('Withdraw with checks %s') % rec.check_ids[0].mapped('name')
            vals['date_maturity'] = rec.check_ids[0].payment_date

        else:
            raise UserError(_(
                'This operatios is not implemented for checks:\n'
                '* Payment type: %s\n'
                '* Partner type: %s\n'
                '* Payment method: %s\n'
                '* Destination journal: %s\n' % (
                    rec.payment_type,
                    rec.partner_type,
                    rec.payment_method_code,
                    rec.destination_journal_id.type)))
        return vals

    @api.onchange('check_issue_id')
    def onchange_check_issue_id(self):
        if self.check_issue_id:
            self.issue_check_subtype = self.check_issue_id.issue_check_subtype
            self.check_number = self.check_issue_id.number
            self.check_name = self.check_issue_id.name
            self.check_issue_date = self.check_issue_id.issue_date
            self.check_payment_date = self.check_issue_id.payment_date
            self.check_bank_id = self.check_issue_id.bank_id
            self.check_owner_vat = self.check_issue_id.owner_vat
            self.check_owner_name = self.check_issue_id.owner_name
            self.amount = self.check_issue_id.amount
            self.amount_company_currency = self.check_issue_id.amount_company_currency

    @api.onchange('checkbook_id')
    def onchange_checkbook(self):
        res = super(AccountPayment, self).onchange_checkbook()
        if not self.checkbook_id:
            self.check_issue_id = False
        return res

    @api.onchange('payment_method_code')
    def onchange_not_endorsable(self):
        if self.payment_type in ['outbound'] and self.payment_method_code == 'delivered_third_check':
            return {'domain': {'check_ids': [('not_endorsable', '=', False),
                                             ('journal_id', '=', self.journal_id.id),
                                             ('state', '=', 'holding'),
                                             ('type', '=', 'third_check')]}}

    def create_check(self, check_type, operation, bank):
        self.ensure_one()
        check_vals = {
            'owner_name': self.check_owner_name,
            'owner_vat': self.check_owner_vat,
            'number': self.check_number,
            'name': self.check_name,
            'issue_date': self.check_issue_date,
            'amount': self.amount,
            'payment_date': self.check_payment_date,
            'currency_id': self.currency_id.id,
            'amount_company_currency': self.amount_company_currency,
        }
        if check_type == 'issue_check' and self.check_issue_id:
            self.check_issue_id.write(check_vals)
            check = self.check_issue_id
            self.check_ids = [(4, self.check_issue_id.id, False)]
        else:
            check_vals.update({
                'bank_id': bank.id,
                'checkbook_id': self.checkbook_id.id,
                'issue_check_subtype': self.issue_check_subtype or self.checkbook_id.issue_check_subtype or 'deferred',
                'type': self.check_type,
                'journal_id': self.journal_id.id,
                'not_endorsable': self.not_endorsable,
            })
            if self.check_id and self.check_id.state == 'draft' and self.check_id == self.check_ids:
                self.check_id.write(check_vals)
                check = self.check_id
            else:
                check = self.env['account.check'].create(check_vals)
                self.check_ids = [(4, check.id, False)]
        check._add_operation(
            operation, self, self.partner_id, date=self.payment_date)
        return check