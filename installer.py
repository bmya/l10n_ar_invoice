# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2004-2010 Moldeo Interactive
#    (<http://www.moldeointeractive.com.ar>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import fields, osv

_invoice_types = [ ('A', 'A'), ('B', 'B'), ('C','C'), ('E','E'), ('M','M'), ('X','X')]
_action_types = [
    ('FC', 'Factura', 'sale'),
    ('DC', 'Nota de Débito', 'sale'),
    ('CC', 'Nota de Crédito', 'sale_refund'),
    ('FP', 'Factura de Compras', 'purchase'),
    ('DP', 'Nota de Débito de Compra', 'purchase'),
    ('CP', 'Nota de Crédito de Compra', 'purchase_refund'),
]
_situation_invoices = {
    'monotributo': { 'sent': 'C', 'receive': 'X' },
    'responsableinscripto': { 'sent': 'ABM', 'receive': 'X' },
    'noresponsableinscripto': { 'sent': 'ABM', 'receive': 'X' },
}

class account_invoice_ar_installer(osv.osv_memory):
    _name = 'account.invoice.ar.installer'
    _inherit = 'res.config.installer'
    _columns = {
        'situation': fields.selection([
            ('monotributo','Monotributista'),
            ('responsableinscripto','Responsable Inscripto'),
            ('noresponsableinscripto','No Responsable Inscripto')],
            'Situación con respecto al IVA', required=True),
        'do_export': fields.boolean('Realiza o realizará operaciones de Exportación', required=True),
        'remove_old_journals': fields.boolean('Eliminar los diarios existentes', required=True, help='Si es su primera instalación indique que necesita borrar los diarios existentes. Si agrega un nuevo punto de ventas indique que no va a eliminar los journals.'),
        'point_of_sale': fields.integer('Número de Punto de Venta', help='Este es el número que aparecerá como prefijo del número de la factura. Si solo tiene un solo talonario ese número es 1. Si necesita agregar un nuevo punto de venta debe acceder a opciones Administración/Configuración/Wizards de Configuración/Wizards de Configuración y ejecutar nuevamente el wizard de "Configuración de Facturación".'),
        'ing_brutos': fields.char('Ingresos Brutos', size=32, help="ID o descripción de estado en Ingresos Brutos."),
        'startup_activities': fields.date('Inicio de Actividades'),
    }

    _defaults= {
        'situation': 'monotributo',
        'do_export': False,
        'remove_old_journals': False,
        'point_of_sale': 1,
    }

    def generate_invoice_journals(self, cr, uid, ids, situation, ing_brutos, startup_activities, export, remove_old_journals, point_of_sale, context=None):
        """
        Generate Sequences and Journals associated to Invoices Types
        """
        obj_sequence = self.pool.get('ir.sequence')
        obj_currency = self.pool.get('res.currency')
        obj_acc_account = self.pool.get('account.account')
        obj_acc_journal_view = self.pool.get('account.journal.view')
        obj_acc_chart_template = self.pool.get('account.chart.template')
        obj_acc_template = self.pool.get('account.account.template')
        obj_analytic_journal = self.pool.get('account.analytic.journal')
        obj_journal = self.pool.get('account.journal')
        obj_mod = self.pool.get('ir.model.data')
        obj_property = self.pool.get('ir.property')
        obj_user = self.pool.get('res.users')
        obj_company = self.pool.get('res.company')

        # Remove Sale Journal, Purchase Journal, Sale Refund Journal, Purchase Refund Journal.
        if remove_old_journals:
            jou_ids = obj_journal.search(cr, uid, [('type','in',['sale','purchase','sale_refund','purchase_refund'])])
            obj_journal.unlink(cr, uid, jou_ids)

        # Create Journals for Argentinian Invoices.
        company_id = obj_user.browse(cr, uid, uid).company_id

        obj_company.write(cr, uid, [company_id.id], {
                'situation': situation,
                'ing_brutos': ing_brutos,
                'startup_activities': startup_activities,
            })

        def get_property(p):
            property_id = obj_property.search(cr, uid, [('name','=',p),('company_id','=',company_id.id)])
            if property_id and len(property_id) == 1:
                obj = obj_property.browse(cr, uid, property_id[0]).value_reference
                return obj.id
            else:
                return False

        account_id = {
            'A': get_property('property_account_receivable'),
            'B': get_property('property_account_payable'),
            'sale': get_property('property_account_income_categ'),
            'sale_refund': get_property('property_account_income_categ'),
            'purchase': get_property('property_account_expense_categ'),
            'purchase_refund': get_property('property_account_expense_categ'),
        }

        invoices_filter = {
            'FC': _situation_invoices[situation]['sent'],
            'DC': _situation_invoices[situation]['sent'],
            'CC': _situation_invoices[situation]['sent'],
            'FP': _situation_invoices[situation]['receive'],
            'DP': _situation_invoices[situation]['receive'],
            'CP': _situation_invoices[situation]['receive'],
        }

        if export:
            invoices_filter['FC'] += 'E'
            invoices_filter['DC'] += 'E'
            invoices_filter['CC'] += 'E'

        view_id_invoice = obj_acc_journal_view.search(cr, uid, [('name', '=', 'Sale/Purchase Journal View')], context=context)[0]
        view_id_refund = obj_acc_journal_view.search(cr, uid, [('name', '=', 'Sale/Purchase Refund Journal View')], context=context)[0]
        view_id = {
            'sale': view_id_invoice, 
            'purchase': view_id_invoice, 
            'sale_refund': view_id_refund, 
            'purchase_refund': view_id_refund, 
        }

        for action_code, action_name, action_type in _action_types:
            for invoice_code, invoice_name in _invoice_types:
                if not invoice_code in invoices_filter[action_code]:
                    continue

                data = {'point_of_sale': point_of_sale,
                        'act_name': action_name,
                        'act_code': action_code,
                        'inv_name': invoice_name,
                        'inv_code': invoice_code,
                        'journal_type': action_type}
                # Create Sequences
                vals_seq = {
                    'name': '%(act_name)s %(inv_code)s %(point_of_sale)04i' % data,
                    'code': 'account.journal',
                    'prefix': '%(point_of_sale)04i-' % data,
                    'company_id': company_id.id,
                    'padding': 8,
                }
                seq_id = obj_sequence.create(cr, uid, vals_seq, context=context)

                # Create Journals
                analitical_ids = obj_analytic_journal.search(cr, uid, [('type', '=', data['journal_type'])], context=context)
                analitical_journal = analitical_ids and analitical_ids[0] or False
                vals_journal = {}
                vals_journal = {
                    'name': "%(act_name)s (%(point_of_sale)04i-%(inv_code)s)" % data,
                    'code': "%(act_code)s%(inv_code)s%(point_of_sale)1i" % data,
                    'sequence_id': seq_id,
                    'type': "%(journal_type)s" % data, #'cash',
                    'company_id': company_id.id,
                    'analytic_journal_id': analitical_journal,
                    'view_id': view_id[data['journal_type']],
                    'default_credit_account_id': account_id[data['journal_type']],
                    'default_debit_account_id': account_id[data['journal_type']],
                }

                obj_journal.create(cr, uid, vals_journal, context=context)

        pass

    def execute(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        r = super(account_invoice_ar_installer, self).execute(cr, uid, ids, context)
        record = self.browse(cr, uid, ids, context=context)[0]

        for res in self.read(cr, uid, ids, context=context):
            self.generate_invoice_journals(cr, uid, ids,
                                           record.situation,
                                           record.ing_brutos,
                                           record.startup_activities,
                                           record.do_export,
                                           record.remove_old_journals,
                                           record.point_of_sale,
                                           context=None)

account_invoice_ar_installer()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
