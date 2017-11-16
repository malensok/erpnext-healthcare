# -*- coding: utf-8 -*-
# Copyright (c) 2017, ESS LLP and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate
from erpnext.healthcare.doctype.healthcare_settings.healthcare_settings import get_account, get_receivable_account,get_income_account
from erpnext.healthcare.doctype.lab_test.lab_test import create_sample_doc
from erpnext.stock.get_item_details import get_bin_details

class ClinicalProcedure(Document):
	def validate(self):
		if self.maintain_stock and not self.start_procedure:
			if not self.warehouse:
				frappe.throw(("Set warehouse for Procedure {0} ").format(self.name))
			self.set_actual_qty()

	def after_insert(self):
		if self.maintain_stock:
			doc = set_stock_items(self, self.procedure_template, "Clinical Procedure Template")
			doc.save()
		if self.appointment:
			self.validate_appointment()
			frappe.db.set_value("Patient Appointment", self.appointment, "status", "Closed")
		if self.has_stages:
			doc = set_stage_detail(self)
			doc.save()
		template = frappe.get_doc("Clinical Procedure Template", self.procedure_template)
		if template.sample:
			patient = frappe.get_doc("Patient", self.patient)
			sample_collection = create_sample_doc(template, patient, None)
			frappe.db.set_value("Clinical Procedure", self.name, "sample", sample_collection.name)
		self.reload()

	def complete(self):
		if self.maintain_stock:
			create_stock_entry(self)
		frappe.db.set_value("Clinical Procedure", self.name, "complete_procedure", 1)

	def start(self):
		allow_start = self.set_actual_qty()
		if allow_start:
			self.start_procedure = True
		else:
			self.start_procedure = False

		self.save()

	def set_actual_qty(self):
		allow_negative_stock = cint(frappe.db.get_value("Stock Settings", None, "allow_negative_stock"))

		allow_start = True
		for d in self.get('items'):
			bin_details = get_bin_details(d.item_code, self.warehouse)

			# get actual stock at source warehouse
			d.actual_qty = bin_details['actual_qty']

			# validate qty
			if not allow_negative_stock and d.actual_qty < d.qty:
				allow_start = False

		return allow_start

	def validate_appointment(self):
		if frappe.db.get_value("Patient Appointment", self.appointment, "status") != "Open":
			frappe.throw(_("Appointment {0} is not in open status").format(self.appointment))

	def make_material_transfer(self):
		stock_entry = frappe.new_doc("Stock Entry")

		stock_entry.purpose = "Material Transfer"
		stock_entry.to_warehouse = self.warehouse
		expense_account = get_account(None, "expense_account", "Healthcare Settings", self.company)
		for item in self.items:
			if item.qty > item.actual_qty:
				se_child = stock_entry.append('items')
				se_child.item_code = item.item_code
				se_child.item_name = item.item_name
				se_child.uom = item.uom
				se_child.stock_uom = item.stock_uom
				se_child.qty = flt(item.qty-item.actual_qty)
				se_child.t_warehouse = self.warehouse
				# in stock uom
				se_child.transfer_qty = flt(item.transfer_qty)
				se_child.conversion_factor = flt(item.conversion_factor)
				cost_center = frappe.db.get_value("Item", item.item_code, "buying_cost_center")
				se_child.cost_center = cost_center
				se_child.expense_account = expense_account
		return stock_entry.as_dict()

	def create_invoice(self):
		sales_invoice = frappe.new_doc("Sales Invoice")
		sales_invoice.customer = frappe.get_value("Patient", self.patient, "customer")
		sales_invoice.due_date = getdate()
		sales_invoice.company = self.company
		sales_invoice.is_pos = '0'
		sales_invoice.debit_to = get_receivable_account(self.company)

		procedure_template = frappe.get_doc("Clinical Procedure Template", self.procedure_template)
		item_line = sales_invoice.append("items")
		item_line.item_code = procedure_template.item_code
		item_line.item_name = procedure_template.name
		item_line.description = procedure_template.description
		item_line.qty = 1
		item_line.uom = "Nos"
		item_line.conversion_factor = 1
		item_line.income_account = get_income_account(None, self.company)
		item_line.rate = procedure_template.rate
		item_line.amount = item_line.rate
		sales_invoice.set_missing_values()
		sales_invoice.save(ignore_permissions=True)
		return {'invoice': sales_invoice.name}

	def get_item_details(self, args=None, for_update=False):
		item = frappe.db.sql("""select stock_uom, description, image, item_name,
			expense_account, buying_cost_center, item_group from `tabItem`
			where name = %s
				and disabled=0
				and (end_of_life is null or end_of_life='0000-00-00' or end_of_life > %s)""",
			(args.get('item_code'), nowdate()), as_dict = 1)
		if not item:
			frappe.throw(_("Item {0} is not active or end of life has been reached").format(args.get('item_code')))

		item = item[0]

		ret = {
			'uom'			      	: item.stock_uom,
			'stock_uom'			  	: item.stock_uom,
			'item_name' 		  	: item.item_name,
			'quantity'				: 0,
			'transfer_qty'			: 0,
			'conversion_factor'		: 1
		}
		# update uom
		if args.get("uom") and for_update:
			ret.update(get_uom_details(args.get('item_code'), args.get('uom'), args.get('quantity')))
		return ret


@frappe.whitelist()
def set_stock_items(doc, stock_detail_parent, parenttype):
	item_dict = get_item_dict("Clinical Procedure Item", stock_detail_parent, parenttype)

	for d in item_dict:
		se_child = doc.append('items')
		se_child.barcode = d["barcode"]
		se_child.item_code = d["item_code"]
		se_child.item_name = d["item_name"]
		se_child.uom = d["uom"]
		se_child.stock_uom = d["stock_uom"]
		se_child.qty = flt(d["qty"])
		# in stock uom
		se_child.transfer_qty = flt(d["transfer_qty"])
		se_child.conversion_factor = flt(d["conversion_factor"])

	return doc

def set_stage_detail(doc):
	stages = get_item_dict("Clinical Procedure Stage", doc.procedure_template, "Clinical Procedure Template")

	for d in stages:
		child = doc.append('stages')
		child.stage = d["stage"]

	return doc

def get_item_dict(table, parent, parenttype):
	query = """select * from `tab{table}` where parent = '{parent}' and parenttype = '{parenttype}' """

	return frappe.db.sql(query.format(table=table, parent=parent, parenttype=parenttype), as_dict=True)

def create_stock_entry(doc):
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry = set_stock_items(stock_entry, doc.name, "Clinical Procedure")
	stock_entry.purpose = "Material Issue"
	stock_entry.from_warehouse = doc.warehouse
	expense_account = get_account(None, "expense_account", "Healthcare Settings", doc.company)

	for item_line in stock_entry.items:
		cost_center = frappe.db.get_value("Item", item_line.item_code, "buying_cost_center")
		#item_line.s_warehouse = warehouse #deaful source warehouse set, stock entry to copy to lines
		item_line.cost_center = cost_center
		#if not expense_account:
		#	expense_account = frappe.db.get_value("Item", item_line.item_code, "expense_account")
		item_line.expense_account = expense_account

	stock_entry.insert(ignore_permissions = True)
	stock_entry.submit()

@frappe.whitelist()
def create_procedure(appointment):
	appointment = frappe.get_doc("Patient Appointment",appointment)
	procedure = frappe.new_doc("Clinical Procedure")
	procedure.appointment = appointment.name
	procedure.patient = appointment.patient
	procedure.patient_age = appointment.patient_age
	procedure.patient_sex = appointment.patient_sex
	procedure.procedure_template = appointment.procedure_template
	procedure.medical_department = appointment.department
	procedure.start_dt = appointment.appointment_date
	procedure.start_tm = appointment.appointment_time
	procedure.invoice = appointment.sales_invoice
	check_detail = frappe.db.get_values("Clinical Procedure Template", appointment.procedure_template, ["maintain_stock","has_stages"], as_dict=True)
	if check_detail[0]['maintain_stock']:
		procedure.maintain_stock = 1
		procedure.warehouse = frappe.db.get_value("Stock Settings", None, "default_warehouse")
	if check_detail[0]['has_stages']:
		procedure.has_stages = 1
	return procedure.as_dict()
