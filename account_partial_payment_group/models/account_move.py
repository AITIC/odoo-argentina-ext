# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_account_invoice_payment_group(self):
        self.ensure_one()
        self.open_move_line_ids.uptate_amount_payable_aux()
        return super(AccountMove, self).action_account_invoice_payment_group()

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"


    @api.depends('amount_residual')
    def _compute_amount_payable(self):
        """
        Para establecer un monto a pagar especifico para cada pago.
        """
        payment_group_id = self._context.get('payment_group_id')
        for rec in self:
            # amount_payable = rec.amount_residual
            # amount_payable_currency = rec.amount_residual_currency
            amount_payable = rec.amount_residual if not rec.currency_id else rec.amount_residual_currency
            amount_payable_company = rec.amount_residual
            if payment_group_id:
                payments = self.env['account.payment.group'].browse(
                    payment_group_id)
                partial_payment_line = payments.mapped('partial_payment_ids'
                                                       ).filtered(lambda x: x.line_move_id == rec)
                if partial_payment_line:
                    matched_amount = sum(partial_payment_line.mapped('amount'))
                    if not rec.currency_id:
                        amount_residual = sum(partial_payment_line.mapped('amount_residual'))
                        if amount_residual != rec.amount_residual:
                            matched_amount -= (amount_residual - rec.amount_residual)
                        if rec.amount_residual < 0.0 and matched_amount > rec.amount_residual:
                            amount_payable = matched_amount
                        elif rec.amount_residual > 0.0 and matched_amount < rec.amount_residual:
                            amount_payable = matched_amount
                    else:
                        amount_residual = sum(partial_payment_line.mapped('amount_residual_currency'))
                        if amount_residual != rec.amount_residual_currency:
                            matched_amount -= (amount_residual - rec.amount_residual_currency)
                        if rec.amount_residual_currency < 0.0 and matched_amount > rec.amount_residual_currency:
                            amount_payable = matched_amount
                        elif rec.amount_residual_currency > 0.0 and matched_amount < rec.amount_residual_currency:
                            amount_payable = matched_amount

                    #Importe en moneda de la compañia
                    matched_amount = sum(partial_payment_line.mapped('amount_company'))
                    amount_residual_company = sum(partial_payment_line.mapped('amount_residual'))
                    if amount_residual_company != rec.amount_residual:
                        matched_amount -= (amount_residual_company - rec.amount_residual)
                    if rec.amount_residual < 0.0 and matched_amount > rec.amount_residual:
                        amount_payable_company = matched_amount
                    elif rec.amount_residual > 0.0 and matched_amount < rec.amount_residual:
                        amount_payable_company = matched_amount
            rec.amount_payable = amount_payable
            rec.amount_payable_company = amount_payable_company

    def _set_amount_payable(self):
        '''Actualiza el monto a pagar cuando se cambia el valor
        '''
        return

    def _set_amount_payable_company(self):
        '''Actualiza el monto a pagar cuando se cambia el valor
        '''
        return


    amount_payable = fields.Monetary(
        string='Amount Payable',
        compute='_compute_amount_payable',
        inverse='_set_amount_payable',
        currency_field='currency_id',
        store=False
    )

    amount_payable_aux = fields.Monetary(
        string='Amount Payable Aux'
    )

    amount_payable_company = fields.Monetary(
        string='Amount Payable Company',
        compute='_compute_amount_payable',
        inverse='_set_amount_payable_company',
        currency_field='company_currency_id',
        store=False
    )

    payment_group_matched_amount_currency = fields.Monetary(
        compute='_compute_payment_group_matched_amount_currency',
        currency_field='currency_id',
    )

    def _compute_payment_group_matched_amount_currency(self):
        for rec in self:
            company_currency_id = rec.move_id.company_currency_id
            rec.payment_group_matched_amount_currency = company_currency_id._convert(rec.payment_group_matched_amount, rec.move_id.currency_id, rec.move_id.company_id,
                rec.date or fields.Date.context_today())

    @api.onchange('amount_payable')
    def onchange_amount_payable(self):
        for rec in self:
            rec.amount_payable_company = rec.currency_id._convert(rec.amount_payable,
                                                                  rec.company_currency_id,
                                                                  rec.company_id,rec.date or
                                                                  fields.Date.context_today())
            amount_residual = rec.amount_residual if not rec.currency_id else rec.amount_residual_currency
            rec.amount_payable_aux = rec.amount_payable
            if (
                    rec.amount_payable > 0 and rec.amount_payable > amount_residual
            ) or (
                    rec.amount_payable < 0 and rec.amount_payable < amount_residual
            ):
                raise UserError(
                    _('The amount to be paid must not be greater than the residual amount'))

    def uptate_amount_payable_aux(self):
        for rec in self:
            rec.amount_payable_aux = rec.amount_residual

    def _get_vals_amount_residual(self, line):
        amount_residual = amount_residual_currency = line.amount_residual
        currency = line.company_currency_id
        if self._context.get('payment_group_id', False):
            amount_residual = amount_residual_currency = line.amount_payable_company
        if line.currency_id:
            amount_residual_currency = line.amount_residual_currency
            if self._context.get('payment_group_id', False):
                amount_residual_currency = line.amount_payable
            currency = line.currency_id
        return amount_residual, amount_residual_currency, currency


    def _prepare_reconciliation_partials(self):
        ''' Prepare the partials on the current journal items to perform the reconciliation.
        /!\ The order of records in self is important because the journal items will be reconciled using this order.

        :return: A recordset of account.partial.reconcile.
        '''
        debit_lines = iter(self.filtered('debit'))
        credit_lines = iter(self.filtered('credit'))
        debit_line = None
        credit_line = None

        debit_amount_residual = 0.0
        debit_amount_residual_currency = 0.0
        credit_amount_residual = 0.0
        credit_amount_residual_currency = 0.0
        debit_line_currency = None
        credit_line_currency = None

        partials_vals_list = []

        while True:

            # Move to the next available debit line.
            if not debit_line:
                debit_line = next(debit_lines, None)
                if not debit_line:
                    break
                debit_amount_residual,debit_amount_residual_currency, debit_line_currency= self._get_vals_amount_residual(debit_line)
                # debit_amount_residual = debit_line.amount_residual
                #
                # if debit_line.currency_id:
                #     debit_amount_residual_currency = debit_line.amount_residual_currency
                #     debit_line_currency = debit_line.currency_id
                # else:
                #     debit_amount_residual_currency = debit_amount_residual
                #     debit_line_currency = debit_line.company_currency_id

            # Move to the next available credit line.
            if not credit_line:
                credit_line = next(credit_lines, None)
                if not credit_line:
                    break
                credit_amount_residual, credit_amount_residual_currency, credit_line_currency = self._get_vals_amount_residual(
                    credit_line)
                # credit_amount_residual = credit_line.amount_residual
                #
                # if credit_line.currency_id:
                #     credit_amount_residual_currency = credit_line.amount_residual_currency
                #     credit_line_currency = credit_line.currency_id
                # else:
                #     credit_amount_residual_currency = credit_amount_residual
                #     credit_line_currency = credit_line.company_currency_id

            min_amount_residual = min(debit_amount_residual, -credit_amount_residual)

            if debit_line_currency == credit_line_currency:
                # Reconcile on the same currency.

                # The debit line is now fully reconciled.
                if debit_line_currency.is_zero(debit_amount_residual_currency) or debit_amount_residual_currency < 0.0:
                    debit_line = None
                    continue

                # The credit line is now fully reconciled.
                if credit_line_currency.is_zero(credit_amount_residual_currency) or credit_amount_residual_currency > 0.0:
                    credit_line = None
                    continue

                min_amount_residual_currency = min(debit_amount_residual_currency, -credit_amount_residual_currency)
                min_debit_amount_residual_currency = min_amount_residual_currency
                min_credit_amount_residual_currency = min_amount_residual_currency

            else:
                # Reconcile on the company's currency.

                # The debit line is now fully reconciled.
                if debit_line.company_currency_id.is_zero(debit_amount_residual) or debit_amount_residual < 0.0:
                    debit_line = None
                    continue

                # The credit line is now fully reconciled.
                if credit_line.company_currency_id.is_zero(credit_amount_residual) or credit_amount_residual > 0.0:
                    credit_line = None
                    continue

                min_debit_amount_residual_currency = credit_line.company_currency_id._convert(
                    min_amount_residual,
                    debit_line.currency_id,
                    credit_line.company_id,
                    credit_line.date,
                )
                min_credit_amount_residual_currency = debit_line.company_currency_id._convert(
                    min_amount_residual,
                    credit_line.currency_id,
                    debit_line.company_id,
                    debit_line.date,
                )

            debit_amount_residual -= min_amount_residual
            debit_amount_residual_currency -= min_debit_amount_residual_currency
            credit_amount_residual += min_amount_residual
            credit_amount_residual_currency += min_credit_amount_residual_currency

            partials_vals_list.append({
                'amount': min_amount_residual,
                'debit_amount_currency': min_debit_amount_residual_currency,
                'credit_amount_currency': min_credit_amount_residual_currency,
                'debit_move_id': debit_line.id,
                'credit_move_id': credit_line.id,
            })

        return partials_vals_list

    # def auto_reconcile_lines(self):
    #     # Create list of debit and list of credit move ordered by date-currency
    #     debit_moves = self.filtered(lambda r: r.debit != 0 or r.amount_currency > 0)
    #     credit_moves = self.filtered(lambda r: r.credit != 0 or r.amount_currency < 0)
    #     debit_moves = debit_moves.sorted(key=lambda a: (a.date_maturity or a.date, a.currency_id))
    #     credit_moves = credit_moves.sorted(key=lambda a: (a.date_maturity or a.date, a.currency_id))
    #     # Compute on which field reconciliation should be based upon:
    #     if self[0].account_id.currency_id and self[0].account_id.currency_id != self[0].account_id.company_id.currency_id:
    #         field = 'amount_residual_currency'
    #         if self._context.get('payment_group_id', False):
    #             field = 'amount_payable'
    #     else:
    #         field = 'amount_residual'
    #         if self._context.get('payment_group_id', False):
    #             field = 'amount_payable_company'
    #     #if all lines share the same currency, use amount_residual_currency to avoid currency rounding error
    #     if self[0].currency_id and all([x.amount_currency and x.currency_id == self[0].currency_id for x in self]):
    #         field = 'amount_residual_currency'
    #         if self._context.get('payment_group_id', False):
    #             field = 'amount_payable'
    #     # Reconcile lines
    #     ret = self._reconcile_lines(debit_moves, credit_moves, field)
    #     return ret
    #
    # def _get_amount_reconcile(self, debit_move, credit_move, field):
    #     temp_amount_residual = min(debit_move.amount_residual, -credit_move.amount_residual)
    #     temp_amount_residual_currency = min(debit_move.amount_residual_currency, -credit_move.amount_residual_currency)
    #     if field not in ['amount_residual', 'amount_residual_currency']:
    #         if field == 'amount_payable':
    #             temp_amount_residual_currency = min(debit_move[field], -credit_move[field])
    #             # field_residual = field.replace('_currency', '')
    #             temp_amount_residual = min(debit_move['amount_payable_company'], -credit_move['amount_payable_company'])
    #         else:
    #             temp_amount_residual = min(debit_move[field], -credit_move[field])
    #     amount_reconcile = min(debit_move[field], -credit_move[field])
    #     return temp_amount_residual, temp_amount_residual_currency, amount_reconcile
    #
    #
    # def _reconcile_lines(self, debit_moves, credit_moves, field):
    #     """ This function loops on the 2 recordsets given as parameter as long as it
    #         can find a debit and a credit to reconcile together. It returns the recordset of the
    #         account move lines that were not reconciled during the process.
    #     """
    #     (debit_moves + credit_moves).read([field])
    #     to_create = []
    #     cash_basis = debit_moves and debit_moves[0].account_id.internal_type in ('receivable', 'payable') or False
    #     cash_basis_percentage_before_rec = {}
    #     dc_vals ={}
    #     while (debit_moves and credit_moves):
    #         debit_move = debit_moves[0]
    #         credit_move = credit_moves[0]
    #         company_currency = debit_move.company_id.currency_id
    #         # We need those temporary value otherwise the computation might be wrong below
    #         temp_amount_residual, temp_amount_residual_currency, amount_reconcile = self._get_amount_reconcile(debit_move, credit_move, field)
    #         dc_vals[(debit_move.id, credit_move.id)] = (debit_move, credit_move, temp_amount_residual_currency)
    #
    #         #Remove from recordset the one(s) that will be totally reconciled
    #         # For optimization purpose, the creation of the partial_reconcile are done at the end,
    #         # therefore during the process of reconciling several move lines, there are actually no recompute performed by the orm
    #         # and thus the amount_residual are not recomputed, hence we have to do it manually.
    #         if amount_reconcile == debit_move[field]:
    #             debit_moves -= debit_move
    #         else:
    #             debit_moves[0].amount_residual -= temp_amount_residual
    #             debit_moves[0].amount_residual_currency -= temp_amount_residual_currency
    #
    #         if amount_reconcile == -credit_move[field]:
    #             credit_moves -= credit_move
    #         else:
    #             # credit_moves[0][field] += temp_amount_residual
    #             credit_moves[0].amount_residual += temp_amount_residual
    #             credit_moves[0].amount_residual_currency += temp_amount_residual_currency
    #         #Check for the currency and amount_currency we can set
    #         currency = False
    #         amount_reconcile_currency = 0
    #         if field == 'amount_residual_currency':
    #             currency = credit_move.currency_id.id
    #             amount_reconcile_currency = temp_amount_residual_currency
    #             amount_reconcile = temp_amount_residual
    #         elif bool(debit_move.currency_id) != bool(credit_move.currency_id):
    #             # If only one of debit_move or credit_move has a secondary currency, also record the converted amount
    #             # in that secondary currency in the partial reconciliation. That allows the exchange difference entry
    #             # to be created, in case it is needed. It also allows to compute the amount residual in foreign currency.
    #             currency = debit_move.currency_id or credit_move.currency_id
    #             currency_date = debit_move.currency_id and credit_move.date or debit_move.date
    #             amount_reconcile_currency = company_currency._convert(amount_reconcile, currency, debit_move.company_id, currency_date)
    #             currency = currency.id
    #
    #         if cash_basis:
    #             tmp_set = debit_move | credit_move
    #             cash_basis_percentage_before_rec.update(tmp_set._get_matched_percentage())
    #
    #         to_create.append({
    #             'debit_move_id': debit_move.id,
    #             'credit_move_id': credit_move.id,
    #             'amount': amount_reconcile,
    #             'amount_currency': amount_reconcile_currency,
    #             'currency_id': currency,
    #         })
    #
    #     cash_basis_subjected = []
    #     part_rec = self.env['account.partial.reconcile']
    #     for partial_rec_dict in to_create:
    #         debit_move, credit_move, amount_residual_currency = dc_vals[partial_rec_dict['debit_move_id'], partial_rec_dict['credit_move_id']]
    #         # /!\ NOTE: Exchange rate differences shouldn't create cash basis entries
    #         # i. e: we don't really receive/give money in a customer/provider fashion
    #         # Since those are not subjected to cash basis computation we process them first
    #         if not amount_residual_currency and debit_move.currency_id and credit_move.currency_id:
    #             part_rec.create(partial_rec_dict)
    #         else:
    #             cash_basis_subjected.append(partial_rec_dict)
    #
    #     for after_rec_dict in cash_basis_subjected:
    #         new_rec = part_rec.create(after_rec_dict)
    #         # if the pair belongs to move being reverted, do not create CABA entry
    #         if cash_basis and not (
    #                 new_rec.debit_move_id.move_id == new_rec.credit_move_id.move_id.reversed_entry_id
    #                 or
    #                 new_rec.credit_move_id.move_id == new_rec.debit_move_id.move_id.reversed_entry_id
    #         ):
    #             new_rec.create_tax_cash_basis_entry(cash_basis_percentage_before_rec)
    #     return debit_moves+credit_moves
