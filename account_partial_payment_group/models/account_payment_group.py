# © 2016 ADHOC SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError

class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"

    company_currency_id = fields.Many2one(string='Company Currency', readonly=True, 
        related='company_id.currency_id')

    unmatched_amount_company = fields.Monetary(
        compute='_compute_matched_amounts_company',
        currency_field='company_currency_id',
    )

    writeoff_amount_company = fields.Monetary(
        string='Payment difference amount company',
        compute='_compute_writeoff_amount_company')

    #Registrar monto a pagar parcialmente
    partial_payment_ids = fields.One2many(
        'account.partial.payment',
        'payment_group_id',
        string='Partial Payment Lines',
        ondelete='cascade',
        copy=False,
        readonly=True,
        states={
            'draft': [('readonly', False)],
            'confirmed': [('readonly', False)]},
        auto_join=True,
    )


    def _compute_matched_amounts_company(self):
        for rec in self:
            rec.unmatched_amount_company = rec.currency_id._convert(rec.unmatched_amount, rec.company_currency_id, rec.company_id,
                rec.payment_date or fields.Date.context_today())

    @api.depends('writeoff_amount')
    def _compute_writeoff_amount_company(self):
        for rec in self:
            rec.writeoff_amount_company = rec.currency_id._convert(rec.writeoff_amount, rec.company_currency_id, rec.company_id,
                rec.payment_date or fields.Date.context_today())

    @api.depends(
        'to_pay_move_line_ids.amount_residual',
        'to_pay_move_line_ids.amount_residual_currency',
        'to_pay_move_line_ids.currency_id',
        'to_pay_move_line_ids.move_id',
        'payment_date',
        'currency_id',
    )
    def _compute_selected_debt(self):
        for rec in self:
            selected_finacial_debt = 0.0
            selected_debt = 0.0
            selected_debt_untaxed = 0.0
            for line in rec.to_pay_move_line_ids._origin:
                selected_finacial_debt += line.financial_amount_residual
                # selected_debt += line.amount_residual
                selected_debt += rec._get_amount_residual(line)
                # factor for total_untaxed
                invoice = line.move_id
                factor = invoice and invoice._get_tax_factor() or 1.0
                # selected_debt_untaxed += line.amount_residual * factor
                selected_debt_untaxed += rec._get_amount_residual(line) * factor
            sign = rec.partner_type == 'supplier' and -1.0 or 1.0
            rec.selected_finacial_debt = selected_finacial_debt * sign
            rec.selected_debt = selected_debt * sign
            rec.selected_debt_untaxed = selected_debt_untaxed * sign

    def _get_amount_residual(self, line):
        self.ensure_one()
        for line_parcial in self.partial_payment_ids:
            if line_parcial.line_move_id == line:
                return line_parcial.amount_company
        else:
            return line.amount_residual

    @api.onchange('to_pay_move_line_ids')
    def _inverse_to_pay_move_line_ids(self):
        for rec in self:
            rec.update_partial_payment()

    def remove_all(self):
        self.partial_payment_ids = False
        super(AccountPaymentGroup, self).remove_all()

    def add_all(self):
        super(AccountPaymentGroup, self).add_all()
        self._inverse_to_pay_move_line_ids()

    # Tener en cuenta o no los pagos anticipados en el pago actual.
    def update_advance_payment(self):
        for rec in self:
            payment_ids = rec.to_pay_move_line_ids.filtered(lambda x: x.payment_id)
            if payment_ids:
                rec.to_pay_move_line_ids -= payment_ids
            else:
                domain = rec._get_to_pay_move_lines_domain()
                domain.append(('payment_id', '!=', False))
                rec.to_pay_move_line_ids += rec.env['account.move.line'].search(domain)

    # Actualizar lineas para guardar valores de pagos parciales.
    def update_partial_payment(self):
        self.ensure_one()
        partial_payment_lines_new = [(5, 0, 0)]
        for line in self.to_pay_move_line_ids._origin:
            new_line = self.to_pay_move_line_ids.filtered(
                lambda x: x._origin == line
            )
            amount = line.amount_residual if not line.currency_id else line.amount_residual_currency
            if new_line:
                amount_payable = new_line.amount_payable
                if amount < 0 and amount_payable > amount:
                    amount = amount_payable
                elif amount > 0 and amount_payable < amount:
                    amount = amount_payable
            amount_company = amount
            if line.currency_id:
                amount_company = line.currency_id._convert(amount, line.company_currency_id, line.company_id,
                                         line.date or fields.Date.context_today())
            vals_partial = {
                'line_move_id': line.id,
                'amount': amount,
                'amount_residual_currency': line.amount_residual_currency,
                'amount_company': amount_company,
                'amount_residual': line.amount_residual,
                'currency_id': line.currency_id.id if line.currency_id else line.company_currency_id.id,
            }
            partial_payment_lines_new.append((0, 0, vals_partial))
        self.partial_payment_ids = partial_payment_lines_new

    def update_post_partial_payment(self):
        self.ensure_one()
        for line in self.with_context(payment_group_id=self.id).to_pay_move_line_ids:
            partial_payment = self.partial_payment_ids.filtered(lambda x: x.line_move_id == line)
            if line.payment_id and line.payment_id.payment_group_id:
                vals = {
                    'payment_group_id': line.payment_id.payment_group_id.id
                }
                reconciles = self.env['account.partial.reconcile'].search([
                    ('credit_move_id', '=', line.id)])
                lines = reconciles.mapped('debit_move_id')

                reconciles += self.env['account.partial.reconcile'].search([
                    ('debit_move_id', '=', line.id)])
                lines |= reconciles.mapped('credit_move_id')

                matched_move_line_ids = lines.filtered(lambda x: x != line and self.with_context(
                    payment_group_id=self.id).to_pay_move_line_ids)
                for matched_line in matched_move_line_ids:
                    amount = sum(reconciles.filtered(lambda x: x.credit_move_id == matched_line or
                                                           x.debit_move_id == matched_line).mapped('amount'))
                    if partial_payment.payment_group_id == line.payment_id.payment_group_id:
                        partial_payment.copy({
                            'line_move_id': matched_line.id,
                            'amount': amount
                        })
                    else:
                        vals.update({
                            'line_move_id': matched_line.id,
                            'amount': amount
                        })
                        partial_payment.write(vals)

    def action_draft(self):
        res = super(AccountPaymentGroup, self).action_draft()
        for rec in self:
            rec.update_partial_payment()
        return res

    def post(self):
        create_from_website = self._context.get('create_from_website', False)
        create_from_statement = self._context.get('create_from_statement', False)
        create_from_expense = self._context.get('create_from_expense', False)
        for rec in self:
            # TODO if we want to allow writeoff then we can disable this
            # constrain and send writeoff_journal_id and writeoff_acc_id
            if not rec.payment_ids:
                raise ValidationError(_(
                    'You can not confirm a payment group without payment '
                    'lines!'))
            # si el pago se esta posteando desde statements y hay doble
            # validacion no verificamos que haya deuda seleccionada
            if (rec.payment_subtype == 'double_validation' and
                    rec.payment_difference and rec.payment_difference_handling != 'reconcile' and
                    (not create_from_statement and not create_from_expense)):
                raise ValidationError(_(
                    'To Pay Amount and Payment Amount must be equal!'))

            writeoff_acc_id = False
            writeoff_journal_id = False

            #Conciliar en una cuenta contable la diferencia entre la deuda y lo pagado.
            if rec.payment_difference_handling == 'reconcile':
                rec.reconcile_diff_payment()

            # al crear desde website odoo crea primero el pago y lo postea
            # y no debemos re-postearlo
            if not create_from_website and not create_from_expense:
                rec.payment_ids.sorted(key=lambda l: l.signed_amount).filtered(lambda x: x.state == 'draft').post()

            counterpart_aml = rec.payment_ids.mapped('move_line_ids').filtered(
                lambda r: not r.reconciled and r.account_id.internal_type in (
                    'payable', 'receivable'))

            # porque la cuenta podria ser no recivible y ni conciliable
            # (por ejemplo en sipreco)
            to_pay_move_line_ids = rec.to_pay_move_line_ids.filtered(lambda x: not x.reconciled)
            if counterpart_aml and to_pay_move_line_ids:
                # se modifico para que primero concile lo anterior al pago
                ((to_pay_move_line_ids) + counterpart_aml).with_context(
                    payment_group_id=rec.id, field='amount_payable').reconcile(
                    writeoff_acc_id, writeoff_journal_id)
            self.update_post_partial_payment()
            rec.state = 'posted'
        return True


class AccountPartialPayment(models.Model):
    _name = "account.partial.payment"
    _description = "Partial Payment"

    line_move_id = fields.Many2one(
        'account.move.line',
        ondelete='cascade',
        index=True,
    )
    payment_group_id = fields.Many2one(
        'account.payment.group',
        'Payment Group',
        ondelete='cascade',
        index=True,
    )
    amount = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
        help="Amount concerned by this matching"
    )
    amount_residual_currency = fields.Monetary(
        string="Amount residual currency",
        currency_field='company_currency_id',
        help="Amount concerned by this matching"
    )
    amount_company = fields.Monetary(
        string="Amount in Company",
        currency_field='company_currency_id',
    )
    amount_residual = fields.Monetary(
        string="Amount residual",
        currency_field='company_currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency'
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        string="Company Currency",
        related='company_id.currency_id',
        readonly=True,
        help='Utility field to express amount currency'
    )
    company_id = fields.Many2one(
        'res.company',
        related='payment_group_id.company_id',
        store=True,
        string='Company',
        readonly=False
    )

    @api.depends('amount', 'amount_residual', 'amount_residual_currency')
    def _compute_amount_company(self):
        for rec in self:
            amount_company = rec.currency_id._convert(rec.amount, rec.company_currency_id, rec.company_id,
                                                           rec.line_move_id.date or fields.Date.context_today())

            rec.amount_company = amount_company
