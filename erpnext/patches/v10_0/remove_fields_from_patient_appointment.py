import frappe

def execute():
    #   If exist Patient Appointment

    if frappe.db.exists("DocType", "Patient Appointment"):
        #   Remove coloumn duration (Link - Physician Schedule DocType)
		if 'duration' in frappe.db.get_table_columns("Patient Appointment"):
			frappe.db.sql("alter table `tabPatient Appointment` drop column duration")

        #   Remove coloumn time_per_appointment (Time)
        if 'time_per_appointment' in frappe.db.get_table_columns("Patient Appointment"):
            frappe.db.sql("alter table `tabPatient Appointment` drop coloumn time_per_appointment")
