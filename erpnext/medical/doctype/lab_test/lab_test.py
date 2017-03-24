# -*- coding: utf-8 -*-
# Copyright (c) 2015, ESS and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import time, json
from frappe.utils import cstr, getdate, get_time, math
from erpnext.medical.doctype.op_settings.op_settings import get_receivable_account,get_income_account

class LabTest(Document):
	def on_submit(self):
		if exists_inv_test_item(self):
			lab_test_result_status(self.name,"Submitted")
		frappe.db.set_value(self.doctype,self.name,"submitted_date", getdate())
		insert_lab_test_to_medical_record(self)
		frappe.db.set_value("Lab Test", self.name, "status", "Completed")

	def on_trash(self):
		frappe.throw("""Not permitted""")

	def on_cancel(self):
		if exists_inv_test_item(self):
			lab_test_result_status(self.name,"Cancelled")
		delete_lab_test_from_medical_record(self)
		frappe.db.set_value("Lab Test", self.name, "status", "Cancelled")
		self.reload()

	def on_update(self):
		if(self.sensitivity_test_items):
			sensitivity = sorted(self.sensitivity_test_items, key=lambda x: x.antibiotic_sensitivity)
			for i, item in enumerate(sensitivity):
				item.idx = i+1
			self.sensitivity_test_items = sensitivity

def lab_test_result_status(lab_test,status):
	frappe.db.sql("""update `tabInvoice Test Item` set workflow=%s where lab_test=%s""",(status, lab_test))

def exists_inv_test_item(lab_test):
	return frappe.db.exists({
		"doctype": "Invoice Test Item",
		"lab_test": lab_test.name})

@frappe.whitelist()
def update_status(status, name):
	frappe.db.set_value("Lab Test", name, "status", status)
	frappe.db.set_value("Lab Test", name, "approved_date", getdate())
	lab_test_result_status(name,status)

@frappe.whitelist()
def update_lab_test_print_sms_email_status(print_sms_email, name):
	frappe.db.set_value("Lab Test",name,print_sms_email,1)
	frappe.db.sql("""update `tabInvoice Test Item` set `%s`=1 where lab_test=%s"""\
	 	% (frappe.db.escape(print_sms_email), '%s'), (name))

def create_invoice_test_report(invoice, patient):
	invoice_test_report = frappe.new_doc("Invoice Test Report")
	invoice_test_report.invoice = invoice.name
	invoice_test_report.patient = patient.name
	invoice_test_report.physician = invoice.physician
	invoice_test_report.ref_physician = invoice.ref_physician
	invoice_test_report.patient_age = patient.age
	invoice_test_report.patient_sex = patient.sex
	invoice_test_report.email = patient.email
	invoice_test_report.mobile = patient.mobile
	invoice_test_report.report_preference = patient.report_preference
	return invoice_test_report

def create_lab_test_doc(invoice, consultation, patient, template):
	#create Test Result for template, copy vals from Invoice
	lab_test = frappe.new_doc("Lab Test")
	if(invoice):
		lab_test.invoice = invoice
	if(consultation):
		lab_test.physician = consultation.physician
		lab_test.ref_physician = consultation.ref_physician
	lab_test.patient = patient.name
	lab_test.patient_age = patient.age
	lab_test.patient_sex = patient.sex
	lab_test.email = patient.email
	lab_test.mobile = patient.mobile
	lab_test.lab_test_type = template.lab_test_type
	lab_test.test_name = template.test_name
	lab_test.template = template.name
	lab_test.test_group = template.test_group
	lab_test.result_date = getdate()
	lab_test.report_preference = patient.report_preference

	if patient.admitted:
		service_type = template.lab_test_type
		service_unit = get_service_unit(patient.admission, service_type)
		lab_test.service_unit = service_unit

	return lab_test

def create_normals(template, lab_test):
	lab_test.normal_toggle = "1"
	normal = lab_test.append("normal_test_items")
	normal.test_name = template.test_name
	normal.test_uom = template.test_uom
	normal.normal_range = template.test_normal_range
	normal.require_result_value = 1
	normal.template = template.name

def create_compounds(template, lab_test, is_group):
	lab_test.normal_toggle = "1"
	for normal_test_template in template.normal_test_templates:
		normal = lab_test.append("normal_test_items")
		if is_group:
			normal.test_event = normal_test_template.test_event
		else:
			normal.test_name = normal_test_template.test_event

		normal.test_uom = normal_test_template.test_uom
		normal.normal_range = normal_test_template.normal_range
		normal.require_result_value = 1
		normal.template = template.name

def create_specials(template, lab_test):
	lab_test.special_toggle = "1"
	if(template.sensitivity):
		lab_test.sensitivity_toggle = "1"
	for special_test_template in template.special_test_template:
		special = lab_test.append("special_test_items")
		special.test_particulars = special_test_template.particulars
		special.require_result_value = 1
		special.template = template.name

def create_sample_collection(template, patient, invoice):
	if(template.sample):
		sample_exist = frappe.db.exists({
			"doctype": "Sample Collection",
			"patient": patient.name,
			"docstatus": 0,
			"sample": template.sample})
		if sample_exist :
			#Update Sample Collection by adding quantity
			sample_collection = frappe.get_doc("Sample Collection",sample_exist[0][0])
			quantity = int(sample_collection.sample_quantity)+int(template.sample_quantity)
			if(template.sample_collection_details):
				sample_collection_details = sample_collection.sample_collection_details+"\n==============\n"+"Test :"+template.test_name+"\n"+"Collection Detials:\n\t"+template.sample_collection_details
				frappe.db.set_value("Sample Collection", sample_collection.name, 						"sample_collection_details",sample_collection_details)
			frappe.db.set_value("Sample Collection", sample_collection.name, 						"sample_quantity",quantity)

		else:
			#create Sample Collection for template, copy vals from Invoice
			sample_collection = frappe.new_doc("Sample Collection")
			if(invoice):
				sample_collection.invoice = invoice.name
			sample_collection.patient = patient.name
			sample_collection.patient_age = patient.age
			sample_collection.patient_sex = patient.sex
			sample_collection.sample = template.sample
			sample_collection.sample_uom = template.sample_uom
			sample_collection.sample_quantity = template.sample_quantity
			if(template.sample_collection_details):
				sample_collection.sample_collection_details = "Test :"+template.test_name+"\n"+"Collection Detials:\n\t"+template.sample_collection_details

			if patient.admitted:
				service_type = frappe.get_value("Lab Test Samples", template.sample, "service_type")
				service_unit = get_service_unit(patient.admission, service_type)
				sample_collection.service_unit = service_unit

			sample_collection.save()

		return sample_collection

def get_service_unit(admission, service_type):
	current_facility = frappe.get_value("Patient Admission", admission, "current_facility")
	zone = frappe.get_value("Facility", current_facility, "zone")
	service_unit = frappe.db.get_value("Service Unit List", {"parent": zone, "type" : service_type}, "service_unit")
	return service_unit

@frappe.whitelist()
def create_lab_test_from_invoice(invoice):
	doc = frappe.get_doc("Sales Invoice", invoice)
	patient = frappe.get_doc("Patient", doc.patient)
	invoice_test_report = create_invoice_test_report(doc, patient)
	collect_sample = 0
	if(frappe.db.get_value("Laboratory Settings", None, "require_sample_collection") == "1"):
		collect_sample = 1

	for item_line in doc.items:
		template_exist = frappe.db.exists({
			"doctype": "Lab Test Template",
			"item": item_line.item_code
			})
		if template_exist :
			template = frappe.get_doc("Lab Test Template",{"item":item_line.item_code})
		else:
			continue
		#skip the loop if there is no test_template for Item
		if not (template):
			continue
		lab_test_exist = frappe.db.exists({
			"doctype": "Lab Test",
			"invoice": doc.name,
			"test_name": template.test_name
			})
		if lab_test_exist:
			continue
		lab_test = create_lab_test(patient, template, None, None, doc.name, collect_sample)
		if(lab_test):
			lab_test_item = invoice_test_report.append("lab_test_items")
			lab_test_item.lab_test = lab_test.name
			lab_test_item.workflow = "Draft"
			lab_test_item.invoice = doc.name

	if hasattr(invoice_test_report, "lab_test_items"):
		invoice_test_report.save(ignore_permissions=True)

@frappe.whitelist()
def create_lab_test_from_consultation(consultation):
	doc = frappe.get_doc("Consultation", consultation)
	patient = frappe.get_doc("Patient", doc.patient)
	collect_sample = 0
	if(frappe.db.get_value("Laboratory Settings", None, "require_sample_collection") == "1"):
		collect_sample = 1

	for item_line in doc.test_prescription:
		lab_test_exist = frappe.db.exists({
			"doctype": "Lab Test",
			"prescription": item_line.name
			})
		if lab_test_exist:
			continue
		template = frappe.get_doc("Lab Test Template",item_line.test_code)
		#skip the loop if there is no test_template for Item
		if not (template):
			continue
		lab_test = create_lab_test(patient, template, item_line.name, doc, None, collect_sample)

@frappe.whitelist()
def create_lab_test_from_desk(patient, template, prescription, invoice=None):
	collect_sample = 0
	if(frappe.db.get_value("Laboratory Settings", None, "require_sample_collection") == "1"):
		collect_sample = 1
	lab_test_exist = frappe.db.exists({
		"doctype": "Lab Test",
		"prescription": prescription
		})
	if lab_test_exist:
		return
	template = frappe.get_doc("Lab Test Template", template)
	#skip the loop if there is no test_template for Item
	if not (template):
		return
	patient = frappe.get_doc("Patient", patient)
	consultation_id = frappe.get_value("Lab Prescription", prescription, "parent")
	consultation = frappe.get_doc("Consultation", consultation_id)
	lab_test = create_lab_test(patient, template, prescription, consultation, invoice, collect_sample)
	return lab_test.name

def create_lab_test(patient, template, prescription,  consultation, invoice, collect_sample):
	lab_test = create_lab_test_doc(invoice, consultation, patient, template)
	if(collect_sample == 1):
		sample_collection = create_sample_collection(template, patient, invoice)
		if(sample_collection):
			lab_test.sample = sample_collection.name
	if(template.test_template_type == 'Single'):
		create_normals(template, lab_test)
	elif(template.test_template_type == 'Compound'):
		create_compounds(template, lab_test, False)
	elif(template.test_template_type == 'Descriptive'):
		create_specials(template, lab_test)
	elif(template.test_template_type == 'Grouped'):
		#iterate for each template in the group and create one result for all.
		for test_group in template.test_groups:
			#template_in_group = None
			if(test_group.test_template):
				template_in_group = frappe.get_doc("Lab Test Template",
								test_group.test_template)
			if(template_in_group):
				if(template_in_group.test_template_type == 'Single'):
					create_normals(template_in_group, lab_test)
				elif(template_in_group.test_template_type == 'Compound'):
					normal_heading = lab_test.append("normal_test_items")
					normal_heading.test_name = template_in_group.test_name
					normal_heading.require_result_value = 0
					normal_heading.template = template_in_group.name
					create_compounds(template_in_group, lab_test, True)
				elif(template_in_group.test_template_type == 'Descriptive'):
					special_heading = lab_test.append("special_test_items")
					special_heading.test_name = template_in_group.test_name
					special_heading.require_result_value = 0
					special_heading.template = template_in_group.name
					create_specials(template_in_group, lab_test)
			else:
				normal = lab_test.append("normal_test_items")
				normal.test_name = test_group.group_event
				normal.test_uom = test_group.group_test_uom
				normal.normal_range = test_group.group_test_normal_range
				normal.require_result_value = 1
				normal.template = template.name
	if(template.test_template_type != 'No Result'):
		if(prescription):
			lab_test.prescription = prescription
			if(invoice):
				frappe.db.set_value("Lab Prescription", prescription, "invoice", invoice)
		lab_test.save(ignore_permissions=True) # insert the result
		return lab_test

@frappe.whitelist()
def get_employee_by_user_id(user_id):
	emp_id = frappe.db.get_value("Employee",{"user_id":user_id})
	employee = frappe.get_doc("Employee",emp_id)
	return employee

def insert_lab_test_to_medical_record(doc):
	subject = str(doc.test_name)
	if(doc.test_comment):
		subject += ", \n"+str(doc.test_comment)
	medical_record = frappe.new_doc("Patient Medical Record")
	medical_record.patient = doc.patient
	medical_record.subject = subject
	medical_record.status = "Open"
	medical_record.communication_date = doc.result_date
	medical_record.reference_doctype = "Lab Test"
	medical_record.reference_name = doc.name
	medical_record.reference_owner = doc.owner
	medical_record.save(ignore_permissions=True)

def delete_lab_test_from_medical_record(self):
	medical_record_id = frappe.db.sql("select name from `tabPatient Medical Record` where reference_name=%s",(self.name))

	if(medical_record_id[0][0]):
		frappe.delete_doc("Patient Medical Record", medical_record_id[0][0])

def create_item_line(test_code, sales_invoice):
	if test_code:
		item = frappe.get_doc("Item", test_code)
		if item:
			if not item.disabled:
				sales_invoice_line = sales_invoice.append("items")
				sales_invoice_line.item_code = item.item_code
				sales_invoice_line.item_name =  item.item_name
				sales_invoice_line.qty = 1.0
				sales_invoice_line.description = item.description

@frappe.whitelist()
def create_invoice(company, patient, lab_tests, prescriptions):
	test_ids = json.loads(lab_tests)
	line_ids = json.loads(prescriptions)
	if not test_ids and not line_ids:
		return
	sales_invoice = frappe.new_doc("Sales Invoice")
	sales_invoice.customer = frappe.get_value("Patient", patient, "customer")
	sales_invoice.due_date = getdate()
	sales_invoice.is_pos = '0'
	sales_invoice.debit_to = get_receivable_account(patient, company)
	for line in line_ids:
		test_code = frappe.get_value("Lab Prescription", line, "test_code")
		create_item_line(test_code, sales_invoice)
	for test in test_ids:
		test_code = frappe.get_value("Lab Test", test, "template")
		create_item_line(test_code, sales_invoice)
	sales_invoice.set_missing_values()
	sales_invoice.save()
	#set invoice in lab test
	for test in test_ids:
		frappe.db.set_value("Lab Test", test, "invoice", sales_invoice.name)
		prescription = frappe.db.get_value("Lab Test", test, "prescription")
		if prescription:
			frappe.db.set_value("Lab Prescription", prescription, "invoice", sales_invoice.name)
	#set invoice in prescription
	for line in line_ids:
		frappe.db.set_value("Lab Prescription", line, "invoice", sales_invoice.name)
	return sales_invoice.name