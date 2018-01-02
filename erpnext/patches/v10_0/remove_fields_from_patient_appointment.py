import frappe

def execute():
    if frappe.db.exists("DocType", "Patient Appointment"):
        if 'duration' in frappe.db.get_table_columns("Patient Appointment"):
			frappe.db.sql("alter table `tabPatient Appointment` drop column duration")

        if 'time_per_appointment' in frappe.db.get_table_columns("Patient Appointment"):
            frappe.db.sql("alter table `tabPatient Appointment` drop coloumn time_per_appointment")
