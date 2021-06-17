##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import fields, models, _, api
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)


class AccountCheckOperation(models.Model):
    _inherit = 'account.check.operation'

    operation = fields.Selection(selection_add=[
        ('draft', 'Draft'),
        ('used', 'In use'),
        ('negotiated', 'Negotiate'),
    ])
    lot_operation = fields.Char(
        string='Lot operation'
    )

class AccountCheck(models.Model):
    _inherit = 'account.check'

    name = fields.Char(
        required=False,
        readonly=True,
        copy=False,
        states={'draft': [('readonly', False)]},
        index=True,
    )
    state = fields.Selection(selection_add=[
        ('draft', 'Draft'),
        ('used', 'In use'),
        ('negotiated', 'Negotiate'),
    ])
    deposited_date = fields.Date(
        string='Deposited date'
    )
    deposited_journal_id = fields.Many2one(
        'account.journal',
        string='Deposited Journal'
    )
    deposited_bank_id = fields.Many2one(
        'res.bank',
        string='Deposited Bank'
    )
    notes = fields.Text(
        string='Note'
    )
    lot_operation = fields.Char(
        string='Lot operation',
        copy=True,
        compute='_compute_lot_operation',
    )
    first_operation_id = fields.Many2one(
        'account.check.operation',
        compute='_compute_first_partner',
        string='First operation',
        readonly=True,
        store=True,
        compute_sudo=True
    )
    note = fields.Char(string='Note')
    not_endorsable = fields.Boolean(
        string='Not Endorsable',
        readonly=True,
        states={'draft': [('readonly', False)],
                'holding': [('readonly', False)]}
    )
    first_partner_id = fields.Many2one(
        'res.partner',
        compute='_compute_first_partner',
        string='First operation partner',
        readonly=True,
        store=False,
        compute_sudo=True
    )

    @api.depends('operation_ids', 'operation_ids.partner_id')
    def _compute_first_partner(self):
        for rec in self:
            if not rec.operation_ids:
                rec.first_partner_id = False
                rec.first_operation_id = False
                continue
            rec.first_partner_id = rec.operation_ids[-1].partner_id
            rec.first_operation_id = rec.operation_ids[-1].id

    @api.depends(
        'operation_ids.operation',
        'operation_ids.lot_operation',
    )
    def _compute_lot_operation(self):
        for rec in self:
            if rec.operation_ids.sorted():
                rec.lot_operation = rec.operation_ids.sorted()[0].lot_operation
            else:
                rec.lot_operation = False

    @api.onchange('number')
    def onchange_number(self):
        for rec in self:
            rec.name = self._get_name_from_number(rec.number)

    @api.onchange('journal_id')
    def onchange_journal_id(self):
        for rec in self:
            if rec.journal_id and rec.type == 'issue_check':
                rec.bank_id = rec.journal_id.bank_id

    @api.onchange('amount', 'currency_id')
    def onchange_amount(self):
        for rec in self:
            if rec.amount and rec.currency_id and rec.currency_id != rec.company_currency_id:
                rec.amount_company_currency = rec.currency_id._convert(
                    rec.amount, rec.company_id.currency_id,
                    rec.company_id, rec.issue_date)
            else:
                rec.amount_company_currency = rec.amount

    def _add_operation(
            self, operation, origin, partner=None, date=False, lot_operation=False):
        for rec in self:
            if not self._context.get('no_check'):
                rec._check_state_change(operation)
                # agregamos validacion de fechas
                date = date or fields.Datetime.now()
                if rec.operation_ids and rec.operation_ids[0].date > date:
                    raise ValidationError(_(
                        'The date of a new check operation can not be minor than '
                        'last operation date.\n'
                        '* Check Id: %s\n'
                        '* Check Number: %s\n'
                        '* Operation: %s\n'
                        '* Operation Date: %s\n'
                        '* Last Operation Date: %s') % (
                        rec.id, rec.name, operation, date,
                        rec.operation_ids[0].date))
            vals = {
                'operation': operation,
                'date': date,
                'check_id': rec.id,
                'origin': origin and '%s,%i' % (origin._name, origin.id) or False,
                'partner_id': partner and partner.id or False,
                'lot_operation': lot_operation,
            }
            rec.operation_ids.create(vals)

    def used(self):
        if all([x.state in ['draft'] and x.type == 'issue_check' for x in self]):
            if self._context.get('lot_operation', False):
                name = _('Lot Checks "%s" used') % (self._context.get('lot_operation'))
            else:
                name = _('Check "%s" used') % (self[0].name)
            view_id = self.env.ref('account.view_move_form').id
            journal = self[0].journal_id
            partner_id = self._context.get('partner', False)
            vals = self.get_used_values(journal, name, partner_id, self._context.get('lot_operation'))
            action_context = vals
            return {
                'name': name,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.move',
                'view_id': view_id,
                'type': 'ir.actions.act_window',
                'context': action_context,
            }

    def get_used_values(self, journal, name, partner_id, lot_operation):
        amount = sum(self.mapped('amount'))
        credit_account = journal.default_debit_account_id
        credit_line_vals = {
            'name': name,
            'account_id': credit_account.id,
            'debit': 0.0,
            'credit': amount,
            'exclude_from_invoice_tab': True
        }
        if partner_id:
            credit_line_vals['partner_id'] = partner_id.id
        return {
            'default_ref': name,
            'default_type': 'entry',
            'default_auto_post': True,
            'default_journal_id': journal.id,
            'default_partner_id': partner_id and partner_id.id or False,
            'default_date': self._context.get('action_date'),
            'default_used_check_ids': [(6, 0, self.ids)],
            'default_lot_operation': lot_operation,
            'default_line_ids': [(0, 0, credit_line_vals)]
        }

    def negotiated(self):
        if all([x.state in ['draft', 'holding'] for x in self]):
            action_date = self._context.get('action_date')
            partner = self._context.get('partner', False) or self.company_id.partner_id
            lot_operation = self._context.get('lot_operation')
            self._add_operation('negotiated', False, partner, action_date, lot_operation)

    def selled(self):
        if all([x.state in ['negotiated'] for x in self]):
            action_date = self._context.get('action_date')
            partner = self._context.get('partner', False)
            journal = self._context.get('journal', False)
            expense_account = self._context.get('expense_account', False)
            debit_note = self._context.get('debit_note', False)
            expense_amount = self._context.get('expense_amount', 0.0)
            if not self[0].company_id._get_check_account('selled'):
                raise UserError(_(
                    'You must set the checking account sold in the accounting settings.'))
            if journal and expense_account:
                if self._context.get('lot_operation', False):
                    name = _('Lot Checks "%s" selled') % (self._context.get('lot_operation'))
                else:
                    name = _('Check "%s" selled') % (self[0].name)
                amount_total = sum(x.amount for x in self)
                vals = self[0].get_move_values(name,
                    debit_note, journal, expense_account, expense_amount, amount_total)

                action_date = self._context.get('action_date')
                lot_operation = self._context.get('lot_operation', False)
                vals['date'] = action_date
                move = self.env['account.move'].create(vals)
                move.post()
                self._add_operation('selled', move, partner, action_date, lot_operation)
                if debit_note and expense_amount > 0.0:
                    tax_ids = self._context.get('tax_ids')
                    return self[0].action_create_debit_note('selled', 'supplier', partner,
                                                            expense_account, expense_amount, tax_ids)

    def deposited(self):
        if all([x.state in ['draft', 'holding'] for x in self]) or \
                (all([x.state in ['rejected'] for x in self]) and self._context.get('no_check_op', False)):
            journal = self._context.get('journal', False)
            if journal:
                payment_ids = self.env['account.payment']
                if self[0].type == 'third_check':
                    payment_ids += self.create_payment_deposited(journal, self[0].type)
                else:
                    for rec in self:
                        payment_ids += rec.create_payment_deposited(journal, rec.type)
                action = self.env.ref('account_payment_group.action_account_payments_transfer').read()[0]
                action['name'] = _('Deposited Checks')
                action['domain'] = [('id', 'in', payment_ids.ids)]
                return action

    def create_payment_deposited(self, journal, type):
        vals = self[0].get_payment_values(self[0].journal_id)
        ctx = dict(self._context)
        if type == 'third_check':
            vals['check_ids'] = [(4, check.id, None) for check in self]
            payment_method_code_id = self.env['account.payment.method'].search(
                                                [('code', '=', 'delivered_third_check')])
            if payment_method_code_id:
                vals['payment_method_id'] = payment_method_code_id.id
        else:
            # vals['check_id'] = self.id
            vals['check_ids'] = [(4, self.id, None)]
            vals['check_number'] = self.number
            vals['checkbook_id'] = self.checkbook_id.id
            vals['check_name'] = self.name
            payment_method_code_id = self.env['account.payment.method'].search(
                [('code', '=', 'issue_check')])
            if payment_method_code_id:
                vals['payment_method_id'] = payment_method_code_id.id
        vals['communication'] = self._context.get('communication', False)
        vals['payment_type'] = 'transfer'
        vals['destination_journal_id'] = journal.id,
        payment = self.env['account.payment'].with_context(ctx).create(vals)
        payment.post()
        return payment

    def get_move_values(self, name, debit_note, journal, expense_account, expense_amount, amount_total=0.0):
        if self.type == 'third_check':
            credit_account = self[0].journal_id.default_credit_account_id
        else:
            credit_account = self[0].company_id._get_check_account('selled')
        debit_account = journal.default_debit_account_id
        debit = amount_total
        amount_move = amount_total
        line_ids = []
        debit_line_vals1 = False
        if not debit_note:
            debit = amount_move - expense_amount
            debit_line_vals1 = {
                'name': name,
                'account_id': expense_account.id,
                'debit': expense_amount,
                'exclude_from_invoice_tab': True
                # 'amount_currency': self.amount_currency,
                # 'currency_id': self.currency_id.id,
            }
        debit_line_vals = {
            'name': name,
            'account_id': debit_account.id,
            'debit': debit,
            'exclude_from_invoice_tab': True
            # 'amount_currency': self.amount_currency,
            # 'currency_id': self.currency_id.id,
        }
        line_ids.append((0, False, debit_line_vals))
        if debit_line_vals1:
            line_ids.append((0, False, debit_line_vals1))
        credit_line_vals = {
            'name': name,
            'account_id': credit_account.id,
            'credit': amount_move,
            'exclude_from_invoice_tab': True
            # 'amount_currency': self.amount_currency,
            # 'currency_id': self.currency_id.id,
        }
        line_ids.append((0, False, credit_line_vals))
        return {
            'ref': name,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'line_ids': line_ids,
            'type': 'entry',
        }

    def _check_state_change(self, operation):
        """
        We only check state change from _add_operation because we want to
        leave the user the possibility of making anything from interface.
        Necesitamos este chequeo para evitar, por ejemplo, que un cheque se
        agregue dos veces en un pago y luego al confirmar se entregue dos veces
        On operation_from_state_map dictionary:
        * key is 'to state'
        * value is 'from states'
        """
        self.ensure_one()
        # if we do it from _add_operation only, not from a contraint of before
        # computing the value, we can just read it
        old_state = self.state
        operation_from_state_map = {
            # 'draft': [False],
            'holding': [
                'draft', 'deposited', 'changed', 'delivered', 'transfered'],
            'delivered': ['holding'],
            'deposited': ['holding', 'rejected', 'draft'],
            'changed': ['holding'],
            'handed': ['draft'],
            'transfered': ['holding'],
            'withdrawed': ['draft'],
            'rejected': ['delivered', 'deposited', 'changed', 'handed'],
            'debited': ['handed', 'selled'],
            'returned': ['handed', 'holding'],
            'used': ['draft'],
            'negotiated': ['draft', 'holding'],
            'selled': ['negotiated'],
            'cancel': ['draft'],
            'reclaimed': ['rejected'],
        }
        from_states = operation_from_state_map.get(operation)
        if not from_states:
            raise ValidationError(_(
                'Operation %s not implemented for checks!') % operation)
        if old_state not in from_states:
            raise ValidationError(_(
                'You can not "%s" a check from state "%s"!\n'
                'Check nbr (id): %s (%s)') % (
                    self.operation_ids._fields['operation'].convert_to_export(
                        operation, self),
                    self._fields['state'].convert_to_export(old_state, self),
                    self.name,
                    self.id))

    def handed_reconcile(self, move):
        """
        Funcion que por ahora solo intenta conciliar cheques propios entregados
        cuando se hace un debito o cuando el proveedor lo rechaza
        """

        self.ensure_one()
        if self.state == 'selled':
            debit_account = self.company_id._get_check_account('selled')
            operation = self._get_operation('selled')
        else:
            debit_account = self.company_id._get_check_account('deferred')
            operation = self._get_operation("handed")

        # conciliamos
        if debit_account.reconcile:
            if operation.origin._name == 'account.payment':
                move_lines = operation.origin.move_line_ids
            elif operation.origin._name == 'account.move':
                move_lines = operation.origin.line_ids
            move_lines |= move.line_ids
            move_lines = move_lines.filtered(
                lambda x: x.account_id == debit_account)
            if len(move_lines) != 2:
                raise ValidationError(_(
                    'We have found more or less than two journal items to '
                    'reconcile with check debit.\n'
                    '*Journal items: %s') % move_lines.ids)
            move_lines.reconcile()

    def _get_related_invoice(self):
        self.ensure_one()
        related_inv = False
        for move in self.operation_ids.filtered(lambda o: o.operation == 'holding').sorted(lambda o: o.id):
            if move.origin and getattr(move.origin, 'invoice_ids') and move.origin.invoice_ids:
                related_inv = move.origin.invoice_ids.filtered(lambda x: x.is_invoice())
            elif move.origin and getattr(move.origin, 'reconciled_invoice_ids') and move.origin.reconciled_invoice_ids:
                related_inv = move.origin.reconciled_invoice_ids.filtered(
                    lambda x: x.is_invoice() and x.l10n_latam_document_type_id)
        if related_inv:
            return related_inv[0]
        else:
            return related_inv

    def action_create_debit_note(
            self, operation, partner_type, partner, account, amount=0.0, tax_ids=False):
        self.ensure_one()
        action_date = self._context.get('action_date')

        if partner_type == 'supplier':
            invoice_type = 'in_invoice'
            journal_type = 'purchase'
        else:
            invoice_type = 'out_invoice'
            journal_type = 'sale'

        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', journal_type),
        ], limit=1)

        related_inv = self._get_related_invoice()

        # si pedimos rejected o reclamo, devolvemos mensaje de rechazo y cuenta
        # de rechazo
        if operation in ['rejected', 'reclaimed']:
            name = 'Rechazo cheque "%s"' % (self.name)
        # si pedimos la de holding es una devolucion
        elif operation == 'returned':
            name = 'Devolución cheque "%s"' % (self.name)
        elif operation == 'selled':
            name = 'Venta de cheque "%s"' % (self.name)
        else:
            raise ValidationError(_(
                'Debit note for operation %s not implemented!' % (
                    operation)))
        price_unit = self.amount
        if amount > 0.0:
            price_unit = amount

        inv_line_vals = {
            # 'product_id': self.product_id.id,
            'name': name,
            'account_id': account.id,
            'price_unit': price_unit,
            # 'invoice_id': invoice.id,
        }
        if tax_ids:
            inv_line_vals['tax_ids'] = [(6, 0, tax_ids.ids)]

        inv_vals = {
            # this is the reference that goes on account.move.line of debt line
            # 'name': name,
            # this is the reference that goes on account.move
            'rejected_check_id': self.id,
            'ref': name,
            'invoice_date': action_date,
            'invoice_origin': _('Check nbr (id): %s (%s)') % (self.name, self.id),
            'journal_id': journal.id,
            # this is done on muticompany fix
            # 'company_id': journal.company_id.id,
            'partner_id': partner.id,
            'type': invoice_type,
            'debit_origin_id': related_inv and related_inv.id or False,
            'invoice_line_ids': [(0, 0, inv_line_vals)],
        }
        if self.currency_id:
            inv_vals['currency_id'] = self.currency_id.id
        # we send internal_type for compatibility with account_document
        invoice = self.env['account.move'].with_context(
            company_id=journal.company_id.id, force_company=journal.company_id.id,
            internal_type='debit_note').create(inv_vals)
        if not operation == 'selled':
            self._add_operation(operation, invoice, partner, date=action_date)

        return {
            'name': name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'type': 'ir.actions.act_window',
        }

    def name_get(self):
        result = []
        for record in self:
            name = record.name or ''
            if not record.name:
                name = record.number and str(record.number) or ''
            if record.bank_id:
                name += ' / ' + record.bank_id.name
            if record.owner_name:
                name += ' / ' + record.owner_name
            result.append((record.id, name))
        return result

    def _get_name_from_number(self, number):
        padding = 8
        if len(str(number)) > padding:
            padding = len(str(number))
        return ('%%0%sd' % padding % number)

    def _get_number(self, checkbook_id, number=False):
        if checkbook_id and not checkbook_id.numerate_on_printing:
            sequence = checkbook_id.sequence_id
            if number:
                sequence.sudo().write(
                    {
                        'number_next_actual': number
                    })
            else:
                number = checkbook_id.next_number
            sequence.next_by_id()
        return number

    @api.model
    def create(self, vals):
        checkbook = self.env['account.checkbook']
        if vals.get('checkbook_id') and not vals.get('number', False):
            checkbook_id = checkbook.browse(vals.get('checkbook_id'))
            vals['number'] = self._get_number(checkbook_id)
        if (not vals.get('name', False) or vals['name'] == '00000000')and vals['number']:
            vals['name'] = self._get_name_from_number(vals['number'])
        return super(AccountCheck, self).create(vals)

    def _update_check_cancel(self, payment):
        for rec in self:
            if rec.state in ['holding'] and rec.type == 'third_check' and payment.payment_type in ['inbound',
                                                                                                   'transfer']:
                operation = rec._get_init_operation('holding', True)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    rec.with_context(no_check=True)._add_operation('draft', payment, operation.partner_id, date=operation.date)
                if payment.payment_method_code == 'delivered_third_check' and payment.payment_type == 'transfer':
                    inbound_method = (payment.destination_journal_id.inbound_payment_method_ids)
                    if len(inbound_method) == 1 and (
                            inbound_method.code == 'received_third_check'):
                        rec.journal_id = operation.origin.journal_id.id

            elif rec.state in ['changed', 'deposited'] and rec.type == 'third_check' and payment.payment_type in ['transfer']:
                operation = rec._get_operation(rec.state, False)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    operation = rec._get_init_operation('holding', True)
                    payment_link = operation.origin if operation.origin._name == 'account.payment' else payment
                    rec.with_context(no_check=True)._add_operation('holding', payment_link, operation.partner_id, date=operation.date)

            elif rec.state in ['delivered'] and rec.type == 'third_check' and payment.payment_type == 'outbound':
                operation = rec._get_operation('delivered', True)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    operation_holding = rec._get_init_operation('holding', True)
                    payment_link = operation_holding.origin if operation_holding.origin and operation_holding.origin._name == 'account.payment' else False
                    rec.with_context(no_check=True)._add_operation('holding', payment_link, operation_holding.partner_id, date=operation.date)

            elif rec.state in ['handed'] and rec.type == 'issue_check':
                operation = rec._get_operation('handed', True)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    rec.with_context(no_check=True)._add_operation('draft', payment, operation.partner_id, date=operation.date)

            elif rec.state in ['deposited'] and rec.type == 'issue_check' and payment.payment_type == 'transfer':
                operation = rec._get_operation('deposited', False)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    rec.with_context(no_check=True)._add_operation('draft', payment, operation.partner_id, date=operation.date)

            elif rec.state in ['withdrawed'] and rec.type == 'issue_check' and payment.payment_type == 'transfer':
                operation = rec._get_operation('withdrawed', False)
                if operation and operation.origin and operation.origin._name == 'account.payment':
                    rec.with_context(no_check=True)._add_operation('draft', payment, operation.partner_id, date=operation.date)

            elif rec.state in ['rejected'] and payment.payment_type == 'transfer' and self._context.get('no_check_op', False):
                return
            # elif rec.state in ['transfered'] and payment.payment_type == 'transfer':
            #     operation = self.operation_ids.search([('check_id', '=', self.id)], limit=2)
            #     if operation and operation[0].origin and operation[0].origin._name == 'account.payment':
            #         rec.with_context(no_check=True)._add_operation(operation[1].operation, operation[1].origin, operation.partner_id,
            #                               date=operation.date)
            else:
                raise UserError(
                    _(
                        'You cannot cancel a payment with a %s check because you are in another state unrelated to the payment, this check operation must be changed.') % rec.number)

    def _get_init_operation(self, operation, partner_required=False):
        self.ensure_one()
        op = self.operation_ids.search([
            ('check_id', '=', self.id), ('operation', '=', operation)], order='date,id asc',
            limit=1)
        if partner_required:
            if not op.partner_id:
                raise ValidationError((
                    'The %s (id %s) operation has no partner linked.'
                    'You will need to do it manually.') % (operation, op.id))
        return op

    def _get_operation(self, operation, partner_required=False):
        self.ensure_one()
        op = self.operation_ids.search([
            ('check_id', '=', self.id), ('operation', '=', operation)],
            limit=1)
        if partner_required:
            if not op.partner_id:
                raise ValidationError((
                                          'The %s (id %s) operation has no partner linked.'
                                          'You will need to do it manually.') % (operation, op.id))
        return op

    def bank_debit(self):
        self.ensure_one()
        if self.state in ['handed']:
            payment_values = self.get_payment_values(self.journal_id)
            payment = self.env['account.payment'].with_context(
                default_name=_('Check "%s" debit') % (self.name),
                force_account_id=self.company_id._get_check_account(
                    'deferred').id,
            ).create(payment_values)
            self.post_payment_check(payment)
            self.handed_reconcile(payment.move_line_ids.mapped('move_id'))
            self._add_operation('debited', payment, date=payment.payment_date)

    def bank_debit(self):
        for rec in self:
            if rec.state in ['handed', 'selled'] and rec.type == 'issue_check':
                if rec.state == 'selled':
                    vals = rec.get_bank_vals(
                        'bank_debit_selled', rec.journal_id)
                else:
                    vals = rec.get_bank_vals(
                        'bank_debit', rec.journal_id)
                action_date = self._context.get('action_date')
                vals['date'] = action_date
                move = self.env['account.move'].create(vals)
                rec.handed_reconcile(move)
                move.post()
                rec._add_operation('debited', move, date=action_date)

    def get_bank_vals(self, action, journal):
        self.ensure_one()
        if action == 'bank_debit':
            credit_account = journal.default_debit_account_id
            debit_account = self.company_id._get_check_account('deferred')
            name = _('Check "%s" debit') % (self.name)
        elif action == 'bank_debit_selled':
            credit_account = journal.default_debit_account_id
            debit_account = self.company_id._get_check_account('selled')
            name = _('Check "%s" debit') % (self.name)
        # elif action == 'bank_reject':
        #     credit_account = journal.default_debit_account_id
        #     debit_account = self.company_id._get_check_account('rejected')
        #     name = _('Check "%s" rejection') % (self.name)
        else:
            raise ValidationError(_(
                'Action %s not implemented for checks!') % action)
        debit_line_vals = {
            'name': name,
            'account_id': debit_account.id,
            'debit': self.amount,
            'amount_currency': self.amount_company_currency * -1 if self.currency_id != self.company_currency_id else 0.0,
            'currency_id': self.currency_id.id if self.currency_id != self.company_currency_id else False,
        }
        credit_line_vals = {
            'name': name,
            'account_id': credit_account.id,
            'credit': self.amount,
            'amount_currency': self.amount_company_currency * -1 if self.currency_id != self.company_currency_id else 0.0,
            'currency_id': self.currency_id.id if self.currency_id != self.company_currency_id else False,
        }
        return {
            'ref': name,
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, False, debit_line_vals),
                (0, False, credit_line_vals)],
        }

    def re_deposited(self):
        self.ensure_one()
        if self.state in ['rejected']:
            operation = self._get_operation(self.state)
            op_deposited = self.operation_ids.search([
                ('check_id', '=', self.id), ('id', '<', operation.id)],
                limit=1)
            action_date = self._context.get('action_date')
            if action_date < operation.date:
                raise ValidationError(_(
                    'The re-deposit date must be greater than the banks rejection date.'))
            journal = operation.origin.journal_id
            if op_deposited.operation == 'deposited':
                if operation.origin and operation.origin._name == 'account.payment':
                    payment_vals = self.get_payment_values(journal)
                    payment_vals['payment_type'] = 'inbound'
                    payment = self.env['account.payment'].with_context(
                        default_name=_('Check "%s" re-deposited') % (self.name),
                        force_account_id=self.company_id._get_check_account(
                            'rejected').id,
                    ).create(payment_vals)
                    self.post_payment_check(payment)
                    self._add_operation('deposited', payment, date=payment.payment_date)
                #         and \
                #         op_deposited.origin._name == 'account.payment':
                #     operation.origin.with_context(no_check_op=True).cancel()
                #     # move_account_line = op_deposited.origin.move_line_ids
                #     # move_account_line.remove_move_reconcile()
                #     op_deposited.origin.with_context(no_check_op=True).cancel()
                #     self.with_context(no_check_op=True, journal=journal).deposited()
                # elif operation.origin and operation.origin._name == 'account.payment' and \
                #         op_deposited.origin._name == 'account.move':
                #     operation.origin.button_cancel()
                #     op_deposited.origin.button_cancel()
                #     self.with_context(no_check_op=True, journal=journal).deposited()
                else:
                    raise ValidationError(_(
                        'This operation is only allowed if the rejection of the check was from the bank.'))
            else:
                raise ValidationError(_(
                    'This operation is only allowed if the rejection of the check was from the bank.'))
        else:
            raise ValidationError(_(
                'This operation is only allowed if the rejection of the check was from the bank.'))

